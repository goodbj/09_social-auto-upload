"""09-YouPick 互动闭环本地镜像库（SQLite 单文件，2026-11-13）。

定位：**平台是真源，本地库是镜像 + 决策留痕**。只在本机读写，不部署服务、不改上游项目原有的
`db/createTable.py` / `database.db`。单账号、单机、每轮百来条留言，SQLite 足够，不上 MySQL/Postgres。

四张表：
  rounds        每一轮巡检（开始/结束、读到多少条、新增/变更、动作数、状态）
  comments      每轮留言全量快照（顶层 + L2 摊平，带 content_hash 判内容变化）
  actions       对外动作账（like / reply；跨轮去重、失败留痕、回读核验结果）
  candidates    候选话题池（第 4 步「搜集有价值留言」落库，供下期内容分析，带 source_tag）

设计要点：
- `comments` 按 (round_id, comment_id) 唯一：每轮存一份全量快照，不靠「差上次」猜状态，
  归档时可直接重建「当时评论区长什么样」。
- `actions` 用部分唯一索引做**跨轮幂等**：同一 comment_id + action_kind 成功过就不再做第二次
  （点赞重复 = UNLIKE 取消赞，这个坑必须靠库挡住）；失败的允许重试但本脚本不自动重试。
- `source_tag` 三态：亲友自测 / 引子钩子 / 自然流量。老泡儿 2026-11-13 点破的坑：
  别把「玻璃栈道 / 海鸥 / 灯塔」这堆自己埋的钩子当真网友共识去拍下一集。
- 昵称用已知自测小号名单 + 主号 username 自动标，标不准的一律 `待核`，不冒充自然流量。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "youpick_workflow" / "data" / "youpick_interaction.sqlite3"

# 已知亲友 / 自测样本（老泡儿 2026-11-13 当面说明；后续有新号往这儿补）
SELF_NICKNAMES = {"丸小子998"}                 # 主号自己
RELATIVE_NICKNAMES = {
    "对方正在输入中...",   # 老泡儿小号（已确认自测）
    # 老泡儿 2026-11-13：「这些都是亲友」——本轮这几位按亲友标，别当自然流量共识
    "磊", "红太狼~[emoji]", "梦中人9070", "景荣",
}
# 早期引子期由咱自己埋的话题钩子，命中即标「引子钩子」，别当自然流量共识
HOOK_WORDS = ("玻璃栈道", "海鸥", "灯塔", "下集让它", "咱下回")

DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- 账号真源（多平台多账号的锚点）：平台 + 账号昵称唯一；每个账号绑定其 export_id
CREATE TABLE IF NOT EXISTS accounts (
    account_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL DEFAULT 'weixin',  -- weixin / douyin / xiaohongshu / kuaishou ...
    account         TEXT NOT NULL DEFAULT '丸小子998',
    export_id       TEXT NOT NULL DEFAULT '',         -- 该账号的视频 objectId（视频号用）
    display_name    TEXT NOT NULL DEFAULT '',
    persona         TEXT NOT NULL DEFAULT '北京胡同串子',  -- 该账号的人设，按号分防关联
    daily_soft_cap  INTEGER NOT NULL DEFAULT 40,      -- 单日软上限（观察期保守值，非 200 硬上限）
    status          TEXT NOT NULL DEFAULT 'active',
    note            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    UNIQUE(platform, account)
);
CREATE INDEX IF NOT EXISTS idx_accounts_pf ON accounts(platform);

CREATE TABLE IF NOT EXISTS rounds (
    round_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES accounts(account_id),
    platform        TEXT NOT NULL DEFAULT 'weixin',
    account         TEXT NOT NULL DEFAULT '丸小子998',
    export_id       TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    comments_seen   INTEGER NOT NULL DEFAULT 0,
    new_count       INTEGER NOT NULL DEFAULT 0,
    changed_count   INTEGER NOT NULL DEFAULT 0,
    actions_done    INTEGER NOT NULL DEFAULT 0,
    candidates_out  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running',   -- running / done / aborted
    note            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_rounds_acct ON rounds(account_id);

CREATE TABLE IF NOT EXISTS comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        INTEGER NOT NULL REFERENCES rounds(round_id),
    account_id      INTEGER NOT NULL REFERENCES accounts(account_id),
    platform        TEXT NOT NULL DEFAULT 'weixin',
    account         TEXT NOT NULL DEFAULT '丸小子998',
    comment_id      TEXT NOT NULL,
    root_id         TEXT NOT NULL,                    -- 顶层自身 id 或所属顶层 id
    level           INTEGER NOT NULL,                -- 1 顶层 / 2 楼中楼
    reply_to_id     TEXT NOT NULL DEFAULT '',
    nickname        TEXT NOT NULL DEFAULT '',
    username        TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',
    content_hash    TEXT NOT NULL,
    like_count      INTEGER NOT NULL DEFAULT 0,
    like_flag       INTEGER NOT NULL DEFAULT 0,       -- 1 = 本号已点过赞
    create_time     TEXT NOT NULL DEFAULT '',
    display_flag    INTEGER NOT NULL DEFAULT 0,
    source_tag      TEXT NOT NULL DEFAULT '待核',      -- 亲友自测 / 引子钩子 / 自然流量 / 自家回复 / 待核
    raw_json        TEXT NOT NULL DEFAULT '{}',
    UNIQUE(round_id, comment_id)
);
CREATE INDEX IF NOT EXISTS idx_comments_cid ON comments(comment_id);
CREATE INDEX IF NOT EXISTS idx_comments_root ON comments(root_id);
CREATE INDEX IF NOT EXISTS idx_comments_acct ON comments(account_id);

CREATE TABLE IF NOT EXISTS actions (
    action_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        INTEGER NOT NULL REFERENCES rounds(round_id),
    account_id      INTEGER NOT NULL REFERENCES accounts(account_id),
    platform        TEXT NOT NULL DEFAULT 'weixin',
    account         TEXT NOT NULL DEFAULT '丸小子998',
    comment_id      TEXT NOT NULL,
    action_kind     TEXT NOT NULL,                   -- like / reply
    target_nickname TEXT NOT NULL DEFAULT '',
    target_text     TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',        -- 回复文本（点赞为空）
    status          TEXT NOT NULL,                   -- success / failed / skipped
    err_code        INTEGER,
    verify          TEXT NOT NULL DEFAULT '',        -- 回读核验结论
    response_json   TEXT NOT NULL DEFAULT '{}',
    at              TEXT NOT NULL
);
-- 跨轮幂等：同一账号、同一条留言、同一种动作，成功过就不许再成功一次
-- （不同账号的同一 comment_id 互不干扰——多账号矩阵的关键）
CREATE UNIQUE INDEX IF NOT EXISTS uq_action_success
    ON actions(account_id, comment_id, action_kind) WHERE status = 'success';
CREATE INDEX IF NOT EXISTS idx_actions_acct ON actions(account_id);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        INTEGER NOT NULL REFERENCES rounds(round_id),
    account_id      INTEGER NOT NULL REFERENCES accounts(account_id),
    platform        TEXT NOT NULL DEFAULT 'weixin',
    account         TEXT NOT NULL DEFAULT '丸小子998',
    comment_id      TEXT NOT NULL,
    nickname        TEXT NOT NULL DEFAULT '',
    text            TEXT NOT NULL,
    like_count      INTEGER NOT NULL DEFAULT 0,
    source_tag      TEXT NOT NULL DEFAULT '待核',
    signals         TEXT NOT NULL DEFAULT '',        -- 潜力信号（不按赞排序）
    decision        TEXT NOT NULL DEFAULT '待拍板',  -- 待拍板 / 采纳 / 搁置
    note            TEXT NOT NULL DEFAULT '',
    at              TEXT NOT NULL,
    UNIQUE(round_id, comment_id)
);
"""

# 默认账号（向后兼容老脚本 / 老数据）：视频号 · 丸小子998
DEFAULT_PLATFORM = "weixin"
DEFAULT_ACCOUNT = "丸小子998"
DEFAULT_EXPORT_ID = "export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_account(platform: str = DEFAULT_PLATFORM, account: str = DEFAULT_ACCOUNT,
                   export_id: str = DEFAULT_EXPORT_ID, note: str = "") -> int:
    """账号真源：没有就建（绑定 platform+account 唯一），返回 account_id。"""
    conn = connect()
    try:
        cur = conn.execute(
            "SELECT account_id FROM accounts WHERE platform=? AND account=?", (platform, account))
        row = cur.fetchone()
        if row:
            aid = int(row["account_id"])
            # 同步最新 export_id（同一账号换视频时用到）
            conn.execute("UPDATE accounts SET export_id=? WHERE account_id=?", (export_id, aid))
            conn.commit()
            return aid
        cur = conn.execute(
            "INSERT INTO accounts(platform,account,export_id,created_at,note) VALUES(?,?,?,?,?)",
            (platform, account, export_id, now(), note))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def account_id(platform: str = DEFAULT_PLATFORM, account: str = DEFAULT_ACCOUNT) -> int:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT account_id FROM accounts WHERE platform=? AND account=?", (platform, account)
        ).fetchone()
        return int(row["account_id"]) if row else 0
    finally:
        conn.close()


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(DDL)
        conn.commit()
    finally:
        conn.close()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def flatten(lst: dict) -> list[dict]:
    """把 comment_list 响应的顶层 + levelTwoComment 摊平，统一成库表字段结构。"""
    out = []
    for top in (lst.get("data") or {}).get("comment") or []:
        tid = str(top.get("commentId") or "")
        out.append(_row(top, tid, 1))
        for l2 in top.get("levelTwoComment") or []:
            out.append(_row(l2, tid, 2))
    return out


def flatten(lst: dict, platform: str = DEFAULT_PLATFORM, account: str = DEFAULT_ACCOUNT) -> list[dict]:
    """把 comment_list 响应的顶层 + levelTwoComment 摊平，统一成库表字段结构。"""
    out = []
    for top in (lst.get("data") or {}).get("comment") or []:
        tid = str(top.get("commentId") or "")
        out.append(_row(top, tid, 1, platform, account))
        for l2 in top.get("levelTwoComment") or []:
            out.append(_row(l2, tid, 2, platform, account))
    return out


def _row(c: dict, root_id: str, level: int, platform: str = DEFAULT_PLATFORM,
         account: str = DEFAULT_ACCOUNT) -> dict:
    text = str(c.get("commentContent") or "")
    nick = str(c.get("commentNickname") or "")
    uname = str(c.get("username") or "")
    if nick in SELF_NICKNAMES or (uname and nick == "丸小子998"):
        tag = "自家回复"
    elif nick in RELATIVE_NICKNAMES:
        tag = "亲友自测"
    elif any(w in text for w in HOOK_WORDS):
        tag = "引子钩子"
    elif uname == "" and nick:
        tag = "待核"          # 平台没给 username 的，不擅自认定自然流量
    else:
        tag = "自然流量"
    return {
        "platform": platform,
        "account": account,
        "comment_id": str(c.get("commentId") or ""),
        "root_id": root_id,
        "level": level,
        "reply_to_id": str(c.get("replyCommentId") or ""),
        "nickname": nick,
        "username": uname,
        "content": text,
        "content_hash": content_hash(text),
        "like_count": int(c.get("commentLikeCount") or 0),
        "like_flag": int(c.get("likeFlag") or 0),
        "create_time": str(c.get("commentCreatetime") or ""),
        "display_flag": int(c.get("displayFlag") or 0),
        "source_tag": tag,
        "raw_json": json.dumps(c, ensure_ascii=False),
    }


def start_round(export_id: str, note: str = "", platform: str = DEFAULT_PLATFORM,
                account: str = DEFAULT_ACCOUNT) -> int:
    aid = ensure_account(platform, account, export_id, note)
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO rounds(account_id,platform,account,export_id,started_at,note,status) "
            "VALUES(?,?,?,?,?,?, 'running')", (aid, platform, account, export_id, now(), note))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def previous_snapshot(export_id: str, platform: str = DEFAULT_PLATFORM,
                      account: str = DEFAULT_ACCOUNT) -> dict[str, dict]:
    """取最近一轮 done 的留言快照（同一账号），按 comment_id 索引，用来判新增/变更。"""
    aid = account_id(platform, account)
    conn = connect()
    try:
        r = conn.execute(
            "SELECT MAX(round_id) AS rid FROM rounds WHERE account_id=? AND status='done'", (aid,)
        ).fetchone()
        if not r or not r["rid"]:
            return {}
        rows = conn.execute("SELECT * FROM comments WHERE round_id=?", (r["rid"],)).fetchall()
        return {row["comment_id"]: dict(row) for row in rows}
    finally:
        conn.close()


def save_snapshot(round_id: int, rows: list[dict]) -> tuple[int, int]:
    prev = previous_snapshot_by_round(round_id)
    new_n = changed_n = 0
    conn = connect()
    try:
        rnd = conn.execute("SELECT account_id,platform,account FROM rounds WHERE round_id=?",
                           (round_id,)).fetchone()
        aid, pf, acct = rnd["account_id"], rnd["platform"], rnd["account"]
        for r in rows:
            conn.execute("""
                INSERT OR IGNORE INTO comments
                (round_id,account_id,platform,account,comment_id,root_id,level,reply_to_id,
                 nickname,username,content,content_hash,like_count,like_flag,create_time,
                 display_flag,source_tag,raw_json)
                VALUES(:round_id,:account_id,:platform,:account,:comment_id,:root_id,:level,
                       :reply_to_id,:nickname,:username,:content,:content_hash,:like_count,
                       :like_flag,:create_time,:display_flag,:source_tag,:raw_json)
            """, {**r, "round_id": round_id, "account_id": aid, "platform": pf, "account": acct})
            old = prev.get(r["comment_id"])
            if old is None:
                new_n += 1
            elif old["content_hash"] != r["content_hash"] or old["like_count"] != r["like_count"]:
                changed_n += 1
        conn.commit()
    finally:
        conn.close()
    return new_n, changed_n


def previous_snapshot_by_round(round_id: int) -> dict[str, dict]:
    conn = connect()
    try:
        cur = conn.execute("SELECT account_id FROM rounds WHERE round_id=?", (round_id,))
        row = cur.fetchone()
        if not row:
            return {}
        aid = row["account_id"]
        r = conn.execute(
            "SELECT MAX(round_id) AS rid FROM rounds WHERE account_id=? AND status='done' "
            "AND round_id < ?", (aid, round_id)).fetchone()
        if not r or not r["rid"]:
            return {}
        rows = conn.execute("SELECT * FROM comments WHERE round_id=?", (r["rid"],)).fetchall()
        return {row["comment_id"]: dict(row) for row in rows}
    finally:
        conn.close()


def action_succeeded(comment_id: str, kind: str, platform: str = DEFAULT_PLATFORM,
                    account: str = DEFAULT_ACCOUNT) -> bool:
    aid = account_id(platform, account)
    conn = connect()
    try:
        r = conn.execute(
            "SELECT 1 FROM actions WHERE account_id=? AND comment_id=? AND action_kind=? "
            "AND status='success' LIMIT 1", (aid, comment_id, kind)).fetchone()
        return r is not None
    finally:
        conn.close()


def log_action(round_id: int, comment_id: str, kind: str, *,
               target_nickname: str = "", target_text: str = "", content: str = "",
               status: str = "success", err_code: int | None = None, verify: str = "",
               response: dict | None = None,
               platform: str = DEFAULT_PLATFORM, account: str = DEFAULT_ACCOUNT) -> None:
    aid = account_id(platform, account)
    conn = connect()
    try:
        conn.execute("""
            INSERT INTO actions
            (round_id,account_id,platform,account,comment_id,action_kind,target_nickname,
             target_text,content,status,err_code,verify,response_json,at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (round_id, aid, platform, account, comment_id, kind, target_nickname, target_text,
              content, status, err_code, verify,
              json.dumps(response or {}, ensure_ascii=False), now()))
        conn.commit()
    finally:
        conn.close()


def save_candidate(round_id: int, c: dict,
                  platform: str = DEFAULT_PLATFORM, account: str = DEFAULT_ACCOUNT) -> None:
    aid = account_id(platform, account)
    conn = connect()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO candidates
            (round_id,account_id,platform,account,comment_id,nickname,text,like_count,
             source_tag,signals,decision,note,at)
            VALUES(?,?,?,?,?,?,?,?,?,?,'待拍板',?,?)
        """, (round_id, aid, platform, account, c["comment_id"], c["nickname"], c["text"],
              c["like_count"], c["source_tag"], c["signals"], c.get("note", ""), now()))
        conn.commit()
    finally:
        conn.close()


def finish_round(round_id: int, *, actions_done: int = 0, candidates_out: int = 0,
                 comments_seen: int = 0, new_count: int = 0, changed_count: int = 0,
                 status: str = "done") -> None:
    conn = connect()
    try:
        conn.execute("""
            UPDATE rounds SET finished_at=?, comments_seen=?, new_count=?, changed_count=?,
                actions_done=?, candidates_out=?, status=? WHERE round_id=?
        """, (now(), comments_seen, new_count, changed_count, actions_done,
              candidates_out, status, round_id))
        conn.commit()
    finally:
        conn.close()


def summary(round_id: int) -> dict:
    conn = connect()
    try:
        rnd = dict(conn.execute("SELECT * FROM rounds WHERE round_id=?", (round_id,)).fetchone())
        rnd["actions"] = [dict(x) for x in conn.execute(
            "SELECT action_kind,status,count(*) AS n FROM actions WHERE round_id=? "
            "GROUP BY action_kind,status", (round_id,)).fetchall()]
        rnd["candidates"] = [dict(x) for x in conn.execute(
            "SELECT comment_id,nickname,text,source_tag,signals,decision FROM candidates "
            "WHERE round_id=? ORDER BY candidate_id", (round_id,)).fetchall()]
        rnd["source_breakdown"] = [dict(x) for x in conn.execute(
            "SELECT source_tag,count(*) AS n FROM comments WHERE round_id=? GROUP BY source_tag",
            (round_id,)).fetchall()]
        rnd["accounts"] = [dict(x) for x in conn.execute(
            "SELECT platform,account,export_id,persona,daily_soft_cap FROM accounts").fetchall()]
        return rnd
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"✅ 闭环库就绪: {DB_PATH}")

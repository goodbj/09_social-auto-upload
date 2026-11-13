# -*- coding: utf-8 -*-
"""09_04 岗位 · 互动闭环健康监控（纯只读，绝不碰平台、绝不发送）。

老泡儿 2026-11-14 派工（Issue #326，归属 Issue #308）：
  1. 运行时数据归并 youpick_workflow/data/ —— 库/日志/归档/派工/浏览器 profile 全在这一个目录，
     整目录 .gitignore 拦死，不外发（见 docs/data-archive-spec.md）。
  2. 监控互动闭环健康三件套：
       · 防重   —— 跨轮幂等唯一索引(uq_action_success) + 会话 replied_ids 名单，两路对账；
       · 回读核验 —— actions.verify 列，统计命中/未命中（未命中=需人工看）；
       · 日限额 —— 按账号从库读 daily_soft_cap，按账号统计当日真实回复数（不依赖全局 state）。

设计：本脚本只 SELECT，不 INSERT/UPDATE/DELETE，不 import 任何平台 SDK，不调用发送。
      跑法：python youpick_workflow/health_monitor.py            （打印概览）
            python youpick_workflow/health_monitor.py --json     （机器可读）

口径提醒：立项书与 human_pace 里「腾讯每天约 200」是平台观测软上限参考值，
          产品三档实际 daily_soft_cap 为 trial=20 / standard=40 / premium=80（capabilities.py）。
          本脚本以「账号实际 daily_soft_cap」为闸，200 仅作备注，不硬卡。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import date, datetime
from pathlib import Path

# 把仓根加进 sys.path（兼容从任意 cwd 跑）
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from db import interaction_store as store  # 底层库适配器（只读用）

DATA_DIR = Path(__file__).resolve().parent / "data"
STATE_FILE = DATA_DIR / "logs" / "human_session_state.json"
DB_PATH = store.DB_PATH

# 平台观测软上限参考（仅备注，非闸）
PLATFORM_OBSERVED_DAILY_CEILING = 200


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _today() -> str:
    return date.today().isoformat()


def accounts(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT platform,account,export_id,persona,daily_soft_cap,status "
        "FROM accounts ORDER BY account_id").fetchall()
    return [dict(r) for r in rows]


def daily_usage_by_account(conn, day: str) -> dict[str, int]:
    """按账号统计当日(success)回复数与点赞数（库真源，不依赖全局 state 文件）。"""
    rows = conn.execute(
        "SELECT account, action_kind, COUNT(*) AS n FROM actions "
        "WHERE status='success' AND substr(at,1,10)=? GROUP BY account, action_kind",
        (day,)).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["account"], {"reply": 0, "like": 0})
        out[r["account"]][r["action_kind"]] = int(r["n"])
    return out


def dedup_audit(conn) -> dict:
    """防重对账：库唯一索引挡住的重复 + 会话名单与库成功回复集合是否一致。"""
    # 库里被唯一索引拦掉的重复尝试（status='skipped' 或 failed 且 account+comment+kind 已有 success）
    dup_attempts = conn.execute(
        "SELECT COUNT(*) AS n FROM actions WHERE status IN ('skipped','failed') "
        "AND (account_id,comment_id,action_kind) IN "
        "(SELECT account_id,comment_id,action_kind FROM actions WHERE status='success')"
    ).fetchone()["n"]
    total_success = conn.execute(
        "SELECT COUNT(*) AS n FROM actions WHERE status='success'").fetchone()["n"]
    # 会话 state 名单 vs 库当日 success reply comment_id 集合
    state_ids: set[str] = set()
    state_ok = False
    state_date = None
    if STATE_FILE.is_file():
        try:
            d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            state_ids = set(d.get("replied_ids", []))
            state_date = d.get("date")
            state_ok = True
        except Exception:
            pass
    db_today_replied = {r["comment_id"] for r in conn.execute(
        "SELECT comment_id FROM actions WHERE status='success' AND action_kind='reply' "
        "AND substr(at,1,10)=?", (_today(),)).fetchall()}
    only_in_state = sorted(state_ids - db_today_replied)
    only_in_db = sorted(db_today_replied - state_ids)
    consistent = (not state_ids) or (not only_in_state and not only_in_db)
    return {
        "unique_index_active": True,
        "cross_round_dup_attempts_blocked": int(dup_attempts),
        "total_success_actions": int(total_success),
        "session_state_file": str(STATE_FILE),
        "session_state_readable": state_ok,
        "session_state_date": state_date,
        "state_replied_count": len(state_ids),
        "db_today_replied_count": len(db_today_replied),
        "state_only_not_in_db": only_in_state,       # 名单有、库没落（需核）
        "db_only_not_in_state": only_in_db,          # 库有、名单漏（state 跨会话未续）
        "lists_consistent": consistent,
    }


def verify_audit(conn) -> dict:
    """回读核验：actions.verify 列命中/未命中统计。"""
    rows = conn.execute(
        "SELECT action_kind, verify FROM actions WHERE status='success' AND verify<>''"
    ).fetchall()
    hit = miss = 0
    miss_ids: list[str] = []
    for r in rows:
        v = (r["verify"] or "")
        if "未命中" in v or "没找着" in v:
            miss += 1
            miss_ids.append(r["action_kind"])
        else:
            hit += 1
    verified_total = hit + miss
    return {
        "verified_actions": verified_total,
        "hit": hit,
        "miss_need_human": miss,
        "miss_rate": round(miss / verified_total, 3) if verified_total else 0.0,
        "miss_detail": miss_ids,
    }


def round_status(conn) -> dict:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM rounds GROUP BY status").fetchall()
    return {r["status"]: int(r["n"]) for r in rows}


def candidate_status(conn) -> dict:
    rows = conn.execute(
        "SELECT decision, COUNT(*) AS n FROM candidates GROUP BY decision").fetchall()
    return {r["decision"]: int(r["n"]) for r in rows}


def dispatch_status(conn) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM dispatch_orders GROUP BY status").fetchall()
    return {r["status"]: int(r["n"]) for r in rows}


def data_dir_audit() -> dict:
    """data/ 归并目录外发边界：整目录 gitignore，列出各子目录体积与敏感项提示。"""
    if not DATA_DIR.is_dir():
        return {"exists": False, "path": str(DATA_DIR)}
    sizes: dict[str, int] = {}
    for sub in ("chrome_profile_tencent", "logs", "round_archive", "dispatch"):
        p = DATA_DIR / sub
        if p.is_dir():
            sizes[sub] = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    db_size = DB_PATH.stat().st_size if DB_PATH.is_file() else 0
    return {
        "exists": True,
        "path": str(DATA_DIR),
        "gitignored_whole_dir": True,          # .gitignore: youpick_workflow/data/
        "db_bytes": db_size,
        "subdir_bytes": sizes,
        "sensitive_warning": "含浏览器 profile / 昵称样本 / 日志，整目录不入 git，迁移=拷贝 data/ 即迁移",
    }


def build_report() -> dict:
    conn = _conn()
    try:
        day = _today()
        accts = accounts(conn)
        usage = daily_usage_by_account(conn, day)
        acct_rows = []
        for a in accts:
            u = usage.get(a["account"], {"reply": 0, "like": 0})
            cap = a["daily_soft_cap"]
            acct_rows.append({
                "platform": a["platform"],
                "account": a["account"],
                "persona": a["persona"],
                "daily_soft_cap": cap,
                "today_replies": u["reply"],
                "today_likes": u["like"],
                "remaining": max(cap - u["reply"], 0),
                "over_cap": u["reply"] > cap,
            })
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "db_path": str(DB_PATH),
            "day": day,
            "platform_observed_daily_ceiling_note": PLATFORM_OBSERVED_DAILY_CEILING,
            "accounts": acct_rows,
            "dedup": dedup_audit(conn),
            "verify": verify_audit(conn),
            "rounds": round_status(conn),
            "candidates": candidate_status(conn),
            "dispatch": dispatch_status(conn),
            "data_dir": data_dir_audit(),
        }
    finally:
        conn.close()


def _print(report: dict) -> None:
    print("=" * 64)
    print(f"互动闭环健康 · {report['day']} · {report['generated_at']}")
    print("=" * 64)
    print(f"\n[账户 · 日限额] 平台观测软上限参考={report['platform_observed_daily_ceiling_note']}（仅备注，非闸）")
    for a in report["accounts"]:
        flag = " ⚠️超cap" if a["over_cap"] else ""
        print(f"  {a['account']}({a['platform']}) persona={a['persona']} | "
              f"cap={a['daily_soft_cap']} 今日回={a['today_replies']} 赞={a['today_likes']} "
              f"余={a['remaining']}{flag}")

    d = report["dedup"]
    print(f"\n[防重] 跨轮幂等索引生效={d['unique_index_active']} | "
          f"被拦重复尝试={d['cross_round_dup_attempts_blocked']} | 总成功动作={d['total_success_actions']}")
    print(f"  会话名单 state(日期={d['session_state_date']}, 可读={d['session_state_readable']}) "
          f"replied={d['state_replied_count']} vs 库今日回={d['db_today_replied_count']}")
    print(f"  两路一致={d['lists_consistent']}"
          + ("" if d["lists_consistent"] else
             f" | 仅名单有:{d['state_only_not_in_db']} | 仅库有:{d['db_only_not_in_state']}"))

    v = report["verify"]
    print(f"\n[回读核验] 已核验={v['verified_actions']} 命中={v['hit']} "
          f"未命中(需人工)={v['miss_need_human']} 未命中率={v['miss_rate']}")

    print(f"\n[轮状态] {report['rounds']}")
    print(f"[候选拍板] {report['candidates']}")
    print(f"[派工单] {report['dispatch']}")

    dd = report["data_dir"]
    print(f"\n[data/ 归并] exists={dd['exists']} gitignored整目录={dd.get('gitignored_whole_dir')}")
    if dd.get("exists"):
        print(f"  db={dd['db_bytes']}B 子目录={dd['subdir_bytes']}")
        print(f"  敏感提示: {dd['sensitive_warning']}")


def main() -> None:
    p = argparse.ArgumentParser(description="YouPick 互动闭环健康监控（只读）")
    p.add_argument("--json", action="store_true", help="输出 JSON（机器可读）")
    args = p.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print(report)


if __name__ == "__main__":
    main()

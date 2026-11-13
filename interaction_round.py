"""闭环巡检一轮：新评论 → 点赞/回复/回帖 → 候选整理 → 回读核验 → 归档 → 收工。

老泡儿 2026-11-13 出的六步题：
  1 有意思的该点赞点赞  2 该评论评论  3 有回复的该回复回复
  4 搜集有价值的留言整理取回来做下期内容分析  5 数据归档  6 这轮结束
外加「是不是得考虑建一个数据库?」→ 用 `db/interaction_store.py` 的本地 SQLite 镜像库。

规矩：
- 平台是真源，库是镜像 + 决策留痕；跨轮去重靠 `actions` 表，不靠硬编码 id。
- 只处理「本轮相对上一轮 done 快照的新增留言」，且排除自家回复 / 已成功动作过的留言。
- 默认 dry run 只演不发；`--approved` 才真发。前台可见、逐步输出、随机节奏、不黑箱。
- 发完回读 `comment_list` 硬核验，归档出 JSON + Markdown 两份报告。
- 失败不重试、不盲发；任一 errCode != 0 就停批并标 aborted。
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from patchright.async_api import async_playwright  # noqa: E402
from utils.human_pace import nap, human_read, HumanSession, pick_valuable  # noqa: E402
from db import interaction_store as store  # noqa: E402

BASE_DIR = Path(__file__).parent.resolve()
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = BASE_DIR / "youpick_workflow" / "data" / "chrome_profile_tencent"
LOG_DIR = BASE_DIR / "youpick_workflow" / "data" / "logs"
ARCHIVE_DIR = BASE_DIR / "youpick_workflow" / "data" / "round_archive"
COMMENT_PAGE = "https://channels.weixin.qq.com/platform/interaction/comment"
LIST_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/comment_list"
LIKE_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/like_comment"
CREATE_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/create_comment"
EXPORT_ID = "export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw"

APPROVED = "--approved" in sys.argv
ROUND_NOTE = "半小时后第二轮巡检（六步闭环全流程）"


def _arg(name: str, default: str) -> str:
    """取 --platform / --account 这类命令行参数；没传用默认（M1 多账号入口）。"""
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


PLATFORM = _arg("--platform", store.DEFAULT_PLATFORM)
ACCOUNT = _arg("--account", store.DEFAULT_ACCOUNT)
if PLATFORM != store.DEFAULT_PLATFORM or ACCOUNT != store.DEFAULT_ACCOUNT:
    EXPORT_ID = _arg("--export-id", EXPORT_ID)

# 有意思就点赞的信号（不按赞排序，看内容）
LIKE_WORTHY = ("要是", "不如", "下一集", "能不能", "建议", "后来", "然后", "如果", "让它",
               "应该", "怎么", "为啥", "不信", "谦虚", "骄傲", "以假乱真", "技术", "画面",
               "敢", "信你")

# 有回复的接话草稿：按内容关键词挑，不去模板化地群发
REPLY_RULES = (
    (("炒菜",), "嘿，您这题出得够损的！得嘞，小猫颠勺这茬儿我记下了，回头让视频部捯饬一版，您给掌掌眼。"),
    (("不信",), "嘿，您还不信？得嘞，那咱下回拿实物给您瞧瞧，您先蹲着看。"),
    (("谦虚", "骄傲"), "嗬，您这顶帽子扣得可真瓷实！得嘞，那咱就不客气，下回接着给您露一手。"),
    (("怎么", "为啥"), "甭急，咱慢慢盘道——这茬儿底下有伏笔，下集给您揭。"),
    (("要是", "不如", "下一集", "能不能", "建议", "让它", "应该", "后来", "然后"),
     "得嘞，这主意我记下了！您这思路够局气的，回头咱就照着往下捋。"),
    (("技术", "画面", "以假乱真", "灵敏", "活灵活现"),
     "您嘞，谢您捧场！这活儿是拿 AI 做的，您想看哪儿的细节，留句话，咱下回照着来。"),
)
FALLBACK_REPLY = "嗬，您这话说的，咱记下了！甭急，下回接着盘道。"


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "interaction_round.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def pick_reply(text: str) -> str:
    for keys, reply in REPLY_RULES:
        if any(k in text for k in keys):
            return reply
    return FALLBACK_REPLY


def like_worthy(text: str) -> bool:
    return len(text) >= 4 and any(w in text for w in LIKE_WORTHY)


async def post(page, api: str, body: dict) -> dict:
    r = await page.evaluate(
        """async ({api, body}) => {
            const r = await fetch(api, {method:'POST', headers:{'Content-Type':'application/json'},
                                       credentials:'include', body:JSON.stringify(body)});
            return {status:r.status, text:await r.text()};
        }""", {"api": api, "body": body})
    log(f"POST {api.split('/')[-1]} -> HTTP {r['status']} | {len(r['text'])}B")
    try:
        return json.loads(r["text"])
    except Exception:
        return {"raw": r["text"][:600]}


async def read_list(page) -> dict:
    return await post(page, LIST_API, {"lastBuff": "", "exportId": EXPORT_ID,
                                       "commentSelection": False, "forMcn": False})


async def main() -> None:
    store.init_db()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    log(f"=== 巡检轮启动 | approved={APPROVED} | 库={store.DB_PATH.name} ===")

    sess = HumanSession(max_actions=(3, 7))   # 一次上线随机只干 3~7 件，宁慢勿猛
    ok, why = sess.allow()
    if not ok:
        raise RuntimeError(f"会话闸没放行: {why}")

    rid = store.start_round(EXPORT_ID, note=ROUND_NOTE, platform=PLATFORM, account=ACCOUNT)
    log(f"round_id={rid} | 本次上线随机额度 {sess.max_actions} 件 | 账号 {PLATFORM}/{ACCOUNT}")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await nap(kind="navigate", label="打开评论管理页")
            await page.goto(COMMENT_PAGE, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(kind="settle", label="等页面稳当")

            # ── 读 + 比：本轮全量快照落库，跟上一轮 done 比出新增 ──
            lst = await read_list(page)
            if lst.get("errCode") != 0:
                raise RuntimeError(f"comment_list 失败: {json.dumps(lst, ensure_ascii=False)[:400]}")
            rows = store.flatten(lst, platform=PLATFORM, account=ACCOUNT)
            prev = store.previous_snapshot_by_round(rid)
            new_rows = [r for r in rows if r["comment_id"] not in prev]
            changed = [r for r in rows if r["comment_id"] in prev
                       and prev[r["comment_id"]]["content_hash"] != r["content_hash"]]
            store.save_snapshot(rid, rows)
            log(f"读到 {len(rows)} 条（顶层+L2） | 新增 {len(new_rows)} | 内容变更 {len(changed)}")
            for r in new_rows:
                log(f"  NEW L{r['level']} {r['comment_id']} [{r['source_tag']}] {r['nickname']}：{r['content'][:40]}")

            # 归档：(round_id, 原始响应) 先落一份，第 5 步再补报告
            raw_path = ARCHIVE_DIR / f"round_{rid:03d}_raw.json"
            raw_path.write_text(json.dumps(lst, ensure_ascii=False, indent=2), encoding="utf-8")

            # ── 第 4 步：候选整理（不管发不发，先把有价值的取回来） ──
            exclude_ids = {r["comment_id"] for r in rows if r["source_tag"] == "自家回复"}
            pool = [{"commentContent": r["content"], "commentId": r["comment_id"],
                     "commentNickname": r["nickname"], "commentLikeCount": r["like_count"]}
                    for r in rows if r["comment_id"] not in exclude_ids]
            tag_by_id = {r["comment_id"]: r["source_tag"] for r in rows}
            cand = []
            for c in pick_valuable(pool, max_candidates=len(pool)):
                if c.get("note") == "普普通通，留作备选":
                    continue   # 只取「有价值」的，不占下期内容分析名额
                c["comment_id"] = c.get("commentId") or ""
                c["nickname"] = c.get("nickname") or ""
                c["text"] = c.get("text") or ""
                c["like_count"] = c.get("likeCount") or 0
                c["source_tag"] = tag_by_id.get(c["comment_id"], "待核")
                c["signals"] = c.pop("note", "")
                c["note"] = "本轮自动搜集，待老泡儿拍板；不按点赞排序"
                store.save_candidate(rid, c, platform=PLATFORM, account=ACCOUNT)
                cand.append(c)
                log(f"  候选 [{c['source_tag']}] {c['nickname']}：{c['text'][:34]} | {c['signals']}")
                if len(cand) >= 5:      # 老泡儿：「每次搜集几条话题，我们拍板后实施」
                    break

            # ── 第 1~3 步：只对新评论动手；点赞 + 回帖 ──
            acted = 0
            aborted = False
            for r in new_rows:
                if r["source_tag"] == "自家回复":
                    continue
                if sess.actions_done >= sess.max_actions:
                    log(f"本次上线额度 {sess.max_actions} 件用满，剩下的留给下一轮（宁慢勿猛）")
                    break
                ok2, why2 = sess.allow(r["comment_id"])
                if not ok2:
                    log(f"闸拦下 {r['comment_id']}：{why2}")
                    continue

                target = {"commentId": r["comment_id"], "commentNickname": r["nickname"],
                          "commentContent": r["content"]}
                root = r["root_id"]
                await human_read(r["content"], f"看{r['nickname']}这条新留言")

                # 1) 有意思的点赞
                if like_worthy(r["content"]) and r["like_flag"] == 0 \
                        and not store.action_succeeded(r["comment_id"], "like",
                                                        platform=PLATFORM, account=ACCOUNT):
                    body = {"commentId": r["comment_id"], "scene": 1, "exportId": EXPORT_ID}
                    log(f"① 点赞 → {r['nickname']}「{r['content'][:26]}」")
                    await nap(kind="click", label="点赞前核一眼")
                    if APPROVED:
                        res = await post(page, LIKE_API, body)
                        good = res.get("errCode") == 0
                        store.log_action(rid, r["comment_id"], "like",
                                         target_nickname=r["nickname"], target_text=r["content"],
                                         status="success" if good else "failed",
                                         err_code=res.get("errCode"), response=res,
                                         platform=PLATFORM, account=ACCOUNT)
                        if good:
                            acted += 1
                            sess.actions_done += 1
                            log("   ✅ 点赞成功")
                        else:
                            aborted = True
                            log(f"   ❌ 点赞失败，停批：{json.dumps(res, ensure_ascii=False)[:300]}")
                            break
                    else:
                        log("   DRY RUN，不发（记草稿，不写动作账）")
                    await nap(kind="between_replies", label="歇一下再干下一件")

                # 2/3) 该回的回（顶层新留言 / 别人回咱的 L2，一视同仁，按内容接话）
                if store.action_succeeded(r["comment_id"], "reply",
                                          platform=PLATFORM, account=ACCOUNT):
                    continue
                if sess.actions_done >= sess.max_actions:
                    break
                text = pick_reply(r["content"])
                log(f"②③ 回复 → {r['nickname']}「{r['content'][:26]}」")
                log(f"     草稿: {text}" + (f" | 楼中楼 root={root}" if r["level"] == 2 else ""))
                await nap(3, 8, "琢磨怎么接")
                await human_read(text, "把草稿念一遍")
                if APPROVED:
                    body = {"exportId": EXPORT_ID, "replyCommentId": r["comment_id"],
                            "rootCommentId": root, "content": text,
                            "clientId": str(uuid.uuid4()), "comment": json.loads(r["raw_json"])}
                    res = await post(page, CREATE_API, body)
                    good = res.get("errCode") == 0
                    store.log_action(rid, r["comment_id"], "reply",
                                     target_nickname=r["nickname"], target_text=r["content"],
                                     content=text, status="success" if good else "failed",
                                     err_code=res.get("errCode"), response=res,
                                     platform=PLATFORM, account=ACCOUNT)
                    if good:
                        acted += 1
                        sess.consume(r["comment_id"])
                        log(f"   ✅ 已回复 | 今日累计 {sess.state['replies']}/{sess.daily_cap}")
                    else:
                        aborted = True
                        log(f"   ❌ 回复失败，停批：{json.dumps(res, ensure_ascii=False)[:300]}")
                        break
                else:
                    log("   DRY RUN，不发（记草稿，不写动作账）")
                await nap(kind="between_replies", label="两条之间歇会儿")

            # ── 回读硬核验（真发才需要；dry run 也读一遍当本轮终态快照） ──
            await nap(kind="settle", label="发完歇会儿再核")
            lst2 = await read_list(page)
            verify_path = ARCHIVE_DIR / f"round_{rid:03d}_verify.json"
            verify_path.write_text(json.dumps(lst2, ensure_ascii=False, indent=2), encoding="utf-8")
            rows2 = {r["comment_id"]: r for r in store.flatten(lst2)}
            if APPROVED:
                conn = store.connect()
                try:
                    acts = [dict(x) for x in conn.execute(
                        "SELECT * FROM actions WHERE round_id=? AND status='success'", (rid,)).fetchall()]
                finally:
                    conn.close()
                for a in acts:
                    o = rows2.get(a["comment_id"])
                    if a["action_kind"] == "like":
                        v = f"likeFlag={o.get('like_flag') if o else '没找着'}"
                    else:
                        hit = any(a["content"][:12] in (x["content"] or "") for x in rows2.values())
                        v = "回读命中回复" if hit else "回读未命中（需人工看）"
                    log(f"核验 {a['action_kind']} {a['comment_id']}: {v}")
                    # 幂等表里已有 success 行，核验结论直接 UPDATE 回去，不新增动作行
                    conn2 = store.connect()
                    try:
                        conn2.execute(
                            "UPDATE actions SET verify=? WHERE round_id=? AND comment_id=? "
                            "AND action_kind=? AND status='success'",
                            (v, rid, a["comment_id"], a["action_kind"]))
                        conn2.commit()
                    finally:
                        conn2.close()
            else:
                log("DRY RUN：未产生对外动作，回读仅作本轮终态快照")

            # ── 第 5 步：归档 + 第 6 步：收工 ──
            status = "aborted" if aborted else "done"
            store.finish_round(rid, actions_done=acted, candidates_out=len(cand),
                               comments_seen=len(rows), new_count=len(new_rows),
                               changed_count=len(changed), status=status)
            s = store.summary(rid)
            report = {"round": s, "dry_run": not APPROVED, "raw_snapshot": str(raw_path),
                      "verify_snapshot": str(verify_path), "new_comments": [
                          {"comment_id": r["comment_id"], "nickname": r["nickname"],
                           "content": r["content"], "source_tag": r["source_tag"], "level": r["level"]}
                          for r in new_rows]}
            json_path = ARCHIVE_DIR / f"round_{rid:03d}_report.json"
            json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            md = [
                f"# 巡检轮 {rid} · {datetime.now():%Y-%m-%d %H:%M}",
                "",
                f"- 模式：{'真发（--approved）' if APPROVED else 'DRY RUN（未对外发送）'}",
                f"- 留言快照：{s['comments_seen']} 条 | 新增 {s['new_count']} | 变更 {s['changed_count']}",
                f"- 对外动作：{s['actions_done']} 件 | 候选：{s['candidates_out']} 条 | 状态：{s['status']}",
                f"- 来源分布：{ {x['source_tag']: x['n'] for x in s['source_breakdown']} }",
                "", "## 下期内容分析候选（不按赞排序，待老泡儿拍板）", "",
            ]
            for c in s["candidates"]:
                md.append(f"- [{c['source_tag']}] {c['nickname']}：{c['text']}  \n  信号：{c['signals']}")
            md += ["", "## 产物", "", f"- 原始响应 `{raw_path}`", f"- 回读核验 `{verify_path}`",
                   f"- 库 `db/youpick_interaction.sqlite3` round_id={rid}",
                   "", "## ⚠️ 来源提示", "",
                   "- 本轮留言**全部为亲友自测样本**（老泡儿 2026-11-13 确认），**零自然流量**。",
                   "- 第 4 步候选仅供下期内容参考，**不可直接当作真网友共识去拍下一集**；",
                   "  待引入自然流量后，再按 `source_tag=自然流量` 的候选做功课。", ""]
            md_path = ARCHIVE_DIR / f"round_{rid:03d}_report.md"
            md_path.write_text("\n".join(md), encoding="utf-8")
            log(f"⑤ 归档 → {json_path.name} / {md_path.name} / SQLite round_id={rid}")
            log(f"⑥ 这轮结束 | status={status} | 动作 {acted} 件 | 候选 {len(cand)} 条")
        finally:
            await context.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

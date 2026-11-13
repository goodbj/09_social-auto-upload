"""粉丝维护一轮：在小猫海上跑这条视频底下，找精彩评论点赞、找有意义回复接话。

触发语（老泡儿自然话术）：「去小猫海上跑那个视频里，维护一下粉丝：找精彩的评论点评、找有意义的回复」。
本质 = `interaction_round.py` 的「全量维护」变体：不只对「新增」，对全部未处理的精彩/有意义留言动手。

范围判定（只认下面规则，绝不瞎发）：
  - 点赞：source != 自家回复 且 likeFlag==0 且 有内容价值信号（或 是回复咱的有意义 L2）；
  - 回复：L2 且 reply_to_id 指向咱的留言（网友在跟咱聊），且该线程还没咱的回帖（防重复回复）。
  - 跳过：自家回复（username 为主号 / source=自家回复）、已点过赞（likeFlag=1）、已回过（DB 成功记录 / 树上已有丸小子998 子楼）。

规矩：默认 dry_run 只演不发；--approved 才真发。每步随机停、逐字念、两条之间歇 35~120s，
前台可见不黑箱。发完回读 `comment_list` 硬核验，归档进 SQLite（rounds/comments/actions）。

真源见 docs/closed-loop-decisions.md。
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from patchright.async_api import async_playwright  # noqa: E402
from utils.human_pace import nap, human_read, HumanSession  # noqa: E402
from db import interaction_store as store  # noqa: E402

BASE_DIR = Path(__file__).parent.resolve()
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = BASE_DIR / "youpick_workflow" / "data" / "chrome_profile_tencent"
LOG_DIR = BASE_DIR / "logs"
COMMENT_PAGE = "https://channels.weixin.qq.com/platform/interaction/comment"
LIST_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/comment_list"
LIKE_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/like_comment"
CREATE_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/create_comment"
EXPORT_ID = "export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw"

APPROVED = "--approved" in sys.argv


def _arg(name: str, default: str) -> str:
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


PLATFORM = _arg("--platform", store.DEFAULT_PLATFORM)
ACCOUNT = _arg("--account", store.DEFAULT_ACCOUNT)
if PLATFORM != store.DEFAULT_PLATFORM or ACCOUNT != store.DEFAULT_ACCOUNT:
    EXPORT_ID = _arg("--export-id", EXPORT_ID)
SELF_NICK = "丸小子998"
VALUE_WORDS = ("要是", "不如", "下一集", "能不能", "建议", "后来", "然后", "如果", "让它",
               "应该", "怎么", "为啥", "不信", "谦虚", "骄傲", "以假乱真", "技术", "画面",
               "敢", "信你", "炒菜", "颠勺", "玻璃栈道", "海鸥", "灯塔")

REPLY_RULES = (
    (("谦虚", "骄傲"), "嗬，您这顶帽子扣得可真瓷实！得嘞，那咱就不客气，下回接着给您露一手。"),
    (("不信",), "嘿，您还不信？得嘞，那咱下回拿实物给您瞧瞧，您先蹲着看。"),
    (("炒菜", "颠勺"), "嘿，您这题出得够损的！得嘞，小猫颠勺这茬儿我记下了，回头让视频部捯饬一版，您给掌掌眼。"),
    (("玻璃栈道", "海鸥", "灯塔"), "您嘞，您这脑洞够局气！咱先把这集拍圆了，下回让您说的那景儿露个脸。"),
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
    with (LOG_DIR / "maintain_fans.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def pick_reply(text: str) -> str:
    for keys, reply in REPLY_RULES:
        if any(k in text for k in keys):
            return reply
    return FALLBACK_REPLY


def worthwhile(text: str) -> bool:
    return len(text) >= 4 and any(w in text for w in VALUE_WORDS)


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
    log(f"=== 粉丝维护 | 小猫海上跑 | approved={APPROVED} ===")

    sess = HumanSession(max_actions=(3, 7))
    ok, why = sess.allow()
    if not ok:
        raise RuntimeError(f"会话闸没放行: {why}")

    rid = store.start_round(EXPORT_ID, note="粉丝维护轮（全量找精彩/有意义，非仅新增）",
                            platform=PLATFORM, account=ACCOUNT)
    log(f"round_id={rid} | 本次额度 {sess.max_actions} 件")

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

            lst = await read_list(page)
            if lst.get("errCode") != 0:
                raise RuntimeError(f"comment_list 失败: {json.dumps(lst, ensure_ascii=False)[:400]}")
            rows = store.flatten(lst, platform=PLATFORM, account=ACCOUNT)
            store.save_snapshot(rid, rows)
            our_ids = {r["comment_id"] for r in rows if r["nickname"] == SELF_NICK or r["source_tag"] == "自家回复"}
            already_replied_thread = set()   # (root, target) 已被咱回过的线程
            for r in rows:                  # 树上已有丸小子998 子楼 = 这条已被咱回过
                if r["nickname"] == SELF_NICK and r["level"] == 2:
                    already_replied_thread.add((r["root_id"], r["reply_to_id"]))
            log(f"读到 {len(rows)} 条 | 咱自己 {len(our_ids)} 条 | 已回线程 {len(already_replied_thread)}")

            acted = 0
            aborted = False
            for r in rows:
                if r["source_tag"] == "自家回复" or r["comment_id"] in our_ids:
                    continue
                if sess.actions_done >= sess.max_actions:
                    log(f"本额度 {sess.max_actions} 用满，收工（宁慢勿猛）")
                    break
                is_reply_to_us = (r["level"] == 2 and r["reply_to_id"] in our_ids)
                brilliant = worthwhile(r["content"])

                # 精彩/有意义 → 点赞（且没点过）
                if (brilliant or is_reply_to_us) and r["like_flag"] == 0 \
                        and not store.action_succeeded(r["comment_id"], "like",
                                                        platform=PLATFORM, account=ACCOUNT):
                    await human_read(r["content"], f"看{r['nickname']}这条")
                    await nap(kind="click", label="点赞前核一眼")
                    log(f"👍 点赞 → {r['nickname']}「{r['content'][:26]}」")
                    if APPROVED:
                        res = await post(page, LIKE_API,
                                         {"commentId": r["comment_id"], "scene": 1, "exportId": EXPORT_ID})
                        good = res.get("errCode") == 0
                        store.log_action(rid, r["comment_id"], "like", target_nickname=r["nickname"],
                                         target_text=r["content"], status="success" if good else "failed",
                                         err_code=res.get("errCode"), response=res,
                                         platform=PLATFORM, account=ACCOUNT)
                        "✅ 点赞成功" if good else log(f"   ❌ 点赞失败: {json.dumps(res, ensure_ascii=False)[:200]}")
                        if good:
                            acted += 1
                            sess.actions_done += 1
                            log("   ✅ 点赞成功")
                        else:
                            aborted = True
                            break
                    else:
                        log("   DRY RUN，不发")
                    await nap(kind="between_replies", label="歇一下")

                # 有意义的回复（网友回咱的 L2）且这条线程还没咱的回帖 → 接话
                if is_reply_to_us and (r["root_id"], r["comment_id"]) not in already_replied_thread \
                        and not store.action_succeeded(r["comment_id"], "reply",
                                                        platform=PLATFORM, account=ACCOUNT) \
                        and sess.actions_done < sess.max_actions:
                    ok2, why2 = sess.allow(r["comment_id"])
                    if not ok2:
                        log(f"闸拦下 {r['comment_id']}：{why2}")
                        continue
                    text = pick_reply(r["content"])
                    log(f"💬 回复 → {r['nickname']}「{r['content'][:26]}」| 楼中楼 root={r['root_id']}")
                    log(f"     草稿: {text}")
                    await nap(3, 8, "琢磨怎么接")
                    await human_read(text, "把草稿念一遍")
                    if APPROVED:
                        body = {"exportId": EXPORT_ID, "replyCommentId": r["comment_id"],
                                "rootCommentId": r["root_id"], "content": text,
                                "clientId": str(uuid.uuid4()), "comment": json.loads(r["raw_json"])}
                        res = await post(page, CREATE_API, body)
                        good = res.get("errCode") == 0
                        store.log_action(rid, r["comment_id"], "reply", target_nickname=r["nickname"],
                                         target_text=r["content"], content=text,
                                         status="success" if good else "failed",
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
                        log("   DRY RUN，不发")
                    await nap(kind="between_replies", label="两条之间歇会儿")

            # 回读硬核验
            await nap(kind="settle", label="发完歇会儿再核")
            lst2 = await read_list(page)
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
                        v = "回读命中回复" if hit else "回读未命中"
                    log(f"核验 {a['action_kind']} {a['comment_id']}: {v}")
                    c2 = store.connect()
                    try:
                        c2.execute("UPDATE actions SET verify=? WHERE round_id=? AND comment_id=? "
                                   "AND action_kind=? AND status='success'",
                                   (v, rid, a["comment_id"], a["action_kind"]))
                        c2.commit()
                    finally:
                        c2.close()
            else:
                log("DRY RUN：未产生对外动作")
            store.finish_round(rid, actions_done=acted, comments_seen=len(rows),
                               new_count=0, status="aborted" if aborted else "done")
            log(f"⑥ 结束 | status={'aborted' if aborted else 'done'} | 动作 {acted} 件")
        finally:
            await context.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

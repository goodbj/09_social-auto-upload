"""亲友留言批量：点赞 + 回复（2026-11-13，老泡儿点头「这些都是亲友，挨个点赞、挨个回复」）。

范围（只认下面写死的 id，读回列表对得上才动）：
  点赞：小号顶层「我擦，水上漂」、红太狼、玻璃栈道、景荣、磊「以假乱真」、小号 L2「哼哼哼，我不信」
  回复：磊、红太狼、梦中人(Al制作)、梦中人(玻璃栈道)、景荣 → 顶层回复
        小号 L2「哼哼哼，我不信」→ 楼中楼（rootCommentId=小号顶层）
  跳过：主号自己的「太奇怪了」、咱自己的 L2「嗬，您这话说的」、已点过赞的「Al制作」（不点）

规矩：默认 dry_run 只演不发；--approved 才真发。每步随机停，逐步落日志，发完回读核验。
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from patchright.async_api import async_playwright
from utils.human_pace import nap, human_read, HumanSession

BASE_DIR = Path(__file__).parent.resolve()
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = BASE_DIR / "cookies" / "chrome_profile_tencent"
LOG_DIR = BASE_DIR / "logs"
OUT_DIR = BASE_DIR / "docs" / "probe_api_samples"
COMMENT_PAGE = "https://channels.weixin.qq.com/platform/interaction/comment"
LIST_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/comment_list"
LIKE_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/like_comment"
CREATE_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/create_comment"
EXPORT_ID = "export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw"

SMALL_TOP = "15053885978871339652"    # 小号顶层「我擦，水上漂」
SMALL_L2 = "15053904638558935653"     # 小号 L2「哼哼哼，我不信」（挂在咱 L2 下）

# (kind, 目标 commentId, 顶层 rootId(仅 L2 用), 回复文本)
PLAN = [
    ("like",  SMALL_TOP,                      None, None),
    ("reply", "15053906621522446558",         None, "嗬，您这四个字可给我脸上贴金了！这猫要真能以假乱真，咱也算没白折腾。"),
    ("like",  "15053906621522446558",         None, None),
    ("like",  "15053882536466189845",         None, None),
    ("reply", "15053882536466189845",         None, "得嘞，您这话在理儿！猫的身段是比狗灵，下集让它露一手，您接着瞧。"),
    ("like",  "15053878757372794940",         None, None),
    ("reply", "15053878757372794940",         None, "嘿，您这玻璃栈道的点子够局气！您接着往下想想，走到头能碰见点啥，给支个招儿？"),
    ("reply", "15053881293666785334",         None, "您嘞，谢您夸！这活儿是拿 AI 做的，您想看哪儿的细节，留句话，咱下回照着来。"),
    ("like",  "15053873009070902626",         None, None),
    ("reply", "15053873009070902626",         None, "您嘞，谢您捧场！甭客气，接着看，后面还有好戏。"),
    ("like",  SMALL_L2,                      SMALL_TOP, None),
    ("reply", SMALL_L2,                      SMALL_TOP, "嘿，您还不信？得嘞，那咱下回拿实物给您瞧瞧，您先蹲着看。"),
]

APPROVED = "--approved" in sys.argv


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "reply_batch_0413.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


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


def index_comments(lst: dict) -> dict:
    """把顶层与 L2 全部按 commentId 摊平，id -> (对象, 顶层对象)。"""
    idx = {}
    for top in (lst.get("data") or {}).get("comment") or []:
        idx[str(top["commentId"])] = (top, top)
        for l2 in top.get("levelTwoComment") or []:
            idx[str(l2["commentId"])] = (l2, top)
    return idx


async def read_list(page) -> dict:
    return await post(page, LIST_API, {"lastBuff": "", "exportId": EXPORT_ID,
                                       "commentSelection": False, "forMcn": False})


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_reply = sum(1 for s in PLAN if s[0] == "reply")
    n_like = sum(1 for s in PLAN if s[0] == "like")
    log(f"=== 亲友批量 | 点赞 {n_like} · 回复 {n_reply} | approved={APPROVED} ===")

    sess = HumanSession(max_actions=(len(PLAN), len(PLAN)))
    ok, why = sess.allow()
    if not ok:
        raise RuntimeError(f"会话闸没放行: {why}")

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
            idx = index_comments(lst)
            log(f"读回留言 {len(idx)} 条（顶层+L2）")

            done_like, done_reply = [], []
            for i, (kind, tid, root_id, text) in enumerate(PLAN, 1):
                if tid not in idx:
                    log(f"[{i}] ❌ 目标 {tid} 没在读回列表里，跳过（不瞎发）")
                    continue
                obj, top = idx[tid]
                nick = obj.get("commentNickname", "")
                content = obj.get("commentContent", "")

                if kind == "like":
                    if obj.get("likeFlag") == 1:
                        log(f"[{i}] 已点过赞，跳过：{nick}「{content[:20]}」")
                        continue
                    await human_read(content, f"[{i}] 看一眼{nick}这条")
                    await nap(3, 8, f"[{i}] 琢磨一下，顺手点个赞")
                    body = {"commentId": tid, "scene": 1, "exportId": EXPORT_ID}
                    log(f"[{i}] 点赞 → {nick}「{content[:24]}」 body={json.dumps(body, ensure_ascii=False)}")
                    if not APPROVED:
                        log(f"[{i}]   DRY RUN，不发")
                        continue
                    res = await post(page, LIKE_API, body)
                    if res.get("errCode") == 0:
                        sess.actions_done += 1
                        done_like.append(tid)
                        log(f"[{i}] ✅ 点赞成功")
                    else:
                        log(f"[{i}] ❌ 点赞没成：{json.dumps(res, ensure_ascii=False)[:300]}")
                    await nap(kind="between_replies", label=f"[{i}] 歇一下再下一条")

                else:  # reply
                    ok, why = sess.allow(tid)
                    if not ok:
                        log(f"[{i}] 闸拦下：{why}")
                        continue
                    await human_read(content, f"[{i}] 看{nick}说的")
                    await nap(4, 10, f"[{i}] 琢磨怎么接")
                    await human_read(text, f"[{i}] 把草稿念一遍")
                    log(f"[{i}] 回复 → {nick}「{content[:24]}」")
                    log(f"[{i}]   草稿: {text}")
                    if root_id:
                        log(f"[{i}]   楼中楼: replyCommentId={tid} rootCommentId={root_id}")
                    if not APPROVED:
                        log(f"[{i}]   DRY RUN，不发")
                        continue
                    body = {
                        "exportId": EXPORT_ID,
                        "replyCommentId": tid,
                        "rootCommentId": root_id or tid,
                        "content": text,
                        "clientId": str(uuid.uuid4()),
                        "comment": obj,
                    }
                    res = await post(page, CREATE_API, body)
                    (OUT_DIR / f"batch_reply_{i:02d}.json").write_text(
                        json.dumps({"body": body, "response": res}, ensure_ascii=False, indent=2), encoding="utf-8")
                    if res.get("errCode") == 0:
                        sess.consume(tid)
                        done_reply.append(tid)
                        log(f"[{i}] ✅ 已回复 | 今日累计 {sess.state['replies']}/{sess.daily_cap}")
                    else:
                        log(f"[{i}] ❌ 回复没成，不重试：{json.dumps(res, ensure_ascii=False)[:300]}")
                    await nap(kind="between_replies", label=f"[{i}] 两条之间歇会儿")

            if not APPROVED:
                log("DRY RUN 结束：未带 --approved，一条都没发。")
                return

            # 回读硬核验
            await nap(kind="settle", label="发完歇会儿再核")
            lst2 = await read_list(page)
            idx2 = index_comments(lst2)
            (OUT_DIR / "batch_verify.json").write_text(json.dumps(lst2, ensure_ascii=False, indent=2), encoding="utf-8")
            for tid in done_like:
                o = idx2.get(tid, (None, None))[0]
                log(f"核验·赞 {tid}: likeFlag={o.get('likeFlag') if o else '没找着'} 赞数={o.get('commentLikeCount') if o else '-'}")
            # 回复核验：咱的回复文本是否真挂在读回的列表里（顶层或 L2）
            for i, (kind, tid, root_id, text) in enumerate(PLAN, 1):
                if kind != "reply" or tid not in done_reply:
                    continue
                hit = any(text[:12] in (o[0].get("commentContent") or "") for o in idx2.values())
                log(f"核验·回 [{i}] 回在 {tid}: 回读命中 {'1+ 处' if hit else '0 处（需人工看）'}")
            log(f"=== 结束：点赞成功 {len(done_like)} 条，回复成功 {len(done_reply)} 条，无群发 ===")
        finally:
            await context.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

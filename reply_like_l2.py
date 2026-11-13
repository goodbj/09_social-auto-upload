"""第 3 步续：① 给好留言点赞 ② 回 2 级留言（楼中楼）（2026-11-13）。

老泡儿列的两项任务；各做一次、单条、不群发、随机节奏、回读硬核验。

接口（反编译 chunk_251 / chunk_512）：
  POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/like_comment
       {"commentId":"...", "scene":1, "exportId":"..."}     # LIKE=1 / UNLIKE=2
  POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/create_comment
       {"exportId":..., "replyCommentId":"<被回的那条>", "rootCommentId":"<顶层>",
        "content":..., "clientId":<uuid>, "comment":{<被回对象>}}

目标：
  点赞 → 顶层 [3]「水面下铺着一条玻璃栈道，小猫在水面奔跑」（网友自己圆的设定，最有剧情潜力）
  2级回复 → 回在咱自己那条回复（L2 id=15053901028126166689）底下，接「海鸥」那茬

规矩：--approved 才真做；默认 dry_run 只演不发。前台可见、逐步输出、不黑箱。
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
ROOT_ID = "15053885978871339652"          # 顶层「我擦，水上漂」
MY_REPLY_ID = "15053901028126166689"      # 咱 18:14 发的那条 L2
LIKE_TEXT_KEY = "水面下铺着一条玻璃栈道"   # 挑这条好留言点赞
L2_REPLY = "得嘞，那海鸥就定了，下集让它俩搭伴儿往灯塔那边溜达，您给掌掌眼。"

APPROVED = "--approved" in sys.argv


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "reply_like_l2.log").open("a", encoding="utf-8") as f:
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


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log(f"=== 点赞 + 2级回复 | approved={APPROVED} ===")

    sess = HumanSession(max_actions=(2, 2))  # 本次上线就干这两件
    ok, why = sess.allow("like_" + LIKE_TEXT_KEY[:6])
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

            # 读一遍，把目标对象捞出来（防 id 写错、防回错人）
            await nap(kind="read", label="翻评论")
            lst = await post(page, LIST_API, {
                "lastBuff": "", "exportId": EXPORT_ID,
                "commentSelection": False, "forMcn": False})
            comments = (lst.get("data") or {}).get("comment") or []
            like_target = next((c for c in comments if LIKE_TEXT_KEY in (c.get("commentContent") or "")), None)
            root = next((c for c in comments if str(c.get("commentId")) == ROOT_ID), None)
            my_reply = next((r for c in comments for r in (c.get("levelTwoComment") or [])
                             if str(r.get("commentId")) == MY_REPLY_ID), None)
            if not like_target:
                raise RuntimeError("点赞目标没找着，停手")
            if not root or not my_reply:
                raise RuntimeError("顶层/咱那条 L2 没找着，停手（防 2 级回错层）")
            log(f"点赞目标: {like_target['commentId']} |「{like_target['commentContent'][:34]}」当前赞={like_target.get('commentLikeCount')}")
            log(f"2级目标: 回在 L2 {MY_REPLY_ID} 底下 | root={ROOT_ID}")

            # ── ① 给好留言点赞 ──
            await human_read(like_target["commentContent"], "先看看这条值不值得点")
            await nap(2, 5, "琢磨一下，顺手点个赞")
            like_body = {"commentId": like_target["commentId"], "scene": 1, "exportId": EXPORT_ID}
            log(f"拟点赞 body={json.dumps(like_body, ensure_ascii=False)}")
            await nap(kind="before_send", label="点赞前核一眼")
            if not APPROVED:
                log("DRY RUN：未带 --approved，两件都不做。")
                return
            res1 = await post(page, LIKE_API, like_body)
            (OUT_DIR / "like_response.json").write_text(json.dumps(res1, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"点赞响应: {json.dumps(res1, ensure_ascii=False)[:500]}")
            if res1.get("errCode") == 0:
                sess.consume("like_" + like_target["commentId"])
                log("✅ 点赞成功")
            else:
                log("❌ 点赞没成，不重试；但继续单独验 2 级回复")

            # ── ② 2 级留言回复（楼中楼，回到咱自己那条底下）──
            await nap(kind="between_replies", label="两条动作之间歇会儿（真人不会连着秒干）")
            await human_read(my_reply.get("commentContent", ""), "把咱上一条再念一遍")
            await nap(2, 6, "琢磨楼下怎么接")
            await human_read(L2_REPLY, "把楼下草稿念一遍")
            log(f"拟 2 级回复: {L2_REPLY}")
            for _ in L2_REPLY:
                await nap(kind="type", distract=False)
            await nap(kind="before_send", label="回帖前再核一眼层级")
            body2 = {
                "exportId": EXPORT_ID,
                "replyCommentId": MY_REPLY_ID,   # 回的是咱自己那条 L2
                "rootCommentId": ROOT_ID,        # 顶层不变
                "content": L2_REPLY,
                "clientId": str(uuid.uuid4()),
                "comment": my_reply,             # 被回对象 = 咱那条 L2
            }
            (OUT_DIR / "l2_request.json").write_text(json.dumps(body2, ensure_ascii=False, indent=2), encoding="utf-8")
            log("⚠️ 已获批准，POST create_comment（2级）")
            res2 = await post(page, CREATE_API, body2)
            (OUT_DIR / "l2_response.json").write_text(json.dumps(res2, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"2级响应: {json.dumps(res2, ensure_ascii=False)[:800]}")
            if res2.get("errCode") == 0:
                sess.consume("l2_" + MY_REPLY_ID)
                log(f"✅ 2级回复已发 | 今日累计 {sess.state['replies']}/{sess.daily_cap}")
            else:
                log("❌ 2级回复没成，不重试不盲发")

            # ── 回读硬核验：赞数 + 楼中楼 ──
            await nap(kind="between_replies", label="发完歇会儿再核")
            lst2 = await post(page, LIST_API, {
                "lastBuff": "", "exportId": EXPORT_ID,
                "commentSelection": False, "forMcn": False})
            c2 = (lst2.get("data") or {}).get("comment") or []
            lt2 = next((c for c in c2 if str(c.get("commentId")) == str(like_target["commentId"])), None)
            log(f"核验·点赞: 目标赞数 之前={like_target.get('commentLikeCount')} 现在={lt2.get('commentLikeCount') if lt2 else '没找着'}")
            r2 = next((c for c in c2 if str(c.get("commentId")) == ROOT_ID), None)
            l2list = (r2 or {}).get("levelTwoComment") or []
            hit = [x for x in l2list if L2_REPLY[:10] in (x.get("commentContent") or "")]
            log(f"核验·2级: 顶层下 L2 共 {len(l2list)} 条 | 命中我方新回复 {len(hit)} 处")
            for x in l2list:
                log(f"    L2 id={x.get('commentId')} replyTo={x.get('replyCommentId')} | {str(x.get('commentContent'))[:46]}")
            (OUT_DIR / "l2_verify.json").write_text(json.dumps(lst2, ensure_ascii=False, indent=2), encoding="utf-8")

            log("窗口留 10 秒给您看，随后关闭")
            await nap(7, 11, "收尾")
        finally:
            await context.close()
    log("=== 结束：点赞 1 次 + 2级回复 1 条，无群发 ===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

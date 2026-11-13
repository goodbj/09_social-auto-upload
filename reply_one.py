"""真回一条留言（2026-11-13，老泡儿已点头「发」）。

目标：小猫视频里「对方正在输入中...」那条
  commentId = 15053885978871339652
  原文 = 我擦，水上漂，这猫怎么不掉海里去

草稿（胡同串子口气，已过老泡儿目）：
  嗬，您这话说的——这猫脚底下踩着玻璃栈道呢，海看着深，其实它一溜烟就飘过去了。下回让它碰见只海鸥，您说它搭不搭伴儿？

规矩：
- 必须显式传 --approved 才发；默认 dry_run 只演不发（三道闸）。
- 只认死这一条 commentId，硬编码，绝不循环、绝不群回。
- 全程 utils/human_pace 随机节奏：读 → 琢磨 → 逐字敲（在页面里演）→ 发送前核一眼 → POST。
- 发完**回读** comment_list 硬核验，留痕落盘；失败不重试、不盲发第二条。
- 前台可见窗口，逐步输出，不黑箱。
"""
import asyncio
import json
import random
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
CREATE_API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/create_comment"

EXPORT_ID = "export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw"
TARGET_ID = "15053885978871339652"
TARGET_NICK = "对方正在输入中..."
TARGET_TEXT = "我擦，水上漂，这猫怎么不掉海里去"
REPLY = "嗬，您这话说的——这猫脚底下踩着玻璃栈道呢，海看着深，其实它一溜烟就飘过去了。下回让它碰见只海鸥，您说它搭不搭伴儿？"

APPROVED = "--approved" in sys.argv


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "reply_one.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def post(page, api: str, body: dict) -> dict:
    r = await page.evaluate(
        """async ({api, body}) => {
            const r = await fetch(api, {method:'POST', headers:{'Content-Type':'application/json'},
                                       credentials:'include', body:JSON.stringify(body)});
            return {status:r.status, text:await r.text()};
        }""",
        {"api": api, "body": body},
    )
    log(f"POST {api.split('/')[-1]} -> HTTP {r['status']} | {len(r['text'])}B")
    try:
        return json.loads(r["text"])
    except Exception:
        return {"raw": r["text"][:600]}


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log(f"=== 真回一条 | approved={APPROVED} | 目标 {TARGET_ID} ===")

    sess = HumanSession(max_actions=(1, 1))  # 本次上线就干这一件
    ok, why = sess.allow(TARGET_ID)
    if not ok:
        raise RuntimeError(f"会话闸没放行: {why}")
    log(f"会话闸放行: {why} | 本次上限 {sess.max_actions} 件")

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

            # 1) 先读一遍：确认目标留言还在、拿到原对象（create_comment 要传 comment）
            await nap(kind="read", label="翻到那条留言")
            lst = await post(page, LIST_API, {
                "lastBuff": "", "exportId": EXPORT_ID,
                "commentSelection": False, "forMcn": False,
            })
            comments = (lst.get("data") or {}).get("comment") or []
            target = next((c for c in comments if str(c.get("commentId")) == TARGET_ID), None)
            if not target:
                raise RuntimeError("目标留言没在读回的列表里，停手不发")
            log(f"目标确认: 「{target.get('commentContent')}」 by {target.get('commentNickname')}")
            if target.get("commentContent") != TARGET_TEXT:
                raise RuntimeError("目标留言内容对不上，停手不发（防回错人）")

            # 2) 拟人节奏：默读、琢磨、逐字敲（在页面里演给日志看，真正内容走 API）
            await human_read(TARGET_TEXT, "默读网友这条")
            await nap(2, 6, "琢磨怎么接话")
            await human_read(REPLY, "自己把草稿念一遍")
            log(f"拟发: {REPLY}")
            (OUT_DIR / "reply_one_draft.json").write_text(
                json.dumps({"draft": REPLY, "target": target, "approved": APPROVED,
                            "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            for ch in REPLY:  # 逐字节奏留痕（不真往页面输入框敲，评论微应用没挂载）
                await nap(kind="type", label=None, distract=False)
            await nap(kind="before_send", label="点发送前核一眼")

            if not APPROVED:
                log("DRY RUN：未带 --approved，不发送。上面草稿就是全部动作。")
                return

            # 3) 真发：只此一次
            body = {
                "exportId": EXPORT_ID,
                "replyCommentId": TARGET_ID,
                "rootCommentId": TARGET_ID,
                "content": REPLY,
                "clientId": str(uuid.uuid4()),
                "comment": target,
            }
            log(f"⚠️ 已获批准，POST create_comment | body 字段={list(body.keys())}")
            (OUT_DIR / "reply_one_request.json").write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            res = await post(page, CREATE_API, body)
            (OUT_DIR / "reply_one_response.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"响应: {json.dumps(res, ensure_ascii=False)[:800]}")

            sent = res.get("errCode") == 0
            if sent:
                sess.consume(TARGET_ID)
                log(f"✅ 已回复 | 今日累计 {sess.state['replies']}/{sess.daily_cap}")
            else:
                log("❌ 没成功（errCode 非 0）→ 不重试、不盲发第二条，留响应供排查")

            # 4) 回读硬核验：看回复是否真挂上（levelTwoComment 或新顶层）
            await nap(kind="between_replies", label="发完歇会儿再核")
            lst2 = await post(page, LIST_API, {
                "lastBuff": "", "exportId": EXPORT_ID,
                "commentSelection": False, "forMcn": False,
            })
            c2 = (lst2.get("data") or {}).get("comment") or []
            hit = [c for c in c2 if REPLY[:12] in (c.get("commentContent") or "")
                   or any(REPLY[:12] in (r.get("commentContent") or "") for r in (c.get("levelTwoComment") or []))]
            log(f"回读核验: 共 {len(c2)} 条顶层留言 | 命中我方回复 {len(hit)} 处")
            (OUT_DIR / "reply_one_verify.json").write_text(json.dumps(lst2, ensure_ascii=False, indent=2), encoding="utf-8")

            log("窗口留 10 秒给您看，随后关闭")
            await nap(7, 11, "收尾")
        finally:
            await context.close()
    log("=== 结束（只此一条，无群回）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

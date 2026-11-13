"""只读探路 v7：诊断评论微应用为何空白（console + 失败请求 + JS 加载）（2026-11-13）。

v6 结论：评论页能进、post_list 有数据（小猫 commentCount=1），但
micro/interaction/comment iframe 的 <div id="app"> 始终空。
壳 HTML 靠两个 defer script（res.wx.qq.com .../chunk-common、index）灌 Vue。

v7 目的：抓 iframe 控制台报错、请求失败、script 加载状态，定位空白根因。
严格只读：不回帖/不发布/不删除/不点赞/不重放。窗口可见，逐步输出。
"""
import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from patchright.async_api import async_playwright
from utils.human_pace import nap  # 老泡儿 2026-11-13：随机休眠，不一口气跑完

BASE_DIR = Path(__file__).parent.resolve()
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = BASE_DIR / "cookies" / "chrome_profile_tencent"
LOG_DIR = BASE_DIR / "logs"
COMMENT_URL = "https://channels.weixin.qq.com/platform/interaction/comment"


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_comments_v7.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()

            # 全局 console / 请求失败 / 响应状态
            def on_console(m):
                if m.type in ("error", "warning"):
                    log(f"[console:{m.type}] {m.text[:400]} | {m.location.get('url','')[:120]}")
            page.on("console", on_console)

            def on_fail(req):
                log(f"[reqfail] {req.failure} | {req.url[:200]}")
            page.on("requestfailed", on_fail)

            bad_status = []
            def on_resp(r):
                if r.status >= 400:
                    bad_status.append((r.status, r.url))
                    log(f"[http {r.status}] {r.url[:200]}")
            page.on("response", on_resp)

            log(f"直达评论页: {COMMENT_URL}")
            await page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(10.5, 21.0, "页面停顿")

            # 随机休息（模拟人节奏），读完再继续
            await nap(3, 6, "诊断额外停顿")

            cfr = next((f for f in page.frames if "micro/interaction/comment" in f.url), None)
            log(f"iframe = {cfr.url if cfr else 'None'}")
            if cfr:
                info = await cfr.evaluate("""() => ({
                    ready: document.readyState,
                    appChildren: (document.getElementById('app')||{}).children?.length ?? -1,
                    appHTML: ((document.getElementById('app')||{}).innerHTML||'').slice(0,300),
                    scripts: Array.from(document.scripts).map(s=>({src:s.getAttribute('src'), loaded:s.readyState})),
                    err: window.__v7_err || null,
                    ua: navigator.userAgent,
                    href: location.href,
                    referrer: document.referrer,
                    bodyLen: document.body.innerHTML.length
                })""")
                log(f"[iframe info] {json.dumps(info, ensure_ascii=False)}")

            # 主文档里 iframe 标签的属性（看有没有传参 / sandbox）
            ifr = await page.evaluate("""() => Array.from(document.querySelectorAll('iframe')).map(e=>({src:e.getAttribute('src'),id:e.id,cls:(e.className||'').toString(),sandbox:e.getAttribute('sandbox'),w:e.getBoundingClientRect().width,h:e.getBoundingClientRect().height}))""")
            log(f"[iframes] {json.dumps(ifr, ensure_ascii=False)}")

            log(f"HTTP>=400 共 {len(bad_status)} 条")
            await page.screenshot(path=str(LOG_DIR / "probe_v7.png"), full_page=True)
            log("窗口留 8 秒给您看，随后关闭")
            await nap(5.6, 11.2, "收尾停顿")
        finally:
            await context.close()
    log("=== v7 结束（全程只读）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

"""只读探路 v3：直达评论管理页，专钻 micro/interaction/comment iframe（2026-11-13）。

v2 已确认：评论页 URL = /platform/interaction/comment，内容在 iframe
https://channels.weixin.qq.com/micro/interaction/comment 里；主文档抓不到卡片。
v3：直达 URL + 充分等待 + 逐 frame dump DOM/文本/网络请求，摸清留言数据结构。

只读：不回帖、不发布、不删除、不点赞。窗口可见，全程打印。
"""
import asyncio
import json
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
    with (LOG_DIR / "probe_comments_v3.log").open("a", encoding="utf-8") as f:
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

            # 监听 iframe 发出的 XHR/fetch，看评论数据走哪个接口（只读记录，不拦截不重放）
            api_hits = []
            def on_request(req):
                u = req.url
                if any(k in u.lower() for k in ("comment", "interaction", "cgi-bin", "finder")) and ("api" in u or "cgi" in u or "comment" in u):
                    api_hits.append(f"{req.method} {u[:200]}")
            page.on("request", on_request)

            log(f"直达评论页: {COMMENT_URL}")
            await page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            # 给 iframe 充分时间异步灌数据
            await nap(8.4, 16.8, "页面停顿")

            log(f"page URL = {page.url}")
            for i, fr in enumerate(page.frames):
                log(f"=== frame[{i}] {fr.url} ===")
                try:
                    txt = await fr.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,2500)")
                    log(f"frame[{i}] TEXT = {txt}")
                    # 枚举所有带 class 的卡片/列表/点赞/回复相关元素
                    els = await fr.evaluate("""() => {
                        const sels = '[class*="comment"],[class*="list"],[class*="card"],[class*="item"],[class*="like"],[class*="reply"],[class*="content"],[class*="user"],input,textarea,[contenteditable]';
                        return Array.from(document.querySelectorAll(sels)).map(e=>({
                            tag:e.tagName.toLowerCase(), cls:(e.className||'').toString().slice(0,80),
                            t:(e.innerText||e.value||'').trim().replace(/\\s+/g,' ').slice(0,140),
                            ph:e.getAttribute('placeholder')||''
                        })).filter(x=>x.t||x.ph).slice(0,80);
                    }""")
                    for e in els:
                        log(f"frame[{i}] EL = {json.dumps(e, ensure_ascii=False)}")
                    # 整页 HTML 结构片段（找 data 属性 / 列表容器）
                    html = await fr.evaluate("() => document.body.innerHTML.slice(0,4000)")
                    log(f"frame[{i}] HTML(head) = {html[:1500]}")
                except Exception as exc:
                    log(f"frame[{i}] 读取失败: {type(exc).__name__}: {exc}")

            log("=== 捕获到的相关网络请求（只读记录） ===")
            for h in dict.fromkeys(api_hits):
                log(f"  {h}")

            await page.screenshot(path=str(LOG_DIR / "probe_v3_comment.png"), full_page=True)
            log("窗口留 8 秒给您看，随后关闭")
            await nap(5.6, 11.2, "收尾停顿")
        finally:
            await context.close()
    log("=== v3 结束（全程未发布、未回复、未删除、未点赞）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

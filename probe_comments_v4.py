"""只读探路 v4：抓 post_list 响应体 + 监听评论列表接口（2026-11-13）。

v3 结论：评论页 iframe（micro/interaction/comment）body 为空，数据走
POST .../post/post_list（视频列表）。评论数据疑在「选中某条视频」后另起接口拉。

v4 做法：
1) 监听所有 response，落盘 post_list / comment 类接口的响应体（只读记录，不重放）。
2) 直达评论页，等 iframe 渲染出视频卡片；点第一条视频（只读点击，非回复）。
3) 再等，抓冒出来的评论列表接口与响应结构。
只读：不回帖、不发布、不删除、不点赞、不置顶。窗口可见，全程打印。
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
OUT_DIR = BASE_DIR / "docs" / "probe_api_samples"
COMMENT_URL = "https://channels.weixin.qq.com/platform/interaction/comment"

INTEREST = ("post_list", "comment", "msg", "reply", "interaction", "post")


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_comments_v4.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hits = []

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()

            async def on_response(resp):
                u = resp.url
                if not any(k in u.lower() for k in INTEREST):
                    return
                if "cgi-bin" not in u and "micro" not in u:
                    return
                # 跳过纯上报/埋点类
                if any(k in u for k in ("helper_", "report-perf", "mmdata", "helper_report")):
                    return
                try:
                    body = await resp.text()
                except Exception as exc:
                    log(f"[resp] 读响应失败 {type(exc).__name__} {u[:120]}")
                    return
                tag = u.split("?")[0].rstrip("/").split("/")[-1]
                fn = OUT_DIR / f"{tag}_{len(hits):02d}.json"
                fn.write_text(body[:200000], encoding="utf-8")  # 截断防爆
                hits.append(tag)
                log(f"[resp] {resp.status} {tag} len={len(body)} -> {fn}")
                log(f"[resp] head = {body[:600]}")

            page.on("response", on_response)

            log(f"直达评论页: {COMMENT_URL}")
            await page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(7.0, 14.0, "页面停顿")

            # 找评论 iframe
            cfr = None
            for fr in page.frames:
                if "micro/interaction/comment" in fr.url:
                    cfr = fr
                    break
            if not cfr:
                log("没找到评论 iframe，只留截图")
                await page.screenshot(path=str(LOG_DIR / "probe_v4_noiframe.png"))
                return

            log(f"评论 iframe = {cfr.url}")
            txt = await cfr.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,1500)")
            log(f"iframe TEXT = {txt}")

            # 找 iframe 里可点的视频卡片（只读点击，不点任何回复/发送类）
            cards = await cfr.evaluate("""() => {
                const sels='[class*="post"],[class*="card"],[class*="item"],[class*="list"] > *,[class*="video"]';
                return Array.from(document.querySelectorAll(sels)).map(e=>{
                    const r=e.getBoundingClientRect();
                    return {cls:(e.className||'').toString().slice(0,70),
                            t:(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,100),
                            x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), w:Math.round(r.width), h:Math.round(r.height)};
                }).filter(o=>o.w>40 && o.h>20 && o.t).slice(0,30);
            }""")
            for c in cards:
                log(f"[card] {json.dumps(c, ensure_ascii=False)}")

            # 点第一个像视频卡片的（文本含标题/日期，且不含危险词）
            DANGER = ("回复", "发送", "删除", "发表", "发布", "置顶", "屏蔽")
            target = next((c for c in cards if c["t"] and not any(d in c["t"] for d in DANGER)), None)
            if target:
                log(f"[click] 只读点视频卡片: 「{target['t'][:40]}」")
                await page.mouse.click(target["x"], target["y"])
                await nap(5.6, 11.2, "页面停顿")
                log("点完后监听到的接口：")
                for h in hits:
                    log(f"  - {h}")
                txt2 = await cfr.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,2000)")
                log(f"点后 iframe TEXT = {txt2}")
                await page.screenshot(path=str(LOG_DIR / "probe_v4_after_click.png"), full_page=True)
            else:
                log("没找到可点的视频卡片；可能 post_list 已把评论一并返回，见上面响应体")

            log("窗口留 8 秒给您看，随后关闭")
            await nap(5.6, 11.2, "收尾停顿")
        finally:
            await context.close()
    log("=== v4 结束（全程未发布/未回复/未删除/未点赞）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

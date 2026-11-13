"""只读探路 v6：点开带评论的作品，抓「评论详情接口」+ 留言/点赞/回复框结构（2026-11-13）。

v5 结论：post_list 给 commentCount（小猫那条=1），但 commentList 内嵌为空；
评论详情必然另有接口按 objectId 拉。分页靠 data.lastBuff。

v6：用 v2 验证过的「hover 左侧气泡图标 → 点评论」进页（保证 iframe 渲染），
再点带评论的视频卡片，监听新冒出的接口，落盘响应体 + 枚举回复框 DOM。
严格只读：不回帖、不发布、不删除、不点赞、不置顶、不重放请求。窗口可见。

⚠️ 风控：每步之间用 nap() 随机停顿，模拟人节奏，不一口气跑完（utils/human_pace.py）。
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
HOME_URL = "https://channels.weixin.qq.com/platform"

POST_TARGET_ID = "export/UzFfBgAAxKKvfAFEXVuQk8z"  # 今儿 16:34 小猫，commentCount=1
DANGER = ("回复", "发送", "删除", "发表", "发布", "置顶", "屏蔽", "举报")


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_comments_v6.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seen = set()
    api_log = []

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()

            async def on_response(resp):
                u = resp.url
                if "cgi-bin" not in u and "micro" not in u:
                    return
                if any(k in u for k in ("helper_", "report-perf", "mmdata", "helper_report", "auth_", "auth/", "notification")):
                    return
                tag = u.split("?")[0].rstrip("/").split("/")[-1]
                key = (tag, u.split("_rid=")[-1][:20] if "_rid=" in u else "")
                if key in seen:
                    return
                seen.add(key)
                try:
                    body = await resp.text()
                except Exception:
                    return
                fn = OUT_DIR / f"v6_{tag}_{len(api_log):02d}.json"
                fn.write_text(body[:300000], encoding="utf-8")
                api_log.append((tag, len(body), fn.name))
                log(f"[resp] {tag} len={len(body)} -> {fn.name}")
                log(f"  head = {body[:700]}")

            page.on("response", on_response)

            log(f"打开首页: {HOME_URL}")
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(2.8, 5.6, "页面停顿")

            # 1) hover 左侧第 3 个气泡图标（y≈260）展开「互动管理」
            log("hover 左侧气泡图标展开互动管理")
            await page.mouse.move(44, 260)
            await nap(0.84, 1.68, "页面停顿")
            # 找展开后可见的「评论」并点
            hit = await page.evaluate("""() => {
                const els=Array.from(document.querySelectorAll('[class*="sub-menu__item"],[class*="menu__link"]'));
                const h=els.find(e=>(e.innerText||'').trim()==='评论' && e.getBoundingClientRect().width>0);
                if(!h)return null; const r=h.getBoundingClientRect();
                return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};
            }""")
            if not hit:
                log("没找到可见「评论」入口，收工（留截图）")
                await page.screenshot(path=str(LOG_DIR / "probe_v6_noentry.png"))
                return
            log(f"只读点击「评论」({hit})")
            await page.mouse.click(hit["x"], hit["y"])
            await nap(7.0, 14.0, "页面停顿")
            log(f"page URL = {page.url}")

            cfr = next((f for f in page.frames if "micro/interaction/comment" in f.url), None)
            if not cfr:
                log("没评论 iframe，收工")
                await page.screenshot(path=str(LOG_DIR / "probe_v6_noiframe.png"))
                return
            log(f"评论 iframe = {cfr.url}")
            txt = await cfr.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,2000)")
            log(f"iframe TEXT = {txt}")

            # 2) 在 iframe 里找带「小猫在海上跑」的视频卡片（只读点）
            cards = await cfr.evaluate("""() => {
                const sels='[class*="post"],[class*="card"],[class*="item"],[class*="list"] > *,[class*="video"],[class*="desc"]';
                return Array.from(document.querySelectorAll(sels)).map(e=>{
                    const r=e.getBoundingClientRect();
                    return {cls:(e.className||'').toString().slice(0,70),
                            t:(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,110),
                            x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),w:Math.round(r.width),h:Math.round(r.height)};
                }).filter(o=>o.w>40&&o.h>15&&o.t).slice(0,40);
            }""")
            for c in cards:
                log(f"[card] {json.dumps(c, ensure_ascii=False)}")

            target = next((c for c in cards if "小猫在海上" in c["t"] and not any(d in c["t"] for d in DANGER)), None)
            if not target:
                # 退而求其次：点第一个不含危险词、字数较多的卡片
                target = next((c for c in cards if len(c["t"])>8 and not any(d in c["t"] for d in DANGER)), None)
            if target:
                log(f"[click] 只读点视频卡片: 「{target['t'][:50]}」")
                await page.mouse.click(target["x"], target["y"])
                await nap(6.3, 12.6, "页面停顿")
                txt2 = await cfr.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,2500)")
                log(f"点后 iframe TEXT = {txt2}")
                # 枚举回复框 / 留言条目 / 点赞元素（只读）
                els = await cfr.evaluate("""() => {
                    const sels='[class*="comment"],[class*="like"],[class*="reply"],[class*="content"],input,textarea,[contenteditable],[placeholder]';
                    return Array.from(document.querySelectorAll(sels)).map(e=>({
                        tag:e.tagName.toLowerCase(),cls:(e.className||'').toString().slice(0,70),
                        t:(e.innerText||e.value||'').trim().replace(/\\s+/g,' ').slice(0,150),
                        ph:e.getAttribute('placeholder')||''
                    })).filter(x=>x.t||x.ph).slice(0,60);
                }""")
                for e in els:
                    log(f"[el] {json.dumps(e, ensure_ascii=False)}")
                await page.screenshot(path=str(LOG_DIR / "probe_v6_after_click.png"), full_page=True)
            else:
                log("没找到可点视频卡片；请人工看 iframe TEXT 判断")

            log("=== 本次捕获接口清单 ===")
            for tag, n, fn in api_log:
                log(f"  {tag} ({n}B) {fn}")
            log("窗口留 8 秒给您看，随后关闭")
            await nap(5.6, 11.2, "收尾停顿")
        finally:
            await context.close()
    log("=== v6 结束（全程只读：未发布/未回复/未删除/未点赞/未重放）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

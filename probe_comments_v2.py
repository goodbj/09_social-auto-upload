"""只读探路 v2：视频号后台左侧折叠图标菜单 → 评论管理（2026-11-13）。

v1 教训：左侧是纯图标折叠栏，get_by_text 抓到的是隐藏 popup_menu 容器，
点看不见的元素必超时。v2 改为：枚举左侧菜单 DOM → hover 展开 → 点可见项。
只读：不回帖、不发布、不删除、不改设置。窗口可见，全程打印。
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
HOME_URL = "https://channels.weixin.qq.com/platform"
DANGER = ("回复", "发送", "删除", "发表", "发布", "置顶", "屏蔽", "举报", "移入")


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_comments_v2.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def dump(page, tag: str) -> None:
    log(f"[{tag}] URL = {page.url}")
    for fr in page.frames:
        log(f"[{tag}] frame = {fr.url}")
    body = await page.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,1800)")
    log(f"[{tag}] body = {body}")
    await page.screenshot(path=str(LOG_DIR / f"probe_v2_{tag}.png"), full_page=False)


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            log("打开首页")
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(2.1, 4.2, "页面停顿")

            # 1) 枚举左侧菜单项（顶层图标 + 文字），带可见性
            items = await page.evaluate("""() => {
                const sels = '[class*="menu__link"], [class*="menu__name"], [class*="sub-menu__item"], [class*="menu__item"]';
                return Array.from(document.querySelectorAll(sels)).map((e,i) => {
                    const r = e.getBoundingClientRect();
                    return {i, t:(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,30),
                            cls:(e.className||'').toString().slice(0,70),
                            x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height),
                            vis: r.width>0 && r.height>0};
                }).filter(x => x.t).slice(0, 80);
            }""")
            for it in items:
                log(f"[menu] {json.dumps(it, ensure_ascii=False)}")

            # 2) 找「评论」可见项；没有就 hover 顶层图标展开再找
            async def find_comment_visible():
                return await page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('[class*="sub-menu__item"], [class*="menu__link"], [class*="menu__name"]'));
                    const hit = els.find(e => (e.innerText||'').trim()==='评论' && e.getBoundingClientRect().width>0 && getComputedStyle(e).visibility!=='hidden');
                    if(!hit) return null;
                    const r=hit.getBoundingClientRect();
                    return {x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), cls:(hit.className||'').toString()};
                }""")

            hit = await find_comment_visible()
            if not hit:
                # hover 每个顶层图标，展开 popup 菜单
                icons = await page.evaluate("""() => Array.from(document.querySelectorAll('[class*="menu__link"]')).map(e=>{const r=e.getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),t:(e.innerText||'').trim().slice(0,20),w:Math.round(r.width)};}).filter(o=>o.w>0).slice(0,20)""")
                for ic in icons:
                    log(f"[hover] 图标 {json.dumps(ic, ensure_ascii=False)}")
                    await page.mouse.move(ic["x"], ic["y"])
                    await nap(0.42, 0.84, "页面停顿")
                    hit = await find_comment_visible()
                    if hit:
                        log(f"[hover] 展开后找到评论: {json.dumps(hit, ensure_ascii=False)}")
                        break

            if hit:
                log(f"[click] 只读点击可见「评论」({hit['cls']})")
                await page.mouse.click(hit["x"], hit["y"])
                await nap(2.8, 5.6, "页面停顿")
                await dump(page, "comment_page")

                # 3) 评论页结构：列表项 / 点赞数 / 回复入口，只读枚举
                cards = await page.evaluate("""() => {
                    const sels = '[class*="comment"], [class*="list-item"], [class*="card"], [class*="like"], [class*="reply"]';
                    return Array.from(document.querySelectorAll(sels)).map(e=>({
                        cls:(e.className||'').toString().slice(0,70),
                        t:(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,120)
                    })).filter(x=>x.t).slice(0,40);
                }""")
                for c in cards:
                    log(f"[card] {json.dumps(c, ensure_ascii=False)}")
            else:
                log("[click] 没找到可见「评论」入口；只留首页截图供人工核对")
                await dump(page, "no_comment_entry")

            log("窗口留 8 秒给您看，随后关闭")
            await nap(5.6, 11.2, "收尾停顿")
        finally:
            await context.close()
    log("=== v2 结束（全程未发布、未回复、未删除）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

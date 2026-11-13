"""只读探路：视频号后台「评论/互动」入口与留言 DOM 结构勘察（2026-11-13）。

规矩（老泡儿拍的：测试阶段不黑箱）：
- 前台可见窗口 headless=False，全程打印，截图落 logs/。
- 只读：只点导航（内容管理/互动管理/评论类），绝不点 发表/回复/发送/删除。
- 不发布任何内容、不回复任何网友、不改账号设置。

目的：为闭环第 3/4 步（读留言 + 找点赞最高的留言）趟清页面结构与可达性。
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

# 只读允许点击的导航关键词；命中危险词的条目一律跳过
NAV_WORDS = ("内容管理", "互动管理", "评论管理", "评论", "留言", "作品管理")
DANGER_WORDS = ("发表", "回复", "发送", "删除", "新建", "上传", "发布", "保存", "确认")


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_comments.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def dump(page, tag: str) -> list[dict]:
    log(f"[{tag}] URL = {page.url}")
    for fr in page.frames:
        log(f"[{tag}] frame = {fr.url}")
    navs = await page.evaluate(
        """() => {
        const sels = 'a,button,[role="button"],[class*="menu"],[class*="nav"],[class*="tab"]';
        return Array.from(document.querySelectorAll(sels))
          .map(e => ({t:(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,50),
                      href:e.getAttribute('href')||'', cls:(e.className||'').toString().slice(0,60)}))
          .filter(x => x.t).slice(0, 100);
    }"""
    )
    for x in navs:
        log(f"[{tag}] nav = {json.dumps(x, ensure_ascii=False)}")
    # 页面可见文本（前 1200 字），看有没有留言/点赞数的影子
    body = await page.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,1200)")
    log(f"[{tag}] body = {body}")
    shot = LOG_DIR / f"probe_comments_{tag}.png"
    await page.screenshot(path=str(shot), full_page=False)
    log(f"[{tag}] 截图 = {shot}")
    return navs


async def try_click_nav(page, navs: list[dict], tag: str) -> bool:
    """只读导航点击：只点含 NAV_WORDS 且不含 DANGER_WORDS 的第一条。"""
    for word in NAV_WORDS:
        for item in navs:
            t = item.get("t", "")
            if word in t and not any(d in t for d in DANGER_WORDS):
                loc = page.get_by_text(t, exact=False).first
                try:
                    if not await loc.count():
                        continue
                    log(f"[{tag}] 只读点击导航: 「{t}」")
                    await loc.click(timeout=5000)
                    await nap(2.45, 4.9, "页面停顿")
                    return True
                except Exception as exc:
                    log(f"[{tag}] 点「{t}」没成({type(exc).__name__})，换下一个")
                    continue
    return False


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for p in (CHROME_EXE, PROFILE_DIR):
        if not Path(p).exists():
            raise RuntimeError(f"缺失: {p}")

    log("=== 只读勘察开始：窗口可见，不回帖不发布 ===")
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=CHROME_EXE,
            headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            log(f"打开首页: {HOME_URL}")
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(2.8, 5.6, "页面停顿")

            navs = await dump(page, "01_home")
            if await try_click_nav(page, navs, "02_nav"):
                await dump(page, "02_after_nav")
                navs2 = await dump(page, "03_detail")
                # 再往「评论/互动」钻一层
                if await try_click_nav(page, navs2, "04_comment"):
                    await dump(page, "04_comment")

            log("勘察完毕；窗口留 10 秒给您看，随后自动关闭")
            await nap(7.0, 14.0, "收尾停顿")
        finally:
            await context.close()
    log("=== 只读勘察结束（全程未发布、未回复、未删除）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

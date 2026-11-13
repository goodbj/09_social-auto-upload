"""探「微信快捷登录」v2：用 frame 定位器精确点按钮（2026-11-13）。

v1 教训：按钮在 open.weixin.qq.com/connect/qrconnect iframe 里，
面板坐标是 iframe 内部坐标，用主页面 mouse.click 点必点空。
v2 改为 frame_locator('button.js_quick_login_btn').click()，坐标由 Playwright 自己换算。

老泡儿明确授权点这颗按钮恢复会话；不扫码、不等超时、不回帖、不发布。
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from patchright.async_api import async_playwright
from utils.human_pace import nap

BASE_DIR = Path(__file__).parent.resolve()
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = BASE_DIR / "cookies" / "chrome_profile_tencent"
LOG_DIR = BASE_DIR / "logs"
HOME_URL = "https://channels.weixin.qq.com"


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_quick_login_v2.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log("=== 微信快捷登录 v2：精确定位按钮 ===")
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await nap(kind="navigate", label="打开视频号")
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(kind="settle", label="等快捷登录面板出现")

            # 找 qrconnect iframe（快捷登录面板就在里面）
            qfr = next((f for f in page.frames if "qrconnect" in f.url), None)
            if not qfr:
                log("没找着 qrconnect iframe，可能压根没掉登录（直接是后台）")
                log(f"URL={page.url}")
                return
            log(f"qrconnect frame = {qfr.url[:120]}…")

            btn = qfr.locator("button.js_quick_login_btn, a.js_quick_login_btn, .qlogin_btn").first
            cnt = await btn.count()
            log(f"快捷登录按钮 count={cnt}")
            if not cnt:
                log("按钮没挂上，收工")
                return
            txt = (await btn.inner_text()).strip()
            cls = await btn.get_attribute("class")
            log(f"按钮文字=「{txt}」 class={cls}")

            await nap(kind="click", label="伸手点「微信快捷登录」")
            await btn.click(timeout=15000)
            log("已点！等跳转（最多 20 秒，不死磕）")
            try:
                await page.wait_for_url(lambda u: "login.html" not in u, timeout=20000)
                log(f"跳转成功 -> {page.url}")
            except Exception:
                log(f"20 秒内没跳出登录页，当前 URL={page.url}")
            await nap(3, 6, "点完缓一下再看")

            log(f"最终 URL = {page.url}")
            body = await page.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,600)")
            log(f"页面文本 = {body}")
            logged = "login.html" not in page.url and "platform" in page.url
            log(f"免扫码登录成功? {logged}")
            await page.screenshot(path=str(LOG_DIR / "quick_login_v2_result.png"))

            if logged:
                state = await context.storage_state()
                keep = [c for c in state.get("cookies", []) if "weixin.qq.com" in c.get("domain", "")]
                acc = BASE_DIR / "cookies" / "tencent_creator.json"
                acc.write_text(json.dumps({"cookies": keep, "origins": state.get("origins", [])}, ensure_ascii=False, indent=2), encoding="utf-8")
                log(f"会话已刷新落盘 -> {acc} ({len(keep)} 条)")

            log("窗口留 10 秒给您看，随后关闭")
            await nap(7, 11, "收尾")
        finally:
            await context.close()
    log("=== v2 结束（未扫码、未回复、未发布）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

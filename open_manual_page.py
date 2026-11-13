"""给老泡儿手动趟雷用：用已登录 cookie 打开真实可见的视频号发布页，并保持窗口不关。

只读打开，不做任何自动填表/自动点击/自动发表；老泡儿手动走一遍，看坎在哪儿。
"""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from patchright.async_api import async_playwright
from uploader.tencent_uploader.main import TENCENT_HOME_URL

BASE_DIR = Path(__file__).parent.resolve()
ACCOUNT_FILE = BASE_DIR / "cookies" / "tencent_creator.json"


async def main() -> None:
    print(f"使用登录态: {ACCOUNT_FILE}", flush=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context(storage_state=str(ACCOUNT_FILE), viewport={"width": 1440, "height": 1000})
        page = await context.new_page()
        await page.goto(TENCENT_HOME_URL, wait_until="domcontentloaded", timeout=120000)
        print("已打开视频号助手首页，窗口保持不关（Ctrl+C 或关窗口结束）", flush=True)
        # 保持进程存活，窗口交给老泡儿手动操作
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())

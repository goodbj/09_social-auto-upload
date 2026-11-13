"""从本机已登录的系统 Chrome 抽取视频号会话，导出成 storage_state 供 `sau tencent` 复用。

用法（Chrome 必须关闭，profile 不锁）：
    .venv/Scripts/python.exe extract_session.py

机制：
- 用系统 Chrome 的 exe（v20 App-Bound 密钥绑定到 chrome.exe，必须用真身）
  + 一份独立复制的 User Data profile（cookies/chrome_profile_tencent），
  起 persistent context；Chrome 自己解开 v20 加密的 cookie，零依赖、不碰真身。
- 打开视频号创作后台，确认已登录（不出现二维码 / 不跳 login.html），
  再把 storage_state 写进 cookies/tencent_creator.json。
- 之后 `sau tencent check --account creator` 直接读这个文件，不再扫码。

首次需先 `copy_chrome_profile.py` 把系统 profile 复制到 cookies/chrome_profile_tencent。
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from patchright.async_api import async_playwright

BASE_DIR = Path(__file__).parent.resolve()
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = BASE_DIR / "cookies" / "chrome_profile_tencent"
ACCOUNT_FILE = BASE_DIR / "cookies" / "tencent_creator.json"
RUN_LOG = BASE_DIR / "logs" / "extract_session.log"
TENCENT_HOST = "https://channels.weixin.qq.com/platform/post/list"


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line, flush=True)
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def main() -> None:
    for p in (CHROME_EXE, PROFILE_DIR):
        if not Path(p).exists():
            raise RuntimeError(f"缺失: {p}（先确认 Chrome 已关、且跑过 copy_chrome_profile.py）")

    log("=== 抽取视频号会话：用系统 Chrome + 独立 profile 起 persistent context ===")
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=CHROME_EXE,
            headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            log(f"打开视频号创作后台: {TENCENT_HOST}")
            await page.goto(TENCENT_HOST, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await page.wait_for_timeout(5000)

            jumped_login = "login.html" in page.url
            qr = any("open.weixin.qq.com/connect/qrconnect" in fr.url for fr in page.frames)
            if jumped_login or qr:
                raise RuntimeError("视频号未登录（跳登录页/出现二维码）——请先用系统 Chrome 登录视频号，再关 Chrome 重跑")

            log("已登录确认（无二维码、未跳登录页）；导出 storage_state …")
            state = await context.storage_state()
            # 只保留视频号相关域名，减小体积、避免无关 cookie 串味
            keep = [c for c in state.get("cookies", []) if "weixin.qq.com" in c.get("domain", "")]
            state["cookies"] = keep
            ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
            ACCOUNT_FILE.write_text(
                __import__("json").dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log(f"DONE 已导出 {len(keep)} 条视频号 cookie -> {ACCOUNT_FILE}")
            log("下一步：sau tencent check --account creator（应直接 valid，不再扫码）")
        finally:
            await context.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

"""一次性联调 v2：视频号扫码登录 + 立刻真发 11 部门 WF-01 样片。

v1 教训：
- CLI 分开跑 login/upload，中间会话漂移 + 旧 cookie_auth 假阳性 → 上传页被踢回登录页。
- v1 登录等 5 分钟没人扫就超时；且 tencent_setup 内部会再开一个浏览器做
  cookie_auth 二次校验，多一次新会话可能触发风控把刚登录的 session 顶掉。

v2 做法：自己控制登录流程，跳过二次校验，登录成功立刻 storage_state 落盘并
在同一进程内紧邻调用发布；等待窗口放宽到 20 分钟，二维码过期由库内逻辑刷新。
全过程日志落盘，中断后可核查是否真的发布过（防重复发）。
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from patchright.async_api import async_playwright
from uploader.tencent_uploader.main import (
    TENCENT_LOGIN_URL,
    TENCENT_PUBLISH_STRATEGY_IMMEDIATE,
    TencentVideo,
    _build_launch_kwargs,
    _save_tencent_qrcode,
    _wait_for_tencent_login,
    _get_qrcode_utils,
)
from utils.base_social_media import set_init_script

BASE_DIR = Path(__file__).parent.resolve()
ACCOUNT_FILE = BASE_DIR / "cookies" / "tencent_creator.json"
RUN_LOG = BASE_DIR / "logs" / "publish_wf01.log"
VIDEO_FILE = Path(r"E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\videos\youpick_35_linwan.mp4")
TITLE = "AI 生成的小短片看着还挺有意思"
DESC = (
    "用 AI 生成的短视频，画面和节奏都挺顺的，看着还挺解压。"
)
TAGS = ["AI视频", "短视频", "AI生成"]


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line, flush=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def main() -> None:
    assert VIDEO_FILE.is_file(), f"视频文件不存在: {VIDEO_FILE}"
    log("=== v2 启动 | 登录成功后立刻真发，无二次 cookie 校验 ===")
    log(f"STEP 1/3 打开登录页 | account={ACCOUNT_FILE} | video={VIDEO_FILE.name}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**_build_launch_kwargs(headless=False))
        context = await browser.new_context()
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto(TENCENT_LOGIN_URL, timeout=120000, wait_until="domcontentloaded")

        qrcode_utils = _get_qrcode_utils()
        qrcode_info = await _save_tencent_qrcode(page, str(ACCOUNT_FILE))
        qrcode_path = Path(qrcode_info["image_path"])
        log(f"STEP 1/3 二维码已生成（终端已打印）: {qrcode_path}")
        log("STEP 1/3 等待扫码（最多 20 分钟，二维码过期会自动刷新）")

        # 20 分钟等待窗口；不再调用 cookie_auth，避免多余新会话顶掉登录态
        result = await _wait_for_tencent_login(
            page, str(ACCOUNT_FILE), qrcode_info,
            poll_interval=3, max_checks=400,
        )
        qrcode_utils["remove_qrcode_file"](qrcode_path)
        log(f"STEP 1/3 登录结果: {result['status']} | {result['message']}")
        if not result["success"]:
            await browser.close()
            raise RuntimeError(f"登录未成功，未执行发布: {result['message']}")

        await asyncio.sleep(2)
        await context.storage_state(path=str(ACCOUNT_FILE))
        log("STEP 2/3 登录成功，cookie 已落盘；不关浏览器，立刻构造发布任务")
        await browser.close()

        app = TencentVideo(
            title=TITLE,
            file_path=str(VIDEO_FILE),
            tags=TAGS,
            publish_date=0,
            account_file=str(ACCOUNT_FILE),
            is_draft=False,
            desc=DESC,
            publish_strategy=TENCENT_PUBLISH_STRATEGY_IMMEDIATE,
            debug=True,
            headless=False,
        )
        log("STEP 3/3 开始发布（真发，非草稿）…")
        await app.tencent_upload_video()
        log("DONE 发布流程返回成功")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

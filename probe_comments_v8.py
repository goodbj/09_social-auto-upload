"""只读探路 v8：主动调 comment/comment_list 读小猫视频的留言（2026-11-13）。

老泡儿 2026-11-13 点头「继续调试留言和互动」→ 本脚本只读拉留言明细。
- 接口反编译自 wujie 微应用：POST .../micro/interaction/cgi-bin/mmfinderassistant-bin/comment/comment_list
  body: {"lastBuff":"","exportId":"<objectId>","commentSelection":false,"forMcn":false}
- 拟人节奏：每步 nap() 随机停，前台可见窗口，逐步输出，不黑箱。
- 严格只读：不回帖、不点赞、不删除、不置顶、不重放响应以外的任何写操作。
- 从浏览器页面上下文发 fetch（自带 cookie/Referer/Origin），等价真人点开看评论。
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from patchright.async_api import async_playwright
from utils.human_pace import nap, human_read

BASE_DIR = Path(__file__).parent.resolve()
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = BASE_DIR / "cookies" / "chrome_profile_tencent"
LOG_DIR = BASE_DIR / "logs"
OUT_DIR = BASE_DIR / "docs" / "probe_api_samples"
COMMENT_URL = "https://channels.weixin.qq.com/platform/interaction/comment"
EXPORT_ID = "export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw"  # 16:34 小猫
API = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment/comment_list"


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_comments_v8.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log("=== v8 只读读留言：随机节奏，不回帖 ===")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await nap(kind="navigate", label="打开评论页")
            await page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(kind="settle", label="等页面稳当")

            body = {
                "lastBuff": "",
                "exportId": EXPORT_ID,
                "commentSelection": False,
                "forMcn": False,
            }
            log(f"只读 POST comment_list | exportId={EXPORT_ID[:36]}… | body={json.dumps(body, ensure_ascii=False)}")
            await nap(kind="read", label="点开作品、翻到评论区")

            # 从页面上下文发 fetch：带上已登录 cookie / Referer / Origin，跟真人点开一致
            res = await page.evaluate(
                """async ({api, body}) => {
                    const r = await fetch(api, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        credentials: 'include',
                        body: JSON.stringify(body)
                    });
                    const t = await r.text();
                    return {status: r.status, ok: r.ok, body: t};
                }""",
                {"api": API, "body": body},
            )
            await nap(2, 5, "读完先缓一下")
            log(f"HTTP {res['status']} | 响应 {len(res['body'])} 字节")
            fn = OUT_DIR / "comment_list_read_01.json"
            fn.write_text(res["body"][:500000], encoding="utf-8")
            log(f"响应落盘 -> {fn}")

            try:
                d = json.loads(res["body"])
            except Exception:
                log(f"非 JSON，头 600 字: {res['body'][:600]}")
                return
            log(f"errCode={d.get('errCode')} errMsg={d.get('errMsg')}")
            data = d.get("data") or {}
            log(f"data 字段: {list(data.keys())}")
            comments = data.get("comment") or data.get("commentList") or []
            log(f"本页留言 {len(comments)} 条 | commentCount={data.get('commentCount')} | downContinueFlag={data.get('downContinueFlag')}")
            for i, c in enumerate(comments):
                log(f"--- 留言[{i}] 全字段 ---")
                log(json.dumps(c, ensure_ascii=False)[:1600])
                txt = c.get("commentContent") or c.get("content") or c.get("text") or ""
                await human_read(str(txt), label=f"默读留言[{i}]")
                await nap(0.8, 2.0, "看完一条歇口气")

            log("窗口留 8 秒给您看，随后关闭")
            await nap(5, 9, "收尾")
        finally:
            await context.close()
    log("=== v8 结束（全程只读：未回复/未点赞/未删除/未置顶）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

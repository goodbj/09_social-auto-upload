"""只读探路 v5：翻遍全部视频，找带 commentList 的样本（2026-11-13）。

v4 结论：post_list 一次 10 条，最近 10 条评论全 0；需翻页找历史有评论的作品，
才能验「留言文本 + 点赞数 + 回复框」结构。

做法：只读监听 post_list 响应并翻页（滚 iframe 或点更多），把所有响应体落盘，
汇总评论数非 0 的条目。绝不重放请求、绝不回帖、绝不发布。窗口可见，逐步输出。
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


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_comments_v5.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    posts = {}   # objectId -> post
    pages_seen = 0
    reqs = []    # 记录 post_list 请求的 post_data（只读，用于理解分页，不重放）

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()

            async def on_response(resp):
                nonlocal pages_seen
                if "post/post_list" not in resp.url:
                    return
                try:
                    body = await resp.text()
                except Exception:
                    return
                pages_seen += 1
                fn = OUT_DIR / f"post_list_v5_page{pages_seen:02d}.json"
                fn.write_text(body[:300000], encoding="utf-8")
                try:
                    d = json.loads(body)
                    lst = d.get("data", {}).get("list", [])
                    cf = d.get("data", {}).get("continueFlag")
                    log(f"[post_list#{pages_seen}] {len(lst)} 条 continueFlag={cf} -> {fn.name}")
                    for p in lst:
                        posts[p.get("objectId")] = p
                except Exception as exc:
                    log(f"[post_list#{pages_seen}] 解析失败 {exc}")

            page.on("response", on_response)

            def on_request(req):
                if "post/post_list" in req.url:
                    try:
                        reqs.append((req.url, req.post_data))
                    except Exception:
                        pass
            page.on("request", on_request)

            log(f"直达评论页: {COMMENT_URL}")
            await page.goto(COMMENT_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(5.6, 11.2, "页面停顿")

            # 尝试在评论 iframe 里滚动触发分页加载（只读滚动）
            cfr = next((f for f in page.frames if "micro/interaction/comment" in f.url), None)
            log(f"评论 iframe: {cfr.url if cfr else 'None'}")
            if cfr:
                for i in range(8):
                    await cfr.evaluate("() => { window.scrollTo(0, document.body.scrollHeight); const s=document.querySelector('[class*=scroll], [class*=list]'); if(s) s.scrollTop=s.scrollHeight; }")
                    await nap(1.75, 3.5, "页面停顿")
                    log(f"滚动 {i+1}/8 | 累计 post_list 次数={pages_seen} 累计视频={len(posts)}")

            log("=== 汇总 ===")
            log(f"共捕获 post_list 响应 {pages_seen} 次，去重视频 {len(posts)} 条")
            nonzero = [p for p in posts.values() if (p.get("commentCount") or 0) > 0 or (p.get("commentList") or [])]
            log(f"带评论的视频 {len(nonzero)} 条")
            for p in nonzero[:10]:
                ct = datetime.fromtimestamp(p.get("createTime", 0)).strftime("%Y-%m-%d") if p.get("createTime") else "?"
                log(f"  {ct} commentCount={p.get('commentCount')} objectId={str(p.get('objectId'))[:36]}")
                cl = p.get("commentList") or []
                for c in cl[:3]:
                    log(f"    comment 字段: {json.dumps(c, ensure_ascii=False)[:500]}")

            log("=== post_list 请求体（理解分页用，未重放）===")
            for u, pd in reqs[:6]:
                log(f"  URL={u[:140]}")
                log(f"  BODY={str(pd)[:600]}")

            log("窗口留 6 秒给您看，随后关闭")
            await nap(4.2, 8.4, "收尾停顿")
        finally:
            await context.close()
    log("=== v5 结束（全程只读：未发布/未回复/未删除/未点赞/未重放请求）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

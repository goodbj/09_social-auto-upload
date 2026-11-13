"""探「微信快捷登录」按钮：能不能一键免扫码恢复会话（2026-11-13）。

背景：v8 调 comment_list 返回 errCode=300334（会话过期），页面弹出扫码登录。
老泡儿拍板：「出现登录扫码了别急这关」「看看你能点击 微信快捷登录 这个按钮嘛」。

做法：可见窗口打开视频号 → 随机节奏 → 枚举登录页所有按钮/可点元素 →
找「微信快捷登录 / 快捷登录 / 微信登录」→ 点一下 → 观察 URL / 页面 / 是否免扫码成功。
不扫二维码、不等扫码超时；点击快捷登录是老泡儿明确授权的会话恢复动作。
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

QUICK_WORDS = ("快捷登录", "微信快捷", "微信登录", "一键登录", "快速登录")


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_quick_login.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def snap(page, tag: str) -> list[dict]:
    log(f"[{tag}] URL = {page.url}")
    for fr in page.frames:
        log(f"[{tag}] frame = {fr.url}")
    els = await page.evaluate("""() => {
        const sels='button,a,[role="button"],[class*="btn"],[class*="login"],[class*="quick"],input[type=button],input[type=submit],[onclick]';
        return Array.from(document.querySelectorAll(sels)).map(e=>{
            const r=e.getBoundingClientRect();
            return {tag:e.tagName.toLowerCase(),
                    t:(e.innerText||e.value||'').trim().replace(/\\s+/g,' ').slice(0,60),
                    cls:(e.className||'').toString().slice(0,70),
                    x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2),
                    w:Math.round(r.width),h:Math.round(r.height),
                    vis:r.width>0&&r.height>0};
        }).filter(o=>o.t||o.cls).slice(0,80);
    }""")
    for e in els:
        log(f"[{tag}] el = {json.dumps(e, ensure_ascii=False)}")
    body = await page.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,900)")
    log(f"[{tag}] body = {body}")
    shot = LOG_DIR / f"quick_login_{tag}.png"
    await page.screenshot(path=str(shot), full_page=False)
    log(f"[{tag}] 截图 = {shot}")
    return els


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log("=== 探微信快捷登录（不等扫码、不超时死磕）===")
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        # 外部协议（weixin://）可能弹确认框，统一接受
        context.on("page", lambda p: p.on("dialog", lambda d: asyncio.create_task(d.accept())))
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await nap(kind="navigate", label="打开视频号首页")
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await nap(kind="settle", label="等登录页稳当")

            els = await snap(page, "01_login_page")

            # 找「微信快捷登录」这类按钮（含 iframe 里的）
            hits = [e for e in els if any(w in e["t"] for w in QUICK_WORDS)]
            if not hits:
                for fr in page.frames:
                    if fr == page.main_frame:
                        continue
                    try:
                        sub = await fr.evaluate("""() => Array.from(document.querySelectorAll('button,a,[role="button"],[class*="btn"],[class*="login"]')).map(e=>{const r=e.getBoundingClientRect();return {t:(e.innerText||'').trim().slice(0,60),cls:(e.className||'').toString().slice(0,70),x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),w:Math.round(r.width),h:Math.round(r.height)};}).filter(o=>o.w>0&&o.h>0)""")
                        for e in sub:
                            log(f"[iframe el] {json.dumps(e, ensure_ascii=False)}")
                            if any(w in e.get("t", "") for w in QUICK_WORDS):
                                hits.append({**e, "frame": fr})
                    except Exception as exc:
                        log(f"[iframe] 读取失败 {type(exc).__name__}")

            if not hits:
                log("没找着「微信快捷登录」字样的按钮；把上面截图/DOM 给您核")
                await nap(3, 6, "留窗口给您看")
                return

            btn = hits[0]
            log(f"找着了：「{btn['t']}」 @ ({btn['x']},{btn['y']}) class={btn.get('cls','')}")
            await nap(kind="click", label="伸手去点快捷登录")
            # 用真实鼠标点（能触发外部协议 / 前端事件），不直接 evaluate click
            await page.mouse.click(btn["x"], btn["y"])
            await nap(3, 7, "点了之后看反应")

            log(f"点后 URL = {page.url}")
            log(f"点后页面数 = {len(context.pages)}")
            for i, p in enumerate(context.pages):
                log(f"  page[{i}] = {p.url}")
            await snap(page, "02_after_click")

            # 判据：URL 不再是 login.html / 出现后台菜单 = 免扫码登录成功
            logged = "login.html" not in page.url and "platform" in page.url
            log(f"免扫码登录成功? {logged}")
            if logged:
                state = await context.storage_state()
                keep = [c for c in state.get("cookies", []) if "weixin.qq.com" in c.get("domain", "")]
                import json as _json
                acc = BASE_DIR / "cookies" / "tencent_creator.json"
                acc.write_text(_json.dumps({"cookies": keep, "origins": state.get("origins", [])}, ensure_ascii=False, indent=2), encoding="utf-8")
                log(f"会话已刷新落盘 -> {acc} ({len(keep)} 条)")

            log("窗口留 12 秒给您看，随后关闭")
            await nap(8, 13, "收尾")
        finally:
            await context.close()
    log("=== 结束（未扫码、未回复、未发布）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

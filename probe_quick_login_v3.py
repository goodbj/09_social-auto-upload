"""微信快捷登录 v3：绕过 Playwright 可见性判定，在 iframe 上下文触发按钮 click（2026-11-13）。

v2 结论：按钮 <button class="weui-btn weui-btn_primary js_quick_login_btn qlogin_btn">微信快捷登录</button>
确实存在且截图里肉眼可见，但外层 qrconnect iframe 尺寸/挂载异常导致 Playwright 判
"element is not visible" 拒绝点击。

v3 做法：先 dump 按钮与 iframe 的尺寸/样式搞明白，再用 frame.evaluate 调 DOM 原生
btn.click()（与真人点走同一个前端处理函数），随后等跳转、核验登录态、刷新会话文件。
老泡儿明确授权点这颗按钮；不扫码、不等超时死磕、不回帖、不发布。
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
    with (LOG_DIR / "probe_quick_login_v3.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log("=== 微信快捷登录 v3：iframe 内触发原生 click ===")
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

            # 主文档里所有 iframe 的尺寸（看是不是 0×0 惹的祸）
            ifs = await page.evaluate("""() => Array.from(document.querySelectorAll('iframe')).map(e=>{const r=e.getBoundingClientRect();return {src:(e.getAttribute('src')||'').slice(0,110),w:Math.round(r.width),h:Math.round(r.height),disp:getComputedStyle(e).display,vis:getComputedStyle(e).visibility};})""")
            log(f"[iframes] {json.dumps(ifs, ensure_ascii=False)}")

            qfr = next((f for f in page.frames if "qrconnect" in f.url), None)
            if not qfr:
                log("没 qrconnect iframe（可能本来就在后台）")
                log(f"URL={page.url}")
                return

            # 按钮的几何/样式诊断
            diag = await qfr.evaluate("""() => {
                const b=document.querySelector('button.js_quick_login_btn') || document.querySelector('.qlogin_btn');
                if(!b) return null;
                const r=b.getBoundingClientRect(), cs=getComputedStyle(b);
                const p=b.closest('.qlogin_mod, .web_qrcode_panel_quick_login');
                const pr=p?p.getBoundingClientRect():null;
                return {text:b.innerText, cls:b.className,
                        rect:{x:r.x,y:r.y,w:r.width,h:r.height},
                        display:cs.display, visibility:cs.visibility, opacity:cs.opacity,
                        parent: p?{cls:p.className,rect:{x:pr.x,y:pr.y,w:pr.width,h:pr.height},display:getComputedStyle(p).display}:null,
                        iframeSize:{w:innerWidth,h:innerHeight}};
            }""")
            log(f"[btn diag] {json.dumps(diag, ensure_ascii=False)}")
            if not diag:
                log("按钮没挂上，收工")
                return

            await nap(kind="click", label="伸手点「微信快捷登录」")
            # 原生 DOM click：走前端绑定的同一处理函数，不受 Playwright 可见性判定影响
            fired = await qfr.evaluate("""() => {
                const b=document.querySelector('button.js_quick_login_btn') || document.querySelector('.qlogin_btn');
                if(!b) return 'no_button';
                b.click();
                return 'clicked';
            }""")
            log(f"原生 click 触发结果 = {fired}")
            await nap(3, 7, "点完看反应")

            log(f"点后 URL = {page.url}")
            try:
                await page.wait_for_url(lambda u: "login.html" not in u, timeout=25000)
                log(f"跳转成功 -> {page.url}")
            except Exception:
                log(f"25 秒内没跳出登录页，当前 URL={page.url}")
                # 也许开了新页
                for i, p in enumerate(context.pages):
                    log(f"  page[{i}] = {p.url}")
            await nap(kind="settle", label="登录后等页面稳当")

            body = await page.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,500)")
            log(f"页面文本 = {body}")
            logged = "login.html" not in page.url and "platform" in page.url
            log(f"免扫码登录成功? {logged}")
            await page.screenshot(path=str(LOG_DIR / "quick_login_v3_result.png"))

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
    log("=== v3 结束（未扫码、未回复、未发布）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

"""微信快捷登录 v4：浏览器触发 + 本机「允许」弹窗看门狗（2026-11-13）。

趟出来的全链条：
  会话过期 → login.html → qrconnect iframe 里「微信快捷登录」按钮
  → DOM 原生 btn.click() 拉起本机微信 → 系统级「允许」弹窗（不在 DOM，Playwright 够不着）
  → 点「允许」→ 免扫码跳回 platform 后台 → 刷新 storage_state。

v1~v3 的坑：
- v1 用 iframe 内部坐标在主页面 mouse.click → 点空。
- v2 frame_locator.click() → Playwright 判 "element is not visible"（iframe 208x208 但按钮 rect 0x0）。
- v3 原生 click 成功触发，但「允许」是系统级弹窗，浏览器脚本干等 25s 没跳。
- 另：mcp computer_state 连的是云盒子 XFCE，不是本机 Windows，不能用它点本机弹窗。

v4：一个进程里同时跑「浏览器触发」和「本机窗口看门狗」，
弹窗一冒出来（窗口标题/子控件含 允许/授权/登录/确认）就点掉；逾 40s 不死磕。
老泡儿明确授权点「微信快捷登录」及随之而来的「允许」；不扫码、不回帖、不发布。
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
ACC_FILE = BASE_DIR / "cookies" / "tencent_creator.json"

# 本机弹窗看门狗（PowerShell 脚本，独立进程；枚举窗口+子控件，命中就 BM_CLICK）
WATCHDOG_PS = r'''
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class UX {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
}
"@
$deadline = (Get-Date).AddSeconds(180)
$hitWords = @('允许','授权','确认登录','登录确认','确定','同意','Allow','OK')
while ((Get-Date) -lt $deadline) {
  try {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Window)
    $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
    foreach ($w in $wins) {
      $name = $w.Current.Name
      $proc = $w.Current.ProcessId
      # 只看微信/系统级弹窗，跳过 Chrome/资源管理器等大窗
      $btns = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)))
      foreach ($b in $btns) {
        $t = $b.Current.Name
        foreach ($k in $hitWords) {
          if ($t -like "*$k*") {
            Write-Host "WATCHDOG HIT: window='$name' button='$t' pid=$proc"
            try { [UX]::SetForegroundWindow([IntPtr]$w.Current.NativeWindowHandle) | Out-Null } catch {}
            try {
              $ip = $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
              $ip.Invoke()
              Write-Host "WATCHDOG CLICKED via InvokePattern"
            } catch {
              Write-Host "WATCHDOG Invoke failed, fallback SendMessage"
              [UX]::SendMessage([IntPtr]$b.Current.NativeWindowHandle, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
            }
            exit 0
          }
        }
      }
    }
  } catch {}
  Start-Sleep -Milliseconds 700
}
Write-Host "WATCHDOG TIMEOUT: no allow-button seen"
exit 1
'''


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    with (LOG_DIR / "probe_quick_login_v4.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")


async def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    wd_ps = LOG_DIR / "allow_watchdog.ps1"
    wd_ps.write_text(WATCHDOG_PS, encoding="utf-8")
    log("=== v4 快捷登录 + 本机「允许」看门狗 ===")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROME_EXE, headless=False,
            args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await nap(kind="navigate", label="打开视频号")
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=120000)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await nap(kind="settle", label="等快捷登录面板")

        qfr = next((f for f in page.frames if "qrconnect" in f.url), None)
        if not qfr:
            log(f"没 qrconnect（可能已在后台）URL={page.url} —— 窗口留着不关")
            await nap(60, 90, "保持窗口")
            return
        btn = await qfr.evaluate("""() => !!document.querySelector('button.js_quick_login_btn, .qlogin_btn')""")
        log(f"快捷登录按钮存在? {btn}")
        if not btn:
            log("按钮没挂上；窗口留着不关")
            await nap(60, 90, "保持窗口")
            return

        # 看门狗先起，再触发按钮；弹窗一冒就点
        log("启动本机「允许」看门狗（180s，页面不关，弹窗才不会消失）")
        wd = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wd_ps),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        await nap(kind="click", label="伸手点「微信快捷登录」")
        fired = await qfr.evaluate("""() => {const b=document.querySelector('button.js_quick_login_btn')||document.querySelector('.qlogin_btn'); if(!b)return 'no_button'; b.click(); return 'clicked';}""")
        log(f"原生 click = {fired}")

        # 等跳转（最多 90s）；期间浏览器窗口一直开着，看门狗独立在跑
        try:
            await page.wait_for_url(lambda u: "login.html" not in u, timeout=90000)
            log(f"跳转成功 -> {page.url}")
        except Exception:
            log(f"90s 内没跳出登录页 URL={page.url}")
        await nap(kind="settle", label="登录后稳一稳")
        logged = "login.html" not in page.url and "platform" in page.url
        log(f"免扫码登录成功? {logged} | URL={page.url}")
        await page.screenshot(path=str(LOG_DIR / "quick_login_v4_result.png"))

        if logged:
            state = await context.storage_state()
            keep = [c for c in state.get("cookies", []) if "weixin.qq.com" in c.get("domain", "")]
            ACC_FILE.write_text(json.dumps({"cookies": keep, "origins": state.get("origins", [])}, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"会话已刷新 -> {ACC_FILE} ({len(keep)} 条)")

        # 关键：无论成没成，**都不关浏览器**。登录页/弹窗得留着，关了「允许」就没了。
        # 看门狗也不 kill，让它继续盯到自己的 180s 自然收。
        log("窗口保持打开、看门狗继续盯；本脚本到此挂住不返回，绝不关 Chrome")
        # 关键：async_playwright() 上下文一退出就会连带关掉 Chrome，所以这里
        # 用 Event 原地挂住，保持 page/context/浏览器进程全活着，「允许」弹窗才不消失。
        # 看门狗 180s 内一逮到按钮就点；老泡儿收工时 Ctrl+C 或关窗口即可。
        await asyncio.Event().wait()
    log("=== v4 收工（浏览器窗口此前一直未关）===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise

---
name: tencent-quick-login
description: 视频号助手会话过期时，用「微信快捷登录」+ 本机「允许」弹窗免扫码恢复登录态；含 iframe/系统级弹窗的全部踩坑与特征码。Use when sau tencent check 失效、页面弹扫码、或需要零扫码恢复 channels.weixin.qq.com 会话。
license: MIT-0
slug: youpick-tencent-quick-login
displayName: 视频号免扫码恢复会话
version: 1.0.0
summary: 会话过期后点 qrconnect iframe 里的「微信快捷登录」，再点本机「允许」弹层，页面不关才能跳回后台。
---

# 视频号免扫码恢复会话（快捷登录）

**真源**：`E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\docs\closed-loop-decisions.md`
**验证**：2026-11-13 18:00:53 实测成功，`login.html → platform`，18:01:00 会话刷新落盘，全程零扫码。

## 什么时候用

- `sau tencent check --account creator` 失效；
- 调 `post_list` / `comment_list` 返回 **`errCode=300334 request failed`**（会话过期的硬信号，44 字节小响应）；
- 浏览器落到 `https://channels.weixin.qq.com/login.html` 并弹扫码页。

别急着重扫二维码。腾讯给已登录过微信的机器留了「微信快捷登录」，一键就能回来。

## 完整链路（一步都不能少）

```
会话过期 → login.html
  → qrconnect iframe 里出现账号卡「任世伟 丸小子」+「微信快捷登录」按钮
  → 在 iframe 上下文里调 DOM 原生 btn.click()（不是 Playwright click）
  → 拉起本机微信授权，弹出「视频号创作平台 申请使用 / 你的昵称、头像」弹层
  → 点绿按钮「允许」
  → Chrome 跳回 https://channels.weixin.qq.com/platform
  → storage_state() 刷新 cookies/tencent_creator.json
```

**铁律：从点「微信快捷登录」到点「允许」这段时间，那个 Chrome 页面绝对不能关。**
页面一关，授权弹层跟着一起消失（老泡儿 2026-11-13 原话：「你的 web 页面不能关，关了那个 允许 按钮也就消失了」）。

## 特征码（老泡儿 2026-11-13 抓的实物）

登录页 iframe：
```
https://open.weixin.qq.com/connect/qrconnect?appid=wx20d84d087938fd46
  &scope=snsapi_login&redirect_uri=.../platform/oauth-callback.html
  &login_type=jssdk&self_redirect=true
```
iframe 尺寸只有 **208×208**，账号卡叠在里面。

快捷登录按钮（**必须按这个定位**）：
```html
<button class="weui-btn weui-btn_primary js_quick_login_btn qlogin_btn"
        type="button">微信快捷登录</button>
```
同层还有：`div.qlogin_mod`、`div.web_qrcode_panel_quick_login`、
`a.js_switchToNormal.web_qrcode_switch`（「使用其他头像、昵称或账号」）。

本机「允许」弹层（**不是网页 DOM 里的标准按钮**，是 Chrome 窗口里的自绘层）：
```
视频号创作平台 申请使用
你的昵称、头像
[头像] 任世伟 丸小子
[ 允许(绿) ]  [ 拒绝 ]
```

## 趟过的坑（照单全收，别再踩）

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | **v20 App-Bound cookie 硬解** | DPAPI `CryptUnprotectData` 返回空；`app_bound_encrypted_key` 前缀是 `APPB\x01\x00` 不是 `APP_B` | 别解了。用系统 `chrome.exe` + 复制的 profile 起 persistent context，Chrome 自己解开 |
| 2 | **profile 路径是 junction** | `C:\Users\Administrator\AppData\Local\Google\Chrome\User Data` 真身在 `D:\Chrome\User Data` | 两处同一份，指哪个都行；复制 Default 到独立目录，别碰真身 |
| 3 | **venv 没 pip** | `python -m pip` 报 No module named pip | 别装 cryptography，改走系统 Chrome 路线 |
| 4 | **iframe 坐标当主页面坐标** | v1 用 `page.mouse.click(104,93)` 点面板中心，URL 纹丝不动 | 那是 iframe 内部坐标；用 frame 定位器或 iframe 内 evaluate |
| 5 | **Playwright 判 element is not visible** | v2 `frame_locator(...).click()` 超时 15s：按钮 `rect=0×0`，父 `.qlogin_mod` 也 0×0，虽 `visibility:visible` 但框架不肯点 | 改用 **iframe 内 DOM 原生 `btn.click()`**，绕开可见性判定，走的还是同一个前端处理函数 |
| 6 | **「允许」是系统/窗口级弹层** | v3 原生 click 触发成功、干等 25s 不跳；Playwright 够不着，UIAutomation 按顶层 Window 扫 Button 也扫不到 | 得用**本机 Windows 桌面坐标点**（GDI 截屏换算 + `SetCursorPos`/`mouse_event`），或截图后人工点 |
| 7 | **context.close() 把弹窗连根拔** | v1~v3 都在 `finally` 里关浏览器，「允许」还没点就没了 | 登录未成功绝不关窗口；`async_playwright()` 上下文退出也会带关 Chrome，用 `await asyncio.Event().wait()` 原地挂住 |
| 8 | **云盒子不是本机** | `mcp__plugin_box_box__computer_state` 连的是 XFCE 云桌面（还开着 instagram 429），点不到您眼前的 Windows 弹窗 | 本机 GUI 动作用 PowerShell + Win32 API / UIAutomation，别用 box |
| 9 | **截图坐标换算** | 3360×1080 原图显示成 2000 宽，直接点会偏 | 乘 **1.68**：显示 (330,260) → 原图 (554,437) |
| 10 | **评论微应用 wujie 空白** | 直开 `/platform/interaction/comment`，iframe `bodyLen=0`、`<div id=app>` 不存在、真 iframe 是 `empty.html` 0×0 | 微应用靠主应用 wujie 挂载（`__POWERED_BY_WUJIE__`）；但接口不依赖 UI，直接调 CGI 更稳 |
| 11 | **固定等待像机器人** | 一口气跑完，风控风险 | 全走 `utils/human_pace.py` 的 `nap()` 随机停顿，见 [[拟人互动节奏]] |
| 12 | **同一 profile 被两个进程占** | 授权用的常驻 Chrome 没关，新脚本 `launch_persistent_context` 报「正在现有的浏览器会话中打开」→ `TargetClosedError` | 授权期间页面**必须留着**；一旦跳回 platform、会话落盘，立刻收掉常驻脚本/看门狗/那个 Chrome，再跑后续脚本 |
| 13 | **comment_list 字段名 + 状态码** | `errCode=0` 但按 `content`/`likeCount` 取全是空、`human_read` 显示「看 0 字」；且返回 **HTTP 201** 不是 200 | 真字段是 **`commentContent` / `commentLikeCount` / `commentId` / `commentNickname`**；别把 201 当失败 |
| 14 | **账号自己给自己留言** | 「丸小子998」那条混在留言里，差点自己回自己 | 比对 `username` 与 `auth_data.finderUsername`，相同即跳过 |
| 15 | **重复点赞会取消赞** | `like_comment(scene=1)` 对着已点过的留言再发一遍，实际走 UNLIKE | 先读 `comment_list` 看 `likeFlag`，为 1 就跳过；`commentLikeCount` 是总赞数，不能拿来判本号是否已点 |
| 16 | **L2 回复挂错层** | `rootCommentId` 填成 L2 自己的 id，或回在咱自己那条 L2 底下，成了自己跟自己聊 | `rootCommentId` 永远指顶层；先用 `username` 把主号自己的 L2 剔掉 |

### 顺带验通：读留言（`comment/comment_list`）

会话新鲜时，页面上下文里 `fetch` 这个只读接口即可，不必依赖 wujie 微应用渲染：

```
POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/comment_list
{"lastBuff":"","exportId":"<objectId>","commentSelection":false,"forMcn":false}
→ HTTP 201 / errCode=0 / data.comment[6] / commentCount=6
```

实测 2026-11-13 18:05：小猫那条 6 条留言全读到，点赞全 0（故筛选必须按内容潜力，不按赞）。

### 顺带验通：点赞（`comment/like_comment`）

反编译 `chunk_251.txt` / `chunk_512.txt`：
```
async likeComment(e, t) → service.likeComment({
  commentId: e.commentId, scene: t, exportId: this.currentExportId })
枚举：LIKE=1 / UNLIKE=2 / UNRECOGNIZED=-1
POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/like_comment
{"commentId":"<commentId>", "scene":1, "exportId":"<objectId>"}
→ HTTP 201 / errCode=0（响应只有 77B）
```
- 顶层留言和 **L2 楼中楼都能点**，都按 `commentId` 传，别另加层级字段。
- 写之前先读 `comment_list`：`likeFlag==1` 就是本号已点过，再点一次是 **UNLIKE 语义**（`scene=2`），会取消赞，务必跳过。
- 只跳过 `likeFlag==1` 不够，`commentLikeCount` 是总赞数（别人点的也算），别拿它判重。

### 顺带验通：2 级回复 / 楼中楼（`create_comment` 回在 L2 底下）

```
POST .../comment/create_comment
{"exportId":"<objectId>",
 "replyCommentId":"<被回的那条 L2 的 commentId>",
 "rootCommentId":"<顶层留言的 commentId>",     ← 关键：必须指回顶层，不是 L2 自己
 "content":"<回复>", "clientId":"<uuid>",
 "comment":{ <被回的 L2 对象> }}                 ← 前端拿它填 replyNickname / replyContent
```
- `comment_list` 返回的 `levelTwoComment[]` 里每条自带 `replyCommentId`；回它时把它自己的 `commentId` 当 `replyCommentId`，把所在顶层的 `commentId` 当 `rootCommentId`。
- **别自己回自己**：先用 `username == auth_data.finderUsername` 把主号自己的 L2 剔出去。
- 回完必须回读 `comment_list` 看新回复是否挂在 `levelTwoComment` 下，光看 `errCode=0` 不算验收。

### 顺带验通：真回一条（`comment/create_comment`，18:14）

参数（反编译 chunk_251 / chunk_512）：
```
POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/create_comment
{"exportId":"<objectId>", "replyCommentId":"<目标commentId>",
 "rootCommentId":"<顶层commentId，顶层回复时同 replyCommentId>",
 "content":"<回复>", "clientId":"<uuid>", "comment":{<原留言对象>}}
→ HTTP 201 / errCode=0 / data.comment{commentId, replyCommentId, replyContent}
```
- 只回一条、硬编码 id、`--approved` 才发、默认 dry_run、不重试不群回（`reply_one.py`）。
- 发完**必须回读 `comment_list`** 硬核验（本次命中 1 处），别把命令退出码当发布成功。
- 业务闸：草稿人工过审、胡同串子口气、每日上限、防重复 id、拟人随机节奏，全在 `utils/human_pace.py`。

## 可直接复用的脚本

| 脚本（磁盘绝对路径） | 干嘛 |
|---|---|
| `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\probe_quick_login_v4.py` | **正解**：常驻不关页面 + 看门狗 + 原生 click + 会话刷新 |
| `...\probe_quick_login.py` / `_v2.py` / `_v3.py` | 反例留痕（坐标点空 / 可见性超时 / 没点系统弹窗） |
| `...\logs\allow_watchdog.ps1` | 本机「允许」按钮看门狗（UIAutomation InvokePattern，180s） |
| `...\logs\desktop_v4_now.png` / `desktop_v4_after_allow.png` | 弹层现场 / 点完跳回后台的实证 |
| `...\extract_session.py` | 会话还有效时，从系统 Chrome 抽 storage_state |
| `...\utils\human_pace.py` | 拟人节奏单一真源 |

## 标准操作（照抄）

1. 前台跑 `probe_quick_login_v4.py`（**后台常驻**，它会挂住不返回，页面一直留着）。
2. 脚本自己找 `button.js_quick_login_btn` 并 `btn.click()`。
3. 本机弹出「视频号创作平台 申请使用」→ 点绿「允许」：
   - 优先让看门狗 `allow_watchdog.ps1` 自动点；
   - 看门狗没逮着（自绘控件不暴露成 Button），就 GDI 截屏 → 换算坐标 → `Mouse.Click(554,437)` 这类本机点击。
4. 日志出现 `跳转成功 -> .../platform` 且 `免扫码登录成功? True` = 齐活；
   `cookies/tencent_creator.json` 自动刷新（本次 2 条 cookie）。
5. 复核 `sau tencent check --account creator` → `valid`，再继续读留言/发布。

## 红线

- 调试阶段**前台可见窗口、逐步输出、随机休眠**，不黑箱。
- 会话恢复只点「微信快捷登录 / 允许」，**不扫码、不回帖、不发布、不删东西**；真发/真回须老泡儿单独点头。
- 本地改动未提交、未 push，提交须批准。
- 腾讯每日留言上限约 200（老泡儿口述，未经平台核实，保守取用）；号有历史限流记录，互动宁慢勿猛。

## 相关

- [[tencent-upload]] — 发布链路技能
- `docs/manual-publish-findings.md` — 发布趟雷留痕
- `docs/closed-loop-decisions.md` — 闭环决策与全部技术底子

# 视频号互动短剧闭环 · 决策与技术留痕（2026-11-13）

> 老泡儿在本轮对话交代「全局计划」并拍板若干决策；本文档为**立项前**的趟路留痕真源。
> 规矩：先在这儿把闭环六步全趟通，再建 A 级 Issue 立项（老泡儿 2026-11-13 定）。
> 全程调试阶段：前台可见窗口、逐步输出、不黑箱跑；对外发送（发布/回帖）须单独点头。

## 一、全局计划（老泡儿原意，全部由各部门 AI 完成）

A 阶段：初期剧情由老泡儿与 09 探讨起好头；留言不多时先出几集作引子。
B 阶段：后续剧情编写 + 互动留言由各集团部门配合完成。

六步闭环：
1. 视频部（11_ImageGen）设置基础剧情、制作视频短剧
2. 提交 09 发布到视频号
3. 09 派客服与留言网友互动
4. 互动后按网友提议/建议，或找高赞留言，经润色产生新剧情
5. 交视频部制作新视频剧情
6. 回到第 1 步，形成「短剧随网友互动发展」的闭环

## 二、老泡儿本轮拍板的决策（真源）

| # | 议题 | 拍板 |
|---|---|---|
| 1 | 起头 IP 用谁 | **不是一个号的问题，想起几个号一起搞**；先不考虑 IP，先把闭环打通 |
| 2 | 互动人设 | **北京胡同串子口气**交流互动（不用官方客服腔） |
| 3 | 互动量 | 腾讯每天留言上限约 **200 条**；**挑有价值的回，别是个留言都回** |
| 4 | 剧情筛选 | 听劝：不纯按高赞；**每轮搜集几条话题候选 → 老泡儿拍板 → 再实施**；要「最有未来潜力的后续剧情」，不是最能起哄的 |
| 5 | 养号节奏 | 听 09 的：A 阶段先铺 3~5 集引子、埋互动钩子、前期回复人过一遍再发 |
| 6 | 当前优先级 | **首要趟通「留言读取 + 互动」**；这步通了再做「模拟人动作防风控」计划 |

## 三、闭环能力状态（截至 2026-11-13 17:03）

| 环节 | 状态 | 验收项 / 备注 |
|---|---|---|
| 1 视频部出片 | 半通 | 单条转码+出片已验（WF-01、linwan、LocModel 小猫海上跑）；「按剧情连续出集」+ 09↔11 跨部门派活未验 |
| 2 09 发布 | ✅ 通 | 零扫码端到端真发成功（2026-11-13 16:34:22「小猫在海上跑得挺欢」） |
| 3 读留言 + 互动 | ✅ 通 | `post_list` 作品/计数 + `comment_list` 读 6 条留言（18:05）+ **`create_comment` 真回一条并回读核验（18:14/18:16）** 全链路实测通过；拟人节奏、草稿过审、单日闸生效 |
| 4 候选话题润色 | ✅ 通 | 6 条点赞全 0 → 按「内容潜力/提问/具体」挑，不按赞；候选交老泡儿拍板；胡同串子草稿已过审并发出一条 |
| 5 交视频部做新集 | 未验 | 派工单格式、回执、产物落盘 |
| 6 闭环调度 | 未验 | 轮次状态落库：防重发、防重复回帖 |

## 四、已趟通的技术底子

### 零扫码发布（本轮最大成果）
- 系统 Chrome `C:\Program Files\Google\Chrome\Application\chrome.exe`；真身 profile 在 `D:\Chrome\User Data`（`C:\Users\Administrator\AppData\Local\Google\Chrome\User Data` 是它的 junction）。
- 独立副本：`cookies/chrome_profile_tencent`（从 Default 复制 1.34GB，不动真身）。
- `extract_session.py`：用系统 Chrome + 独立 profile 起 persistent context，Chrome 自己解 v20 App-Bound cookie，导出 storage_state 到 `cookies/tencent_creator.json`。
- `uploader/tencent_uploader/main.py` 新增 `tencent_session_refresh()`：`tencent_setup()` 在 cookie 失效时优先零扫码重抽，失败才退回扫码。
- 验证：`sau tencent check --account creator` → valid；发布全程无二维码。

### 会话过期 → 微信快捷登录免扫码（2026-11-13 18:00 实测通过）
- 触发信号：调 `comment_list` 返回 **`errCode=300334 request failed`**（44 字节），页面落 `login.html` 弹扫码。
- **别重扫码**：qrconnect iframe 里有「微信快捷登录」按钮
  `<button class="weui-btn weui-btn_primary js_quick_login_btn qlogin_btn">微信快捷登录</button>`，
  iframe 内调 DOM 原生 `btn.click()` 拉起本机微信授权。
- 随后弹**系统/窗口级「允许」层**（「视频号创作平台 申请使用 / 任世伟 丸小子 / 允许 / 拒绝」），
  不在网页 DOM、UIAutomation 也未必当 Button 暴露；本机 GDI 截屏换算坐标点绿按钮。
- **铁律（老泡儿原话）**：「你的 web 页面不能关，关了那个 允许 按钮也就消失了」——
  从点快捷登录到点允许，Chrome 页面必须一直开着；`async_playwright()` 退出也会带关窗口，用 Event 挂住。
- 实测：18:00:53 `login.html → platform`，18:01:00 会话刷新写回 `cookies/tencent_creator.json`（2 条），**零扫码**。
- 全部 11 个坑（v20 解密、junction、iframe 坐标、可见性误判、系统弹窗、context.close、云盒子连错机器、坐标换算、wujie 空白…）
  已写成技能：`skills/tencent-quick-login/SKILL.md`；正解脚本 `probe_quick_login_v4.py` + `logs/allow_watchdog.ps1`。

### 评论管理入口与接口（只读探路 v1~v7，2026-11-13 17:12 更新）
- 左侧是**纯图标折叠栏**：第 3 个气泡图标 hover 展开「互动管理 → 评论 / 弹幕 / 私信」。
- 评论页 URL：`https://channels.weixin.qq.com/platform/interaction/comment`（SPA 软跳转）。
- 内容是 **wujie 微前端**：`micro/interaction/comment` 壳子 `<div id="app">` 靠 `index.f6549fa6.js` + 10 个异步 chunk 挂载，
  且 `index.js` 判 `window.__POWERED_BY_WUJIE__`——**必须由主应用用 wujie 挂进 iframe 才 bootstrap**；
  直开 URL / 空 iframe（`src=empty.html`, 0×0）挂载不上，故前几次 iframe body 全空。这是渲染空白的根因，不是代码写错。
- 关键接口（只读监听 + 反编译 JS bundle 所得）：
  - `POST /micro/interaction/cgi-bin/mmfinderassistant-bin/post/post_list` ← 视频列表（已抓到响应）
    - 请求体：`{"pageSize":10,"onlyUnread":false,"needAllCommentCount":true,"lastBuff":"","timestamp":"...","scene":7,"reqScene":7}`
    - 响应：`data.list[]`（每条含 `objectId`/`exportId`、`desc`、`createTime`、`likeCount`、`commentCount`、`readCount`、`forwardCount`）、`totalCount`、`continueFlag`、`lastBuff`（翻页用）
    - **实测**：`commentCount` 真实返回（今儿小猫=1），但 `commentList` 内嵌为空 → 留言明细另起接口拉
  - 评论微应用路由表（chunk_512.txt，全部 `POST` + `data`，基址 `/micro/interaction/cgi-bin/mmfinderassistant-bin`）：
    ```
    /comment/comment_list      ← 读留言列表（第3步命门）
    /comment/create_comment    ← 发回复
    /comment/like_comment      ← 给留言点赞
    /comment/get_feed_detail   ← 作品评论详情
    /comment/feed_list
    /comment/set_top_comment   ← 置顶
    /comment/del_comment       ← 删除
    /comment/block_user        ← 拉黑
    /comment/update_comment / update_feed_comment / mcn_comment_list 等
    ```
  - `comment_list` 参数（从 chunk 反编译）：
    ```
    {"lastBuff":"", "exportId":"<objectId>", "commentSelection":false, "forMcn":false}
    ```
    `commentSelection:true` 筛「精选评论」；`rootCommentId` 拉楼中楼；响应含 `comment[]`、`commentCount`、`lastBuff`、`downContinueFlag`。
  - bundle 里还翻出「热评/精选」标记：`FinderCommentDisplayFlag_Hot_Desc`、`FinderComment_Selection`、`ExcellentCommentAction`
    —— 正好对上老泡儿「挑有价值的、不纯按高赞」的筛选需求。
- 账号实测：`post_list` 一次 10 条、`totalCount=76`；最近作品小猫 16:34 已有 `commentCount=1`（真留言）、播放 43、转发 3。
- ⚠️ **2026-11-13 18:05 已主动验通**：会话恢复后 `comment_list` 返回 `HTTP 201 / errCode=0`，
  小猫那条实读 **6 条留言**。响应 `data.comment[]` 字段：
  `commentId` / `commentNickname` / **`commentContent`**（不是 content/text）/ **`commentLikeCount`** /
  `commentCreatetime` / `readFlag` / `displayFlag` / `levelTwoComment[]` / `username`（自己人用它判重）。
  分页：`lastBuff` / `downContinueFlag` / `commentCount`。
  6 条点赞全 0 → 印证「不按赞挑、按内容潜力挑」；其中「丸小子998」那条 `username` 与 finderUser 相同 = 账号自己，禁止自回。
  样本落盘：`docs/probe_api_samples/comment_list_read_01.json`。
- 另一个坑：授权用的常驻 Chrome 占着同一 `user-data-dir` 没关时，新脚本再 `launch_persistent_context` 会报
  「正在现有的浏览器会话中打开」→ `TargetClosedError`；授权完成、会话落盘后须收掉那个窗口才能重跑。

### 真回一条（2026-11-13 18:14，老泡儿点头「发」）

`create_comment` 参数从 `chunk_251.txt` / `chunk_512.txt` 反编译所得：
```
POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/create_comment
{
  "exportId": "<视频 objectId>",
  "replyCommentId": "<要回的 commentId>",
  "rootCommentId": "<顶层留言 commentId；顶层回复时与 replyCommentId 相同>",
  "content": "<回复文本>",
  "clientId": "<uuid>",
  "comment": { <原留言对象，前端拿它填 replyNickname> }
}
→ HTTP 201 / errCode=0 / data.comment{commentId, replyCommentId, replyContent, ...}
```
- 目标：「对方正在输入中...」`15053885978871339652`「我擦，水上漂，这猫怎么不掉海里去」
- 草稿（胡同串子，老泡儿过目）：「嗬，您这话说的——这猫脚底下踩着玻璃栈道呢，海看着深，其实它一溜烟就飘过去了。下回让它碰见只海鸥，您说它搭不搭伴儿？」
- 18:14:07 发出，新 `commentId=15053901028126166689`；18:16:03 **回读 `comment_list` 命中 1 处**（硬核验，非仅看命令退出码）。
- `reply_one.py`：硬编码单条 id、`--approved` 才发、默认 dry_run、只此一次不重试不群回、`HumanSession` 记 1/200。
- 产物：`docs/probe_api_samples/reply_one_{draft,request,response,verify}.json`、日志 `logs/reply_one.log`。
- ⚠️ **验收真相（老泡儿 2026-11-13 收通知后说明）**：这条「对方正在输入中...」的留言是**老泡儿小号发的验收留言**，不是自然流量；
  老泡儿小号确实收到了回复通知，端到端闭环（留言→筛选→回复→送达）确认成功。
  **后续做数据分析/挑剧情候选时须把它标为「自测样本」剔除**，别把「玻璃栈道 / 海鸥」当成真网友共识去拍下一集；
  引子期互动数据要标清来源，否则第 4 步「按潜力挑」容易被自己埋的钩子带跑偏。
  注：该小号 `username` 与主号 `finderUsername` 不同，故「禁止自回」闸未误伤，逻辑正确。

### 点赞 + 2级回复（2026-11-13 18:40 起，老泡儿：「这些都是亲友，挨个点一遍赞 / 挨个都回复」）

老泡儿追加说明：这一拨留言**都是亲友**，不是自然流量；小号又在咱那条 L2 底下回了「哼哼哼，我不信」，
要求「继续在我小号的下面做二级回复」。故本轮按「亲友批量」放行（不再按引子期保守筛法只挑一条）。

接口参数（反编译 `chunk_251.txt` / `chunk_512.txt` 所得）：
```
POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/like_comment
{"commentId":"<commentId>", "scene":1, "exportId":"<objectId>"}     # LIKE=1 / UNLIKE=2
→ HTTP 201 / errCode=0（响应约 77B）；顶层与 L2 都能点，按 commentId 传即可

POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/create_comment
{"exportId":"<objectId>", "replyCommentId":"<被回 L2 的 commentId>",
 "rootCommentId":"<顶层 commentId>", "content":"<回复>", "clientId":"<uuid>",
 "comment":{<被回 L2 对象>}}
→ 回复挂在顶层的 levelTwoComment[] 下，不再是新的顶层
```
- 判重硬信号：`comment_list` 里的 **`likeFlag=1`** 表示本号已点过赞，再发 `scene=1` 会走 UNLIKE 取消赞；
  `commentLikeCount` 是总赞数（含别人点的），**不能**拿来判本号是否已点。
- 防自己回自己：主号自己的顶层/L2 用 `username == auth_data.finderUsername` 剔掉；咱刚发的那条 L2 也不回本身。
- 本轮计划 6 赞 + 6 回复（含小号 L2 楼中楼一条），`--approved` 才真发；每条之间 `between_replies` 随机歇 35~120s。
- 脚本：`reply_batch_0413.py`；逐条日志 `logs/reply_batch_0413.log`；响应样本 `docs/probe_api_samples/batch_reply_*.json`、
  回读样本 `docs/probe_api_samples/batch_verify.json`。
- ⚠️ 这批是亲友/自测互动，第 4 步「挑剧情候选」时仍须标清来源，别把「玻璃栈道 / 海鸥 / 灯塔」当自然流量共识。

### 账号现状（2026-11-13 16:58 后台快照）
- 账号「丸小子998」，视频 87、关注者 46；昨日新增评论 0、新增播放 7。
- 今儿 16:34 那条小猫：播放 10、点赞 0、评论 0 —— 引子期确实还没留言，印证 A 阶段判断。
- ⚠️ 通知里有「**1 条视频被暂时限制传播**」（2025-12-23）——**该号有历史限流记录**，自动化互动必须收着，前期宁慢勿猛。
- 平台已自动给 AI 生成内容打「含 AI 生成内容」标（合规，不用管）。

## 五、风控 / 拟人节奏（老泡儿 2026-11-13 追加拍板：别刷刷一口气全干完）

**新增硬要求**：所有浏览器操作之间必须**随机睡眠**，模拟正常人在跟粉丝互动，不能像脚本流水线。
已落地为 `utils/human_pace.py`（单一真源），要点：

- `nap(kind=...)`：导航 2.5~6s、页面沉淀 3~8s、滚动 1.2~3.5s、点击 0.8~2.5s；
  8% 概率「走神」再加 4~12s。每次实际停多少秒都打印 + 落 `logs/human_pace.log`，不黑箱。
- `human_read()`：按留言字数算阅读时间，人得先看完才回。
- `human_type()`：逐字敲、随机按键间隔、标点处偶尔犹豫，**不整段粘贴**。
- `nap("between_replies")`：两条回复之间 35~120s；`session_break`：会话间 3~10 分钟。
- `HumanSession`：每次上线**随机只干 3~7 件**就歇；单日上限默认 200（数值为老泡儿口述，未经平台核实，保守取用）；
  活跃时段 9~22 点（夜里不操作）；`replied_ids` 落盘防重复回帖。
- `pick_valuable()`：**不按点赞排序**，挑「有剧情潜力/在提问/写得具体」的候选，**原样交老泡儿拍板**；
   spam 词直接过滤；99 赞的「哈哈哈哈」只标「仅参考，不当排序依据」。
- `build_reply_draft()`：北京胡同串子口气，随机起句去模板化；草稿一律 `needs_human_review=True`。
- **三道发送闸**：`SEND_ENABLED` / `approved` / `dry_run`，缺一不点发送；
  `human_reply()` 默认 dry_run=True，前期「AI 起草 → 人过一遍 → 发」。
- 所有 `probe_comments*.py` 的固定 `wait_for_timeout` / `asyncio.sleep` 已全换成 `nap()`，
  7 个脚本编译通过、残留固定等待 = 0。
- 本地演练（`.venv/Scripts/python.exe utils/human_pace.py`，scale=0.05 不联网）已跑通：
  候选筛选、胡同串子草稿、逐字演练、收工长歇全部正常，返回 `draft_only`，**绝没发送**。

已知硬约束：
- 每天回复上限约 200 条 → 必须有**筛选**，只回高价值留言。
- 号有历史限流 → 前期「AI 起草 → 人过一遍 → 发」，别一上来全自动群回。
- 模拟人动作防风控：✅ 独立计划已成文 `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\docs\human-like-anti-risk-plan.md`
  （五层闸门 / 节奏硬指标 / 量与时段 / 文案身份 / 动作清单 / 监控刹车 / P1~P3 欠账；口径是「把 AI 收成人样」，不碰验证码绕过与设备指纹）。
  待补：留言快照 `source_tag`（亲友自测 / 引子钩子 / 自然流量）、`DAILY_SOFT_CAP` 软上限。
- 内容合规：文案不带「测试/自动/验证/联调」等字样；AI 内容打标。

## 六、探路脚本与产物（磁盘绝对路径）

- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\utils\human_pace.py` — **拟人节奏层单一真源**（随机休眠/逐字打字/候选筛选/三道发送闸/会话状态）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\logs\human_pace.log` — 每次随机停顿留痕
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\logs\human_session_state.json` — 单日回复计数 / 已回 id（防重复）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\extract_session.py` — 零扫码会话抽取
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\probe_comments.py` — v1 只读勘察（失败：折叠菜单隐藏容器）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\probe_comments_v2.py` — v2 hover 图标进评论页（成功）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\probe_comments_v3.py` — v3 钻 iframe + 监听接口（部分）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\probe_comments_v4.py` — v4 抓 post_list 响应体（成功，45KB）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\probe_comments_v5.py` — v5 翻页/请求体分析（发现 3 条带评论作品）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\probe_comments_v6.py` — v6 点带评论作品（iframe 挂载不上，未成）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\probe_comments_v7.py` — v7 诊断空白根因（wujie / 空 iframe）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\docs\probe_api_samples\` — 各接口响应体 + wujie chunk 反编译文本
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\logs\probe_comments*.log` / `probe_v2_*.png` / `probe_v3_comment.png` / `probe_v4_*.png` / `probe_v6_*.png` / `probe_v7.png`
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\docs\manual-publish-findings.md` — 发布趟雷留痕
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\docs\human-like-anti-risk-plan.md` — **模拟人动作防风控计划（成文）**
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\skills\tencent-quick-login\SKILL.md` — 免扫码会话 + 读留言 / 回复 / 点赞 / 楼中楼全部接口参数与 16 个坑
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\reply_one.py` — 单条真回（18:14 验通）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\reply_batch_0413.py` — 亲友批 6 赞 + 6 回复（含小号 L2 楼中楼）
- `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\skills\tencent-upload\SKILL.md` — 发布技能

## 七、待办（不立项，继续在这儿趟）

1. ~~**首要**：只读调 `comment/comment_list` 验留言结构~~ ✅ 已验（18:05 六条；18:33 九条含 L2）。
2. ~~摸清 `create_comment` 发送链路~~ ✅ 已验（18:14 顶层回复；18:40 起 2 级楼中楼）。
3. ~~`like_comment` 点赞~~ ✅ 参数已抠、判重信号 `likeFlag` 已写明；批量真发与回读核验进行中（`reply_batch_0413.py`）。
4. **当下**：等本批 `--approved` 跑完 → 回读核验 6 赞 / 6 回复 → 把实测结果补进本文档与 `skills/tencent-quick-login/SKILL.md`。
5. 制定模拟人动作防风控计划（**成文**）——✅ 已落 `docs/human-like-anti-risk-plan.md`；欠账只剩 `source_tag` 与 `DAILY_SOFT_CAP` 两个待补项。
6. 出「候选话题搜集 → 拍板」的数据格式（几条候选、含点赞数/潜力标记/**来源标签**：亲友自测样本必须标出，别当自然流量）。
7. 09↔11 跨部门派活链路（剧情工单格式、回执）。
8. 全部趟通后再建 A 级 Issue 挂「部门-09」标签立项。

## 八、红线

- 调试阶段不黑箱：前台可见窗口、逐步输出、随机休眠。
- 对外发送（发布视频 / 回复网友 / **点赞** / 删除 / 置顶）须老泡儿单独点头；只读勘察不在此列。
- 本地改动未提交、未 push；提交须老泡儿批准。

# 视频号发布 · 手动趟雷留痕（2026-11-13）

> 背景：09_00 用 `social-auto-upload`（`sau tencent`）真发 11 部门 ComfyUI WF-01 样片时，自动流程卡在上传页；老泡儿亲自手动走了一遍并发布成功，本文记录真实坎儿与最终可用文案。

## 结果

- **已真发成功 1 条**（老泡儿手动操作，非草稿）。此前所有自动流程**均未发布成功**，不存在重复发。
- 内容：11 部门 WF-01「小猫玩红球」AnimateDiff 文生视频样片（纯 AI 生成）。
- 发布页：`https://channels.weixin.qq.com/platform/post/create`（须从首页点「发表视频」进入，直接全页打开会落空壳/跳首页）。

## 趟出来的硬坎

### 1. 短标题校验（平台前端）

| 输入 | 平台报错 |
|---|---|
| `小猫玩红球,一玩就是一下午` | 标题包含特殊字符，符号仅支持书名号、引号、冒号、加号、问号、百分号、摄氏度，逗号可用空格代替 |
| `小猫玩红球` | 标题至少 6 个字 |
| **`小猫玩红球一玩就是一下午`** | ✅ 通过（11 字，无特殊符号） |

**规矩**：短标题 ≥6 字（本项目 `format_str_for_short_title` 从严按 7~15 字）；逗号/顿号等一律去掉或换空格；允许符号只有 `《》 “” : + ? % °`。

> 注：代码 `uploader/tencent_uploader/main.py:97` 已实现「逗号→空格 + 7~15 字补足」，本次手动踩坑是因为**给老泡儿的示例文案直接写了带逗号原句**，不是函数失效。下回示例必须用合规串。

### 2. 自动流程没走通的根儿（待修）

- `upload_video_file()` 的 `find_file_input()` 在发布页三个 frame 里查到 `input[type=file]` **全为 0**；上传框疑为点左侧「+」后动态生成，脚本 `set_input_files` 没喂到真上传框。
- 现场截图 `logs/desktop_publish2.png`：标题/话题/描述已填，左侧上传区仍是空虚线框 → 视频压根没上传，脚本在 `wait_for_upload_complete` 里空等到手动止损（已等 447 秒）。
- 平台对规格挑剔：原片 512×512 / 2s / 8fps / **无音轨**；已备转码版 `videos/cat_red_ball.mp4`（1080×1080 / 30fps / 6s / AAC 静音轨 / 3.3MB），内容不变只补规格。
- 作品列表 `platform/post/list` 直接全页打开同样被弹回首页，只读核查得从首页点「内容管理」进。

## 最终可用文案（自然口吻，不带「测试/验证/自动/联调」等风控敏感字样）

**视频描述**（大编辑框）：

```
小猫玩红球，一玩就是一下午

AI 生成的小短片，阳光房里一只小猫追着红球蹦跶，看着还挺解压的。

#喵星人 #AI动画 #治愈系
```

**短标题**（中间那个框，必须合规）：

```
小猫玩红球一玩就是一下午
```

## 平台元素特征码（老泡儿 2026-11-13 抓的实物，修脚本就照这个）

**首页「发表视频」入口**
```html
<div data-v-324a588a="" class="weui-desktop-btn_wrp">
  <button type="button" class="weui-desktop-btn weui-desktop-btn_primary">发表视频 </button>
</div>
```

**上传区（ant-design 拖拽上传，页面加载时没有 input[type=file]）**
```html
<div class="ant-upload-drag-container"><div class="upload-content"><div class="center">
  <span class="add-icon weui-icon-outlined-add"></span>
  <div class="upload-tip"><span>支持上传 8 小时以内、不超过20GB 的视频。建议分辨率为 1080p 及以上。</span>
  ...
```
平台推荐规格（popover 原文）：H.264/H.265、码率 ≤10Mbps、帧率 ≤60fps、分辨率建议 1080p 及以上、**音频 AAC 流 ≥128kbps / 采样率 ≥48kHz**。

**「发表」按钮（不在 `div.form-btns` 里！）**
```html
<span class="weui-desktop-popover__target">
  <div data-v-71b6a0c8="" class="weui-desktop-btn_wrp">
    <button type="button" class="weui-desktop-btn weui-desktop-btn_primary weui-desktop-btn_disabled">发表</button>
  </div>
</span>
```
上传未完成时带 `weui-desktop-btn_disabled`，完成后去掉。

## 按特征码做过的代码修复（本地未提交，待下次真发复验）

1. `wait_for_upload_complete` / `submit_publish`：发表按钮选择器从 `div.form-btns button` 改成 `button.weui-desktop-btn:has-text("发表"):not(:has-text("发表视频"))` —— 旧选择器永远等不到按钮，是干等 447 秒的真凶。
2. `upload_video_file`：改成先等 `div.ant-upload-drag-container` 挂载（落在首页就点 `button.weui-desktop-btn_primary:has-text("发表视频")`），再点 `span.add-icon` 触发 input 动态挂载，最后 `set_input_files`；塞完硬校验上传区真的接收了文件（「支持上传 8 小时以内」提示消失），否则立刻报错并截图，不再假跑空等。
3. `format_str_for_short_title`：补位串从 `"，精彩内容分享"` 改成 `" 精彩内容分享"` —— 旧补位会产出全角逗号，正好撞平台特殊字符黑名单。

## 验证结果（自动链路已跑通，连发两篇均成功）

- 2026-11-13 14:55:31：第 1 篇自动发布成功 —— 11 部门 WF-01 小猫玩红球样片，转码版 `videos/cat_red_ball.mp4`（1080×1080 / 30fps / 6s / AAC），脚本 exit 0。
- 2026-11-13 15:17:57：第 2 篇自动发布成功 —— `YouPick_35_linwan_short_00001_.mp4`（原片 432×240 / 24fps / 1.6s）转码 `videos/youpick_35_linwan.mp4`（1080×1080 / 30fps / 6.6s / AAC），标题「AI生成的小短片看着还挺有意思」，脚本 exit 0。
- 两篇均走完整链路：扫码登录 → 上传 → 填表 → 发表 → cookie 更新 → SUCCESS。

## 相关文件（磁盘绝对路径）

- 转码视频：`E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\videos\cat_red_ball.mp4`
- 11 部门原片：`E:\AI\orca-worktrees\11_ImageGen\ImageGen_11_00\知识库\11-ImageGen-图像视频部\ComfyUI短视频工作流\samples\WF-01\WF-01_0_WF-01-animatediff-lightning-t2v_00001.mp4`
- 现场截图：`E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\logs\desktop_publish2.png`
- 发布联调日志：`E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\logs\publish_wf01.log`
- 本记录：`E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\docs\manual-publish-findings.md`

## 本轮代码改动（本地未提交）

- `uploader/tencent_uploader/main.py`：登录页 `goto` 补 120s 超时 + `domcontentloaded`；`cookie_auth` 假阳性修复（等 networkidle + 查 login.html / qrconnect iframe）；发表按钮选择器对齐实物；上传区改为「等容器→点+→塞文件→硬校验接收」；短标题补位去掉违规逗号。
- `publish_wf01.py`、`open_manual_page.py`、`sau.cmd`：联调/手动页面启动器。
- 远端未 push、未改上游。

---
name: tencent-upload
description: 使用 social-auto-upload 的 `sau tencent` 登录视频号并发布或定时发布视频、保存草稿。Use when 用户要向微信视频号发布视频或检查视频号账号状态。
license: MIT-0
slug: social-auto-upload-tencent-upload
displayName: 微信视频号发布
version: 2.0.0
summary: 登录视频号并发布、定时发布或保存视频草稿；含实测验证的发布链路要素。
---

# 视频号发布

调用现有 `sau tencent` CLI，不另写网页上传流程。先确认 `sau tencent --help`；账号名是本地会话别名。

```powershell
sau tencent login --account creator;
sau tencent check --account creator;
sau tencent upload-video --account creator --file videos/demo.mp4 --title "标题" --desc "简介" --tags 视频号,测试
```

视频号仅支持视频发布。可选参数包括 `--schedule "YYYY-MM-DD HH:MM"`、`--draft`、`--collection`、`--short-title`、`--category`、`--thumbnail-landscape` 和 `--thumbnail-portrait`。--thumbnail 是竖版封面的兼容参数。合集必须已存在。

登录和上传依赖浏览器会话。登录若生成二维码，直接展示二维码图片供用户扫码；需要人工操作页面时使用 `--headed`。定时仅在用户给出明确时间时使用。`--draft` 只保存草稿，不代表发布。

发布前确认目标账号、视频、标题、简介、标签及立即发布/定时/草稿意图。只发布用户明确指定的平台；同一份内容也要逐个平台核对要求。

只依据 CLI 输出和平台页面确认结果，不把命令启动成功当成发布成功。超时或结果未知时先查原作品，不盲目重发。

## 实测验证的发布链路要素（2026-11-13，全自动发布链路已跑通）

本节记录的是一次完整的自动化发布验证留痕：从扫码登录 → 上传 → 填表 → 点发表 → 收 cookie，端到端 **SUCCESS**，exit 0。

### 平台页面要素（特征码）

**首页「发表视频」入口**：

```html
<div data-v-324a588a="" class="weui-desktop-btn_wrp">
  <button type="button" class="weui-desktop-btn weui-desktop-btn_primary">发表视频 </button>
</div>
```

**上传区（ant-design 拖拽上传）**：

```html
<div class="ant-upload-drag-container">
  <div class="upload-content">
    <div class="center">
      <span class="add-icon weui-icon-outlined-add"></span>
      <div class="upload-tip">
        <span>支持上传 8 小时以内、不超过20GB 的视频。建议分辨率为 1080p 及以上。</span>
        ...
```

注意：页面加载时上传区可能没有 `input[type=file]`；需先等容器挂载，再点 `span.add-icon` 触发动态挂载 input，随后才可 `set_input_files`。

**「发表」按钮**（注意：**不在 `div.form-btns` 里**）：

```html
<span class="weui-desktop-popover__target">
  <div data-v-71b6a0c8="" class="weui-desktop-btn_wrp">
    <button type="button" class="weui-desktop-btn weui-desktop-btn_primary weui-desktop-btn_disabled">发表</button>
  </div>
</span>
```

上传未完成时带 `weui-desktop-btn_disabled`，完成后去掉。

### 平台发布要求

- 视频：H.264/H.265、码率 ≤10Mbps、帧率 ≤60fps、分辨率建议 1080p 及以上、音频建议 AAC 流 ≥128kbps、采样率 ≥48kHz。
- 视频号仅支持视频发布。

### 实测发现的硬坎与修复

1. **短标题规则**（平台前端硬校验）：只允许 `《》 “” : + ? % °` 等特殊符号，逗号可用空格代替；标题至少 6 个字。自动流程补足短标题时不得使用逗号（补位串必须是纯汉字/空格）。
2. **自动流程上传失败根因**（一次验证中反复踩）：旧实现在发布页先查找 `input[type=file]` 直接 `set_input_files`；由于上传区是 ant-design 拖拽容器（需先触发点击），文件实际未被接收，随后在 `wait_for_upload_complete` 中空等而超时。**当前实现已改为：先等拖拽容器挂载 → 点 add-icon → set_input_files → 硬校验上传区接收状态，不接收则立即报错截图。**
3. **发表按钮等待**：旧实现等待 `div.form-btns button:has-text("发表")`，但实物按钮并不在 `div.form-btns` 内。当前实现改为按实物特征码选择器：`button.weui-desktop-btn:has-text("发表"):not(:has-text("发表视频"))`，并校验 `weui-desktop-btn_disabled` 类。

### 验证结果

- 2026-11-13：完整自动化发布链路验证通过（扫码登录 → 上传 → 填表 → 发表 → cookie 更新 → SUCCESS），脚本 exit 0。
- 发布成功视频：11 部门 ComfyUI WF-01 小猫玩红球样片（AI 生成），转码版文件使用于验证（1080×1080 / 30fps / 6s / AAC）。

## 故障排查要点

- `cookie_auth` 假阳性：页面在 8 秒内未跳转即判有效，慢网下易误判。已修复为等待 networkidle + 核验 URL/iframe。
- 登录页 goto 无超时、默认 30s；视频号页面较慢时易超时。已修复为 `timeout=120000, wait_until="domcontentloaded"`。
- 二维码：等待窗口建议 20 分钟，过期由库内逻辑刷新。

## 关联文档

- 发布联调留痕：`docs/manual-publish-findings.md`
- 发布流程日志：`logs/publish_wf01.log`

## 参考

- `docs/CLI.md`
- `docs/install.md`
- `docs/update.md`

# YouPick 远程服务 · 客户接入配置模板

> 用途：新客户远程安装时，按这份清单填好，10 分钟内跑通闭环 demo。
> 口径：合作方老泡儿内部用；对外只交付不开放源码。
> 客户数据（data/ 目录）落 09 自管 L1 路径，不进公共库；出境走 L3 申请。

## 一、安装前置（一次性）

1. 环境：Python 3.12 + `.venv`（`patchright` 已装在此 venv，跑脚本必须用 `.venv/Scripts/python.exe`）。
2. 微信会话：把客户视频号登录态塞进 `youpick_workflow/data/chrome_profile_tencent/`（系统 Chrome + 独立 profile，免扫码）。
3. 客户隔离：**每个客户一套 `data/` 目录**——迁移/交付 = 拷贝这个目录即走，互不串数据。

## 二、客户配置项（填表）

| 字段 | 说明 | 示例 |
|---|---|---|
| `platform` | 平台（premium 多平台：weixin/douyin/xiaohongshu/kuaishou） | `weixin` |
| `account` | 账号昵称（多账号矩阵时按号分人设） | `客户号A` |
| `export_id` | 视频 objectId（视频号必填，其他平台对应视频 id） | `export/UzFf...` |
| `edition` | 版本（trial/standard/premium） | `premium` |
| `persona` | 互动人设（北京胡同串子 / 定制） | `北京胡同串子` |
| `daily_soft_cap` | 单日软上限（观察期保守，非 200 硬上限） | `40` |

## 三、拉起闭环（日常）

```bash
# 看客户号活没活
.venv/Scripts/python.exe youpick_workflow/remote.py status --edition premium --account 客户号A --json

# 跑一轮（DRY RUN 默认不发；--approved 才真发，须老泡儿点头）
.venv/Scripts/python.exe youpick_workflow/remote.py run --edition premium --account 客户号A --mode full
.venv/Scripts/python.exe youpick_workflow/remote.py run --edition premium --account 客户号A --mode full --approved

# 出周报（给客户看互动量/续费状态）
.venv/Scripts/python.exe youpick_workflow/remote.py report --edition premium --account 客户号A --days 7 --json
```

## 四、风控红线（装给客户也得守）

- 活跃时段 9~22 点（测试期放宽到 24，正式放量收紧）；单日软上限宁慢勿猛；号有历史限流记录。
- 绝不碰：验证码绕过 / 设备指纹 / 批量养号 / 刷量——卖出去也不能让客户把号作死。
- 对外发送（发布/回帖/点赞/删除/置顶）仍须老泡儿单独点头；草稿→过审→发。

## 五、回执与上报（远程托管接口约定）

- 每轮结束 runner 回执落本地库（rounds/actions/candidates）；
- 真正远端后台心跳上报（POST 状态给后台）属 L3 跨切治理，本模板不启服务器，预留接口：
  `status/run/report` 三动作吐的 JSON 即后台读取契约。

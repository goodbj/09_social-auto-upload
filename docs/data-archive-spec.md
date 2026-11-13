# YouPick 运行时数据归档规范（09_04 岗位真源）

> 派工来源：Issue #326 `[09_00][P2][task] Issue #308 09_04 岗位派工: 数据归档/运行时监控`
> 归属：Issue #308 视频号全自动 AI 交互号产品化立项（M2 里程碑）
> 责任人：09_04（文生视频零件岗兼任数据/监控岗）
> 配套脚本：`youpick_workflow/health_monitor.py`（只读健康监控）

---

## 一、总原则

- **唯一归并目录**：所有运行时产物（库 / 日志 / 归档 / 派工单 / 浏览器 profile）**只进 `youpick_workflow/data/`** 一个目录。
- **整目录不外发**：`.gitignore` 已 `youpick_workflow/data/` 整目录 + `*.sqlite3*` + `logs/` + `*.png` + `chrome_profile_tencent/` 等拦死；提交代码时这一层**绝不进 git**。
- **迁移 = 拷贝 `data/`**：换机/换部署，把 `data/` 整目录拷过去即迁移全部运行态，无需 dump/restore。
- **平台是真源，本地库是镜像 + 留痕**：本产品不持客户数据产权，库只在本机读写（SQLite 单文件），不部署独立服务。

---

## 二、目录结构（data/）

```
youpick_workflow/data/
├── youpick_interaction.sqlite3        # 本地镜像库（账号/轮/留言/动作/候选/派工单）
├── youpick_interaction_v1_backup.sqlite3  # 旧版备份（归档留痕，不删）
├── chrome_profile_tencent/            # 本家浏览器自动化 profile（含登录会话）
├── logs/                              # 运行状态日志
│   ├── human_pace.log                  # 拟人节奏随机停顿留痕
│   ├── human_session_state.json        # 会话闸状态（按日计：今日回复数 + 已回名单）
│   ├── workflow.log                    # 闭环轮日志
│   ├── interaction_round.log / *_real.log
│   └── maintain_fans.log / *_real.log
├── round_archive/                     # 每轮原始响应 + 核验快照 + 巡检报告（复盘用）
│   ├── round_NNN_raw.json             # 平台读评原始响应（archive_workflow写）
│   ├── round_NNN_verify.json          # 回读核验快照
│   ├── round_NNN_report.md/.json      # 巡检报告（含来源分布/候选/采纳）
│   └── ...（按轮自增）
└── dispatch/                          # M4 派工单落盘（候选采纳→派11→回执）
    └── order_NNN.json
```

> 第三方昵称样本：互动闭环读到的 `nickname/username` 一律落在 `comments` 表（库内），
> 不做独立昵称样本文件——既不外发也不单独沉淀，库本身就在 `data/` 内被 gitignore 拦住。

---

## 三、外发边界（红线，不碰敏感数据外发）

| 项 | 是否入库 | 是否进 git | 是否可外发 |
|----|---------|-----------|-----------|
| 源代码 / 插件 / 装配层 | 是 | 是 | 是（卖产品不卖数据） |
| `youpick_interaction.sqlite3` + 备份 | 是 | **否**（gitignore） | **否**（客户运行态） |
| `chrome_profile_tencent/` 登录态 | 是 | **否** | **否**（含会话凭证） |
| `logs/` 运行日志 | 是 | **否** | **否**（含留言样本） |
| `round_archive/` 原始响应用户内容 | 是 | **否** | **否**（含用户 UGC） |
| `dispatch/order_*.json` | 是 | **否** | 内部用，不外发 |

**铁律**：对外发货（部署包/开源仓）只包含代码与文档，**`data/` 整目录永不在交付物内**；
需要排查问题时，按需从 `data/` 本地读取，**绝不打印/上传/贴出用户昵称原文与原始响应**。

---

## 四、运行时监控口径（health_monitor.py）

脚本**只 SELECT 不写库、不 import 平台 SDK、不调用任何发送**，可随时裸跑：

```bash
.venv/Scripts/python.exe youpick_workflow/health_monitor.py            # 概览
.venv/Scripts/python.exe youpick_workflow/health_monitor.py --json     # 机器可读
```

监控四件套，对应 Issue 验收：

1. **防重**
   - 库层 `actions` 唯一索引 `uq_action_success (account_id, comment_id, action_kind) WHERE status='success'` 跨轮幂等；
   - 会话层 `replied_ids` 名单双重把关；
   - 监控对账：被索引拦掉的重复尝试数 + `replied_ids` 名单与库当日 success reply 集合是否一致。
2. **回读核验**
   - `actions.verify` 列记录每次对外动作后回读结论（命中/未命中/没找着）；
   - 监控统计命中率，**未命中 = 需人工看**（平台侧状态可能异步，不自动重试）。
3. **日限额（约 200 的口径澄清）**
   - 产品三档实际 `daily_soft_cap`：**trial=20 / standard=40 / premium=80**（`capabilities.py`）；
   - `human_pace.DAILY_REPLY_CAP_DEFAULT=200` 是「腾讯平台每日留言上限」的**观测软上限参考值**（未经平台核实），仅备注不硬卡；
   - 监控**按账号**从库读实际 `daily_soft_cap`，按账号统计当日真实回复数与剩余额度，超 cap 即告警。
4. **data/ 归并边界**
   - 校验 `data/` 存在 + 整目录 gitignored + 各子目录体积，提示敏感项不外发。

**附带信号**（监控顺手揭示的健康项）：
- 轮状态：是否有 `running` 未收尾的轮（应每轮 `finish_round` 落 `done`）；
- 候选拍板：`待拍板` 积压数（超阈值提示老泡儿拍板）；
- 派工单：`created/dispatched/acked` 分布（卡 `created` 提示未投出）。

> 首次裸跑（2026-11-14）即发现：2 个 round 卡 `running` 未收尾、会话 state 日期(11-13)与今日库对不上（state 跨会话需刷新）。属观察项，不影响闭环跑通，留痕待 09_00 裁定。

---

## 五、保留 / 清理策略

- 库：SQLite 单文件天然追加，不清；备份 `.v1_backup` 保留不删。
- `round_archive/`：按轮自增，复盘用，保留近 30 轮、更早的可按需转冷存。
- `logs/`：文本追加，单文件；长期运行建议按月滚动（脚本不改，运维手动 `mv`）。
- `chrome_profile_tencent/`：含登录态，**不清理、不挪出 data/**，否则需重新扫码会话恢复。

---

## 六、验收对照（Issue #326）

- [x] 数据归档规范落地（本文件 + data/ 单一归并 + gitignore 拦截 + 外发边界红线）
- [x] 监控互动闭环健康：防重 / 回读核验 / 日限额 ≈200 口径（脚本 + 本章第四节）
- [x] 不碰敏感数据外发（见第三节红线表）

---
name: youpick-multi-agent-coordination
description: "YouPick 09_00 协调员派兵总纲：给 09_01~09_04 派工、验收、回收、跨部门协调。当 09_00 要派活给子智能体、接力派工闭环、回收终端、跨簇协调时用。含双信道通信、派工单模板、worker-release 回收、智能体人设派单。⚠️ 角色/目录/红线/派单命令的真源在集团灵魂 + capability-core；任务唯一真源 = GitHub Issues（goodbj/AI_Memory 打部门-09标签 + goodbj/YouPick）。学自 01_Digger multi-agent-coordination，已按 09 的信道/角色/仓库本地化。"
metadata:
  type: reference
  reviewed_at: 2026-11-14
---

# YouPick 09_00 协调员派兵总纲

> ⚠️ **使用前必读（防过期）**：用前先验锚点：
> ```bash
> orca orchestration run-use --id run_7a81c56a6a1a                      # 协调信道还在吗
> gh issue list --repo goodbj/AI_Memory --state open --label "部门-09 YouPick" --limit 5
> orca terminal list --json | head -5                                   # Orca 活着吗
> ```
> 任一失配 → 以最新代码/文档为准，并按文末「技能维护」更新本文件。

## 一、角色与组织（09 部门）

| 角色 | ID | 职责 | 备注 |
|---|---|---|---|
| 部门协调员 | **09_00** | 统筹、派工、验收、回收、跨簇协调 | **绝不亲自干子智能体的活**（串台=失职）；成员话术/人设由成员自己长，协调员不带人设 |
| 视频号创作 | 09_01 | 视频内容创作、发布 | 人设由 09_01 自己长（如北京小妞） |
| 留言交互 | 09_02 | 粉丝互动、留言回复 | 人设由 09_02 自己长 |
| 子项目 C | 09_03 | 待派 | 按任务性质现派 |
| 子项目 D | 09_04 | 待派 | 按任务性质现派 |

**身份真源**：`E:\AI\AI_Memory\Common-公共库\00-Governance-治理规范\dispatch_routing.yaml` 的部门 09 条目。
**寻址靠实时重建**：`orca terminal list` + `orca worktree list`，别死记 tabId（tab 关了会变，worktreeId 永久稳定）。

## 二、双信道通信（正式 + 叫醒）

| 机制 | 用途 | 关键命令 |
|---|---|---|
| **Run 邮箱**（正式） | 派工单、回报、审核结论 | `orca orchestration send --run <run_id> --from "09_00" --type <type> --subject ... --body ... --json` |
| **terminal send**（叫醒） | 喊人去看邮箱，**绝不承载内容** | `orca terminal send --terminal "<handle>" --text "【信道叫醒】...请 check --run <run_id>" --enter` |

**Run ID**（真值见 AGENTS.md + dispatch_routing.yaml）：
```
run_7a81c56a6a1a   本部门协调信道（对 09_01~09_04 派工/收回报）
run_1cd4e1700daf   公共簇信箱（找 00_01；跨簇/L3 权限）
```

**四条铁律（Digger 血泪实测，对 09 同样适用）**：
1. terminal send 消息**伪装成用户输入**（对方把我当老泡儿）→ 正式内容绝不走它
2. 对方**聊天里的回复不可达**（只是它屏幕上的文字）→ 需要答复时写明「请 orchestration send 投递到 run 邮箱」
3. 读对方终端输出用 `orca terminal read --terminal <handle>`，**不是**盯 list 的 preview
4. 命令尾部严禁跟中文问句（被吃进 argv）

**派工前必查人在线**（老泡儿 2026-11-04 批）：`orca terminal list`（connected）+ `orca orchestration worker-list`（liveness），**不在线不空发**——先重拉会话或落盘等。

## 三、派工闭环四步（不是三步）

```bash
# ① task-create → ② worker-start → ③ 等 worker_done → ④ worker-release
orca orchestration worker-release --dispatch <dispatchId> --json
```

**派工单模板（直接抄）**：
```text
09_0X，协调员派工。按优先级逐个干，每个走标准流程
（读真源→改→本地自测→回报→等回收）。

━━━ 工单X【Issue #N / P?】<一句话> ━━━
条目：GitHub Issue #N（goodbj/AI_Memory or goodbj/YouPick）
链接：https://github.com/...
落点（已摸底）：<文件:行号 + 现状>
修法方向：<1/2/3...>
验证：<具体命令 + 断言>
注意：<边界，如：本地改动不 push / 对外发送须老泡儿点头 / 别写死版本>
```

**local 改动不 push**：09 部门产物在 `E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload`（独立 git 仓），L1 自管路径可直接合 main，但**推 origin/main 前先 fetch+merge，禁非快进强推**；未获老泡儿批准不 push 不改上游。

## 四、【09 特色】成员人设派单（老泡儿 2026-11-14 拍板）

**互动客服人设产品化**：一套套人设技能攒库（北京小妞/上海大妈/东北小伙……），用哪套调哪套，**老泡儿 + 09_00 一起去调教**。

- 人设技能落 `skills/youpick-persona-XXX/SKILL.md`，含**人设铁律**（口气/脾气/禁区）——如：不骂人不说脏话、可否定粉丝但不嘲讽不搞地域歧视、胡同妞的傲气但不看不起人。
- 派单时指定人设：工单正文写「按 `skills/youpick-persona-beijing-girl/SKILL.md` 人设执行」。
- **09_00 协调员不带人设**——我是统筹，人是干活+长脾气的，绝不串台。
- **一号一智能体**：一个智能体维护一个账号，多账号矩阵靠 M1 的 `(platform, account)` 隔离；09_00 统管全局运营。

## 五、回收与巡检（收工前必跑）

```bash
# worker-start 方式
orca orchestration worker-list --terminal-state reclaimable --limit 100 --json
# 有内容 → 逐个 orca orchestration worker-release --dispatch <id> --json

# dispatch --to 方式（投现有终端，状态 unsupervised 不能 release）
orca terminal list --json   # 手动 orca terminal close --terminal <handle>
```

**坑（Digger 实测）**：`worker-release` 没有 `--run` 参数；`dispatch --to` 的终端成不了 `settled`，不能 `worker-release` 只能手动 close；**9 个 reclaimable worker 挂 18 小时**的教训——谁派的谁回收。

## 六、技能维护

| 变更 | 改哪 |
|---|---|
| Run ID 作废/重建 | §二 Run ID |
| 子智能体增减（09_05/09_06 招入） | §一表格 |
| 人设技能新增 | §四人设清单 |
| 新翻车案例 | 对应章节 |

**同步**：改完跑 `python tools/sync_skills.py`（如集团有）同步 `.agents/skills/`。
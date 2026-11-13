---
name: youpick-fans-interaction
description: 视频号粉丝维护（读评论/点赞精彩留言/回复有意义互动），按老泡儿一句话触发（「维护一下粉丝」「找精彩评论点评」「找有意义的回复」）。含读评、点赞、楼中楼接话、回读核验、SQLite 归档、拟人口吻与风控节奏。Use when 老泡儿让去某条视频底下维护粉丝/互动，或要跑一轮评论点赞+回复。
license: MIT-0
slug: youpick-fans-interaction
displayName: 视频号粉丝维护（点赞+回复）
version: 1.0.0
summary: 一句话触发对某条视频的粉丝维护——找精彩评论点赞、找有意义回复接话，逐条随机节奏、回读核验、落库防重。
---

# 视频号粉丝维护（点赞 + 回复）

**真源**：`E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\docs\closed-loop-decisions.md`
**脚本**：`E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\maintain_fans.py`
**库**：`E:\AI\orca-worktrees\09_YouPick\09_social-auto-upload\db\interaction_store.py`（SQLite 镜像库）

## 一句话触发（老泡儿自然话术）

- 「去小猫海上跑那个视频里，维护一下粉丝：找精彩的评论点评、找有意义的回复」
- 「维护一下粉丝」「找精彩评论点评」「找有意义的回复」

本质 = 在指定视频（默认 `export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw` 小猫海上跑）底下，
对**全部未处理**的精彩/有意义留言动手（不只对「新增」，区别于 `interaction_round.py` 的巡检轮）。

## 范围判定（只认规则，绝不瞎发）

| 动作 | 触发 | 跳过 |
|---|---|---|
| 👍 点赞 | `source != 自家回复` 且 `likeFlag==0` 且（内容有价值信号 **或** 是回咱的有意义 L2） | 自家回复 / 已点过赞（`likeFlag==1`，再点=取消赞）/ DB 已有成功 like 记录 |
| 💬 回复 | L2 且 `reply_to_id` 指向咱的留言，且该线程还没咱的回帖 | 自家回复 / 已回过（DB 成功记录 或 树上已有 `丸小子998` 子楼）/ 重复回复 |

**防重复靠库不靠硬编码**：`actions` 表对 `(comment_id, action_kind)` 成功记录加唯一索引，跨轮幂等；
点赞重复 = `UNLIKE` 取消赞，这个坑必须靠库挡。

## 参数（反编译 chunk_251 / chunk_512）

```
POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/like_comment
{"commentId":"<commentId>", "scene":1, "exportId":"<objectId>"}   # LIKE=1 / UNLIKE=2
→ HTTP 201 / errCode=0（响应约 77B）

POST /micro/interaction/cgi-bin/mmfinderassistant-bin/comment/create_comment
{"exportId":"<objectId>", "replyCommentId":"<被回 L2 的 commentId>",
 "rootCommentId":"<顶层 commentId>", "content":"<回复>", "clientId":"<uuid>",
 "comment":{<被回 L2 对象>}}
→ 回复挂在顶层 levelTwoComment[] 下
```

## 人话接法（不让 AI 味儿露怯）

- 起句随机：`嗬，您这话说的` / `得嘞，这主意我记下了` / `嘿，还真让您说着了` / `甭急，咱慢慢盘道` / `您这思路够局气的` / `您嘞，这茬儿提得有意思`。
- 按内容关键词接：`谦虚/骄傲`→「帽子扣得瓷实」；`不信`→「下回拿实物给您瞧」；`炒菜/颠勺`→「让视频部捯饬一版」；`玻璃栈道/海鸥/灯塔`→「这景儿露个脸」；通用→「这主意我记下了，回头照着捋」。
- **不编事实**：没拍过的下集不硬许；没养过的宠物不写；修过的文案复查。

## 风控 / 拟人节奏（详见 human-like-anti-risk-plan.md）

- 每步随机停：导航 2.5~6s、沉淀 3~8s、点击 0.8~2.5s、发送前 2~6s；8% 走神 +4~12s。
- 先读再回（按字数算阅读时间），逐字敲（40~200ms/字，标点处犹豫），不整段粘贴。
- 两条动作之间 35~120s；单次上线随机只干 3~7 件就收工；活跃时段 9~22 点。
- 三道发送闸：`SEND_ENABLED` / `approved` / `dry_run`，默认 dry run 只演不发，`--approved` 才真发。

## 标准操作（照抄）

1. 前台跑 `maintain_fans.py`（要真发带 `--approved`；先看 dry run 输出确认只挑对目标）。
2. 脚本：取库最近 done 轮快照 → 找出值得点赞/回复的未处理留言 → 逐条随机节奏处理 → 回读 `comment_list` 硬核验 → 落 SQLite（rounds/comments/actions）+ 日志。
3. 看 `logs/maintain_fans_real.log` 核对每一步；核验行 `likeFlag=1` / 「回读命中回复」= 真成功，光看 `errCode=0` 不算。

## 趟过的坑（接 tencent-quick-login 的 16 个坑）

- **重复点赞取消赞**：`likeFlag==1` 就跳过，`commentLikeCount` 是总赞数（含别人）不能判本号是否已点。
- **L2 挂错层**：`rootCommentId` 永远指顶层；用 `username / source_tag` 把主号自己的 L2 剔掉，不自己回自己。
- **会话过期**：`errCode=300334` → 走 `skills/tencent-quick-login/SKILL.md` 免扫码恢复，不重新扫。
- **账号有历史限流**：互动宁慢勿猛，前期「AI 起草→人过目→发」。

## 红线

- 调试阶段不黑箱：前台可见窗口、逐步输出、随机休眠。
- 发布 / 回帖 / 点赞 须老泡儿单独点头；只读勘察不在此列。
- 本地改动未提交、未 push；提交须批准。
- 不碰验证码绕过、设备指纹、批量养号。

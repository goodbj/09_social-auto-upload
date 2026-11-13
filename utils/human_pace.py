# -*- coding: utf-8 -*-
"""拟人节奏层：让「读留言 / 回粉丝」像真人在操作，不像脚本刷刷一口气跑完。

老泡儿 2026-11-13 拍板（真源：docs/closed-loop-decisions.md）：
- 操作之间必须有**随机睡眠**，不能一口气全干完；
- 腾讯每天留言上限约 200 条（数值未经平台核实，按保守默认）→ **挑有价值的回，别是个留言都回**；
- 互动人设：**北京胡同串子**口气，不用官方客服腔；
- 剧情/话题：**每轮搜集几条候选 → 老泡儿拍板 → 再实施**，不纯按点赞排序；
- 前期：AI 起草 → 人过一遍 → 发；**本模块默认 dry_run=True，绝不自动发送**。

「像人」具体拆成这些动作：
1. 每个动作前随机停顿（不同动作不同区间），偶发「走神」长停顿；
2. 读留言按字数算阅读时间——人得先看完才回；
3. 打字逐字敲、带随机按键间隔、标点处偶尔犹豫，不整段粘贴；
4. 一个会话随机只干几件事就歇，不把队列一口气清空；
5. 单日总量上限 + 活跃时段 + 相邻动作最小间隔 + 会话间长休息；
6. 每次实际停多少秒都打印出来，可核查、不黑箱。

⚠️ 安全闸：`human_reply()` 默认 dry_run=True 且 approved=False；
   不发批准就调用发送，直接抛异常。任何对外发送须老泡儿单独点头。
"""
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = BASE_DIR / "logs" / "human_session_state.json"

# 各类动作的随机停顿区间（秒）。调试想快进可传 scale<1，但正式跑必须是 1.0。
RANGES: dict[str, tuple[float, float]] = {
    "navigate": (2.5, 6.0),        # 打开页面 / 切导航
    "settle": (3.0, 8.0),          # 等页面异步灌数据
    "scroll": (1.2, 3.5),          # 滚动翻页
    "click": (0.8, 2.5),           # 点击前
    "read": (1.0, 2.5),            # 开始读一条留言前
    "type": (0.04, 0.20),          # 每个字之间的按键间隔
    "before_send": (2.0, 6.0),     # 点发送前再核一眼
    "between_replies": (35.0, 120.0),  # 两条回复之间：真人不会连着秒回
    "session_break": (180.0, 600.0),   # 一个会话结束后歇会儿
}

# 硬闸：未经点头绝不发送
SEND_ENABLED = False
DAILY_REPLY_CAP_DEFAULT = 200
ACTIVE_HOURS_DEFAULT = (9, 22)   # 夜里不操作，别半夜刷屏
DISTRACT_CHANCE = 0.08           # 8% 概率走神，多停 4~12 秒


def _stamp(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}", flush=True)
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with (BASE_DIR / "logs" / "human_pace.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n")
    except Exception:
        pass


async def nap(
    lo: float | None = None,
    hi: float | None = None,
    label: str = "",
    kind: str | None = None,
    scale: float = 1.0,
    distract: bool = True,
) -> float:
    """随机停一会儿。可用 nap(kind="scroll") 走预设区间，也可 nap(2, 5, "xxx") 自定义。

    scale<1 只用于本地演练（会在日志里标「演练」），正式跑一律 1.0。
    返回实际停的秒数，方便留痕。
    """
    if kind:
        lo, hi = RANGES[kind]
    if lo is None or hi is None:
        lo, hi = RANGES["settle"]
    if hi < lo:
        lo, hi = hi, lo
    secs = random.uniform(lo, hi)
    if distract and random.random() < DISTRACT_CHANCE:
        secs += random.uniform(4, 12)   # 走神：回个消息、喝口水
    secs *= scale
    tag = f" — {label}" if label else ""
    mode = " 演练" if scale != 1.0 else ""
    _stamp(f"[human_pace{mode}] 随机停 {secs:.1f}s{tag}")
    await asyncio.sleep(secs)
    return secs


async def human_read(text: str, label: str = "读留言", scale: float = 1.0) -> float:
    """按留言字数算阅读时间：人得先看完才能回。"""
    base = 1.2 + min(len(text or ""), 200) * 0.09
    jit = random.uniform(0.7, 1.5)
    secs = (base * jit) * scale
    _stamp(f"[human_pace] 看 {len(text or '')} 字，停 {secs:.1f}s — {label}")
    await asyncio.sleep(secs)
    return secs


async def human_type(page, locator, text: str, dry_run: bool = True, scale: float = 1.0) -> None:
    """逐字敲回复，带随机按键间隔；标点处偶尔犹豫一下。dry_run=True 只演不敲。"""
    preview = (text[:20] + "…") if len(text) > 20 else text
    if dry_run:
        _stamp(f"[human_pace] 演练打字（未触碰页面）: {preview}")
        await human_read(text, "演练时默读一遍", scale=scale)
        return
    await nap(kind="click", label="点进回复框", scale=scale)
    await locator.click()
    for i, ch in enumerate(text):
        await page.keyboard.type(ch)
        await nap(kind="type", scale=scale, distract=False)
        if ch in "，。？！,:?! " and random.random() < 0.25:
            await nap(0.4, 1.2, "标点处犹豫一下", scale=scale, distract=False)
    _stamp(f"[human_pace] 已逐字敲完 {len(text)} 字")


def pick_valuable(comments: list[dict], max_candidates: int = 5) -> list[dict]:
    """挑「值得回 / 有后续剧情潜力」的候选，**不按点赞数排序**——老泡儿拍板：
    「要最有未来潜力的后续剧情，不一定点赞最高的」。

    返回带 note 的候选清单，交给老泡儿拍板，不擅自决定拍哪条。
    """
    spam = ("加微", "私信我", "代发", "刷单", "兼职", "优惠券", "点击链接", "二维码")
    creative = ("要是", "不如", "下一集", "能不能", "建议", "后来", "然后", "如果", "让它", "应该")
    out = []
    for c in comments:
        # 视频号 comment_list 实字段名是 commentContent / commentLikeCount（不是 content/text）
        txt = (c.get("commentContent") or c.get("content") or c.get("text") or "").strip()
        if len(txt) < 4 or any(w in txt for w in spam):
            continue
        signals = []
        if any(w in txt for w in creative):
            signals.append("提了剧情走向/建议")
        if "?" in txt or "？" in txt or "怎么" in txt or "为啥" in txt:
            signals.append("在提问，接得上话")
        if len(txt) >= 20:
            signals.append("写得具体，有得聊")
        likes = c.get("commentLikeCount", c.get("likeCount", c.get("like_count", 0))) or 0
        if likes >= 3:
            signals.append(f"有 {likes} 赞（仅参考，不当排序依据）")
        out.append({
            "commentId": c.get("commentId") or c.get("id"),
            "nickname": c.get("commentNickname", ""),
            "text": txt,
            "likeCount": likes,
            "note": "；".join(signals) or "普普通通，留作备选",
        })
    # 故意不打乱也不排序：候选原样交给拍板人，避免算法替人做主
    return out[:max_candidates]


# 胡同串子口气起句（去模板化用，随机挑，别每条都一个腔调）
HUTONG_OPENERS = (
    "嗬，您这话说的",
    "得嘞，这主意我记下了",
    "嘿，还真让您说着了",
    "甭急，咱慢慢盘道",
    "您这思路够局气的",
    "您嘞，这茬儿提得有意思",
)


def build_reply_draft(comment_text: str, intent: str = "接话") -> dict:
    """只出草稿，不发送。文案须「AI 起草 → 人过一遍 → 发」，草稿一律标待审。"""
    opener = random.choice(HUTONG_OPENERS)
    body = (comment_text or "").strip()[:40]
    return {
        "status": "draft",
        "needs_human_review": True,     # 前期必须人过一遍
        "persona": "北京胡同串子",
        "text": f"{opener}——{body}，这事儿咱下回接着聊。",
        "intent": intent,
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }


async def human_reply(
    page,
    locator,
    send_button,
    draft: dict,
    *,
    approved: bool = False,
    dry_run: bool = True,
    scale: float = 1.0,
) -> str:
    """一条完整回复的人形节奏：读 → 想 → 敲 → 核 → 发。

    三道闸：SEND_ENABLED / approved / dry_run，缺一不发。
    """
    # 演练（dry_run）只走节奏、绝不触碰发送；真发才卡「人工审核」这道闸
    if not dry_run and draft.get("needs_human_review") and not approved:
        raise RuntimeError("草稿还没过人工审核，不许发（老泡儿前期规矩）")
    if draft.get("needs_human_review") and dry_run:
        _stamp("[human_pace] 演练：草稿标了「待人工审核」，本轮只演不审核")
    await human_read(draft.get("text", ""), "发出前自己再读一遍", scale=scale)
    await nap(2, 6, "琢磨措辞", scale=scale)
    await human_type(page, locator, draft.get("text", ""), dry_run=dry_run, scale=scale)
    await nap(kind="before_send", label="点发送前核一眼", scale=scale)

    if dry_run or not approved or not SEND_ENABLED:
        _stamp("[human_pace] 演练/未批准：不点发送，回复留作草稿")
        return "draft_only"
    _stamp("[human_pace] ⚠️ 已获批准且开闸，准备点发送")
    await nap(kind="click", label="伸手点发送", scale=scale)
    await send_button.click()
    return "sent"


class HumanSession:
    """一个「真人上线」会话：随机只干几件事就歇，带单日上限与活跃时段。

    状态落 logs/human_session_state.json（按日期计），防跨会话超量、防重复回帖。
    """

    def __init__(
        self,
        daily_cap: int = DAILY_REPLY_CAP_DEFAULT,
        active_hours: tuple[int, int] = ACTIVE_HOURS_DEFAULT,
        max_actions: tuple[int, int] = (3, 7),
        state_file: Path = STATE_FILE,
    ):
        self.daily_cap = daily_cap
        self.active_hours = active_hours
        self.max_actions = random.randint(*max_actions)  # 本次上线打算干几件事，开局就随机定
        self.actions_done = 0
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> dict:
        try:
            d = json.loads(self.state_file.read_text(encoding="utf-8"))
            if d.get("date") == date.today().isoformat():
                return d
        except Exception:
            pass
        return {"date": date.today().isoformat(), "replies": 0, "replied_ids": []}

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def allow(self, comment_id: str | None = None) -> tuple[bool, str]:
        h = datetime.now().hour
        if not (self.active_hours[0] <= h < self.active_hours[1]):
            return False, f"当前 {h} 点不在活跃时段 {self.active_hours}，夜里不操作"
        if self.state["replies"] >= self.daily_cap:
            return False, f"今日已回 {self.state['replies']} 条，触到上限 {self.daily_cap}"
        if self.actions_done >= self.max_actions:
            return False, f"本次上线已干 {self.actions_done} 件，该歇了（本次上限 {self.max_actions}）"
        if comment_id and comment_id in self.state["replied_ids"]:
            return False, "这条已经回过了，不重复回帖"
        return True, "ok"

    async def before_action(self, kind: str = "click", label: str = "", scale: float = 1.0) -> None:
        await nap(kind=kind, label=label, scale=scale)

    def consume(self, comment_id: str | None = None) -> None:
        self.actions_done += 1
        self.state["replies"] += 1
        if comment_id:
            self.state["replied_ids"].append(comment_id)
        self._save()

    async def finish(self, scale: float = 1.0) -> None:
        _stamp(f"[human_pace] 本次上线干了 {self.actions_done} 件，今日累计 {self.state['replies']}/{self.daily_cap} 条，收工歇会儿")
        await nap(kind="session_break", label="会话间长休息", scale=scale)


if __name__ == "__main__":
    # 纯本地演练：不碰浏览器、不碰平台，只验证节奏与候选筛选逻辑
    async def demo():
        print("=== 拟人节奏 · 本地演练（scale=0.05，不联网）===")
        s = HumanSession(max_actions=(3, 5))
        print(f"本次上线随机定下干 {s.max_actions} 件事")
        ok, why = s.allow("c1")
        print("allow:", ok, why)
        await nap(kind="navigate", label="打开评论页", scale=0.05)
        await human_read("这猫下一集能不能跑到灯塔那儿去，我赌它半路得歇", scale=0.05)
        cands = pick_valuable([
            {"commentId": "c1", "content": "这猫下一集能不能跑到灯塔那儿去，我赌它半路得歇", "likeCount": 2},
            {"commentId": "c2", "content": "哈哈哈哈", "likeCount": 99},
            {"commentId": "c3", "content": "加微信代发视频", "likeCount": 0},
            {"commentId": "c4", "content": "建议让它遇见一只海鸥，俩人搭伴走", "likeCount": 1},
        ])
        print("候选（不按赞排序，交拍板）:")
        for c in cands:
            print("  -", c["commentId"], "|", c["text"], "|", c["note"])
        d = build_reply_draft(cands[0]["text"])
        print("草稿:", d)
        r = await human_reply(None, None, None, d, approved=False, dry_run=True, scale=0.05)
        print("human_reply 返回:", r, "（应为 draft_only，绝没发送）")
        await nap(kind="between_replies", label="两条回复之间", scale=0.05)
        await s.finish(scale=0.05)
        print("=== 演练完 ===")

    asyncio.run(demo())

"""core 业务：互动裁决（赞/回的纯判断，无平台/无库依赖）。

老泡儿 2026-11-14 拍板：**互动话术由 Claude 本人亲笔写，废掉代码固定接话规则**——
批量程序同款句式群回没意思，每条回复都是我自己的判断（见
`skills/youpick-fans-reply/SKILL.md`）。本模块只保留「值不值得赞/值不值得接」的**机械信号**
（供筛选候选用），具体回复文本一律由 Claude 亲笔写，`reply_text` 由调用方注入。

判断流程：
  1. 程序（手）：读出值得互动的候选留言 → 幂等/闸把关 → 呈给我；
  2. 我（脑）：逐条看语境，亲自写回复文本（胡同串子口气、小脾气、不嘲讽）；
  3. 程序（手）：把我写的话发出去 → 回读核验 → 落库。
"""
from __future__ import annotations

from youpick_workflow.connectors.base import Comment

# 粗略的内容价值信号——只用来筛「哪些留言值得我亲自看」，不决定回复什么
LIKE_WORTHY = ("要是", "不如", "下一集", "能不能", "建议", "后来", "然后", "如果", "让它",
               "应该", "怎么", "为啥", "不信", "谦虚", "骄傲", "以假乱真", "技术", "画面",
               "敢", "信你", "炒菜", "颠勺", "玻璃栈道", "海鸥", "灯塔")

# 粗筛：内容太短/明显灌水的不值得我费神
TRIVIAL = ("哈哈", "666", "支持", "路过", "第一", "沙发")


def is_like_worthy(text: str) -> bool:
    """内容有价值信号（粗筛点赞候选，非严格判定）。"""
    return len(text or "") >= 4 and any(w in text for w in LIKE_WORTHY)


def worth_engaging(text: str) -> bool:
    """粗筛：这条留言值不值得我亲自过目（点赞或回复）。太短/灌水的跳过。"""
    t = (text or "").strip()
    if len(t) < 4:
        return False
    if t in TRIVIAL or (len(t) <= 6 and all(w in t for w in ("哈", "哈"))):
        return False
    return True


def decide(c: Comment, reply_text: str = "") -> dict:
    """核心裁决。**reply_text 由 Claude 亲笔写后注入，本模块绝不自动生成回复文本。**"""
    worthwhile = worth_engaging(c.content)
    return {
        "comment_id": c.comment_id,
        "like_worthy": is_like_worthy(c.content) and worthwhile,
        "reply_worthy": worthwhile,
        "reply_text": reply_text,          # 由我注入；空 = 本轮只赞不回
        "source_tag": c.source_tag,
        "level": c.level,
    }
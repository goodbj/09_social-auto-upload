"""身份/来源判定策略（平台无关，中性层）。

判断一条留言是「自家回复 / 亲友自测 / 引子钩子 / 自然流量 / 待核」。
不放 core/ 也不放 platform/——两边都要用，提到包根当中性依赖，避免反向耦合。
"""
from __future__ import annotations


# 默认账号（向后兼容老数据）：视频号 · 丸小子998
SELF_NICKNAMES = {"丸小子998"}
# 已知亲友 / 自测样本（老泡儿 2026-11-13 当面说明；后续新号往这儿补）
RELATIVE_NICKNAMES = {
    "对方正在输入中...",   # 老泡儿小号
    "磊", "红太狼~[emoji]", "梦中人9070", "景荣",
}
# 早期引子期由咱自己埋的话题钩子，命中即标「引子钩子」，别当自然流量共识
HOOK_WORDS = ("玻璃栈道", "海鸥", "灯塔", "下集让它", "咱下回")


def classify_source(
    nickname: str,
    username: str,
    content: str,
    *,
    self_nicks: set[str] | None = None,
    relative_nicks: set[str] | None = None,
    hook_words: tuple[str, ...] | None = None,
) -> str:
    """返回 source_tag。名单可注入替换（定制版/多账号各自不同）。"""
    self_nicks = self_nicks or SELF_NICKNAMES
    relative_nicks = relative_nicks or RELATIVE_NICKNAMES
    hook_words = hook_words or HOOK_WORDS
    if nickname in self_nicks or (username and nickname in self_nicks):
        return "自家回复"
    if nickname in relative_nicks:
        return "亲友自测"
    if any(w in (content or "") for w in hook_words):
        return "引子钩子"
    if username == "" and nickname:
        return "待核"        # 平台没给 username 的，不擅自认定自然流量
    return "自然流量"

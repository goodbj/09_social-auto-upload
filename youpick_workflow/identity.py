"""身份/来源判定策略（平台无关，中性层）。

判断一条留言是「自家回复 / 粉丝」两态——老泡儿 2026-11-14 拍板：
**「亲友自测」去掉，一视同仁都是粉丝**（不再分自然流量/待核/引子钩子）。
不放 core/ 也不放 platform/——两边都要用，提到包根当中性依赖，避免反向耦合。
"""
from __future__ import annotations


# 默认账号（向后兼容老数据）：视频号 · 丸小子998
SELF_NICKNAMES = {"丸小子998"}
# 以下两组名单保留常量定义（历史 import 兼容），但老泡儿 2026-11-14 拍板：不再参与判定，粉丝一视同仁
RELATIVE_NICKNAMES = {
    "对方正在输入中...",   # 老泡儿小号
    "磊", "红太狼~[emoji]", "梦中人9070", "景荣",
}
HOOK_WORDS = ("玻璃栈道", "海鸥", "灯塔", "下集让它", "咱下回")


def classify_source(
    nickname: str,
    username: str,
    content: str,
    *,
    self_nicks: set[str] | None = None,
    relative_nicks: set[str] | None = None,    # 已废弃，保留位兼容调用方
    hook_words: tuple[str, ...] | None = None,  # 已废弃，保留位兼容调用方
) -> str:
    """返回 source_tag：自家回复 / 粉丝（老泡儿 2026-11-14 拍板：一视同仁都是粉丝）。"""
    self_nicks = self_nicks or SELF_NICKNAMES
    if nickname in self_nicks or (username and nickname in self_nicks):
        return "自家回复"
    return "粉丝"

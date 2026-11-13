"""core 业务：互动裁决（赞/回/接话 的纯判断，无平台/无库依赖）。

只回答「这条该不该赞 / 该不该回 / 接什么话」，不碰浏览器、不碰库、不碰发送闸。
幂等（已成功过的不重复）由 runner 结合 store 在外层把关。

接话草稿按内容关键词挑、手写胡同串子口气、不去模板化群发——这是内容策略，不是平台逻辑，
保留在 core（内容决策层），但**产出一律是草稿，是否发送由 runner 的发送闸决定**。
"""
from __future__ import annotations

from youpick_workflow.connectors.base import Comment

# 有意思就赞的信号（看内容，不按赞排序）
LIKE_WORTHY = ("要是", "不如", "下一集", "能不能", "建议", "后来", "然后", "如果", "让它",
               "应该", "怎么", "为啥", "不信", "谦虚", "骄傲", "以假乱真", "技术", "画面",
               "敢", "信你", "炒菜", "颠勺", "玻璃栈道", "海鸥", "灯塔")

# 有回复时的接话草稿：按内容关键词挑，不模板化群发
REPLY_RULES = (
    (("谦虚", "骄傲"), "嗬，您这顶帽子扣得可真瓷实！得嘞，那咱就不客气，下回接着给您露一手。"),
    (("不信",), "嘿，您还不信？得嘞，那咱下回拿实物给您瞧瞧，您先蹲着看。"),
    (("炒菜", "颠勺"), "嘿，您这题出得够损的！得嘞，小猫颠勺这茬儿我记下了，回头让视频部捯饬一版，您给掌掌眼。"),
    (("玻璃栈道", "海鸥", "灯塔"), "您嘞，您这脑洞够局气！咱先把这集拍圆了，下回让您说的那景儿露个脸。"),
    (("怎么", "为啥"), "甭急，咱慢慢盘道——这茬儿底下有伏笔，下集给您揭。"),
    (("要是", "不如", "下一集", "能不能", "建议", "让它", "应该", "后来", "然后"),
     "得嘞，这主意我记下了！您这思路够局气的，回头咱就照着往下捋。"),
    (("技术", "画面", "以假乱真", "灵敏", "活灵活现"),
     "您嘞，谢您捧场！这活儿是拿 AI 做的，您想看哪儿的细节，留句话，咱下回照着来。"),
)
FALLBACK_REPLY = "嗬，您这话说的，咱记下了！甭急，下回接着盘道。"


def is_like_worthy(text: str) -> bool:
    return len(text or "") >= 4 and any(w in text for w in LIKE_WORTHY)


def should_reply(text: str) -> bool:
    """core 只判「内容值不值得接」；是否真发、回谁，由 runner 结合幂等/闸把关。"""
    return any(k in text for keys, _ in REPLY_RULES for k in keys)


def build_reply(text: str) -> str:
    """按内容挑接话草稿（纯文本，待人工过审后发）。"""
    for keys, reply in REPLY_RULES:
        if any(k in text for k in keys):
            return reply
    return FALLBACK_REPLY


def decide(c: Comment) -> dict:
    """给定一条留言，给出 core 的裁决（草稿级，不发送）。"""
    return {
        "comment_id": c.comment_id,
        "like_worthy": is_like_worthy(c.content),
        "reply_worthy": should_reply(c.content),
        "reply_draft": build_reply(c.content) if should_reply(c.content) else "",
        "source_tag": c.source_tag,
        "level": c.level,
    }

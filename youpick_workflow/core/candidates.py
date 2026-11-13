"""core 业务：候选筛选（第4步主体，纯函数，无平台/无库依赖）。

只决定「哪些留言有后续剧情潜力」，由老泡儿拍板，绝不擅自排序或发送。
"""
from __future__ import annotations

from youpick_workflow.connectors.base import Comment

_SPAM = ("加微", "私信我", "代发", "刷单", "兼职", "优惠券", "点击链接", "二维码")
_CREATIVE = ("要是", "不如", "下一集", "能不能", "建议", "后来", "然后", "如果", "让它", "应该")


def pick_valuable(comments: list[Comment], max_candidates: int = 5) -> list[dict]:
    """挑「值得回 / 有后续剧情潜力」的候选，**不按点赞数排序**（老泡儿拍板）。
    返回带 signals 的候选清单交给拍板人，不擅自决定拍哪条。
    """
    out: list[dict] = []
    for c in comments:
        txt = (c.content or "").strip()
        if len(txt) < 4 or any(w in txt for w in _SPAM):
            continue
        signals: list[str] = []
        if any(w in txt for w in _CREATIVE):
            signals.append("提了剧情走向/建议")
        if "?" in txt or "？" in txt or "怎么" in txt or "为啥" in txt:
            signals.append("在提问，接得上话")
        if len(txt) >= 20:
            signals.append("写得具体，有得聊")
        # like_count 仅作参考，不当排序依据
        if c.like_count >= 3:
            signals.append(f"有 {c.like_count} 赞（仅参考）")
        out.append({
            "comment_id": c.comment_id, "nickname": c.nickname, "text": txt,
            "like_count": c.like_count, "source_tag": c.source_tag,
            "signals": "；".join(signals) or "普普通通，留作备选",
        })
    return out[:max_candidates]

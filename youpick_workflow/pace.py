"""拟人节奏适配器：core 不直接戳 human_pace，只认这里暴露的接口。

把现有 `utils/human_pace.py` 包一层，满足 core.runner 的契约：
  - .session        : HumanSession（allow/consume）
  - .nap(...)       : 异步随机停顿（走预设区间或自定义）
  - .human_read(...) : 按字数算阅读时间
  - .consume_like()  : 点赞记账（只算「本次上线额度」，不进日回复数）
  - .consume_reply(id): 回复记账（进日回复数 + 已回名单，防重复回帖）

版本差异（日软上限、单账号/多账号）在 assemble 装配时传入 daily_cap / max_actions。
"""
from __future__ import annotations

from pathlib import Path

from utils.human_pace import HumanSession, nap as _nap, human_read as _read


class PaceAdapter:
    def __init__(self, daily_cap: int = 40, max_actions: tuple[int, int] = (3, 7)):
        self.session = HumanSession(daily_cap=daily_cap, max_actions=max_actions)

    @property
    def log_dir(self) -> Path:
        from utils.human_pace import STATE_FILE
        return STATE_FILE.parent

    async def nap(self, lo=None, hi=None, label="", kind=None, scale=1.0, distract=True):
        return await _nap(lo, hi, label, kind, scale, distract)

    async def human_read(self, text: str, label: str = "读留言", scale: float = 1.0):
        return await _read(text, label, scale)

    def consume_like(self) -> None:
        """点赞只进「本次上线额度」，不进日回复数（原脚本口径）。"""
        self.session.actions_done += 1
        self.session._save()

    def consume_reply(self, comment_id: str) -> None:
        self.session.consume(comment_id)

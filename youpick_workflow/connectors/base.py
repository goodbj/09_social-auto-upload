"""平台抽象层契约（唯二被 core 直接 import 的 platform 模块）。

铁律：core/ 只认这里的 `Comment` 数据结构和 `PlatformClient` 接口，
绝不直接认任何平台 SDK / 平台字段名 / edition。版本差异只准写在
`capabilities.py` + `assemble.py`。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Comment:
    """平台无关的统一留言结构。core 只认它，不认微信字段名。"""
    comment_id: str
    root_id: str          # 顶层自身 id 或所属顶层 id
    level: int            # 1 顶层 / 2 楼中楼
    reply_to_id: str      # 该留言回复了谁（L2 才有意义）
    nickname: str
    username: str
    content: str
    content_hash: str     # 内容指纹，判是否变更
    like_count: int
    like_flag: int        # 1 = 本号已点过赞
    create_time: str
    display_flag: int
    source_tag: str       # 亲友自测 / 引子钩子 / 自然流量 / 自家回复 / 待核
    raw_json: str         # 原始平台响应，回帖时原样回传


@dataclass
class ActionResult:
    ok: bool
    err_code: int | None
    raw: dict


class PlatformClient(ABC):
    """一个平台接入点的最小契约。"""

    @abstractmethod
    async def open(self) -> None:
        """打开浏览器/会话，使其 ready 可调用 read/like/reply。"""

    @abstractmethod
    async def close(self) -> None:
        """关闭会话，释放浏览器。"""

    @abstractmethod
    async def read_comments(self, export_id: str) -> list[Comment]:
        """读取某作品下的留言（顶层 + 楼中楼，已摊平成统一 Comment 列表）。"""

    @abstractmethod
    async def like(self, *, comment_id: str, export_id: str) -> ActionResult:
        """对一条留言点赞（scene=1 点赞 / 2 取消）。"""

    @abstractmethod
    async def reply(self, *, export_id: str, comment_id: str,
                    root_id: str, content: str, raw_json: str) -> ActionResult:
        """回复一条留言（顶层或楼中楼）。raw_json 为原平台 comment 对象。"""

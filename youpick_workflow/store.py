"""库适配器：core 不直接戳 interaction_store，只认这里暴露的接口。

把现有 `db/interaction_store.py` 包一层，满足 core.runner 的契约：
  - start_round(export_id, note, platform, account) → round_id
  - save_snapshot(round_id, comments)  # comments 是 Comment 列表
  - previous_snapshot(round_id) → {comment_id: Comment}
  - action_succeeded(comment_id, kind, platform, account) → bool
  - log_action(round_id, comment_id, kind, ...) → void
  - save_candidate(round_id, candidate_dict) → void
  - finish_round(round_id, ...) → void
  - successful_actions(round_id) → 列表（含 action_id/comment_id/action_kind/content）
  - verify(action_id, verify_text) → void
  - summary(round_id) → dict

多平台多账号隔离在适配器内部走 account_id 分组，core 不用知道。
"""
from __future__ import annotations

from db import interaction_store as _store
from youpick_workflow.connectors.base import Comment


class StoreAdapter:
    def __init__(self, platform: str = "weixin", account: str = "丸小子998"):
        self.platform = platform
        self.account = account

    def start_round(self, export_id: str, note: str = "") -> int:
        return _store.start_round(export_id, note, self.platform, self.account)

    def save_snapshot(self, round_id: int, comments: list[Comment]) -> tuple[int, int]:
        """把 Comment 列表转成 interaction_store 要的 dict 格式。"""
        rows = [
            {
                "platform": self.platform,
                "account": self.account,
                "comment_id": c.comment_id,
                "root_id": c.root_id,
                "level": c.level,
                "reply_to_id": c.reply_to_id,
                "nickname": c.nickname,
                "username": c.username,
                "content": c.content,
                "content_hash": c.content_hash,
                "like_count": c.like_count,
                "like_flag": c.like_flag,
                "create_time": c.create_time,
                "display_flag": c.display_flag,
                "source_tag": c.source_tag,
                "raw_json": c.raw_json,
            }
            for c in comments
        ]
        return _store.save_snapshot(round_id, rows)

    def previous_snapshot(self, round_id: int) -> dict[str, Comment]:
        """返回 comment_id → Comment 映射。"""
        prev = _store.previous_snapshot_by_round(round_id)
        return {
            cid: Comment(
                comment_id=r["comment_id"], root_id=r["root_id"], level=r["level"],
                reply_to_id=r["reply_to_id"], nickname=r["nickname"], username=r["username"],
                content=r["content"], content_hash=r["content_hash"], like_count=r["like_count"],
                like_flag=r["like_flag"], create_time=r["create_time"], display_flag=r["display_flag"],
                source_tag=r["source_tag"], raw_json=r["raw_json"],
            )
            for cid, r in prev.items()
        }

    def action_succeeded(self, comment_id: str, kind: str) -> bool:
        return _store.action_succeeded(comment_id, kind, self.platform, self.account)

    def log_action(self, round_id: int, comment_id: str, kind: str, *,
                  target_nickname: str = "", target_text: str = "", content: str = "",
                  status: str = "success", err_code: int | None = None, verify: str = "",
                  response: dict | None = None) -> None:
        _store.log_action(round_id, comment_id, kind, target_nickname=target_nickname,
                          target_text=target_text, content=content, status=status,
                          err_code=err_code, verify=verify, response=response,
                          platform=self.platform, account=self.account)

    def save_candidate(self, round_id: int, c: dict) -> None:
        _store.save_candidate(round_id, c, self.platform, self.account)

    def finish_round(self, round_id: int, *, actions_done: int = 0, candidates_out: int = 0,
                     comments_seen: int = 0, new_count: int = 0, changed_count: int = 0,
                     status: str = "done") -> None:
        _store.finish_round(round_id, actions_done=actions_done, candidates_out=candidates_out,
                            comments_seen=comments_seen, new_count=new_count,
                            changed_count=changed_count, status=status)

    def successful_actions(self, round_id: int) -> list[dict]:
        """返回 action_id/comment_id/action_kind/content，供回读核验用。"""
        conn = _store.connect()
        try:
            return [dict(x) for x in conn.execute(
                "SELECT action_id,comment_id,action_kind,content FROM actions "
                "WHERE round_id=? AND status='success'", (round_id,)).fetchall()]
        finally:
            conn.close()

    def verify(self, action_id: int, verify_text: str) -> None:
        conn = _store.connect()
        try:
            conn.execute("UPDATE actions SET verify=? WHERE action_id=?", (verify_text, action_id))
            conn.commit()
        finally:
            conn.close()

    def summary(self, round_id: int) -> dict:
        return _store.summary(round_id)

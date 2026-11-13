"""微信视频号平台实现（PlatformClient 契约的具体落地）。

只负责「怎么跟视频号打交道」，不负责「赞谁/回谁/今天干几件」——那是 core/ 的活。
所有拟人节奏（nap/human_read）在调用处（core/runner 或 assemble）注入，本模块不内置节奏，
保证「防风控」是统一策略、不被平台实现偷偷改掉。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from youpick_workflow.connectors.base import ActionResult, Comment, PlatformClient

# ── 微信视频号 CGI 真源（2026-11-13 实测）──────────────────────────────
BASE = "https://channels.weixin.qq.com/platform/interaction/comment"
CGI = "/micro/interaction/cgi-bin/mmfinderassistant-bin/comment"
LIST_API = f"{CGI}/comment_list"
LIKE_API = f"{CGI}/like_comment"
CREATE_API = f"{CGI}/create_comment"

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class WeixinClient(PlatformClient):
    def __init__(
        self,
        profile_dir: str | Path,
        chrome_exe: str = CHROME_EXE,
        self_nick: str = "丸小子998",
        self_nicks: set[str] | None = None,
        relative_nicks: set[str] | None = None,
        hook_words: tuple[str, ...] | None = None,
    ):
        self.profile_dir = Path(profile_dir)
        self.chrome_exe = chrome_exe
        self.self_nick = self_nick
        self.self_nicks = self_nicks or {self_nick}
        self.relative_nicks = relative_nicks
        self.hook_words = hook_words
        self._pw = None
        self._ctx = None
        self._page = None

    # ── 会话管理 ────────────────────────────────────────────────────
    async def open(self) -> None:
        from patchright.async_api import async_playwright  # 局部 import，保持平台 SDK 可插拔
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir), executable_path=self.chrome_exe,
            headless=False, args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"])
        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        await self._page.goto(BASE, wait_until="domcontentloaded", timeout=120000)
        try:
            await self._page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass

    async def close(self) -> None:
        if self._ctx:
            await self._ctx.close()
        if self._pw:
            await self._pw.stop()

    # ── 底层 POST（含日志；节奏在外面注入） ─────────────────────────
    async def _post(self, api: str, body: dict) -> dict:
        r = await self._page.evaluate(
            """async ({api, body}) => {
                const r = await fetch(api, {method:'POST',
                    headers:{'Content-Type':'application/json'},
                    credentials:'include', body:JSON.stringify(body)});
                return {status:r.status, text:await r.text()};
            }""", {"api": api, "body": body})
        try:
            return json.loads(r["text"])
        except Exception:
            return {"raw": r["text"][:600]}

    # ── 读评 ───────────────────────────────────────────────────────
    async def read_comments(self, export_id: str) -> list[Comment]:
        lst = await self._post(LIST_API, {"lastBuff": "", "exportId": export_id,
                                          "commentSelection": False, "forMcn": False})
        if lst.get("errCode") != 0:
            raise RuntimeError(f"comment_list 失败: {json.dumps(lst, ensure_ascii=False)[:400]}")
        out: list[Comment] = []
        from youpick_workflow.identity import classify_source
        for top in (lst.get("data") or {}).get("comment") or []:
            tid = str(top.get("commentId") or "")
            out.append(self._to_comment(top, tid, 1, classify_source))
            for l2 in top.get("levelTwoComment") or []:
                out.append(self._to_comment(l2, tid, 2, classify_source))
        return out

    @staticmethod
    def _to_comment(c: dict, root_id: str, level: int, classify) -> Comment:
        text = str(c.get("commentContent") or "")
        nick = str(c.get("commentNickname") or "")
        uname = str(c.get("username") or "")
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return Comment(
            comment_id=str(c.get("commentId") or ""),
            root_id=root_id, level=level,
            reply_to_id=str(c.get("replyCommentId") or ""),
            nickname=nick, username=uname, content=text, content_hash=h,
            like_count=int(c.get("commentLikeCount") or 0),
            like_flag=int(c.get("likeFlag") or 0),
            create_time=str(c.get("commentCreatetime") or ""),
            display_flag=int(c.get("displayFlag") or 0),
            source_tag=classify(nick, uname, text),
            raw_json=json.dumps(c, ensure_ascii=False),
        )

    # ── 互动 ───────────────────────────────────────────────────────
    async def like(self, *, comment_id: str, export_id: str) -> ActionResult:
        res = await self._post(LIKE_API, {"commentId": comment_id, "scene": 1, "exportId": export_id})
        return ActionResult(ok=res.get("errCode") == 0, err_code=res.get("errCode"), raw=res)

    async def reply(self, *, export_id: str, comment_id: str, root_id: str,
                   content: str, raw_json: str) -> ActionResult:
        body = {"exportId": export_id, "replyCommentId": comment_id, "rootCommentId": root_id,
                "content": content, "clientId": str(uuid.uuid4()), "comment": json.loads(raw_json)}
        res = await self._post(CREATE_API, body)
        return ActionResult(ok=res.get("errCode") == 0, err_code=res.get("errCode"), raw=res)

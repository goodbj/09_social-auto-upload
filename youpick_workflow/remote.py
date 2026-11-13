"""YouPick 远程服务控制入口（产品侧封装，不碰部署服务端）。

卖服务不卖代码：本模块把已跑通的闭环包成「远程可调」的形态，远端后台只需读它吐的 JSON。
三个动作：
  - status : 读 DB 出健康/今日额度/最近轮次（供后台看客户号活没活）
  - run    : 拉起一轮闭环（前台可见、随机节奏、回读核验），跑完回执落库
  - report : 生成给客户的周报（互动量/候选/续费状态）

真发（run --approved）仍须老泡儿单独点头；本入口不替他拍板。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from youpick_workflow import capabilities as cap
from youpick_workflow.assemble import build
from youpick_workflow.core import workflow


def _db():
    from db import interaction_store as store
    store.init_db()
    return store


def cmd_status(edition: str, account: str) -> dict:
    """读本地库出客户号健康快照。"""
    store = _db()
    conn = store.connect()
    try:
        today = date.today().isoformat()
        replies_today = conn.execute(
            "SELECT COUNT(*) n FROM actions WHERE action_kind='reply' AND status='success' "
            "AND substr(at,1,10)=?", (today,)).fetchone()["n"]
        last = conn.execute(
            "SELECT round_id,started_at,status,actions_done,comments_seen,candidates_out "
            "FROM rounds ORDER BY round_id DESC LIMIT 1").fetchone()
        acc_rows = conn.execute(
            "SELECT platform,account,export_id,persona,daily_soft_cap FROM accounts").fetchall()
    finally:
        conn.close()
    ed = cap.get_edition(edition)
    return {
        "edition": edition, "account": account,
        "features_open": len(ed.features),
        "daily_soft_cap": ed.daily_soft_cap,
        "replies_today": replies_today,
        "last_round": dict(last) if last else None,
        "accounts": [dict(r) for r in acc_rows],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def cmd_run(edition: str, account: str, approved: bool, mode: str = "incremental") -> dict:
    cfg = build(edition, account=account, approved=approved, mode=mode)
    rid = asyncio.run(workflow.run_round(**cfg))
    return {"round_id": rid, "approved": approved, "mode": mode,
            "finished_at": datetime.now().isoformat(timespec="seconds")}


def cmd_report(edition: str, account: str, days: int = 7) -> dict:
    """给客户的周报：近期互动量 + 候选 + 续费状态。"""
    store = _db()
    conn = store.connect()
    try:
        total = conn.execute(
            "SELECT action_kind,COUNT(*) n FROM actions WHERE status='success' "
            "AND account=? GROUP BY action_kind", (account,)).fetchall()
        cand = conn.execute(
            "SELECT COUNT(*) n FROM candidates WHERE account=? AND decision='待拍板'",
            (account,)).fetchone()["n"]
        rounds = conn.execute(
            "SELECT COUNT(*) n FROM rounds WHERE account=? AND status='done'",
            (account,)).fetchone()["n"]
    finally:
        conn.close()
    by_kind = {r["action_kind"]: r["n"] for r in total}
    return {
        "account": account, "edition": edition,
        "window_days": days,
        "likes": by_kind.get("like", 0), "replies": by_kind.get("reply", 0),
        "rounds_done": rounds, "pending_candidates": cand,
        "renewal_status": "active" if by_kind.get("reply", 0) > 0 else "review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="YouPick 远程服务控制入口")
    p.add_argument("action", choices=["status", "run", "report"])
    p.add_argument("--edition", default=cap.DEFAULT_EDITION)
    p.add_argument("--account", default="丸小子998")
    p.add_argument("--mode", default="incremental", choices=["incremental", "full"])
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--approved", action="store_true", help="run 真发才带；不带=DRY RUN")
    p.add_argument("--json", action="store_true", help="只吐 JSON（供后台读）")
    a = p.parse_args()

    if a.action == "status":
        out = cmd_status(a.edition, a.account)
    elif a.action == "run":
        out = cmd_run(a.edition, a.account, a.approved, a.mode)
    else:
        out = cmd_report(a.edition, a.account, a.days)

    print(json.dumps(out, ensure_ascii=False, indent=2) if a.json else out)


if __name__ == "__main__":
    main()

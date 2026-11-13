"""第 5 步·拍板（老泡儿决定候选采纳/搁置）。

M2 落库的 candidates 默认 `待拍板`；本脚本出报告（按 round 分组、标信号），供老泡儿拍板。
改 `decision` 字段 = 库写入，按红线须老泡儿点头：默认 `--dry` 只出报告不写库；
带 `--apply --ids 1,2 --decision 采纳` 才落库（仍须老泡儿明确批准这一句）。

真源见 docs/product-development-plan.md M4 段。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from db import interaction_store as store


def _report(pending: list[dict]) -> dict:
    by_round: dict[int, list[dict]] = {}
    for c in pending:
        by_round.setdefault(c["round_id"], []).append(c)
    out = []
    for rid, items in sorted(by_round.items()):
        out.append({"round_id": rid, "candidates": [
            {"candidate_id": i["candidate_id"], "nickname": i["nickname"],
             "source_tag": i["source_tag"], "text": i["text"], "signals": i["signals"]}
            for i in items]})
    return {"pending_total": len(pending), "by_round": out}


def main() -> None:
    p = argparse.ArgumentParser(description="YouPick 候选拍板")
    p.add_argument("--account", default="丸小子998")
    p.add_argument("--dry", action="store_true", help="只出报告（默认）")
    p.add_argument("--apply", action="store_true", help="真改库（须老泡儿批准）")
    p.add_argument("--ids", help="逗号分隔的 candidate_id，配合 --apply")
    p.add_argument("--decision", choices=["采纳", "搁置"], default="采纳")
    a = p.parse_args()

    store.init_db()
    pending = store.list_pending_candidates(account=a.account)
    rep = _report(pending)

    if not a.apply:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        print(f"\n共 {rep['pending_total']} 条待拍板。拍板：--apply --ids 1,2 --decision 采纳（须老泡儿批准）")
        return

    # 真改库：红线——对外发送/改库须老泡儿单独点头，这里只承接他已批的指令
    ids = [int(x) for x in (a.ids or "").split(",") if x.strip()]
    if not ids:
        print("❌ --apply 须带 --ids"); return
    n = store.decide_candidates(ids, a.decision)
    print(f"✅ 已拍板 {n} 条 → {a.decision}")


if __name__ == "__main__":
    main()

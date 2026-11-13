"""第 6 步·派 11（把采纳候选打包成派工单，投给 11-ImageGen 图像视频部）。

11 号簇真源：`E:/AI/AI_Memory/知识库/11-ImageGen-图像视频部/`（主管 11_00，信道 `run_c4f2e504f048`）。
本职给下游 09 供 L2 视频生成插件——所以「派 11 做新集」= 把采纳的选题/痛点投过去，让它生成新视频。

本脚本：
- 读 `decision=采纳` 的候选 → 打包成派工 JSON（选题/痛点/目标平台=weixin）；
- 落 `dispatch_orders` 表（created 态）+ `data/dispatch/` 工单文件（本地留痕）；
- 真投递走 orca 信道须先 `orca terminal list` 确认 11 在线（不空发，红线）。

真源见 docs/product-development-plan.md M4 段。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from db import interaction_store as store

TARGET_CLUSTER = "11-ImageGen"
TARGET_RUN = "run_c4f2e504f048"
DISPATCH_DIR = Path(__file__).parent / "data" / "dispatch"


def build_payload(c: dict) -> dict:
    """候选 → 派工 JSON。选题从信号提炼，痛点用原文，目标平台固定 weixin（视频号）。"""
    return {
        "topic": c["text"],
        "signals": c["signals"],
        "source_tag": c["source_tag"],
        "nickname": c["nickname"],
        "target_platform": "weixin",
        "intent": "基于粉丝痛点/选题做新一期视频号内容（文生视频 / 图生视频）",
        "from_cluster": "09-YouPick",
        "from_run": "run_7a81c56a6a1a",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="YouPick 派 11 做新集")
    p.add_argument("--account", default="丸小子998")
    p.add_argument("--dry", action="store_true", help="只列将派工候选，不落库不投出（默认）")
    p.add_argument("--do", action="store_true", help="落库派工单 + 写工单文件（仍不投 orca，投出须 --send 且 11 在线）")
    p.add_argument("--send", action="store_true", help="真投 orca 信道（须先确认 11 在线，红线不空发）")
    a = p.parse_args()

    store.init_db()
    # 取采纳但未派工的候选
    conn = store.connect()
    try:
        adopted = [dict(x) for x in conn.execute(
            "SELECT * FROM candidates WHERE account=? AND decision='采纳' "
            "AND candidate_id NOT IN (SELECT candidate_id FROM dispatch_orders)",
            (a.account,)).fetchall()]
    finally:
        conn.close()

    if not adopted:
        print("✅ 无采纳待派工候选"); return

    print(f"将派工 {len(adopted)} 条采纳候选 → {TARGET_CLUSTER}（{TARGET_RUN}）")
    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    created = []
    for c in adopted:
        payload = build_payload(c)
        if a.dry:
            print(f"  [dry] #{c['candidate_id']} {c['nickname']}: {c['text'][:30]}")
            continue
        oid = store.create_dispatch_order(c["candidate_id"], payload, account=a.account,
                                         target_cluster=TARGET_CLUSTER, target_run=TARGET_RUN)
        f = DISPATCH_DIR / f"order_{oid:03d}.json"
        f.write_text(json.dumps({"order_id": oid, **payload}, ensure_ascii=False, indent=2), encoding="utf-8")
        created.append((oid, c["candidate_id"]))
        print(f"  ✅ 派工单 #{oid}（候选 {c['candidate_id']}）→ {f.name}")

    if a.do and not a.send:
        print(f"\n✅ 已落 {len(created)} 张派工单（created 态）。真投出须 --send 且确认 11 在线。")

    if a.send:
        # 真投递：先确认 11 在线（红线不空发），再走 orca 信道
        print("\n⚠️ --send 真投递需在 orca 终端确认 11 号簇在线后执行：")
        print(f"   orca terminal list   # 看 {TARGET_CLUSTER} connected")
        print(f"   orca orchestration run-use --id {TARGET_RUN}")
        print(f"   orca orchestration send --run {TARGET_RUN} --payload <order_XXX.json>")
        print("   投出后 store.dispatch_order(oid) 标 dispatched；11 回执 store.ack_dispatch_order(oid, result)")


if __name__ == "__main__":
    main()

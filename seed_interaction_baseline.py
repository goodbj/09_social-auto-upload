"""把 19:00 批次回读快照灌成「第 1 轮基线」（只建库，不碰平台、不发任何动作）。

用途：下一轮 `interaction_round.py` 才有上一轮可比，能真算出「半小时后新增了哪几条」。
跑了不幂等：用 `IF NOT EXISTS` 的轮次概念靠文件防重复，见 main() 里的 existing 判断。
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from db import interaction_store as store  # noqa: E402

BASE_DIR = Path(__file__).parent.resolve()
SNAPSHOT = BASE_DIR / "docs" / "probe_api_samples" / "batch_verify.json"
EXPORT_ID = "export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw"


def main() -> None:
    store.init_db()
    conn = store.connect()
    try:
        n = conn.execute("SELECT count(*) AS n FROM rounds").fetchone()["n"]
    finally:
        conn.close()
    if n:
        print(f"库里已有 {n} 轮，基线不用重灌。")
        return
    lst = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = store.flatten(lst)
    rid = store.start_round(EXPORT_ID, note="基线：19:00 亲友批回读快照（非巡检轮，历史补录）")
    store.save_snapshot(rid, rows)
    store.finish_round(rid, comments_seen=len(rows), status="done")
    s = store.summary(rid)
    print(f"✅ 基线轮 round_id={rid} | 留言 {s['comments_seen']} 条 | 状态 {s['status']}")
    print("   来源分布:", {x['source_tag']: x['n'] for x in s['source_breakdown']})


if __name__ == "__main__":
    main()

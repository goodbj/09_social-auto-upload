"""source_tag 规范化：老泡儿 2026-11-14 拍板「一视同仁都是粉丝」。

历史库里的 亲友自测 / 自然流量 / 待核 / 引子钩子 四态一律刷成「粉丝」；
自家回复 不动。本地镜像库标签规范化，不动平台、不动动作账。

用法：python db/migrate_source_tag_v3.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from db import interaction_store as store  # noqa: E402

OLD_TAGS = ("亲友自测", "自然流量", "待核", "引子钩子")


def main() -> None:
    store.init_db()
    conn = store.connect()
    try:
        before = {r["source_tag"]: r["n"] for r in conn.execute(
            "SELECT source_tag,count(*) n FROM comments GROUP BY source_tag")}
        n = 0
        for tag in OLD_TAGS:
            c = conn.execute("UPDATE comments SET source_tag='粉丝' WHERE source_tag=?", (tag,))
            n += c.rowcount
        # candidates 表同步（候选来源也一视同仁）
        for tag in OLD_TAGS:
            c = conn.execute("UPDATE candidates SET source_tag='粉丝' WHERE source_tag=?", (tag,))
            n += c.rowcount
        conn.commit()
        after = {r["source_tag"]: r["n"] for r in conn.execute(
            "SELECT source_tag,count(*) n FROM comments GROUP BY source_tag")}
        print(f"规范化前: {before}")
        print(f"规范化后: {after}")
        print(f"✅ 共刷 {n} 行 → 粉丝")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
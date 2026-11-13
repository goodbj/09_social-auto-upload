"""M1 重灌：用新 (platform, account) schema 重建本地镜像库，从磁盘原始快照回填。

数据源（都在磁盘，真源是平台）：
  - 基线快照：docs/probe_api_samples/batch_verify.json（19:00 全量，18 条）
  - 真发动作账（来自 logs/reply_batch_0413.log / maintain_fans_real.log / interaction_round_real.log）：
      点赞 6：小号顶层 / 磊 / 红太狼 / 玻璃栈道 / 景荣 / 小号L2「哼哼哼」
      回复 7：小号顶层(18:14) / 磊 / 红太狼 / 玻璃栈道 / Al / 景荣 / 小号L2
      round6 真发：like+reply → 小号L2「小猫炒菜」
      round8 真发：like+reply → 磊L2「过分谦虚」
     （Al 那条只回复不点赞，因为已被别人点过 likeFlag=1；主号自己那条跳过）
这些动作跨轮幂等靠 actions 表，重灌把真发过的补进去，防下一轮重复点赞变取消赞。
"""
import json, sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
from db import interaction_store as store  # noqa: E402

EXPORT_ID = store.DEFAULT_EXPORT_ID
SNAPSHOT = BASE / "docs" / "probe_api_samples" / "batch_verify.json"

# (comment_id, nickname, content 摘要, kind) —— 按 log 复原
REAL_ACTIONS = [
    ("15053885978871339652", "对方正在输入中...", "我擦，水上漂，这猫怎么不掉海里去", "like"),
    ("15053885978871339652", "对方正在输入中...", "我擦，水上漂，这猫怎么不掉海里去", "reply"),
    ("15053906621522446558", "磊", "以假乱真", "like"),
    ("15053906621522446558", "磊", "以假乱真", "reply"),
    ("15053882536466189845", "红太狼~[emoji]", "猫比狗的动作更灵敏", "like"),
    ("15053882536466189845", "红太狼~[emoji]", "猫比狗的动作更灵敏", "reply"),
    ("15053878757372794940", "梦中人9070", "水面下铺着一条玻璃栈道，小猫在水面奔跑", "like"),
    ("15053878757372794940", "梦中人9070", "水面下铺着一条玻璃栈道，小猫在水面奔跑", "reply"),
    ("15053881293666785334", "梦中人9070", "Al制作技术太神奇了", "reply"),
    ("15053873009070902626", "景荣", "画面活灵活现，作者利用Ai技术制作", "like"),
    ("15053873009070902626", "景荣", "画面活灵活现，作者利用Ai技术制作", "reply"),
    ("15053904638558935653", "对方正在输入中...", "哼哼哼，我不信", "like"),
    ("15053904638558935653", "对方正在输入中...", "哼哼哼，我不信", "reply"),
    ("15053926233306700385", "对方正在输入中...", "你敢做一个小猫炒菜的视频吗？", "like"),
    ("15053926233306700385", "对方正在输入中...", "你敢做一个小猫炒菜的视频吗？", "reply"),
    ("15053921514551511244", "磊", "过分谦虚就是骄傲", "like"),
    ("15053921514551511244", "磊", "过分谦虚就是骄傲", "reply"),
]


def main():
    import os
    db = store.DB_PATH
    for suffix in ("", "-wal", "-shm"):
        p = str(db) + suffix
        if os.path.exists(p):
            os.remove(p)
    store.init_db()
    aid = store.ensure_account(store.DEFAULT_PLATFORM, store.DEFAULT_ACCOUNT, EXPORT_ID, "M1 v2 重灌")
    print("account_id =", aid)

    lst = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = store.flatten(lst)
    rid = store.start_round(EXPORT_ID, note="M1 v2 重灌：19:00 全量快照 + 真发动作账复原")
    store.save_snapshot(rid, rows)
    for cid, nick, text, kind in REAL_ACTIONS:
        store.log_action(rid, cid, kind, target_nickname=nick, target_text=text,
                         status="success", err_code=0, verify="M1 重灌复原（历史真发）")
    store.finish_round(rid, actions_done=len(REAL_ACTIONS), comments_seen=len(rows),
                       new_count=len(rows), status="done")

    n = store.connect()
    try:
        for t in ["accounts", "rounds", "comments", "actions", "candidates"]:
            print(t, n.execute(f"SELECT count(*) n FROM {t}").fetchone()["n"])
    finally:
        n.close()
    # 幂等核验：这些 comment_id 对的动作应判定为「已成功」
    for cid, _, _, kind in REAL_ACTIONS[:4]:
        assert store.action_succeeded(cid, kind), f"幂等漏判 {cid}/{kind}"
    print("✅ M1 v2 重灌完成；真发动作幂等核验通过")


if __name__ == "__main__":
    main()

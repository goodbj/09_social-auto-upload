"""M1 迁移脚本：旧单账号库 → 新 (platform, account) 多账号库。

旧库：rounds/comments/actions/candidates 无 account_id。
新库：新增 accounts 表，所有表挂 account_id。
做法：旧文件改名 backup，建新库，注册默认账号(weixin/丸小子998)，把旧行按默认账号回填。
真源始终是平台，本地只是镜像，迁移安全。
"""
import sqlite3, shutil, datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
DB = BASE / "db" / "youpick_interaction.sqlite3"
OLD = BASE / "db" / "youpick_interaction_v1_backup.sqlite3"
import sys
sys.path.insert(0, str(BASE))
from db.interaction_store import (init_db, DB_PATH, DEFAULT_PLATFORM, DEFAULT_ACCOUNT,
                                 DEFAULT_EXPORT_ID, ensure_account, connect, now)  # noqa: E402

def q(row, *cols):
    return {c: row[c] for c in cols}

def main():
    shutil.copy(DB, OLD)
    print(f"旧库备份 -> {OLD.name}")
    # 把旧库挪出项目 db 目录，让 init_db 用新 schema 全新建表
    import os
    for suffix in ("", "-wal", "-shm"):
        p = str(DB) + suffix
        if os.path.exists(p):
            os.remove(p)
    print("旧库已移出（备份保留），init_db 建新表")
    init_db()
    aid = ensure_account(DEFAULT_PLATFORM, DEFAULT_ACCOUNT, DEFAULT_EXPORT_ID, "M1 迁移：旧单账号库")
    print("默认账号 account_id =", aid)

    old = sqlite3.connect(str(OLD)); old.row_factory = sqlite3.Row
    new = connect(); new.execute("PRAGMA foreign_keys=OFF")   # 可信回填，导入期间不校验外键
    try:
        # rounds
        for r in old.execute("SELECT * FROM rounds"):
            new.execute(
                "INSERT INTO rounds(account_id,platform,account,export_id,started_at,finished_at,"
                "comments_seen,new_count,changed_count,actions_done,candidates_out,status,note) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, DEFAULT_PLATFORM, DEFAULT_ACCOUNT, r["export_id"], r["started_at"],
                 r["finished_at"], r["comments_seen"], r["new_count"], r["changed_count"],
                 r["actions_done"], r["candidates_out"], r["status"], r["note"]))
        # comments
        for c in old.execute("SELECT * FROM comments"):
            new.execute(
                "INSERT OR IGNORE INTO comments(round_id,account_id,platform,account,comment_id,"
                "root_id,level,reply_to_id,nickname,username,content,content_hash,like_count,"
                "like_flag,create_time,display_flag,source_tag,raw_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c["round_id"], aid, DEFAULT_PLATFORM, DEFAULT_ACCOUNT, c["comment_id"], c["root_id"],
                 c["level"], c["reply_to_id"], c["nickname"], c["username"], c["content"],
                 c["content_hash"], c["like_count"], c["like_flag"], c["create_time"],
                 c["display_flag"], c["source_tag"], c["raw_json"]))
        # actions
        for a in old.execute("SELECT * FROM actions"):
            new.execute(
                "INSERT INTO actions(round_id,account_id,platform,account,comment_id,action_kind,"
                "target_nickname,target_text,content,status,err_code,verify,response_json,at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (a["round_id"], aid, DEFAULT_PLATFORM, DEFAULT_ACCOUNT, a["comment_id"],
                 a["action_kind"], a["target_nickname"], a["target_text"], a["content"],
                 a["status"], a["err_code"], a["verify"], a["response_json"], a["at"]))
        # candidates
        for c in old.execute("SELECT * FROM candidates"):
            new.execute(
                "INSERT OR IGNORE INTO candidates(round_id,account_id,platform,account,comment_id,"
                "nickname,text,like_count,source_tag,signals,decision,note,at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c["round_id"], aid, DEFAULT_PLATFORM, DEFAULT_ACCOUNT, c["comment_id"],
                 c["nickname"], c["text"], c["like_count"], c["source_tag"], c["signals"],
                 c["decision"], c["note"], c["at"]))
        new.commit()
    finally:
        old.close(); new.close()
    # 核验
    n = connect()
    try:
        for t in ["rounds","comments","actions","candidates","accounts"]:
            print(t, n.execute(f"SELECT count(*) n FROM {t}").fetchone()["n"])
    finally:
        n.close()
    print("✅ M1 迁移完成")

if __name__ == "__main__":
    main()

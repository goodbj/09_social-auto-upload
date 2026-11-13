"""core 业务：六步闭环调度（runner）。

把「读→比→赞/回→候选→核验→归档」编织起来。本文件**不 import 任何平台 SDK、不 import
interaction_store、不出现 edition**——所有外部能力都从构造器注入：
  - client      : connectors.base.PlatformClient（平台怎么发）
  - store       : 库适配器（平台是真源，库是镜像+留痕；按 account_id 隔离）
  - pace        : 节奏器（nap/human_read + HumanSession 闸，防风控统一策略）
  - gate        : 发送闸（approved / dry_run，对外动作须经老泡儿点头）

版本差异只在外层 assemble.py 决定「装哪些模块、开哪些开关」，core 永不动。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from youpick_workflow.connectors.base import Comment

import core.candidates as candidates
import core.interaction as interaction


def _stamp(msg: str, log_dir: Path | None = None) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line, flush=True)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "workflow.log").open("a", encoding="utf-8").write(line + "\n")


async def run_round(
    *, client,
    store,
    pace,
    export_id: str,
    approved: bool,
    archive_dir: Path,
    log_dir: Path,
    mode: str = "incremental",   # incremental=只对新留言动手；full=对全部未处理留言动手
    candidate_cap: int = 5,
    persona_reply: bool = True,
) -> int:
    """跑一轮六步闭环，返回 round_id。Platform/库/节奏/发送闸全部注入。

    store 适配器需实现：start_round / save_snapshot / previous_snapshot / action_succeeded /
                         log_action / save_candidate / finish_round / summary
    pace 需实现：HumanSession（allow/consume）+ 可 await 的 nap(kind) / human_read(text,label)
    """
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    _stamp(f"=== 闭环轮启动 | mode={mode} | approved={approved} ===", log_dir)

    sess = pace.session
    ok, why = sess.allow()
    if not ok:
        raise RuntimeError(f"会话闸没放行: {why}")
    _stamp(f"本次额度 {sess.max_actions} 件 | 日软上限 {sess.daily_cap}", log_dir)

    rid = store.start_round(export_id, note=f"闭环轮（{mode}）")
    _stamp(f"round_id={rid} | 本次额度 {sess.max_actions} 件", log_dir)

    await client.open()
    try:
        comments = await client.read_comments(export_id)
        store.save_snapshot(rid, comments)
        prev = store.previous_snapshot(rid)
        new_ids = {c.comment_id for c in comments} - set(prev.keys())
        _stamp(f"读到 {len(comments)} 条 | 新增 {len(new_ids)}", log_dir)

        # 归档原始响应快照（平台对象已含 raw_json，整轮落盘供复盘）
        (archive_dir / f"round_{rid:03d}_raw.json").write_text(
            json.dumps([json.loads(c.raw_json) for c in comments], ensure_ascii=False, indent=2),
            encoding="utf-8")

        # 第4步：候选搜集（不管发不发，先把有价值的取回来，交老泡儿拍板）
        cand = candidates.pick_valuable(comments, max_candidates=candidate_cap)
        saved = 0
        for c in cand:
            if c["signals"] == "普普通通，留作备选":
                continue
            store.save_candidate(rid, c)
            _stamp(f"  候选 [{c['source_tag']}] {c['nickname']}：{c['text'][:34]} | {c['signals']}", log_dir)
            saved += 1
            if saved >= candidate_cap:
                break

        # 第1~3步：对新留言（或全量未处理）动手
        acted = 0
        aborted = False
        targets: list[Comment] = (
            [c for c in comments if c.comment_id in new_ids] if mode == "incremental"
            else list(comments)
        )
        for c in targets:
            if c.source_tag == "自家回复":
                continue
            if sess.actions_done >= sess.max_actions:
                _stamp(f"本次额度 {sess.max_actions} 件用满，收工（宁慢勿猛）", log_dir)
                break

            dec = interaction.decide(c)
            name = c.nickname or "网友"

            # ① 点赞：内容有价值 + 没点过
            if dec["like_worthy"] and c.like_flag == 0 \
                    and not store.action_succeeded(c.comment_id, "like"):
                await pace.human_read(c.content, f"看{name}这条")
                await pace.nap(kind="click", label="点赞前核一眼")
                _stamp(f"① 点赞 → {name}「{c.content[:26]}」", log_dir)
                if approved:
                    res = await client.like(comment_id=c.comment_id, export_id=export_id)
                    store.log_action(rid, c.comment_id, "like", target_text=c.content,
                                     status="success" if res.ok else "failed",
                                     err_code=res.err_code, response=res.raw)
                    if res.ok:
                        acted += 1
                        pace.consume_like()
                        _stamp("   ✅ 点赞成功", log_dir)
                    else:
                        aborted = True
                        _stamp(f"   ❌ 点赞失败，停批: {res.raw}", log_dir)
                        break
                else:
                    _stamp("   DRY RUN，不发", log_dir)
                await pace.nap(kind="between_replies", label="歇一下")

            # ②③ 回复：内容值得接 + 幂等过关
            if dec["reply_worthy"] and not store.action_succeeded(c.comment_id, "reply") \
                    and sess.actions_done < sess.max_actions:
                ok2, why2 = sess.allow(c.comment_id)
                if not ok2:
                    _stamp(f"闸拦下 {c.comment_id}：{why2}", log_dir)
                    continue
                text = dec["reply_draft"]
                _stamp(f"②③ 回复 → {name}「{c.content[:26]}」" + (f" | 楼中楼 root={c.root_id}" if c.level == 2 else ""), log_dir)
                _stamp(f"     草稿: {text}", log_dir)
                await pace.nap(3, 8, "琢磨怎么接")
                await pace.human_read(text, "把草稿念一遍")
                if approved:
                    res = await client.reply(export_id=export_id, comment_id=c.comment_id,
                                             root_id=c.root_id, content=text, raw_json=c.raw_json)
                    store.log_action(rid, c.comment_id, "reply", target_text=c.content, content=text,
                                     status="success" if res.ok else "failed",
                                     err_code=res.err_code, response=res.raw)
                    if res.ok:
                        acted += 1
                        pace.consume_reply(c.comment_id)
                        _stamp(f"   ✅ 已回复 | 今日累计 {pace.session.state['replies']}", log_dir)
                    else:
                        aborted = True
                        _stamp(f"   ❌ 回复失败，停批: {res.raw}", log_dir)
                        break
                else:
                    _stamp("   DRY RUN，不发", log_dir)
                await pace.nap(kind="between_replies", label="两条之间歇会儿")

        # 回读硬核验
        await pace.nap(kind="settle", label="发完歇会儿再核")
        after = await client.read_comments(export_id)
        after_map = {c.comment_id: c for c in after}
        (archive_dir / f"round_{rid:03d}_verify.json").write_text(
            json.dumps([json.loads(c.raw_json) for c in after], ensure_ascii=False, indent=2),
            encoding="utf-8")
        if approved:
            for a in store.successful_actions(rid):
                o = after_map.get(a["comment_id"])
                if a["action_kind"] == "like":
                    v = f"likeFlag={o.like_flag if o else '没找着'}"
                else:
                    hit = any(a["content"][:12] in (x.content or "") for x in after)
                    v = "回读命中回复" if hit else "回读未命中（需人工看）"
                store.verify(a["action_id"], v)
                _stamp(f"核验 {a['action_kind']} {a['comment_id']}: {v}", log_dir)
        else:
            _stamp("DRY RUN：未产生对外动作", log_dir)

        # 第5步归档 + 第6步收工
        status = "aborted" if aborted else "done"
        store.finish_round(rid, actions_done=acted, candidates_out=saved,
                           comments_seen=len(comments), new_count=len(new_ids), status=status)
        _stamp(f"④⑤⑥ 结束 | status={status} | 动作 {acted} 件 | 候选 {saved} 条", log_dir)
        return rid
    finally:
        await client.close()

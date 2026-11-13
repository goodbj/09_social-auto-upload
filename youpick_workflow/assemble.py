"""版本装配层（版本差异的唯二落脚点之一，另一处是 capabilities.py）。

职责：按 capabilities 的 edition 配置，组装出「这一版该有的 runner 依赖」。
- 体验版：装只读+少量互动+单账号（daily_cap 低、max_actions 低、candidate_cap 低）；
- 标准版：全闭环+单账号+自托管；
- 至尊版：全装（多账号多平台、高额度、远程托管在 M3 接）。

core/ 完全不知道 edition，只接注入进来的 client/store/pace/gate。
本文件是「把 capabilities 翻译成具体模块参数」的唯一地方——新增平台只需加 platform 实现，
新增版本只需在 capabilities.py 登记 feature + 在这里加一个 if 分支。
"""
from __future__ import annotations

from pathlib import Path

from youpick_workflow import capabilities as cap
from youpick_workflow.pace import PaceAdapter
from youpick_workflow.store import StoreAdapter

# 默认浏览器 profile（视频号实现用；多账号时按 account 换目录在 assemble 里决定）
PROFILE_DIR = Path(__file__).parent.parent / "cookies" / "chrome_profile_tencent"
ARCHIVE_DIR = Path(__file__).parent.parent / "docs" / "round_archive"


def build_client(edition: str, *, platform: str, account: str, export_id: str):
    """按 edition 选平台实现。目前只落地了 weixin；douyin 在 M1 起预留。"""
    ed = cap.get_edition(edition)
    if platform not in ed.platforms:
        raise RuntimeError(f"版本 {edition} 不支持平台 {platform}（仅 {ed.platforms}）")
    if platform == "weixin":
        from youpick_workflow.connectors.weixin import WeixinClient
        return WeixinClient(profile_dir=PROFILE_DIR)
    raise NotImplementedError(f"platform {platform} 尚未实现（M1 起预留）")


def build(edition: str = cap.DEFAULT_EDITION, *,
          platform: str = "weixin", account: str = "丸小子998",
          export_id: str = "export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw",
          approved: bool = False, mode: str = "incremental"):
    """组装一版 runner 所需的全部依赖，返回给 core.runner.run_round 调用。"""
    ed = cap.get_edition(edition)
    if "single_account" in ed.features and "multi_account" not in ed.features:
        # 单账号版本：多账号入参一律拒收
        if account != "丸小子998":
            raise RuntimeError(f"版本 {edition} 为单账号，不可指定 {account}")
    client = build_client(edition, platform=platform, account=account, export_id=export_id)
    store = StoreAdapter(platform=platform, account=account)
    # 体验版额度更保守（引流、不猛）；至尊版放宽
    pace = PaceAdapter(daily_cap=ed.daily_soft_cap, max_actions=(3, 7))
    return {
        "client": client,
        "store": store,
        "pace": pace,
        "export_id": export_id,
        "approved": approved,
        "archive_dir": ARCHIVE_DIR,
        "log_dir": pace.log_dir,
        "mode": mode,
        # 体验版候选只做演示、封顶更少
        "candidate_cap": 2 if edition == "trial" else 5,
        "persona_reply": "persona_custom" in ed.features,
    }


if __name__ == "__main__":
    cap.validate()
    for key in ("trial", "standard", "premium"):
        cfg = build(key, approved=False, mode="incremental")
        print(f"{key:9s} | daily_cap={cfg['pace'].session.daily_cap} | "
              f"候选封顶 {cfg['candidate_cap']} | 平台 1/账号 1 | client={type(cfg['client']).__name__}")

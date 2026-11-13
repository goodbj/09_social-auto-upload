"""YouPick 视频工作流 · 命令行入口。

一句话触发（老泡儿自然话术）：
  python youpick_workflow/cli.py --task fans --approved          # 维护一下粉丝
  python youpick_workflow/cli.py --task round --approved         # 跑一轮巡检
  python youpick_workflow/cli.py --task fans --edition premium --mode full --approved

默认 dry_run（--approved 才真发）。默认至尊版全功能（capabilities.DEFAULT_EDITION）。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from youpick_workflow import capabilities as cap
from youpick_workflow.assemble import build
from youpick_workflow.core import workflow


async def _run(task: str, edition: str, approved: bool, mode: str,
               platform: str, account: str, export_id: str) -> None:
    cfg = build(edition, platform=platform, account=account, export_id=export_id,
                approved=approved, mode=mode)
    await workflow.run_round(**cfg)


def main() -> None:
    p = argparse.ArgumentParser(description="YouPick 视频工作流（粉丝维护 / 巡检）")
    p.add_argument("--task", choices=["fans", "round"], default="round", help="fans=全量维护；round=增量巡检")
    p.add_argument("--edition", default=cap.DEFAULT_EDITION, choices=list(cap.EDITIONS),
                   help="版本（默认至尊版全功能）")
    p.add_argument("--mode", default="incremental", choices=["incremental", "full"])
    p.add_argument("--platform", default="weixin")
    p.add_argument("--account", default="丸小子998")
    p.add_argument("--export-id", default="export/UzFfBgAAxKKvfAFEXVuQk8zT4DCaQNEF-86yppcDKTqY6HYtkw")
    p.add_argument("--approved", action="store_true", help="不带=DRY RUN 不发送；带=真发")
    args = p.parse_args()

    mode = "full" if args.task == "fans" else args.mode
    asyncio.run(_run(args.task, args.edition, args.approved, mode,
                     args.platform, args.account, args.export_id))


if __name__ == "__main__":
    main()

"""YouPick 视频工作流 · 版本能力开关（单一真源）。

铁律（老泡儿 2026-11-13）：
- 先按至尊版（全功能）开发，完全开发完再裁剪出普通版/体验版；
- **版本差异只准出现在本文件 + assemble.py**，core/ 里不准出现 edition 判断；
- 裁剪 = 换一份 capabilities + 少装模块，不动 core 逻辑。

新增功能时：先在 FEATURES 里登记 → 各版本按需要开放 → assemble 按 edition 装配。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Feature:
    """一个可开关的功能点。enabled 由各版本配置决定。"""
    key: str
    desc: str


# ── 功能清单（唯一登记处；版本只能引用这里的 key）──────────────────────────
FEATURES = {
    "publish":            Feature("publish",            "发布视频（零扫码）"),
    "read_comments":      Feature("read_comments",      "读评论"),
    "like_comment":       Feature("like_comment",       "点赞"),
    "reply_comment":      Feature("reply_comment",      "回复（含楼中楼）"),
    "candidate_collect":  Feature("candidate_collect",  "候选话题搜集/整理"),
    "human_pace":         Feature("human_pace",         "拟人节奏/防风控"),
    "draft_review":       Feature("draft_review",       "AI 草稿→人过审→发"),
    "single_account":     Feature("single_account",     "单账号"),
    "multi_account":      Feature("multi_account",      "多账号矩阵"),
    "single_platform":    Feature("single_platform",    "单平台"),
    "multi_platform":     Feature("multi_platform",     "多平台（抖音/小红书/快手…）"),
    "persona_custom":     Feature("persona_custom",     "定制人设"),
    "workflow_dispatch":  Feature("workflow_dispatch",  "闭环第4~6步：拍板→09↔11派工→新集"),
    "remote_hosting":     Feature("remote_hosting",     "远程托管"),
    "priority_support":   Feature("priority_support",   "优先客服/SLA"),
    "dashboard":          Feature("dashboard",          "数据看板/续费管理"),
}


@dataclass(frozen=True)
class Edition:
    key: str
    desc: str
    features: frozenset[str]          # 引用的都是 FEATURES 的 key
    daily_soft_cap: int = 40          # 单日互动软上限
    max_accounts: int = 1
    platforms: tuple[str, ...] = ("weixin",)


EDITIONS: dict[str, Edition] = {
    # 体验版：上手即见闭环，留钩子买标准/至尊
    "trial": Edition(
        key="trial",
        desc="体验版·引流：部分功能，上手即见闭环",
        features=frozenset({
            "publish", "read_comments", "like_comment", "reply_comment",
            "candidate_collect", "human_pace", "draft_review",
            "single_account", "single_platform",
        }),
        daily_soft_cap=20,
        max_accounts=1,
        platforms=("weixin",),
    ),
    # 标准版：全闭环、单账号、可自托管、定制人设
    "standard": Edition(
        key="standard",
        desc="标准版：全闭环·单账号·可自托管",
        features=frozenset({
            "publish", "read_comments", "like_comment", "reply_comment",
            "candidate_collect", "human_pace", "draft_review",
            "single_account", "single_platform", "persona_custom",
            "workflow_dispatch",
        }),
        daily_soft_cap=40,
        max_accounts=1,
        platforms=("weixin",),
    ),
    # 至尊版：全功能（多账号多平台+远程托管+定制人设+优先客服）
    "premium": Edition(
        key="premium",
        desc="至尊版：全功能·多账号多平台·远程托管",
        features=frozenset(FEATURES.keys()),
        daily_soft_cap=80,
        max_accounts=99,
        platforms=("weixin", "douyin", "xiaohongshu", "kuaishou"),
    ),
}

DEFAULT_EDITION = "premium"   # 开发顺序：至尊版优先（老泡儿 2026-11-13）


def get_edition(key: str = DEFAULT_EDITION) -> Edition:
    return EDITIONS.get(key, EDITIONS[DEFAULT_EDITION])


def has(feature: str, edition: str = DEFAULT_EDITION) -> bool:
    """core/ 之外（装配层、CLI、UI）用它判功能开关；core 内部不准用。"""
    return feature in get_edition(edition).features


def validate() -> None:
    """自检：所有 Edition.features 的 key 必须在 FEATURES 里登记。"""
    for ed in EDITIONS.values():
        unknown = ed.features - set(FEATURES)
        assert not unknown, f"{ed.key} 引用未登记功能: {unknown}"


if __name__ == "__main__":
    validate()
    for k, ed in EDITIONS.items():
        print(f"{k:9s} | 账号上限 {ed.max_accounts:3d} | 平台 {ed.platforms} | "
              f"日软上限 {ed.daily_soft_cap} | 功能 {len(ed.features)}/{len(FEATURES)}")

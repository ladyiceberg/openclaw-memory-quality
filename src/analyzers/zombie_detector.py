from __future__ import annotations
"""
zombie_detector.py · B1 僵尸条目识别

短期记忆中的"僵尸条目"：存活时间长、几乎不再被召回、或已晋升但仍占位的条目。
这些条目会虚高 recallCount，浪费存储，干扰晋升候选排序。

四条规则（全部来自产品规格文档 5.2，已锁定，不在业务代码里改阈值）：

  R1 single_recall_stale  : recallCount==1 AND 距今 > 90 天
  R2 long_inactive        : 距今 > 180 天（不管 recallCount）
  R3 no_concept_low_recall: conceptTags==[] AND recallCount < 3
  R4 promoted_and_stale   : 已晋升 AND 距今 promotedAt > 30 天

设计原则：
  - 四条规则相互独立，一条命中即判定为僵尸（OR 逻辑）
  - 返回第一条命中的规则名（最具解释性的那条）
  - 规则顺序按"确定性从高到低"排列：R1/R2 有明确时间阈值最确定
  - 时间比较用 days_since_iso()，已在 shortterm_reader.py 实现
"""

from dataclasses import dataclass, field
from typing import Optional

from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore, days_since_iso


# ── 阈值常量（集中定义，不在业务逻辑里硬编码）────────────────────────────────

SINGLE_RECALL_STALE_DAYS: float = 90.0   # R1：单次召回后超过 90 天未再召回
LONG_INACTIVE_DAYS: float = 180.0        # R2：180 天内没有任何召回
PROMOTED_STALE_DAYS: float = 30.0        # R4：已晋升超过 30 天

NO_CONCEPT_MAX_RECALL: int = 3           # R3：recallCount 严格小于 3


# ── 单条判断 ───────────────────────────────────────────────────────────────────

def is_zombie(entry: ShortTermEntry, now_ms: int) -> tuple[bool, str]:
    """
    判断单条短期记忆是否为僵尸。

    Args:
        entry  : 短期记忆条目
        now_ms : 当前时间（毫秒时间戳），由调用方传入，方便测试

    Returns:
        (True, rule_name)  如果是僵尸，rule_name 是触发的规则
        (False, "")        如果不是僵尸
    """
    days_since_last = days_since_iso(entry.last_recalled_at, now_ms)

    # R1：只被召回一次，且距今超过 90 天
    if entry.recall_count == 1 and days_since_last > SINGLE_RECALL_STALE_DAYS:
        return True, "single_recall_stale"

    # R2：距今超过 180 天（长时间完全不活跃）
    if days_since_last > LONG_INACTIVE_DAYS:
        return True, "long_inactive"

    # R3：无语义标签且召回次数极少（内容语义贫瘠，可能是 FTS 偶发命中）
    if len(entry.concept_tags) == 0 and entry.recall_count < NO_CONCEPT_MAX_RECALL:
        return True, "no_concept_low_recall"

    # R4：已晋升到 MEMORY.md，且距晋升超过 30 天（短期条目本身可以清理）
    if entry.promoted_at is not None:
        days_since_promoted = days_since_iso(entry.promoted_at, now_ms)
        if days_since_promoted > PROMOTED_STALE_DAYS:
            return True, "promoted_and_stale"

    return False, ""


# ── 聚合统计 ───────────────────────────────────────────────────────────────────

@dataclass
class ZombieStats:
    """B1 统计结果，供 health_check 工具使用。"""
    total: int                              # 总条目数
    zombie_count: int                       # 僵尸条目数
    zombie_ratio: float                     # 僵尸占比（0.0-1.0）
    by_rule: dict[str, int] = field(default_factory=dict)
    # 按规则分组的僵尸数量，key 为规则名：
    #   "single_recall_stale", "long_inactive",
    #   "no_concept_low_recall", "promoted_and_stale"


def compute_zombie_stats(store: ShortTermStore, now_ms: int) -> ZombieStats:
    """
    对整个 ShortTermStore 执行 B1 统计。

    Args:
        store  : 短期记忆全量数据
        now_ms : 当前时间（毫秒时间戳）

    Returns:
        ZombieStats
    """
    total = len(store.entries)
    zombie_count = 0
    by_rule: dict[str, int] = {
        "single_recall_stale": 0,
        "long_inactive": 0,
        "no_concept_low_recall": 0,
        "promoted_and_stale": 0,
    }

    for entry in store.entries:
        flag, rule = is_zombie(entry, now_ms)
        if flag:
            zombie_count += 1
            by_rule[rule] = by_rule.get(rule, 0) + 1

    zombie_ratio = zombie_count / total if total > 0 else 0.0

    return ZombieStats(
        total=total,
        zombie_count=zombie_count,
        zombie_ratio=zombie_ratio,
        by_rule=by_rule,
    )

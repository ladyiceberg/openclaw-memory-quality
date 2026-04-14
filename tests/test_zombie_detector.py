"""
test_zombie_detector.py · B1 僵尸条目识别测试

边界值测试原则：对每个时间阈值都测 n-1、n、n+1 天（严格 > 阈值）
"""
from pathlib import Path
from typing import List, Optional

import pytest

from src.analyzers.zombie_detector import (
    LONG_INACTIVE_DAYS,
    NO_CONCEPT_MAX_RECALL,
    PROMOTED_STALE_DAYS,
    SINGLE_RECALL_STALE_DAYS,
    ZombieStats,
    compute_zombie_stats,
    is_zombie,
)
from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

# 基准时间：2026-04-14T08:00:00Z（毫秒时间戳）
NOW_MS = 1776153600000

# 一天的毫秒数
DAY_MS = 86_400_000


def _iso(offset_days: float = 0.0) -> str:
    """
    生成距今 offset_days 天之前的 ISO 8601 字符串。
    offset_days=0 → 现在，offset_days=90 → 90 天前。
    """
    from datetime import datetime, timezone
    ts_ms = NOW_MS - int(offset_days * DAY_MS)
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _entry(
    *,
    recall_count: int = 3,
    total_score: float = 1.5,
    max_score: float = 0.6,
    concept_tags: Optional[List[str]] = None,
    last_recalled_days_ago: float = 10.0,
    first_recalled_days_ago: Optional[float] = None,
    promoted_days_ago: Optional[float] = None,
) -> ShortTermEntry:
    """构造一条 ShortTermEntry，用于测试。"""
    if concept_tags is None:
        concept_tags = ["test"]
    if first_recalled_days_ago is None:
        first_recalled_days_ago = last_recalled_days_ago

    promoted_at = _iso(promoted_days_ago) if promoted_days_ago is not None else None

    return ShortTermEntry(
        key="memory:memory/2026-04-01.md:1:10",
        path="memory/2026-04-01.md",
        start_line=1,
        end_line=10,
        source="memory",
        snippet="test snippet",
        recall_count=recall_count,
        total_score=total_score,
        max_score=max_score,
        first_recalled_at=_iso(first_recalled_days_ago),
        last_recalled_at=_iso(last_recalled_days_ago),
        query_hashes=["a1b2c3"],
        recall_days=["2026-04-04"],
        concept_tags=concept_tags,
        promoted_at=promoted_at,
    )


# ── R1：single_recall_stale ────────────────────────────────────────────────────

class TestR1SingleRecallStale:
    def test_not_zombie_at_threshold(self):
        """recallCount==1，恰好 90 天：不是僵尸（需 > 90）。"""
        entry = _entry(recall_count=1, last_recalled_days_ago=SINGLE_RECALL_STALE_DAYS)
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is False

    def test_zombie_just_over_threshold(self):
        """recallCount==1，90.01 天：是僵尸。"""
        entry = _entry(recall_count=1, last_recalled_days_ago=SINGLE_RECALL_STALE_DAYS + 0.01)
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "single_recall_stale"

    def test_zombie_well_over_threshold(self):
        """recallCount==1，120 天：是僵尸。"""
        entry = _entry(recall_count=1, last_recalled_days_ago=120)
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "single_recall_stale"

    def test_not_zombie_two_recalls_over_threshold(self):
        """recallCount==2（不是1），91 天：R1 不触发。"""
        entry = _entry(recall_count=2, last_recalled_days_ago=91)
        flag, _ = is_zombie(entry, NOW_MS)
        # R2 (>180天) 不触发，R3 需要 tags 为空，此处 tags 非空，所以正常
        assert flag is False

    def test_not_zombie_recent_single_recall(self):
        """recallCount==1，只过了 5 天：不是僵尸。"""
        entry = _entry(recall_count=1, last_recalled_days_ago=5)
        flag, _ = is_zombie(entry, NOW_MS)
        assert flag is False


# ── R2：long_inactive ──────────────────────────────────────────────────────────

class TestR2LongInactive:
    def test_not_zombie_at_threshold(self):
        """恰好 180 天：不是僵尸（需 > 180）。"""
        entry = _entry(recall_count=10, last_recalled_days_ago=LONG_INACTIVE_DAYS)
        flag, _ = is_zombie(entry, NOW_MS)
        assert flag is False

    def test_zombie_just_over_threshold(self):
        """180.01 天：是僵尸。"""
        entry = _entry(recall_count=10, last_recalled_days_ago=LONG_INACTIVE_DAYS + 0.01)
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "long_inactive"

    def test_zombie_one_year(self):
        """365 天不活跃：是僵尸。"""
        entry = _entry(recall_count=5, last_recalled_days_ago=365)
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "long_inactive"

    def test_r2_overrides_high_recall_count(self):
        """recall_count=100，但 181 天没被召回：R2 触发（不因 recallCount 高就豁免）。"""
        entry = _entry(recall_count=100, last_recalled_days_ago=181)
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "long_inactive"


# ── R3：no_concept_low_recall ──────────────────────────────────────────────────

class TestR3NoConceptLowRecall:
    def test_zombie_empty_tags_recall_1(self):
        """tags=[]，recallCount=1（<3）：是僵尸。"""
        entry = _entry(concept_tags=[], recall_count=1, last_recalled_days_ago=5)
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "no_concept_low_recall"

    def test_zombie_empty_tags_recall_2(self):
        """tags=[]，recallCount=2（<3）：是僵尸。"""
        entry = _entry(concept_tags=[], recall_count=2, last_recalled_days_ago=5)
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "no_concept_low_recall"

    def test_not_zombie_at_threshold(self):
        """tags=[]，recallCount=3（不满足 <3）：R3 不触发。"""
        entry = _entry(concept_tags=[], recall_count=NO_CONCEPT_MAX_RECALL, last_recalled_days_ago=5)
        flag, _ = is_zombie(entry, NOW_MS)
        assert flag is False

    def test_not_zombie_has_tags_low_recall(self):
        """有 tags，recallCount=1：R3 不触发。"""
        entry = _entry(concept_tags=["python"], recall_count=1, last_recalled_days_ago=5)
        # R1 也不触发（只过了5天），R2 不触发
        flag, _ = is_zombie(entry, NOW_MS)
        assert flag is False

    def test_r3_no_time_constraint(self):
        """R3 不依赖时间：tags=[]，recallCount=2，仅 1 天前召回：也是僵尸。"""
        entry = _entry(concept_tags=[], recall_count=2, last_recalled_days_ago=1)
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "no_concept_low_recall"


# ── R4：promoted_and_stale ─────────────────────────────────────────────────────

class TestR4PromotedAndStale:
    def test_zombie_promoted_over_threshold(self):
        """已晋升 30.01 天：是僵尸。"""
        entry = _entry(
            concept_tags=["test"],
            recall_count=5,
            last_recalled_days_ago=5,
            promoted_days_ago=PROMOTED_STALE_DAYS + 0.01,
        )
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "promoted_and_stale"

    def test_not_zombie_at_threshold(self):
        """恰好晋升 30 天：不是僵尸（需 > 30）。"""
        entry = _entry(
            concept_tags=["test"],
            recall_count=5,
            last_recalled_days_ago=5,
            promoted_days_ago=PROMOTED_STALE_DAYS,
        )
        flag, _ = is_zombie(entry, NOW_MS)
        assert flag is False

    def test_not_zombie_recently_promoted(self):
        """刚晋升 5 天：不是僵尸。"""
        entry = _entry(
            concept_tags=["test"],
            recall_count=5,
            last_recalled_days_ago=5,
            promoted_days_ago=5,
        )
        flag, _ = is_zombie(entry, NOW_MS)
        assert flag is False

    def test_not_zombie_not_promoted(self):
        """未晋升（promoted_at=None）：R4 不触发。"""
        entry = _entry(
            concept_tags=["test"],
            recall_count=5,
            last_recalled_days_ago=5,
            promoted_days_ago=None,
        )
        flag, _ = is_zombie(entry, NOW_MS)
        assert flag is False


# ── 规则优先级（多规则同时满足时触发第一个）──────────────────────────────────

class TestRulePriority:
    def test_r1_before_r3(self):
        """recallCount==1, tags==[], 91 天：R1 先于 R3 触发。"""
        entry = _entry(
            recall_count=1,
            concept_tags=[],
            last_recalled_days_ago=91,
        )
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "single_recall_stale"  # R1 排在 R3 前面

    def test_r2_before_r4(self):
        """181 天不活跃，且已晋升 31 天：R2 先于 R4 触发。"""
        entry = _entry(
            recall_count=5,
            concept_tags=["test"],
            last_recalled_days_ago=181,
            promoted_days_ago=31,
        )
        flag, rule = is_zombie(entry, NOW_MS)
        assert flag is True
        assert rule == "long_inactive"  # R2 排在 R4 前面


# ── compute_zombie_stats ───────────────────────────────────────────────────────

class TestComputeZombieStats:
    def _make_store(self, entries: List[ShortTermEntry]) -> ShortTermStore:
        from datetime import datetime, timezone
        now_iso = datetime.fromtimestamp(NOW_MS / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        return ShortTermStore(version=1, updated_at=now_iso, entries=entries)

    def test_empty_store(self):
        """空 store：zombie_count=0，ratio=0.0。"""
        store = self._make_store([])
        stats = compute_zombie_stats(store, NOW_MS)
        assert stats.total == 0
        assert stats.zombie_count == 0
        assert stats.zombie_ratio == pytest.approx(0.0)

    def test_all_healthy(self):
        """全部健康条目：僵尸数=0。"""
        entries = [_entry() for _ in range(5)]
        store = self._make_store(entries)
        stats = compute_zombie_stats(store, NOW_MS)
        assert stats.zombie_count == 0
        assert stats.zombie_ratio == pytest.approx(0.0)

    def test_all_zombies(self):
        """全部是僵尸：zombie_count=total，ratio=1.0。"""
        entries = [_entry(recall_count=1, last_recalled_days_ago=91) for _ in range(3)]
        store = self._make_store(entries)
        stats = compute_zombie_stats(store, NOW_MS)
        assert stats.zombie_count == 3
        assert stats.zombie_ratio == pytest.approx(1.0)

    def test_mixed(self):
        """2 僵尸 + 3 健康。"""
        entries = [
            _entry(recall_count=1, last_recalled_days_ago=91),  # R1
            _entry(last_recalled_days_ago=181),                 # R2
            _entry(),                                            # ok
            _entry(),                                            # ok
            _entry(),                                            # ok
        ]
        store = self._make_store(entries)
        stats = compute_zombie_stats(store, NOW_MS)
        assert stats.zombie_count == 2
        assert stats.zombie_ratio == pytest.approx(0.4)

    def test_by_rule_counts(self):
        """by_rule 按规则正确分组计数。"""
        entries = [
            _entry(recall_count=1, last_recalled_days_ago=91),   # R1
            _entry(recall_count=1, last_recalled_days_ago=91),   # R1
            _entry(last_recalled_days_ago=181),                  # R2
            _entry(concept_tags=[], recall_count=1, last_recalled_days_ago=5),  # R3
        ]
        store = self._make_store(entries)
        stats = compute_zombie_stats(store, NOW_MS)
        assert stats.by_rule["single_recall_stale"] == 2
        assert stats.by_rule["long_inactive"] == 1
        assert stats.by_rule["no_concept_low_recall"] == 1

    def test_returns_zombie_stats_type(self):
        """返回值是 ZombieStats 类型。"""
        store = self._make_store([_entry()])
        stats = compute_zombie_stats(store, NOW_MS)
        assert isinstance(stats, ZombieStats)

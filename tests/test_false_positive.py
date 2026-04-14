"""
test_false_positive.py · B2 假阳性检测测试

边界值测试：对 avg=0.34/0.35/0.36、max=0.54/0.55/0.56 等阈值边界分别测试
"""
from pathlib import Path
from typing import List, Optional

import pytest

from src.analyzers.false_positive import (
    AMBIGUOUS_AVG_HIGH,
    AMBIGUOUS_AVG_LOW,
    AMBIGUOUS_MAX_HIGH,
    AMBIGUOUS_MAX_LOW,
    CLEAR_FP_AVG_THRESHOLD,
    CLEAR_FP_MAX_THRESHOLD,
    HIGH_FREQ_MIN_RECALLS,
    FalsePositiveStats,
    classify_false_positive,
    compute_avg_score,
    compute_false_positive_stats,
)
from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _entry(
    *,
    recall_count: int = 3,
    total_score: float = 1.5,
    max_score: float = 0.7,
    concept_tags: Optional[List[str]] = None,
    promoted_at: Optional[str] = None,
) -> ShortTermEntry:
    """构造一条 ShortTermEntry 用于测试（仅设置影响 B2 的字段）。"""
    if concept_tags is None:
        concept_tags = ["test"]
    return ShortTermEntry(
        key="memory:memory/test.md:1:5",
        path="memory/test.md",
        start_line=1,
        end_line=5,
        source="memory",
        snippet="test snippet",
        recall_count=recall_count,
        total_score=total_score,
        max_score=max_score,
        first_recalled_at="2026-04-01T00:00:00.000Z",
        last_recalled_at="2026-04-14T00:00:00.000Z",
        query_hashes=["abc"],
        recall_days=["2026-04-14"],
        concept_tags=concept_tags,
        promoted_at=promoted_at,
    )


def _store(entries: List[ShortTermEntry]) -> ShortTermStore:
    return ShortTermStore(
        version=1,
        updated_at="2026-04-14T08:00:00.000Z",
        entries=entries,
    )


# ── compute_avg_score ─────────────────────────────────────────────────────────

class TestComputeAvgScore:
    def test_normal(self):
        """正常计算：totalScore / recallCount。"""
        entry = _entry(recall_count=4, total_score=2.0)
        assert compute_avg_score(entry) == pytest.approx(0.5)

    def test_zero_recalls(self):
        """recallCount=0：不除零，返回 0.0。"""
        entry = _entry(recall_count=0, total_score=0.0)
        assert compute_avg_score(entry) == pytest.approx(0.0)

    def test_single_recall(self):
        """recallCount=1：avg = totalScore。"""
        entry = _entry(recall_count=1, total_score=0.75)
        assert compute_avg_score(entry) == pytest.approx(0.75)


# ── classify_false_positive：阈值边界 ────────────────────────────────────────

class TestClassifyFalsePositiveThresholds:
    """
    专门测试阈值边界，确保 < vs <= 语义正确。
    HIGH_FREQ_MIN_RECALLS=5，即 recalls > 5 才算高频（6次开始）。
    CLEAR_FP_AVG_THRESHOLD=0.35，avg < 0.35 才算低质。
    CLEAR_FP_MAX_THRESHOLD=0.55，max < 0.55 才算"从未真正相关"。
    """

    # recalls 边界
    def test_not_high_freq_at_threshold(self):
        """recalls = HIGH_FREQ_MIN_RECALLS（5次）：不算高频，不触发 high_freq_low_quality。"""
        entry = _entry(recall_count=HIGH_FREQ_MIN_RECALLS, total_score=0.34 * HIGH_FREQ_MIN_RECALLS, max_score=0.3)
        cat, _ = classify_false_positive(entry)
        assert cat != "high_freq_low_quality"

    def test_high_freq_just_over_threshold(self):
        """recalls = HIGH_FREQ_MIN_RECALLS+1（6次）：算高频。"""
        entry = _entry(recall_count=HIGH_FREQ_MIN_RECALLS + 1, total_score=0.20 * (HIGH_FREQ_MIN_RECALLS + 1), max_score=0.3)
        cat, _ = classify_false_positive(entry)
        assert cat == "high_freq_low_quality"

    # avg 边界
    def test_avg_just_below_threshold(self):
        """avg = 0.349（< 0.35）+ 高频 + max<0.55：是 high_freq_low_quality。"""
        recalls = 10
        entry = _entry(recall_count=recalls, total_score=0.349 * recalls, max_score=0.3)
        cat, sub = classify_false_positive(entry)
        assert cat == "high_freq_low_quality"

    def test_avg_at_threshold_not_triggered(self):
        """avg = 0.35（不满足 < 0.35）：不是 high_freq_low_quality。"""
        recalls = 10
        entry = _entry(recall_count=recalls, total_score=CLEAR_FP_AVG_THRESHOLD * recalls, max_score=0.3)
        cat, _ = classify_false_positive(entry)
        assert cat != "high_freq_low_quality"

    def test_avg_just_above_threshold(self):
        """avg = 0.351（> 0.35）：不是 high_freq_low_quality。"""
        recalls = 10
        entry = _entry(recall_count=recalls, total_score=0.351 * recalls, max_score=0.3)
        cat, _ = classify_false_positive(entry)
        assert cat != "high_freq_low_quality"

    # max 边界（区分 never_truly_relevant vs occasional_hit）
    def test_max_below_threshold_never_truly_relevant(self):
        """avg<0.35 + recalls>5 + max=0.549（< 0.55）→ never_truly_relevant。"""
        recalls = 10
        entry = _entry(recall_count=recalls, total_score=0.30 * recalls, max_score=CLEAR_FP_MAX_THRESHOLD - 0.001)
        cat, sub = classify_false_positive(entry)
        assert cat == "high_freq_low_quality"
        assert sub == "never_truly_relevant"

    def test_max_at_threshold_occasional_hit(self):
        """avg<0.35 + recalls>5 + max=0.55（不满足 < 0.55）→ occasional_hit。"""
        recalls = 10
        entry = _entry(recall_count=recalls, total_score=0.30 * recalls, max_score=CLEAR_FP_MAX_THRESHOLD)
        cat, sub = classify_false_positive(entry)
        assert cat == "high_freq_low_quality"
        assert sub == "occasional_hit"

    def test_max_above_threshold_occasional_hit(self):
        """avg<0.35 + recalls>5 + max=0.8（>> 0.55）→ occasional_hit。"""
        recalls = 10
        entry = _entry(recall_count=recalls, total_score=0.30 * recalls, max_score=0.8)
        cat, sub = classify_false_positive(entry)
        assert cat == "high_freq_low_quality"
        assert sub == "occasional_hit"


# ── classify_false_positive：各类别 ──────────────────────────────────────────

class TestClassifyFalsePositiveCategories:
    def test_high_freq_low_quality_never_truly_relevant(self):
        """高频低质 + 从未真正相关。"""
        recalls = 10
        entry = _entry(recall_count=recalls, total_score=0.25 * recalls, max_score=0.4)
        cat, sub = classify_false_positive(entry)
        assert cat == "high_freq_low_quality"
        assert sub == "never_truly_relevant"

    def test_high_freq_low_quality_occasional_hit(self):
        """高频低质 + 偶发命中。"""
        recalls = 10
        entry = _entry(recall_count=recalls, total_score=0.25 * recalls, max_score=0.8)
        cat, sub = classify_false_positive(entry)
        assert cat == "high_freq_low_quality"
        assert sub == "occasional_hit"

    def test_semantic_void(self):
        """语义空洞：tags=[] + 高频（不满足低质阈值）。"""
        recalls = 10
        # avg=0.50（不低于0.35），所以不是 high_freq_low_quality
        entry = _entry(recall_count=recalls, total_score=0.50 * recalls, max_score=0.8, concept_tags=[])
        cat, sub = classify_false_positive(entry)
        assert cat == "semantic_void"
        assert sub == ""

    def test_ambiguous(self):
        """模糊区间：avg∈[0.35,0.55) AND max∈[0.55,0.75)。"""
        recalls = 3   # 不高频，所以不走 high_freq 分支
        avg = 0.45
        max_score = 0.65
        entry = _entry(recall_count=recalls, total_score=avg * recalls, max_score=max_score, concept_tags=["test"])
        cat, sub = classify_false_positive(entry)
        assert cat == "ambiguous"
        assert sub == ""

    def test_normal_high_avg(self):
        """正常：avg > 0.55。"""
        recalls = 5
        entry = _entry(recall_count=recalls, total_score=0.70 * recalls, max_score=0.9)
        cat, sub = classify_false_positive(entry)
        assert cat == ""
        assert sub == ""

    def test_normal_low_recall(self):
        """正常：召回次数少（不算高频），不触发任何规则。"""
        entry = _entry(recall_count=3, total_score=0.20 * 3, max_score=0.3, concept_tags=["test"])
        cat, sub = classify_false_positive(entry)
        assert cat == ""

    def test_zero_recalls_normal(self):
        """召回0次：avg=0.0，但 recalls 不满足高频（0<=5），正常。"""
        entry = _entry(recall_count=0, total_score=0.0, max_score=0.0)
        cat, sub = classify_false_positive(entry)
        assert cat == ""

    def test_high_freq_low_quality_priority_over_semantic_void(self):
        """tags=[] + 高频 + avg<0.35：high_freq_low_quality 优先于 semantic_void。"""
        recalls = 10
        entry = _entry(recall_count=recalls, total_score=0.20 * recalls, max_score=0.3, concept_tags=[])
        cat, sub = classify_false_positive(entry)
        assert cat == "high_freq_low_quality"  # 优先级 1 先于优先级 2


# ── 模糊区间精确边界 ──────────────────────────────────────────────────────────

class TestAmbiguousBoundaries:
    """
    模糊区间：AMBIGUOUS_AVG_LOW(0.35) <= avg < AMBIGUOUS_AVG_HIGH(0.55)
              AMBIGUOUS_MAX_LOW(0.55) <= max < AMBIGUOUS_MAX_HIGH(0.75)
    注意：需要 recalls 不高频（<=5），否则走 high_freq 分支
    """
    def _ambiguous_entry(self, avg: float, max_score: float) -> ShortTermEntry:
        recalls = 3  # 不高频
        return _entry(recall_count=recalls, total_score=avg * recalls, max_score=max_score, concept_tags=["test"])

    def test_avg_at_lower_bound(self):
        """avg = 0.35（下边界，包含）→ ambiguous（如果 max 也在区间内）。
        注意：直接设 total_score 避免浮点误差（0.35 * 3 = 1.05 浮点可能偏移）。
        """
        # 用 total_score=1.05, recalls=3 → avg = 0.35（精确）
        entry = _entry(recall_count=3, total_score=1.05, max_score=0.65)
        # 验证 avg 计算正确
        from src.analyzers.false_positive import compute_avg_score
        assert compute_avg_score(entry) == pytest.approx(0.35)
        cat, _ = classify_false_positive(entry)
        assert cat == "ambiguous"

    def test_avg_just_below_lower_bound(self):
        """avg = 0.349（低于下边界）+ recalls<=5 → 正常（不高频所以不是 high_freq_lq）。"""
        entry = self._ambiguous_entry(avg=AMBIGUOUS_AVG_LOW - 0.001, max_score=0.65)
        # recalls=3（不高频），avg<0.35 但不高频，所以不是 high_freq_low_quality
        # 但也不在模糊区间（avg < AMBIGUOUS_AVG_LOW）
        cat, _ = classify_false_positive(entry)
        assert cat == ""

    def test_avg_at_upper_bound_not_ambiguous(self):
        """avg = 0.55（上边界，不含）→ 不是 ambiguous。"""
        entry = self._ambiguous_entry(avg=AMBIGUOUS_AVG_HIGH, max_score=0.65)
        cat, _ = classify_false_positive(entry)
        assert cat == ""

    def test_max_at_lower_bound(self):
        """max = 0.55（下边界，包含）→ ambiguous。"""
        entry = self._ambiguous_entry(avg=0.45, max_score=AMBIGUOUS_MAX_LOW)
        cat, _ = classify_false_positive(entry)
        assert cat == "ambiguous"

    def test_max_at_upper_bound_not_ambiguous(self):
        """max = 0.75（上边界，不含）→ 不是 ambiguous。"""
        entry = self._ambiguous_entry(avg=0.45, max_score=AMBIGUOUS_MAX_HIGH)
        cat, _ = classify_false_positive(entry)
        assert cat == ""


# ── compute_false_positive_stats ─────────────────────────────────────────────

class TestComputeFalsePositiveStats:
    def test_empty_store(self):
        """空 store：所有计数为 0，健康分 100。"""
        stats = compute_false_positive_stats(_store([]))
        assert stats.total == 0
        assert stats.suspect_count == 0
        assert stats.retrieval_health_score == 100
        assert stats.promotion_risk_score == 0
        assert stats.fts_degradation_suspected is False

    def test_all_healthy(self):
        """全部健康条目：健康分高，可疑数=0。"""
        entries = [_entry(recall_count=3, total_score=0.8 * 3, max_score=0.9) for _ in range(10)]
        stats = compute_false_positive_stats(_store(entries))
        assert stats.suspect_count == 0
        assert stats.retrieval_health_score == 100
        assert stats.suspect_ratio == pytest.approx(0.0)

    def test_suspect_count_correct(self):
        """2 条高频低质 + 1 条语义空洞 → suspect_count=3。"""
        entries = [
            _entry(recall_count=10, total_score=0.25 * 10, max_score=0.3),  # high_freq_lq
            _entry(recall_count=10, total_score=0.25 * 10, max_score=0.3),  # high_freq_lq
            _entry(recall_count=10, total_score=0.50 * 10, max_score=0.8, concept_tags=[]),  # semantic_void
            _entry(),  # ok
        ]
        stats = compute_false_positive_stats(_store(entries))
        assert stats.high_freq_low_quality_count == 2
        assert stats.semantic_void_count == 1
        assert stats.suspect_count == 3
        assert stats.suspect_ratio == pytest.approx(3 / 4)

    def test_retrieval_health_decreases_with_suspects(self):
        """假阳性越多，健康分越低。"""
        # 全健康
        healthy = [_entry(recall_count=3, total_score=0.8 * 3, max_score=0.9) for _ in range(10)]
        stats_healthy = compute_false_positive_stats(_store(healthy))

        # 一半是高频低质
        bad = [_entry(recall_count=10, total_score=0.25 * 10, max_score=0.3) for _ in range(5)]
        mixed = healthy[:5] + bad
        stats_mixed = compute_false_positive_stats(_store(mixed))

        assert stats_healthy.retrieval_health_score > stats_mixed.retrieval_health_score

    def test_retrieval_health_score_range(self):
        """健康分在 0-100 范围内。"""
        entries = [_entry(recall_count=10, total_score=0.10 * 10, max_score=0.2) for _ in range(100)]
        stats = compute_false_positive_stats(_store(entries))
        assert 0 <= stats.retrieval_health_score <= 100

    def test_promotion_risk_only_unpromoted(self):
        """Promotion Risk 只统计尚未晋升（promoted_at=None）的条目中的假阳性比例。"""
        entries = [
            # 已晋升，高频低质 → 不算晋升风险（已经晋升了）
            _entry(recall_count=10, total_score=0.25 * 10, max_score=0.3, promoted_at="2026-04-01T00:00:00.000Z"),
            # 未晋升，高频低质 → 算晋升风险
            _entry(recall_count=10, total_score=0.25 * 10, max_score=0.3, promoted_at=None),
            # 未晋升，健康 → 不算晋升风险
            _entry(recall_count=3, total_score=0.8 * 3, max_score=0.9, promoted_at=None),
        ]
        stats = compute_false_positive_stats(_store(entries))
        # 未晋升 2 条，其中 1 条是假阳性 → risk = 50%
        assert stats.promotion_risk_score == 50

    def test_returns_false_positive_stats_type(self):
        """返回值是 FalsePositiveStats 类型。"""
        stats = compute_false_positive_stats(_store([_entry()]))
        assert isinstance(stats, FalsePositiveStats)

    def test_ambiguous_not_counted_in_suspect(self):
        """ambiguous 条目不计入 suspect_count（suspect 只含 high_freq_lq + semantic_void）。"""
        entries = [
            _entry(recall_count=3, total_score=0.45 * 3, max_score=0.65),  # ambiguous（avg=0.45, max=0.65）
            # 明确正常条目：avg=0.80 >> 0.55，不进 ambiguous
            _entry(recall_count=3, total_score=0.80 * 3, max_score=0.95),  # ok
        ]
        stats = compute_false_positive_stats(_store(entries))
        assert stats.ambiguous_count == 1
        assert stats.suspect_count == 0  # ambiguous 不算 suspect


# ── 真实数据回归测试 ───────────────────────────────────────────────────────────

class TestRealFixture:
    REAL_PATH = Path("tests/fixtures/real/memory/.dreams/short-term-recall.json")

    def test_real_data_classifies_without_error(self):
        """真实数据：所有条目分类无报错，返回合法类别。"""
        if not self.REAL_PATH.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.readers.shortterm_reader import read_shortterm_from_path
        store = read_shortterm_from_path(self.REAL_PATH)

        valid_cats = {"high_freq_low_quality", "semantic_void", "ambiguous", ""}
        for entry in store.entries:
            cat, sub = classify_false_positive(entry)
            assert cat in valid_cats

    def test_real_data_stats_in_range(self):
        """真实数据：聚合统计结果合法（分数在范围内，计数非负）。"""
        if not self.REAL_PATH.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.readers.shortterm_reader import read_shortterm_from_path
        store = read_shortterm_from_path(self.REAL_PATH)
        stats = compute_false_positive_stats(store)

        assert stats.total == len(store.entries)
        assert stats.suspect_count >= 0
        assert 0 <= stats.retrieval_health_score <= 100
        assert 0 <= stats.promotion_risk_score <= 100
        assert 0.0 <= stats.suspect_ratio <= 1.0

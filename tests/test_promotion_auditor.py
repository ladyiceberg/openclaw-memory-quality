"""
test_promotion_auditor.py · Layer 2 晋升前质量预检单元测试

覆盖：
  - estimate_promotion_score：六维评分各分量
  - check_gate1_source：来源文件存在性
  - check_gate2_content：内容有效性（低价值检测）
  - check_gate3_duplicate：与 MEMORY.md 重复
  - check_gate4_false_positive：假阳性信号
  - build_promoted_set：已晋升集合构建
  - run_promotion_audit：完整流程
"""
import math
import tempfile
from pathlib import Path
from typing import Optional

import pytest

from src.analyzers.promotion_auditor import (
    PromotionAuditResult,
    PromotionCandidate,
    PromotionScore,
    _FP_AVG_THRESHOLD,
    _FP_MAX_THRESHOLD,
    _RECENCY_HALF_LIFE_DAYS,
    build_promoted_set,
    check_gate1_source,
    check_gate2_content,
    check_gate3_duplicate,
    check_gate4_false_positive,
    estimate_promotion_score,
    run_promotion_audit,
)
from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore
from src.readers.longterm_reader import LongTermStore, MemorySection, MemoryItem


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

# 固定时间戳：2026-04-15 00:00:00 UTC（毫秒）
_NOW_MS = 1744675200000

def _iso(days_ago: float) -> str:
    """生成距今 N 天前的 ISO 8601 字符串。"""
    ts = _NOW_MS / 1000 - days_ago * 86400
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _entry(
    key: str = "memory:memory/f.md:1:5",
    path: str = "memory/f.md",
    start: int = 1,
    end: int = 5,
    snippet: str = "Gateway binds loopback and port 18789",
    recall_count: int = 5,
    total_score: float = 4.0,     # avg = 0.80
    max_score: float = 0.92,
    query_hashes: Optional[list] = None,
    concept_tags: Optional[list] = None,
    last_recalled_at: Optional[str] = None,
    promoted_at: Optional[str] = None,
) -> ShortTermEntry:
    return ShortTermEntry(
        key=key,
        path=path,
        start_line=start,
        end_line=end,
        source="memory",
        snippet=snippet,
        recall_count=recall_count,
        total_score=total_score,
        max_score=max_score,
        first_recalled_at=_iso(10),
        last_recalled_at=last_recalled_at or _iso(1),
        query_hashes=["h1", "h2", "h3"] if query_hashes is None else query_hashes,
        recall_days=["2026-04-14"],
        concept_tags=["gateway", "port"] if concept_tags is None else concept_tags,
        promoted_at=promoted_at,
    )


def _store(entries: list) -> ShortTermStore:
    return ShortTermStore(version=1, updated_at=_iso(0), entries=entries)


def _lt_store(items: list[tuple]) -> LongTermStore:
    """
    快速构造 LongTermStore。
    items: list of (source_path, start_line, end_line)
    """
    section = MemorySection(date="2026-04-14")
    for path, start, end in items:
        section.items.append(MemoryItem(
            snippet="test", score=0.9, recalls=3, avg_score=0.75,
            source_path=path, source_start=start, source_end=end,
        ))
    return LongTermStore(
        sections=[section],
        total_items=len(items),
        manual_content_lines=0,
        manual_content_chars=0,
        has_manual_content=False,
        format_name="source_code",
        raw_char_count=100,
        parsed_char_count=100,
    )


# ── estimate_promotion_score ───────────────────────────────────────────────────

class TestEstimatePromotionScore:
    def test_returns_promotion_score_type(self):
        """返回 PromotionScore 类型。"""
        e = _entry()
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert isinstance(s, PromotionScore)

    def test_composite_in_range(self):
        """综合分在 [0, 1] 范围内。"""
        e = _entry()
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert 0.0 <= s.composite <= 1.0

    def test_all_dimensions_in_range(self):
        """所有分量都在 [0, 1]。"""
        e = _entry()
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        for dim in [s.frequency, s.relevance, s.diversity, s.recency, s.conceptual]:
            assert 0.0 <= dim <= 1.0

    def test_frequency_zero_recall_count(self):
        """recall_count=0 → frequency=0。"""
        e = _entry(recall_count=0, total_score=0.0)
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.frequency == pytest.approx(0.0)

    def test_frequency_recall_count_10(self):
        """recall_count=10 → frequency = log(11)/log(11) = 1.0。"""
        e = _entry(recall_count=10)
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.frequency == pytest.approx(1.0, abs=1e-9)

    def test_relevance_equals_avg_score(self):
        """relevance 等于 totalScore/recallCount。"""
        e = _entry(recall_count=4, total_score=3.0)  # avg = 0.75
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.relevance == pytest.approx(0.75)
        assert s.avg_score == pytest.approx(0.75)

    def test_diversity_capped_at_1(self):
        """queryHashes >= 5 → diversity = 1.0。"""
        e = _entry(query_hashes=["h1", "h2", "h3", "h4", "h5", "h6"])
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.diversity == pytest.approx(1.0)

    def test_diversity_proportional(self):
        """queryHashes = 2 → diversity = 0.4。"""
        e = _entry(query_hashes=["h1", "h2"])
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.diversity == pytest.approx(0.4)

    def test_recency_fresh_entry_near_1(self):
        """刚被召回（0天前）→ recency ≈ 1.0。"""
        e = _entry(last_recalled_at=_iso(0))
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.recency > 0.99

    def test_recency_half_life(self):
        """距今 14 天（半衰期）→ recency ≈ 0.5。"""
        e = _entry(last_recalled_at=_iso(_RECENCY_HALF_LIFE_DAYS))
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.recency == pytest.approx(0.5, abs=0.01)

    def test_recency_old_entry_near_0(self):
        """距今 100 天 → recency 非常小。"""
        e = _entry(last_recalled_at=_iso(100))
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.recency < 0.05

    def test_conceptual_capped_at_1(self):
        """conceptTags >= 6 → conceptual = 1.0。"""
        e = _entry(concept_tags=["a", "b", "c", "d", "e", "f", "g"])
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.conceptual == pytest.approx(1.0)

    def test_conceptual_zero_tags(self):
        """conceptTags = [] → conceptual = 0.0。"""
        e = _entry(concept_tags=[])
        s = estimate_promotion_score(e, now_ms=_NOW_MS)
        assert s.conceptual == pytest.approx(0.0)

    def test_higher_recall_count_higher_composite(self):
        """其他条件相同时，recall_count 更高 → composite 更高。"""
        low = _entry(recall_count=2, total_score=1.6)
        high = _entry(recall_count=8, total_score=6.4)
        s_low  = estimate_promotion_score(low,  now_ms=_NOW_MS)
        s_high = estimate_promotion_score(high, now_ms=_NOW_MS)
        assert s_high.composite > s_low.composite

    def test_now_ms_none_uses_system_time(self):
        """now_ms=None 时不崩溃（使用系统时间）。"""
        e = _entry()
        s = estimate_promotion_score(e, now_ms=None)
        assert isinstance(s, PromotionScore)
        assert 0.0 <= s.composite <= 1.0


# ── check_gate1_source ─────────────────────────────────────────────────────────

class TestGate1Source:
    def test_file_exists_returns_none(self):
        """来源文件存在 → 返回 None（通过）。"""
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "memory").mkdir()
            (ws / "memory" / "f.md").write_text("content")
            e = _entry(path="memory/f.md")
            assert check_gate1_source(e, str(ws)) is None

    def test_file_missing_returns_skip_reason(self):
        """来源文件不存在 → 返回 'source_deleted'。"""
        with tempfile.TemporaryDirectory() as d:
            e = _entry(path="memory/missing.md")
            assert check_gate1_source(e, d) == "source_deleted"

    def test_nested_path_resolved_correctly(self):
        """嵌套路径 memory/subdir/f.md 正确拼接 workspace。"""
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "memory" / "subdir").mkdir(parents=True)
            (ws / "memory" / "subdir" / "f.md").write_text("x")
            e = _entry(path="memory/subdir/f.md")
            assert check_gate1_source(e, str(ws)) is None


# ── check_gate2_content ────────────────────────────────────────────────────────

class TestGate2Content:
    # ── 正常内容（应通过）────────────────────────────────────────────────────

    def test_normal_code_passes(self):
        """正常代码 snippet → 通过。"""
        e = _entry(snippet="Gateway binds loopback and port 18789")
        assert check_gate2_content(e) is None

    def test_function_definition_passes(self):
        """函数定义 → 通过。"""
        e = _entry(snippet="def process_data(items): return [x for x in items if x]")
        assert check_gate2_content(e) is None

    def test_import_with_code_passes(self):
        """import + 实质代码混合 → 通过。"""
        e = _entry(snippet="import os def get_path(): return os.path.join('a', 'b')")
        assert check_gate2_content(e) is None

    # ── debug_code ─────────────────────────────────────────────────────────────

    def test_console_log_detected(self):
        """含 console.log → debug_code。"""
        e = _entry(snippet="console.log(result)")
        assert check_gate2_content(e) == "debug_code"

    def test_console_warn_detected(self):
        """含 console.warn → debug_code。"""
        e = _entry(snippet="console.warn('something went wrong')")
        assert check_gate2_content(e) == "debug_code"

    def test_print_detected(self):
        """含 print( → debug_code。"""
        e = _entry(snippet="print(result)")
        assert check_gate2_content(e) == "debug_code"

    def test_pdb_detected(self):
        """含 pdb.set_trace → debug_code。"""
        e = _entry(snippet="pdb.set_trace()")
        assert check_gate2_content(e) == "debug_code"

    def test_breakpoint_detected(self):
        """含 breakpoint() → debug_code。"""
        e = _entry(snippet="breakpoint()")
        assert check_gate2_content(e) == "debug_code"

    def test_debugger_detected(self):
        """含 debugger → debug_code。"""
        e = _entry(snippet="debugger")
        assert check_gate2_content(e) == "debug_code"

    # ── boilerplate ────────────────────────────────────────────────────────────

    def test_only_braces_is_boilerplate(self):
        """只有括号 → boilerplate。"""
        e = _entry(snippet="{ }")
        assert check_gate2_content(e) == "boilerplate"

    def test_empty_snippet_is_boilerplate(self):
        """空 snippet → boilerplate。"""
        e = _entry(snippet="")
        assert check_gate2_content(e) == "boilerplate"

    def test_only_whitespace_is_boilerplate(self):
        """只有空白 → boilerplate。"""
        e = _entry(snippet="   ")
        assert check_gate2_content(e) == "boilerplate"

    # ── import_only ────────────────────────────────────────────────────────────

    def test_single_import_detected(self):
        """只有 import 语句 → import_only。"""
        e = _entry(snippet="import os")
        assert check_gate2_content(e) == "import_only"

    def test_from_import_detected(self):
        """from ... import ... → import_only。"""
        e = _entry(snippet="from pathlib import Path")
        assert check_gate2_content(e) == "import_only"

    # ── comments_only ──────────────────────────────────────────────────────────

    def test_python_comment_only(self):
        """只有 # 注释 → comments_only。"""
        e = _entry(snippet="# this is a comment")
        assert check_gate2_content(e) == "comments_only"

    def test_js_comment_only(self):
        """只有 // 注释 → comments_only。"""
        e = _entry(snippet="// this is a comment")
        assert check_gate2_content(e) == "comments_only"

    def test_block_comment_only(self):
        """只有 /* 注释 → comments_only。"""
        e = _entry(snippet="/* block comment */")
        assert check_gate2_content(e) == "comments_only"


# ── check_gate3_duplicate ──────────────────────────────────────────────────────

class TestGate3Duplicate:
    def test_not_in_promoted_passes(self):
        """不在已晋升集合 → 通过。"""
        promoted = frozenset({("memory/other.md", 1, 5)})
        e = _entry(path="memory/f.md", start=1, end=5)
        assert check_gate3_duplicate(e, promoted) is None

    def test_exact_match_returns_already_promoted(self):
        """精确匹配 → already_promoted。"""
        promoted = frozenset({("memory/f.md", 1, 5)})
        e = _entry(path="memory/f.md", start=1, end=5)
        assert check_gate3_duplicate(e, promoted) == "already_promoted"

    def test_different_path_same_lines_passes(self):
        """路径不同但行号相同 → 通过（不同文件）。"""
        promoted = frozenset({("memory/other.md", 1, 5)})
        e = _entry(path="memory/f.md", start=1, end=5)
        assert check_gate3_duplicate(e, promoted) is None

    def test_same_path_different_lines_passes(self):
        """路径相同但行号不同 → 通过。"""
        promoted = frozenset({("memory/f.md", 6, 10)})
        e = _entry(path="memory/f.md", start=1, end=5)
        assert check_gate3_duplicate(e, promoted) is None

    def test_empty_promoted_set_passes(self):
        """空集合 → 通过。"""
        e = _entry()
        assert check_gate3_duplicate(e, frozenset()) is None


# ── check_gate4_false_positive ─────────────────────────────────────────────────

class TestGate4FalsePositive:
    def test_both_above_threshold_passes(self):
        """avg >= 0.45 AND maxScore >= 0.65 → 通过。"""
        e = _entry(max_score=0.70)
        assert check_gate4_false_positive(e, avg_score=0.50) is None

    def test_both_below_threshold_flags(self):
        """avg < 0.45 AND maxScore < 0.65 → potential_false_positive。"""
        e = _entry(max_score=0.60)
        assert check_gate4_false_positive(e, avg_score=0.40) == "potential_false_positive"

    def test_avg_below_but_max_above_passes(self):
        """avg < 0.45 但 maxScore >= 0.65 → 通过。"""
        e = _entry(max_score=0.70)
        assert check_gate4_false_positive(e, avg_score=0.40) is None

    def test_avg_above_but_max_below_passes(self):
        """avg >= 0.45 但 maxScore < 0.65 → 通过。"""
        e = _entry(max_score=0.60)
        assert check_gate4_false_positive(e, avg_score=0.50) is None

    def test_avg_exactly_threshold_passes(self):
        """avg == 0.45（边界，不触发）→ 通过。"""
        e = _entry(max_score=0.60)
        assert check_gate4_false_positive(e, avg_score=_FP_AVG_THRESHOLD) is None

    def test_max_exactly_threshold_passes(self):
        """maxScore == 0.65（边界，不触发）→ 通过。"""
        e = _entry(max_score=_FP_MAX_THRESHOLD)
        assert check_gate4_false_positive(e, avg_score=0.40) is None


# ── build_promoted_set ─────────────────────────────────────────────────────────

class TestBuildPromotedSet:
    def test_none_returns_empty(self):
        """lt_store=None → 空集合。"""
        assert build_promoted_set(None) == frozenset()

    def test_items_added_to_set(self):
        """LongTermStore 中的条目被加入集合。"""
        lt = _lt_store([("memory/f.md", 1, 5), ("memory/g.md", 3, 8)])
        ps = build_promoted_set(lt)
        assert ("memory/f.md", 1, 5) in ps
        assert ("memory/g.md", 3, 8) in ps

    def test_returns_frozenset(self):
        """返回类型是 frozenset。"""
        lt = _lt_store([("memory/f.md", 1, 5)])
        assert isinstance(build_promoted_set(lt), frozenset)

    def test_empty_lt_store(self):
        """LongTermStore 无条目 → 空集合。"""
        lt = _lt_store([])
        assert build_promoted_set(lt) == frozenset()


# ── run_promotion_audit（整体流程）────────────────────────────────────────────

class TestRunPromotionAudit:
    def test_empty_store_returns_empty_candidates(self):
        """无条目 → candidates 为空，不崩溃。"""
        store = _store([])
        with tempfile.TemporaryDirectory() as d:
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        assert result.candidates == []
        assert result.total_unpromotted == 0

    def test_returns_promotion_audit_result_type(self):
        """返回 PromotionAuditResult 类型。"""
        store = _store([_entry()])
        with tempfile.TemporaryDirectory() as d:
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        assert isinstance(result, PromotionAuditResult)

    def test_already_promoted_entries_excluded(self):
        """promoted_at 非 None 的条目不进入候选池。"""
        e_promoted = _entry(key="k1", path="memory/a.md", promoted_at=_iso(2))
        e_fresh    = _entry(key="k2", path="memory/b.md")
        store = _store([e_promoted, e_fresh])
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "memory").mkdir()
            (ws / "memory" / "b.md").write_text("x")
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        assert result.total_unpromotted == 1
        assert len(result.candidates) == 1
        assert result.candidates[0].entry.key == "k2"

    def test_top_n_limits_candidates(self):
        """top_n 限制候选数量。"""
        entries = [
            _entry(key=f"k{i}", path=f"memory/f{i}.md", recall_count=i+1,
                   total_score=float(i+1)*0.8)
            for i in range(20)
        ]
        store = _store(entries)
        with tempfile.TemporaryDirectory() as d:
            result = run_promotion_audit(store, d, top_n=5, now_ms=_NOW_MS)
        assert len(result.candidates) <= 5

    def test_candidates_sorted_by_composite_desc(self):
        """候选按 composite 降序排列。"""
        # 高分条目：recall_count=10，低分条目：recall_count=1
        e_high = _entry(key="high", path="memory/h.md", recall_count=10,
                        total_score=8.0, query_hashes=["h1","h2","h3","h4","h5"])
        e_low  = _entry(key="low",  path="memory/l.md", recall_count=1,
                        total_score=0.5, query_hashes=["h1"])
        store = _store([e_low, e_high])
        with tempfile.TemporaryDirectory() as d:
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        scores = [c.score.composite for c in result.candidates]
        assert scores == sorted(scores, reverse=True)

    def test_gate1_triggers_skip(self):
        """来源文件不存在 → verdict=skip, skip_reason=source_deleted。"""
        e = _entry(path="memory/missing.md")
        store = _store([e])
        with tempfile.TemporaryDirectory() as d:
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        assert result.candidates[0].verdict == "skip"
        assert result.candidates[0].skip_reason == "source_deleted"

    def test_gate2_triggers_skip(self):
        """低价值内容 → verdict=skip。"""
        e = _entry(path="memory/f.md", snippet="import os")
        store = _store([e])
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "memory").mkdir()
            (ws / "memory" / "f.md").write_text("x")
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        assert result.candidates[0].verdict == "skip"
        assert result.candidates[0].skip_reason == "import_only"

    def test_gate3_triggers_skip(self):
        """已在 MEMORY.md 中 → verdict=skip, skip_reason=already_promoted。"""
        e = _entry(path="memory/f.md", start=1, end=5)
        store = _store([e])
        lt = _lt_store([("memory/f.md", 1, 5)])
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "memory").mkdir()
            (ws / "memory" / "f.md").write_text("x")
            result = run_promotion_audit(store, d, lt_store=lt, now_ms=_NOW_MS)
        assert result.candidates[0].verdict == "skip"
        assert result.candidates[0].skip_reason == "already_promoted"

    def test_gate4_triggers_flag(self):
        """假阳性信号 → verdict=flag, flag_reason=potential_false_positive。"""
        # avg = 0.4 / 5 = 0.08，max = 0.30，均低于阈值
        e = _entry(path="memory/f.md", recall_count=5,
                   total_score=0.4, max_score=0.30)
        store = _store([e])
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "memory").mkdir()
            (ws / "memory" / "f.md").write_text("x")
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        assert result.candidates[0].verdict == "flag"
        assert result.candidates[0].flag_reason == "potential_false_positive"

    def test_healthy_entry_passes_all_gates(self):
        """健康条目通过全部关卡 → verdict=pass。"""
        e = _entry(path="memory/f.md", recall_count=5,
                   total_score=4.0, max_score=0.92)
        store = _store([e])
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "memory").mkdir()
            (ws / "memory" / "f.md").write_text("good content def func(): pass")
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        assert result.candidates[0].verdict == "pass"

    def test_gate1_blocks_gate2_check(self):
        """关卡 1 触发后跳过关卡 2（不重复标记）。"""
        # 文件不存在 + snippet 是 import，应该只报 source_deleted
        e = _entry(path="memory/missing.md", snippet="import os")
        store = _store([e])
        with tempfile.TemporaryDirectory() as d:
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        c = result.candidates[0]
        assert c.skip_reason == "source_deleted"
        assert c.flag_reason is None

    def test_pass_count_skip_count_flag_count(self):
        """pass/skip/flag 计数正确。"""
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "memory").mkdir()
            (ws / "memory" / "pass.md").write_text("def func(): return 42")
            (ws / "memory" / "flag.md").write_text("x")

            pass_e = _entry(key="k_pass", path="memory/pass.md",
                            recall_count=5, total_score=4.0, max_score=0.92)
            skip_e = _entry(key="k_skip", path="memory/missing.md")
            flag_e = _entry(key="k_flag", path="memory/flag.md",
                            recall_count=5, total_score=0.4, max_score=0.30)
            store = _store([pass_e, skip_e, flag_e])
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)

        assert result.pass_count == 1
        assert result.skip_count == 1
        assert result.flag_count == 1

    def test_no_lt_store_skips_gate3(self):
        """lt_store=None → 关卡 3 不触发（不因重复而 skip）。"""
        e = _entry(path="memory/f.md", start=1, end=5)
        store = _store([e])
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "memory").mkdir()
            (ws / "memory" / "f.md").write_text("def func(): return 1")
            # 不传 lt_store
            result = run_promotion_audit(store, d, lt_store=None, now_ms=_NOW_MS)
        assert result.candidates[0].skip_reason != "already_promoted"

    def test_top_n_default_is_10(self):
        """默认 top_n=10。"""
        entries = [
            _entry(key=f"k{i}", path=f"memory/f{i}.md")
            for i in range(20)
        ]
        store = _store(entries)
        with tempfile.TemporaryDirectory() as d:
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        assert result.top_n == 10

    def test_total_unpromotted_excludes_promoted(self):
        """total_unpromotted 只计未晋升条目数量。"""
        entries = [
            _entry(key="k1", path="memory/a.md"),
            _entry(key="k2", path="memory/b.md"),
            _entry(key="k3", path="memory/c.md", promoted_at=_iso(1)),
        ]
        store = _store(entries)
        with tempfile.TemporaryDirectory() as d:
            result = run_promotion_audit(store, d, now_ms=_NOW_MS)
        assert result.total_unpromotted == 2

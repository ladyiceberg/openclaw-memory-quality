"""
test_longterm_auditor.py · V1 + V3 审计测试

需要控制文件系统的测试用 tempfile.mkdtemp() 创建临时目录，
测试结束后自动清理。
"""
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional

import pytest

from src.analyzers.longterm_auditor import (
    AuditedItem,
    LongtermAuditResult,
    char_level_similarity,
    normalize_snippet,
    run_audit,
)
from src.readers.longterm_reader import (
    LongTermStore,
    MemoryItem,
    MemorySection,
)


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _item(
    source_path: str = "memory/2026-04-01.md",
    source_start: int = 1,
    source_end: int = 10,
    score: float = 0.9,
    snippet: str = "test snippet",
) -> MemoryItem:
    """构造一条 MemoryItem 用于测试。"""
    return MemoryItem(
        snippet=snippet,
        score=score,
        recalls=3,
        avg_score=0.7,
        source_path=source_path,
        source_start=source_start,
        source_end=source_end,
        promotion_key=None,
    )


def _store(sections_items: List[List[MemoryItem]]) -> LongTermStore:
    """
    构造 LongTermStore。
    sections_items: 每个元素是一个 section 的 item 列表。
    """
    sections = []
    for i, items in enumerate(sections_items):
        sections.append(MemorySection(
            date=f"2026-04-{14 - i:02d}",
            items=items,
            non_standard_lines=0,
        ))
    total = sum(len(s.items) for s in sections)
    return LongTermStore(
        sections=sections,
        total_items=total,
        manual_content_lines=0,
        manual_content_chars=0,
        has_manual_content=False,
        format_name="source_code",
        raw_char_count=1000,
        parsed_char_count=900,
    )


class TempWorkspace:
    """上下文管理器：创建临时 workspace 目录，测试结束后清理。"""
    def __init__(self):
        self.path: Path = Path(tempfile.mkdtemp())

    def create_file(self, rel_path: str, content: str = "test content") -> Path:
        """在 workspace 内创建一个文件，自动创建父目录。"""
        p = self.path / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def cleanup(self):
        shutil.rmtree(self.path, ignore_errors=True)


# ── normalize_snippet ─────────────────────────────────────────────────────────

class TestNormalizeSnippet:
    def test_multiline_becomes_single(self):
        """多行文本压缩为单行。"""
        result = normalize_snippet("hello\nworld\ntest")
        assert result == "hello world test"

    def test_leading_trailing_whitespace_stripped(self):
        """首尾空白去除。"""
        result = normalize_snippet("  hello world  ")
        assert result == "hello world"

    def test_multiple_spaces_collapsed(self):
        """多个空格压缩为一个。"""
        result = normalize_snippet("hello   world")
        assert result == "hello world"

    def test_tabs_replaced(self):
        """制表符替换为空格。"""
        result = normalize_snippet("hello\tworld")
        assert result == "hello world"

    def test_empty_string(self):
        """空字符串返回空字符串，不崩溃。"""
        result = normalize_snippet("")
        assert result == ""

    def test_already_normalized(self):
        """已经是单行的文本保持不变。"""
        result = normalize_snippet("hello world test")
        assert result == "hello world test"

    def test_mixed_whitespace(self):
        """混合空白符（换行+空格+制表符）全部压缩。"""
        result = normalize_snippet("hello\n  \t world\n")
        assert result == "hello world"


# ── char_level_similarity ─────────────────────────────────────────────────────

class TestCharLevelSimilarity:
    def test_identical(self):
        """完全相同 → 1.0。"""
        assert char_level_similarity("hello world", "hello world") == pytest.approx(1.0)

    def test_empty_both(self):
        """两个都空 → 1.0（视为相同）。"""
        assert char_level_similarity("", "") == pytest.approx(1.0)

    def test_one_empty(self):
        """一个空一个不空 → 0.0。"""
        assert char_level_similarity("abc", "") == pytest.approx(0.0)
        assert char_level_similarity("", "abc") == pytest.approx(0.0)

    def test_completely_different(self):
        """完全不同 → 接近 0.0（difflib 可能给小正值，< 0.1）。"""
        result = char_level_similarity("abcdef", "xyz123")
        assert result < 0.1

    def test_returns_float(self):
        """返回值是 float。"""
        result = char_level_similarity("hello", "world")
        assert isinstance(result, float)

    def test_range_zero_to_one(self):
        """返回值在 0.0-1.0 范围内。"""
        result = char_level_similarity("hello", "hell")
        assert 0.0 <= result <= 1.0

    def test_high_similarity_near_identical(self):
        """差一个字符：相似度 > 0.8。"""
        result = char_level_similarity("hello world", "hello world!")
        assert result > 0.8

    def test_normalized_multiline_matches_single(self):
        """normalize 后的多行与单行 snippet 相似度高。"""
        multiline = normalize_snippet("hello\nworld\ntest")   # → "hello world test"
        single = "hello world test"
        assert char_level_similarity(multiline, single) == pytest.approx(1.0)


# ── V1：来源文件存在性 ────────────────────────────────────────────────────────

class TestV1SourceFileExists:
    def test_exists(self):
        """来源文件存在 → action=keep，v1_status=exists。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md", "test content")
            item = _item(source_path="memory/2026-04-01.md")
            store = _store([[item]])
            result = run_audit(store, ws.path)

            assert len(result.items) == 1
            assert result.items[0].v1_status == "exists"
            assert result.items[0].action_hint == "keep"
        finally:
            ws.cleanup()

    def test_deleted(self):
        """来源文件不存在，workspace 内也无同名 → action=delete，v1_status=deleted。"""
        ws = TempWorkspace()
        try:
            # 不创建文件
            item = _item(source_path="memory/2026-04-01.md")
            store = _store([[item]])
            result = run_audit(store, ws.path)

            assert result.items[0].v1_status == "deleted"
            assert result.items[0].action_hint == "delete"
        finally:
            ws.cleanup()

    def test_possibly_moved(self):
        """文件不在原路径，但同名文件在 workspace 其他位置 → v1_status=possibly_moved。"""
        ws = TempWorkspace()
        try:
            # 原路径：memory/2026-04-01.md（不创建）
            # 同名文件在其他位置
            ws.create_file("memory/archive/2026-04-01.md", "archived content")
            item = _item(source_path="memory/2026-04-01.md")
            store = _store([[item]])
            result = run_audit(store, ws.path)

            assert result.items[0].v1_status == "possibly_moved"
            assert result.items[0].action_hint == "review"
        finally:
            ws.cleanup()

    def test_relative_path_correctly_resolved(self):
        """相对路径正确拼接 workspace_dir。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/subdir/2026-04-01.md")
            item = _item(source_path="memory/subdir/2026-04-01.md")
            store = _store([[item]])
            result = run_audit(store, ws.path)

            assert result.items[0].v1_status == "exists"
        finally:
            ws.cleanup()

    def test_mixed_exists_and_deleted(self):
        """部分文件存在，部分不存在 → 各自独立判断。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/exists.md")
            item_exists = _item(source_path="memory/exists.md")
            item_deleted = _item(source_path="memory/deleted.md")
            store = _store([[item_exists, item_deleted]])
            result = run_audit(store, ws.path)

            statuses = {a.item.source_path: a.v1_status for a in result.items}
            assert statuses["memory/exists.md"] == "exists"
            assert statuses["memory/deleted.md"] == "deleted"
        finally:
            ws.cleanup()


# ── V3：精确重复 ───────────────────────────────────────────────────────────────

class TestV3ExactDuplicate:
    def test_two_duplicates_lower_score_deleted(self):
        """同一 key 出现 2 次，score 低的标 duplicate_loser → delete。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md")
            item_high = _item(score=0.9)   # 应保留
            item_low  = _item(score=0.7)   # 应删除
            store = _store([[item_high, item_low]])
            result = run_audit(store, ws.path)

            actions = {a.item.score: a.action_hint for a in result.items}
            assert actions[0.9] == "keep"
            assert actions[0.7] == "delete"
        finally:
            ws.cleanup()

    def test_three_duplicates_only_highest_kept(self):
        """同一 key 出现 3 次，只保留 score 最高的。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md")
            items = [
                _item(score=0.6),
                _item(score=0.9),   # 最高，应保留
                _item(score=0.7),
            ]
            store = _store([[items[0], items[1], items[2]]])
            result = run_audit(store, ws.path)

            actions = [a.action_hint for a in result.items]
            # 只有 1 个 keep，2 个 delete
            assert actions.count("keep") == 1
            assert actions.count("delete") == 2
            # score=0.9 的那个是 keep
            kept = [a for a in result.items if a.action_hint == "keep"]
            assert kept[0].item.score == pytest.approx(0.9)
        finally:
            ws.cleanup()

    def test_same_score_first_wins(self):
        """同一 key，score 相同时保留最早出现的。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md")
            item1 = _item(score=0.8, snippet="first")
            item2 = _item(score=0.8, snippet="second")
            store = _store([[item1, item2]])
            result = run_audit(store, ws.path)

            kept = [a for a in result.items if a.action_hint == "keep"]
            assert len(kept) == 1
            assert kept[0].item.snippet == "first"
        finally:
            ws.cleanup()

    def test_different_files_same_lines_not_duplicate(self):
        """不同文件相同行号 → 不触发重复检测。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/file_a.md")
            ws.create_file("memory/file_b.md")
            item_a = _item(source_path="memory/file_a.md", source_start=1, source_end=10)
            item_b = _item(source_path="memory/file_b.md", source_start=1, source_end=10)
            store = _store([[item_a, item_b]])
            result = run_audit(store, ws.path)

            assert all(a.v3_status == "ok" for a in result.items)
            assert all(a.action_hint == "keep" for a in result.items)
        finally:
            ws.cleanup()

    def test_v3_delete_overrides_v1_keep(self):
        """V3 duplicate_loser → delete，即使 V1=exists。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md")
            item_high = _item(score=0.9)
            item_low  = _item(score=0.7)
            store = _store([[item_high, item_low]])
            result = run_audit(store, ws.path)

            # item_low 的 v1=exists，但 v3=duplicate_loser → action=delete
            low_audited = [a for a in result.items if a.item.score == pytest.approx(0.7)][0]
            assert low_audited.v1_status == "exists"
            assert low_audited.v3_status == "duplicate_loser"
            assert low_audited.action_hint == "delete"
        finally:
            ws.cleanup()


# ── V3：行号范围重叠 ──────────────────────────────────────────────────────────

class TestV3RangeOverlap:
    def test_overlapping_ranges_both_review(self):
        """同文件，行号区间重叠 → 两条都标 overlap → review。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md")
            item1 = _item(source_start=1,  source_end=20)
            item2 = _item(source_start=15, source_end=30)   # 与 item1 重叠 [15,20]
            store = _store([[item1, item2]])
            result = run_audit(store, ws.path)

            assert all(a.v3_status == "overlap" for a in result.items)
            assert all(a.action_hint == "review" for a in result.items)
        finally:
            ws.cleanup()

    def test_adjacent_ranges_not_overlap(self):
        """相邻但不重叠（end1+1 == start2）→ 不触发 overlap。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md")
            item1 = _item(source_start=1,  source_end=10)
            item2 = _item(source_start=11, source_end=20)   # 紧邻，不重叠
            store = _store([[item1, item2]])
            result = run_audit(store, ws.path)

            assert all(a.v3_status == "ok" for a in result.items)
        finally:
            ws.cleanup()

    def test_contained_range_overlap(self):
        """一个区间完全包含另一个 → 触发 overlap。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md")
            item_outer = _item(source_start=1,  source_end=30)
            item_inner = _item(source_start=10, source_end=20)   # 被包含
            store = _store([[item_outer, item_inner]])
            result = run_audit(store, ws.path)

            assert all(a.v3_status == "overlap" for a in result.items)
        finally:
            ws.cleanup()

    def test_single_line_overlap(self):
        """只有一行重叠（end1 == start2）→ 触发 overlap。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md")
            item1 = _item(source_start=1, source_end=10)
            item2 = _item(source_start=10, source_end=20)   # line 10 重叠
            store = _store([[item1, item2]])
            result = run_audit(store, ws.path)

            assert all(a.v3_status == "overlap" for a in result.items)
        finally:
            ws.cleanup()

    def test_different_files_no_overlap(self):
        """不同文件的区间，即使行号完全一样 → 不触发 overlap。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/file_a.md")
            ws.create_file("memory/file_b.md")
            item_a = _item(source_path="memory/file_a.md", source_start=1, source_end=20)
            item_b = _item(source_path="memory/file_b.md", source_start=5, source_end=15)
            store = _store([[item_a, item_b]])
            result = run_audit(store, ws.path)

            assert all(a.v3_status == "ok" for a in result.items)
        finally:
            ws.cleanup()

    def test_overlap_only_among_ok_items(self):
        """duplicate_loser 的 item 不参与 overlap 检测。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/2026-04-01.md")
            # item1, item2：精确重复（item2 是 loser）
            item1 = _item(source_start=1, source_end=10, score=0.9)
            item2 = _item(source_start=1, source_end=10, score=0.7)   # duplicate_loser
            # item3：与 item1 行号重叠
            item3 = _item(source_start=5, source_end=15, score=0.8)
            store = _store([[item1, item2, item3]])
            result = run_audit(store, ws.path)

            a1, a2, a3 = result.items
            # item2 是 duplicate_loser
            assert a2.v3_status == "duplicate_loser"
            # item1 和 item3 应该触发 overlap
            assert a1.v3_status == "overlap"
            assert a3.v3_status == "overlap"
        finally:
            ws.cleanup()


# ── action_hint 合并优先级 ────────────────────────────────────────────────────

class TestActionHintPriority:
    def test_v1_deleted_wins_over_v3_ok(self):
        """V1=deleted，V3=ok → delete。"""
        ws = TempWorkspace()
        try:
            item = _item()  # 文件不存在
            store = _store([[item]])
            result = run_audit(store, ws.path)

            assert result.items[0].action_hint == "delete"
        finally:
            ws.cleanup()

    def test_v1_deleted_wins_over_v3_overlap(self):
        """V1=deleted + V3=overlap → delete（V1 deleted 优先）。"""
        ws = TempWorkspace()
        try:
            # 两条相同文件，行号重叠，但文件不存在
            item1 = _item(source_start=1, source_end=10)
            item2 = _item(source_start=5, source_end=15)
            store = _store([[item1, item2]])
            result = run_audit(store, ws.path)

            # v1=deleted 优先于 v3=overlap → delete
            assert all(a.action_hint == "delete" for a in result.items)
        finally:
            ws.cleanup()


# ── 聚合统计 ──────────────────────────────────────────────────────────────────

class TestAggregation:
    def test_empty_store(self):
        """空 store：total_items=0，所有计数为 0。"""
        ws = TempWorkspace()
        try:
            store = _store([])
            result = run_audit(store, ws.path)

            assert result.total_items == 0
            assert result.sections_count == 0
            assert result.items_by_action["keep"] == 0
            assert result.items_by_action["review"] == 0
            assert result.items_by_action["delete"] == 0
        finally:
            ws.cleanup()

    def test_items_by_action_sum_equals_total(self):
        """keep + review + delete 之和 = total_items。"""
        ws = TempWorkspace()
        try:
            ws.create_file("memory/exists.md")
            items = [
                _item(source_path="memory/exists.md"),          # keep
                _item(source_path="memory/deleted.md"),         # delete (v1)
                _item(source_path="memory/exists.md", source_start=1, source_end=5, score=0.9),   # dup winner
                _item(source_path="memory/exists.md", source_start=1, source_end=5, score=0.7),   # dup loser → delete
            ]
            store = _store([items])
            result = run_audit(store, ws.path)

            total = sum(result.items_by_action.values())
            assert total == result.total_items
        finally:
            ws.cleanup()

    def test_sections_count_correct(self):
        """sections_count 与 store 中 section 数量一致。"""
        ws = TempWorkspace()
        try:
            store = _store([[_item()], [_item()], [_item()]])
            result = run_audit(store, ws.path)
            assert result.sections_count == 3
        finally:
            ws.cleanup()

    def test_returns_longterm_audit_result_type(self):
        """返回值是 LongtermAuditResult 类型。"""
        ws = TempWorkspace()
        try:
            store = _store([[_item()]])
            result = run_audit(store, ws.path)
            assert isinstance(result, LongtermAuditResult)
        finally:
            ws.cleanup()

    def test_mtime_populated_when_file_given(self):
        """传入 memory_md_path 时，mtime 被正确读取。"""
        ws = TempWorkspace()
        try:
            md_path = ws.create_file("MEMORY.md", "# Long-Term Memory\n")
            store = _store([[]])
            result = run_audit(store, ws.path, memory_md_path=md_path)

            assert result.memory_md_mtime is not None
            assert isinstance(result.memory_md_mtime, float)
        finally:
            ws.cleanup()

    def test_mtime_none_when_no_file(self):
        """不传 memory_md_path 时，mtime=None。"""
        ws = TempWorkspace()
        try:
            store = _store([])
            result = run_audit(store, ws.path, memory_md_path=None)
            assert result.memory_md_mtime is None
        finally:
            ws.cleanup()


# ── 真实 fixture 回归测试 ──────────────────────────────────────────────────────

class TestRealFixture:
    REAL_MEMORY = Path("tests/fixtures/real/MEMORY.md")
    REAL_WS = Path("tests/fixtures/real")

    def test_real_data_audit_runs(self):
        """真实 MEMORY.md 审计无报错，返回合法结果。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.readers.longterm_reader import read_longterm_from_path
        store = read_longterm_from_path(self.REAL_MEMORY, "mixed")
        result = run_audit(store, self.REAL_WS, memory_md_path=self.REAL_MEMORY)

        assert isinstance(result, LongtermAuditResult)
        assert result.total_items == 2
        assert sum(result.items_by_action.values()) == result.total_items

    def test_real_data_source_files_exist(self):
        """真实数据的来源文件（memory/2026-04-09.md 等）存在 → v1=exists。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.readers.longterm_reader import read_longterm_from_path
        store = read_longterm_from_path(self.REAL_MEMORY, "mixed")
        result = run_audit(store, self.REAL_WS, memory_md_path=self.REAL_MEMORY)

        for audited in result.items:
            assert audited.v1_status == "exists", (
                f"Expected exists for {audited.item.source_path}, got {audited.v1_status}"
            )

    def test_real_data_no_duplicates(self):
        """真实数据无重复条目 → v3=ok。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.readers.longterm_reader import read_longterm_from_path
        store = read_longterm_from_path(self.REAL_MEMORY, "mixed")
        result = run_audit(store, self.REAL_WS)

        assert all(a.v3_status == "ok" for a in result.items)

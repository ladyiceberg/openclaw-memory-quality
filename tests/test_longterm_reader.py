"""
test_longterm_reader.py · 长期记忆读取器测试
"""
from pathlib import Path

import pytest

from src.readers.longterm_reader import (
    LongTermReadError,
    LongTermStore,
    MemoryItem,
    MemorySection,
    read_longterm_from_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "longterm"
REAL_FIXTURE = Path(__file__).parent / "fixtures" / "real" / "MEMORY.md"


# ── 基础读取 ───────────────────────────────────────────────────────────────────

class TestReadFromPath:
    def test_normal_multi_section(self):
        """标准格式：3 个 section，共 6 条 item。"""
        result = read_longterm_from_path(FIXTURES / "normal_multi_section.md")

        assert isinstance(result, LongTermStore)
        assert len(result.sections) == 3
        assert result.total_items == 6

    def test_empty_file(self):
        """只有 H1 文件头，无 section，无 item。"""
        result = read_longterm_from_path(FIXTURES / "empty_file.md")

        assert isinstance(result, LongTermStore)
        assert len(result.sections) == 0
        assert result.total_items == 0

    def test_single_section_single_item(self):
        """最简情况：1 个 section，1 条 item。"""
        result = read_longterm_from_path(FIXTURES / "single_section_single.md")

        assert isinstance(result, LongTermStore)
        assert len(result.sections) == 1
        assert result.total_items == 1

    def test_file_not_found(self):
        """文件不存在 → LongTermReadError，不抛异常。"""
        result = read_longterm_from_path(Path("/nonexistent/path/MEMORY.md"))

        assert isinstance(result, LongTermReadError)
        assert result.error_code == "file_not_found"
        assert len(result.message) > 0

    def test_manual_only_no_sections(self):
        """纯手动格式：无 Dreaming section，total_items=0。"""
        result = read_longterm_from_path(FIXTURES / "manual_only.md")

        assert isinstance(result, LongTermStore)
        assert len(result.sections) == 0
        assert result.total_items == 0


# ── 格式识别 ───────────────────────────────────────────────────────────────────

class TestFormatDetection:
    def test_source_code_format(self):
        """纯 Dreaming 格式 → source_code。"""
        result = read_longterm_from_path(FIXTURES / "normal_multi_section.md")

        assert isinstance(result, LongTermStore)
        assert result.format_name == "source_code"

    def test_mixed_format(self):
        """手动内容 + Dreaming section → mixed。"""
        result = read_longterm_from_path(FIXTURES / "mixed_format.md")

        assert isinstance(result, LongTermStore)
        assert result.format_name == "mixed"
        assert result.has_manual_content is True

    def test_manual_format(self):
        """纯手动格式，无 Dreaming section → manual。"""
        result = read_longterm_from_path(FIXTURES / "manual_only.md")

        assert isinstance(result, LongTermStore)
        assert result.format_name == "manual"
        assert result.has_manual_content is True

    def test_empty_file_format(self):
        """空文件（只有 H1）→ sections 为空，has_manual=False。"""
        result = read_longterm_from_path(FIXTURES / "empty_file.md")

        assert isinstance(result, LongTermStore)
        assert result.has_manual_content is False


# ── Section 解析 ───────────────────────────────────────────────────────────────

class TestSectionParsing:
    def _get_sections(self, fixture_name: str) -> list[MemorySection]:
        result = read_longterm_from_path(FIXTURES / fixture_name)
        assert isinstance(result, LongTermStore)
        return result.sections

    def test_section_dates_correct(self):
        """section 日期字符串正确解析。"""
        sections = self._get_sections("normal_multi_section.md")

        assert sections[0].date == "2026-04-07"
        assert sections[1].date == "2026-04-08"
        assert sections[2].date == "2026-04-14"

    def test_section_item_counts(self):
        """每个 section 的 item 数量正确。"""
        sections = self._get_sections("normal_multi_section.md")

        assert len(sections[0].items) == 2
        assert len(sections[1].items) == 1
        assert len(sections[2].items) == 3

    def test_sections_in_order(self):
        """section 按文件顺序排列（最早的在前）。"""
        sections = self._get_sections("normal_multi_section.md")

        dates = [s.date for s in sections]
        assert dates == sorted(dates)

    def test_no_non_standard_lines_in_clean_fixture(self):
        """标准格式文件里没有 non_standard_lines。"""
        sections = self._get_sections("normal_multi_section.md")

        for section in sections:
            assert section.non_standard_lines == 0


# ── MemoryItem 字段解析 ────────────────────────────────────────────────────────

class TestItemParsing:
    def _get_first_item(self, fixture_name: str) -> MemoryItem:
        result = read_longterm_from_path(FIXTURES / fixture_name)
        assert isinstance(result, LongTermStore)
        assert result.total_items > 0
        return result.sections[0].items[0]

    def test_core_fields(self):
        """核心字段正确解析。"""
        item = self._get_first_item("single_section_single.md")

        assert isinstance(item.snippet, str) and item.snippet
        assert item.score == pytest.approx(0.900)
        assert item.recalls == 3
        assert item.avg_score == pytest.approx(0.750)

    def test_source_fields(self):
        """source_path / source_start / source_end 正确分离。"""
        item = self._get_first_item("single_section_single.md")

        assert item.source_path == "memory/2026-04-13.md"
        assert item.source_start == 5
        assert item.source_end == 8

    def test_promotion_key_present(self):
        """有 <!-- --> 注释行时 promotion_key 正确提取。"""
        item = self._get_first_item("single_section_single.md")

        assert item.promotion_key == "memory:memory/2026-04-13.md:5:8"

    def test_promotion_key_absent_when_no_comment(self):
        """没有 <!-- --> 注释行时（旧格式）promotion_key 为 None。"""
        item = self._get_first_item("no_comment_lines.md")

        assert item.promotion_key is None

    def test_special_chars_in_snippet_dont_break_parsing(self):
        """snippet 中含 [ ] 字符不干扰 metadata 解析。"""
        result = read_longterm_from_path(FIXTURES / "special_chars.md")
        assert isinstance(result, LongTermStore)
        items = result.sections[0].items

        # 两条都成功解析
        assert len(items) == 2
        # snippet 包含 [ ]，不被截断
        assert "[mmr_enabled=false]" in items[0].snippet
        assert "[a, b, c]" in items[1].snippet
        # metadata 仍然正确
        assert items[0].score == pytest.approx(0.850)
        assert items[1].source_path == "memory/2026-04-11.md"

    def test_score_is_float(self):
        """score / avg_score 是浮点数。"""
        item = self._get_first_item("normal_multi_section.md")

        assert isinstance(item.score, float)
        assert isinstance(item.avg_score, float)

    def test_recalls_is_int(self):
        """recalls 是整数。"""
        item = self._get_first_item("normal_multi_section.md")

        assert isinstance(item.recalls, int)

    def test_source_lines_are_int(self):
        """source_start / source_end 是整数。"""
        item = self._get_first_item("normal_multi_section.md")

        assert isinstance(item.source_start, int)
        assert isinstance(item.source_end, int)


# ── 手动内容统计 ───────────────────────────────────────────────────────────────

class TestManualContentStats:
    def test_no_manual_in_pure_dreaming(self):
        """纯 Dreaming 格式：manual_content_lines=0，has_manual=False。"""
        result = read_longterm_from_path(FIXTURES / "normal_multi_section.md")

        assert isinstance(result, LongTermStore)
        assert result.manual_content_lines == 0
        assert result.has_manual_content is False

    def test_manual_lines_counted_in_mixed(self):
        """mixed 格式：手动内容行数 > 0。"""
        result = read_longterm_from_path(FIXTURES / "mixed_format.md")

        assert isinstance(result, LongTermStore)
        assert result.manual_content_lines > 0
        assert result.has_manual_content is True

    def test_h1_header_not_counted_as_manual(self):
        """H1 标题行（# Long-Term Memory）不算入手动内容。"""
        result = read_longterm_from_path(FIXTURES / "normal_multi_section.md")

        assert isinstance(result, LongTermStore)
        # "# Long-Term Memory" 是唯一非 section 行，但不应被计为 manual
        assert result.manual_content_lines == 0


# ── parsed_ratio（80% 安全阀相关）────────────────────────────────────────────

class TestParsedRatio:
    def test_parsed_ratio_is_float(self):
        """parsed_ratio 是浮点数，在 0-1 范围内。"""
        result = read_longterm_from_path(FIXTURES / "normal_multi_section.md")

        assert isinstance(result, LongTermStore)
        assert 0.0 <= result.parsed_ratio <= 1.0

    def test_empty_file_does_not_trigger_safety_valve(self):
        """空文件（只有文件头）→ 无 section，不触发安全阀，返回 LongTermStore 而非 Error。"""
        result = read_longterm_from_path(FIXTURES / "empty_file.md")

        # 无 section → 安全阀不检查 → 正常返回 Store（不是 Error）
        assert isinstance(result, LongTermStore)
        assert result.total_items == 0

    def test_raw_char_count_positive(self):
        """raw_char_count > 0（文件非空）。"""
        result = read_longterm_from_path(FIXTURES / "normal_multi_section.md")

        assert isinstance(result, LongTermStore)
        assert result.raw_char_count > 0


# ── 真实数据集成测试 ───────────────────────────────────────────────────────────

class TestRealFixture:
    def test_real_data_parses_successfully(self):
        """真实 MEMORY.md 正确解析，无报错。"""
        if not REAL_FIXTURE.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = read_longterm_from_path(REAL_FIXTURE, "mixed")

        assert isinstance(result, LongTermStore)
        assert result.format_name == "mixed"
        assert result.has_manual_content is True

    def test_real_data_sections_and_items(self):
        """真实数据有 1 个 Dreaming section，2 条 item。"""
        if not REAL_FIXTURE.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = read_longterm_from_path(REAL_FIXTURE, "mixed")
        assert isinstance(result, LongTermStore)

        assert len(result.sections) == 1
        assert result.total_items == 2

    def test_real_data_item_fields_correct(self):
        """真实数据 item 的所有字段类型正确。"""
        if not REAL_FIXTURE.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = read_longterm_from_path(REAL_FIXTURE, "mixed")
        assert isinstance(result, LongTermStore)

        for section in result.sections:
            for item in section.items:
                assert isinstance(item.snippet, str) and item.snippet
                assert isinstance(item.score, float)
                assert isinstance(item.recalls, int)
                assert isinstance(item.avg_score, float)
                assert isinstance(item.source_path, str) and item.source_path
                assert isinstance(item.source_start, int)
                assert isinstance(item.source_end, int)

    def test_real_data_has_promotion_keys(self):
        """真实数据的 item 有 promotion_key（新版格式有注释行）。"""
        if not REAL_FIXTURE.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = read_longterm_from_path(REAL_FIXTURE, "mixed")
        assert isinstance(result, LongTermStore)

        for section in result.sections:
            for item in section.items:
                assert item.promotion_key is not None
                assert "memory:" in item.promotion_key

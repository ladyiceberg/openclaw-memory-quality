"""
test_shortterm_reader.py · 短期记忆读取器测试
"""
from pathlib import Path

import pytest

from src.readers.shortterm_reader import (
    ShortTermEntry,
    ShortTermReadError,
    ShortTermStore,
    days_since_iso,
    read_shortterm_from_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "shortterm"
REAL_FIXTURE = Path(__file__).parent / "fixtures" / "real" / "memory" / ".dreams" / "short-term-recall.json"


# ── 基础读取 ───────────────────────────────────────────────────────────────────

class TestReadFromPath:
    def test_normal_multi(self):
        """正常读取多条条目。"""
        result = read_shortterm_from_path(FIXTURES / "normal_multi.json")

        assert isinstance(result, ShortTermStore)
        assert result.version == 1
        assert result.updated_at == "2026-04-14T08:00:00.000Z"
        assert len(result.entries) == 3

    def test_empty_entries(self):
        """entries 为空时返回空列表，不报错。"""
        result = read_shortterm_from_path(FIXTURES / "empty_entries.json")

        assert isinstance(result, ShortTermStore)
        assert len(result.entries) == 0

    def test_single(self):
        """只有 1 条条目。"""
        result = read_shortterm_from_path(FIXTURES / "single.json")

        assert isinstance(result, ShortTermStore)
        assert len(result.entries) == 1

    def test_file_not_found(self):
        """文件不存在 → ShortTermReadError，不抛异常。"""
        result = read_shortterm_from_path(Path("/nonexistent/path/store.json"))

        assert isinstance(result, ShortTermReadError)
        assert result.error_code == "file_not_found"
        assert len(result.message) > 0

    def test_broken_json(self):
        """JSON 损坏 → ShortTermReadError，不抛异常。"""
        result = read_shortterm_from_path(FIXTURES / "broken.json")

        assert isinstance(result, ShortTermReadError)
        assert result.error_code == "json_invalid"


# ── 字段解析 ───────────────────────────────────────────────────────────────────

class TestEntryParsing:
    def _get_first_entry(self, fixture_name: str) -> ShortTermEntry:
        result = read_shortterm_from_path(FIXTURES / fixture_name)
        assert isinstance(result, ShortTermStore)
        assert len(result.entries) > 0
        return result.entries[0]

    def test_core_fields(self):
        """核心字段正确解析。"""
        entry = self._get_first_entry("single.json")

        assert entry.key == "memory:memory/2026-04-14.md:1:10"
        assert entry.path == "memory/2026-04-14.md"
        assert entry.start_line == 1
        assert entry.end_line == 10
        assert entry.source == "memory"
        assert isinstance(entry.snippet, str)
        assert entry.recall_count == 1
        assert isinstance(entry.total_score, float)
        assert isinstance(entry.max_score, float)

    def test_timestamps_are_iso_strings(self):
        """时间戳字段是 ISO 字符串，不是毫秒数字。"""
        entry = self._get_first_entry("single.json")

        assert isinstance(entry.first_recalled_at, str)
        assert isinstance(entry.last_recalled_at, str)
        assert "T" in entry.first_recalled_at   # ISO 格式包含 T
        assert "Z" in entry.first_recalled_at   # UTC 时区

    def test_promoted_at_present(self):
        """已晋升条目：promoted_at 是 ISO 字符串。"""
        entry = self._get_first_entry("with_promoted.json")

        assert entry.promoted_at is not None
        assert isinstance(entry.promoted_at, str)
        assert "T" in entry.promoted_at

    def test_promoted_at_absent(self):
        """未晋升条目：promoted_at 为 None（字段不出现 ≠ null）。"""
        entry = self._get_first_entry("without_promoted.json")

        assert entry.promoted_at is None

    def test_new_fields_present(self):
        """新版字段（dailyCount/groundedCount/claimHash）存在时正确解析。"""
        entry = self._get_first_entry("with_new_fields.json")

        assert entry.daily_count == 2
        assert entry.grounded_count == 1
        assert entry.claim_hash == "abc123def456"

    def test_new_fields_absent_default_values(self):
        """旧版格式不含新字段时，使用默认值（不报错）。"""
        entry = self._get_first_entry("without_new_fields.json")

        assert entry.daily_count == 0        # 默认值
        assert entry.grounded_count == 0     # 默认值
        assert entry.claim_hash is None      # 默认值

    def test_many_query_hashes(self):
        """queryHashes 达到 32 个上限时正常读取，不截断。"""
        entry = self._get_first_entry("many_queries.json")

        assert len(entry.query_hashes) == 32

    def test_many_recall_days(self):
        """recallDays 达到 16 个上限时正常读取。"""
        entry = self._get_first_entry("many_queries.json")

        assert len(entry.recall_days) == 16

    def test_list_fields_are_lists(self):
        """query_hashes / recall_days / concept_tags 是 list 类型。"""
        entry = self._get_first_entry("normal_multi.json")

        assert isinstance(entry.query_hashes, list)
        assert isinstance(entry.recall_days, list)
        assert isinstance(entry.concept_tags, list)


# ── days_since_iso 辅助函数 ────────────────────────────────────────────────────

class TestDaysSinceIso:
    def test_same_time(self):
        """距今 0 天。"""
        iso = "2026-04-14T08:00:00.000Z"
        now_ms = 1776153600000  # 2026-04-14T08:00:00Z
        assert days_since_iso(iso, now_ms) == pytest.approx(0.0, abs=0.01)

    def test_one_day(self):
        """距今恰好 1 天。"""
        iso = "2026-04-13T08:00:00.000Z"
        now_ms = 1776153600000  # 2026-04-14T08:00:00Z
        result = days_since_iso(iso, now_ms)
        assert result == pytest.approx(1.0, abs=0.01)

    def test_ninety_days(self):
        """90 天前。"""
        iso = "2026-01-14T08:00:00.000Z"
        now_ms = 1776153600000  # 2026-04-14T08:00:00Z
        result = days_since_iso(iso, now_ms)
        assert result == pytest.approx(90.0, abs=1.0)

    def test_returns_float(self):
        """返回值是浮点数。"""
        result = days_since_iso("2026-04-13T20:00:00.000Z", 1744617600000)
        assert isinstance(result, float)


# ── 真实数据集成测试 ───────────────────────────────────────────────────────────

class TestRealFixture:
    def test_real_data_parses_successfully(self):
        """真实数据（15条）正确解析，无报错。"""
        if not REAL_FIXTURE.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = read_shortterm_from_path(REAL_FIXTURE)

        assert isinstance(result, ShortTermStore)
        assert result.version == 1
        assert len(result.entries) == 15

    def test_real_data_has_expected_fields(self):
        """真实数据的字段类型全部正确。"""
        if not REAL_FIXTURE.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = read_shortterm_from_path(REAL_FIXTURE)
        assert isinstance(result, ShortTermStore)

        for entry in result.entries:
            assert isinstance(entry.key, str) and entry.key
            assert isinstance(entry.path, str) and entry.path
            assert isinstance(entry.start_line, int)
            assert isinstance(entry.end_line, int)
            assert entry.source == "memory"
            assert isinstance(entry.recall_count, int)
            assert isinstance(entry.total_score, float)
            assert isinstance(entry.max_score, float)
            assert isinstance(entry.first_recalled_at, str)
            assert isinstance(entry.last_recalled_at, str)
            assert isinstance(entry.query_hashes, list)
            assert isinstance(entry.recall_days, list)
            assert isinstance(entry.concept_tags, list)
            # 新版字段有默认值，不管有没有都不报错
            assert isinstance(entry.daily_count, int)
            assert isinstance(entry.grounded_count, int)

    def test_real_data_has_promoted_entry(self):
        """真实数据里至少有一条已晋升的条目。"""
        if not REAL_FIXTURE.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = read_shortterm_from_path(REAL_FIXTURE)
        assert isinstance(result, ShortTermStore)

        promoted = [e for e in result.entries if e.promoted_at is not None]
        assert len(promoted) >= 1
        # 确认 promotedAt 是 ISO 字符串
        assert "T" in promoted[0].promoted_at

    def test_real_data_timestamps_are_strings(self):
        """真实数据的时间戳是 ISO 字符串，不是数字。"""
        if not REAL_FIXTURE.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = read_shortterm_from_path(REAL_FIXTURE)
        assert isinstance(result, ShortTermStore)

        for entry in result.entries:
            assert isinstance(entry.first_recalled_at, str)
            assert isinstance(entry.last_recalled_at, str)
            assert "T" in entry.first_recalled_at

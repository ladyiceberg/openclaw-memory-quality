"""
test_shortterm_writer.py · short-term-recall.json 重建测试

所有测试直接调用 build_cleaned_json()，不做文件 IO。
"""
import json
from pathlib import Path

import pytest

from src.writers.shortterm_writer import (
    ShorttermCleanupStats,
    ShorttermWriteError,
    build_cleaned_json,
)


REAL_ST = Path("tests/fixtures/real/memory/.dreams/short-term-recall.json")
FIXED_NOW = "2026-04-14T10:00:00.000Z"


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _make_json(entries: dict, version: int = 1, updated_at: str = "2026-04-14T08:00:00.000Z") -> str:
    return json.dumps({
        "version": version,
        "updatedAt": updated_at,
        "entries": entries,
    }, indent=2, ensure_ascii=False) + "\n"


def _entry(recall_count: int = 3) -> dict:
    return {
        "key": "placeholder",
        "path": "memory/f.md",
        "startLine": 1,
        "endLine": 5,
        "source": "memory",
        "snippet": "test",
        "recallCount": recall_count,
        "totalScore": 1.5,
        "maxScore": 0.7,
        "firstRecalledAt": "2026-04-01T00:00:00.000Z",
        "lastRecalledAt": "2026-04-14T00:00:00.000Z",
        "queryHashes": [],
        "recallDays": [],
        "conceptTags": ["test"],
    }


# ── 基本行为 ───────────────────────────────────────────────────────────────────

class TestNoDeletion:
    def test_empty_keys_all_entries_kept(self):
        """keys_to_delete 为空时，所有条目保留。"""
        original = _make_json({"k1": _entry(), "k2": _entry()})
        new_json, stats = build_cleaned_json(original, set(), now_iso=FIXED_NOW)

        data = json.loads(new_json)
        assert set(data["entries"].keys()) == {"k1", "k2"}
        assert stats.deleted == 0
        assert stats.kept == 2

    def test_real_fixture_no_deletion(self):
        """真实数据，不删任何条目，条目数不变。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        original = REAL_ST.read_text()
        new_json, stats = build_cleaned_json(original, set(), now_iso=FIXED_NOW)

        new_data = json.loads(new_json)
        original_data = json.loads(original)
        assert len(new_data["entries"]) == len(original_data["entries"])
        assert stats.deleted == 0


class TestDeleteEntries:
    def test_delete_single_entry(self):
        """删除单条：该 key 从 entries 中消失，其他保留。"""
        original = _make_json({"k1": _entry(), "k2": _entry(), "k3": _entry()})
        new_json, stats = build_cleaned_json(original, {"k1"}, now_iso=FIXED_NOW)

        data = json.loads(new_json)
        assert "k1" not in data["entries"]
        assert "k2" in data["entries"]
        assert "k3" in data["entries"]
        assert stats.deleted == 1
        assert stats.kept == 2

    def test_delete_multiple_entries(self):
        """删除多条。"""
        original = _make_json({
            "k1": _entry(), "k2": _entry(), "k3": _entry(), "k4": _entry()
        })
        new_json, stats = build_cleaned_json(original, {"k1", "k3"}, now_iso=FIXED_NOW)

        data = json.loads(new_json)
        assert set(data["entries"].keys()) == {"k2", "k4"}
        assert stats.deleted == 2
        assert stats.kept == 2

    def test_delete_all_entries(self):
        """删除全部条目，entries 变为空字典。"""
        original = _make_json({"k1": _entry(), "k2": _entry()})
        new_json, stats = build_cleaned_json(original, {"k1", "k2"}, now_iso=FIXED_NOW)

        data = json.loads(new_json)
        assert data["entries"] == {}
        assert stats.deleted == 2
        assert stats.kept == 0

    def test_delete_nonexistent_key_ignored(self):
        """删除不存在的 key 不影响任何内容。"""
        original = _make_json({"k1": _entry()})
        new_json, stats = build_cleaned_json(original, {"nonexistent"}, now_iso=FIXED_NOW)

        data = json.loads(new_json)
        assert "k1" in data["entries"]
        assert stats.deleted == 0
        assert stats.kept == 1

    def test_real_fixture_delete_first_two(self):
        """真实数据删除前两条，总数减 2。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        original = REAL_ST.read_text()
        original_data = json.loads(original)
        all_keys = list(original_data["entries"].keys())
        to_delete = set(all_keys[:2])

        new_json, stats = build_cleaned_json(original, to_delete, now_iso=FIXED_NOW)
        new_data = json.loads(new_json)

        assert len(new_data["entries"]) == len(original_data["entries"]) - 2
        assert stats.deleted == 2
        assert stats.kept == len(original_data["entries"]) - 2
        for k in to_delete:
            assert k not in new_data["entries"]


# ── 字段更新 ──────────────────────────────────────────────────────────────────

class TestFieldUpdates:
    def test_updated_at_changed(self):
        """updatedAt 更新为 now_iso。"""
        original = _make_json({}, updated_at="2026-04-01T00:00:00.000Z")
        new_json, _ = build_cleaned_json(original, set(), now_iso=FIXED_NOW)

        data = json.loads(new_json)
        assert data["updatedAt"] == FIXED_NOW

    def test_version_preserved(self):
        """version 字段保持不变。"""
        original = _make_json({}, version=1)
        new_json, _ = build_cleaned_json(original, set(), now_iso=FIXED_NOW)

        data = json.loads(new_json)
        assert data["version"] == 1

    def test_other_top_level_fields_preserved(self):
        """顶层其他字段（version、updatedAt 以外）也保留。"""
        raw = json.dumps({
            "version": 1,
            "updatedAt": "2026-04-14T08:00:00.000Z",
            "entries": {},
            "customField": "some_value",
        }, indent=2) + "\n"
        new_json, _ = build_cleaned_json(raw, set(), now_iso=FIXED_NOW)

        data = json.loads(new_json)
        assert data.get("customField") == "some_value"

    def test_updated_at_auto_set_when_not_provided(self):
        """now_iso 不传时，updatedAt 被自动设为当前时间（格式正确）。"""
        original = _make_json({})
        new_json, _ = build_cleaned_json(original, set())

        data = json.loads(new_json)
        updated = data["updatedAt"]
        assert "T" in updated
        assert updated.endswith("Z")

    def test_entry_data_content_preserved(self):
        """保留的 entry 数据字段完整，无内容损坏。"""
        entry_data = _entry(recall_count=42)
        original = _make_json({"k1": entry_data})
        new_json, _ = build_cleaned_json(original, set(), now_iso=FIXED_NOW)

        data = json.loads(new_json)
        assert data["entries"]["k1"]["recallCount"] == 42


# ── 输出格式 ──────────────────────────────────────────────────────────────────

class TestOutputFormat:
    def test_output_is_valid_json(self):
        """输出是合法 JSON。"""
        original = _make_json({"k1": _entry()})
        new_json, _ = build_cleaned_json(original, set(), now_iso=FIXED_NOW)
        data = json.loads(new_json)   # 不抛就是合法 JSON
        assert isinstance(data, dict)

    def test_output_ends_with_newline(self):
        """输出末尾有换行符。"""
        original = _make_json({"k1": _entry()})
        new_json, _ = build_cleaned_json(original, set(), now_iso=FIXED_NOW)
        assert new_json.endswith("\n")

    def test_output_uses_indent_2(self):
        """输出使用 indent=2（与 OpenClaw 格式一致）。"""
        original = _make_json({"k1": _entry()})
        new_json, _ = build_cleaned_json(original, set(), now_iso=FIXED_NOW)
        # indent=2 时第一级缩进是 2 个空格
        assert '  "version"' in new_json

    def test_output_preserves_unicode(self):
        """中文等 Unicode 字符不被转义（ensure_ascii=False）。"""
        entry = _entry()
        entry["snippet"] = "这是中文内容"
        original = _make_json({"k1": entry})
        new_json, _ = build_cleaned_json(original, set(), now_iso=FIXED_NOW)

        assert "这是中文内容" in new_json


# ── 统计数字 ──────────────────────────────────────────────────────────────────

class TestStats:
    def test_total_before_correct(self):
        """total_before 等于原始 entries 总数。"""
        original = _make_json({"k1": _entry(), "k2": _entry(), "k3": _entry()})
        _, stats = build_cleaned_json(original, {"k1"}, now_iso=FIXED_NOW)
        assert stats.total_before == 3

    def test_deleted_plus_kept_equals_total_before(self):
        """deleted + kept = total_before。"""
        original = _make_json({f"k{i}": _entry() for i in range(5)})
        _, stats = build_cleaned_json(original, {"k0", "k2"}, now_iso=FIXED_NOW)
        assert stats.deleted + stats.kept == stats.total_before

    def test_returns_shortterm_cleanup_stats_type(self):
        """返回值第二个是 ShorttermCleanupStats。"""
        original = _make_json({})
        _, stats = build_cleaned_json(original, set(), now_iso=FIXED_NOW)
        assert isinstance(stats, ShorttermCleanupStats)


# ── 错误处理 ──────────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_invalid_json_raises(self):
        """无效 JSON 抛出 ShorttermWriteError。"""
        with pytest.raises(ShorttermWriteError) as exc_info:
            build_cleaned_json("this is not json", set())
        assert "JSON" in str(exc_info.value)

    def test_non_dict_json_raises(self):
        """顶层不是对象（如数组）抛出 ShorttermWriteError。"""
        with pytest.raises(ShorttermWriteError):
            build_cleaned_json("[1, 2, 3]", set())

    def test_missing_entries_field_treated_as_empty(self):
        """entries 字段缺失时等同于空 entries，不报错。"""
        raw = json.dumps({"version": 1, "updatedAt": "2026-04-14T08:00:00.000Z"}) + "\n"
        new_json, stats = build_cleaned_json(raw, set(), now_iso=FIXED_NOW)
        data = json.loads(new_json)
        assert data["entries"] == {}
        assert stats.total_before == 0

"""
test_longterm_writer.py · MEMORY.md 重建逻辑测试

所有测试直接调用 build_cleaned_content()，不做文件 IO。
IO（备份+原子写入+加锁）在 cleanup 工具层测试。

覆盖场景：
  - 无删除时内容不变
  - 删除单条：comment 行 + item 行一起消失
  - 删除多条
  - 删除 section 内全部 item → section header 被清除
  - 手动内容（section 外）无条件保留
  - 非标准行无条件保留，且阻止 empty section 清理
  - 无 comment 行的旧格式（fallback key 匹配）
  - 统计数字正确（deleted+kept = 总 item 数）
  - 末尾换行符
"""
from pathlib import Path
import pytest

from src.writers.longterm_writer import CleanupStats, build_cleaned_content


# ── Fixture 文本构造辅助 ───────────────────────────────────────────────────────

REAL_MEMORY_MD = Path("tests/fixtures/real/MEMORY.md")


def _make_md(sections: list[list[dict]], manual_header: str = "# Long-Term Memory") -> str:
    """
    构造一个 MEMORY.md 文本。

    sections: 每个元素是一个 section 的 item 列表，每个 item 是 dict：
      {
        "key": "memory:memory/f.md:1:5",    # promotion_key（可省，省略则无 comment 行）
        "source": "memory/f.md:1-5",         # source 字段
        "snippet": "test snippet",
        "score": 0.9, "recalls": 3, "avg": 0.7,
        "nonstandard_line": None,            # 可选：在 item 前插入非标准行
      }
    """
    lines = [f"{manual_header}\n", "\n"]
    for i, items in enumerate(sections):
        date = f"2026-04-{i+1:02d}"
        lines.append(f"## Promoted From Short-Term Memory ({date})\n")
        lines.append("\n")
        for item in items:
            if item.get("nonstandard_line"):
                lines.append(f"{item['nonstandard_line']}\n")
            if item.get("key"):
                lines.append(f"<!-- openclaw-memory-promotion:{item['key']} -->\n")
            snippet = item.get("snippet", "test snippet")
            score   = item.get("score", 0.9)
            recalls = item.get("recalls", 3)
            avg     = item.get("avg", 0.7)
            source  = item["source"]
            lines.append(
                f"- {snippet} [score={score:.3f} recalls={recalls} avg={avg:.3f} source={source}]\n"
            )
        lines.append("\n")
    return "".join(lines)


# ── 基本行为 ───────────────────────────────────────────────────────────────────

class TestNoDeletion:
    def test_empty_keys_content_unchanged(self):
        """keys_to_delete 为空时，输出与输入完全一致。"""
        md = _make_md([
            [{"key": "memory:f.md:1:5", "source": "f.md:1-5"}]
        ])
        new_content, stats = build_cleaned_content(md, set())

        assert new_content == md
        assert stats.deleted == 0
        assert stats.kept == 1

    def test_real_fixture_unchanged(self):
        """真实 MEMORY.md，不删任何条目，输出不变。"""
        if not REAL_MEMORY_MD.exists():
            pytest.skip("tests/fixtures/real 不存在")

        original = REAL_MEMORY_MD.read_text(encoding="utf-8")
        new_content, stats = build_cleaned_content(original, set())

        assert new_content == original
        assert stats.deleted == 0
        assert stats.kept == 2


class TestDeleteSingleItem:
    def test_comment_and_item_both_removed(self):
        """删除一条：comment 行 + item 行都从输出中消失。"""
        key = "memory:memory/f.md:1:5"
        md = _make_md([
            [{"key": key, "source": "memory/f.md:1-5", "snippet": "target item"}]
        ])
        new_content, stats = build_cleaned_content(md, {key})

        assert "target item" not in new_content
        assert "openclaw-memory-promotion" not in new_content
        assert stats.deleted == 1
        assert stats.kept == 0

    def test_other_items_unaffected(self):
        """删除一条时，同 section 内其他条目不受影响。"""
        key1 = "memory:memory/f1.md:1:5"
        key2 = "memory:memory/f2.md:1:5"
        md = _make_md([
            [
                {"key": key1, "source": "memory/f1.md:1-5", "snippet": "to delete"},
                {"key": key2, "source": "memory/f2.md:1-5", "snippet": "to keep"},
            ]
        ])
        new_content, stats = build_cleaned_content(md, {key1})

        assert "to delete" not in new_content
        assert "to keep" in new_content
        assert stats.deleted == 1
        assert stats.kept == 1

    def test_different_section_items_unaffected(self):
        """删除 section A 的条目，section B 的条目不受影响。"""
        key_a = "memory:memory/a.md:1:5"
        key_b = "memory:memory/b.md:1:5"
        md = _make_md([
            [{"key": key_a, "source": "memory/a.md:1-5", "snippet": "from A"}],
            [{"key": key_b, "source": "memory/b.md:1-5", "snippet": "from B"}],
        ])
        new_content, stats = build_cleaned_content(md, {key_a})

        assert "from A" not in new_content
        assert "from B" in new_content
        assert stats.deleted == 1
        assert stats.kept == 1


class TestDeleteMultipleItems:
    def test_delete_all_items_in_section(self):
        """删除 section 内全部 item → section header 也被删除。"""
        key1 = "memory:memory/f1.md:1:5"
        key2 = "memory:memory/f2.md:1:5"
        md = _make_md([
            [
                {"key": key1, "source": "memory/f1.md:1-5"},
                {"key": key2, "source": "memory/f2.md:1-5"},
            ]
        ])
        new_content, stats = build_cleaned_content(md, {key1, key2})

        assert "Promoted From Short-Term Memory" not in new_content
        assert stats.deleted == 2
        assert stats.kept == 0
        assert stats.sections_before == 1
        assert stats.sections_after == 0
        assert stats.empty_sections_removed == 1

    def test_delete_across_multiple_sections(self):
        """跨 section 删除，每个 section 各删一条。"""
        key_a = "memory:memory/a.md:1:5"
        key_b = "memory:memory/b.md:1:5"
        keep_a = "memory:memory/a2.md:1:5"
        keep_b = "memory:memory/b2.md:1:5"
        md = _make_md([
            [
                {"key": key_a,   "source": "memory/a.md:1-5",  "snippet": "del A"},
                {"key": keep_a,  "source": "memory/a2.md:1-5", "snippet": "keep A"},
            ],
            [
                {"key": key_b,   "source": "memory/b.md:1-5",  "snippet": "del B"},
                {"key": keep_b,  "source": "memory/b2.md:1-5", "snippet": "keep B"},
            ],
        ])
        new_content, stats = build_cleaned_content(md, {key_a, key_b})

        assert "del A" not in new_content and "del B" not in new_content
        assert "keep A" in new_content and "keep B" in new_content
        assert stats.deleted == 2
        assert stats.kept == 2

    def test_only_empty_section_header_removed(self):
        """只有全空 section 的 header 被删，有保留 item 的 section header 保留。"""
        key_del = "memory:memory/del.md:1:5"
        key_keep = "memory:memory/keep.md:1:5"
        md = _make_md([
            [{"key": key_del,  "source": "memory/del.md:1-5",  "snippet": "to delete"}],
            [{"key": key_keep, "source": "memory/keep.md:1-5", "snippet": "to keep"}],
        ])
        new_content, stats = build_cleaned_content(md, {key_del})

        # 有保留 item 的 section 的 header 还在
        assert "Promoted From Short-Term Memory (2026-04-02)" in new_content
        # 全空 section 的 header 被删
        assert "Promoted From Short-Term Memory (2026-04-01)" not in new_content
        assert stats.sections_after == 1


# ── 手动内容保留 ──────────────────────────────────────────────────────────────

class TestManualContentPreserved:
    def test_manual_header_preserved(self):
        """文件头（手动内容）无条件保留。"""
        md = _make_md(
            [
                [{"key": "memory:f.md:1:5", "source": "f.md:1-5"}],
            ],
            manual_header="# MEMORY.md - Long-term Memory"
        )
        new_content, _ = build_cleaned_content(md, {"memory:f.md:1:5"})

        assert "# MEMORY.md - Long-term Memory" in new_content

    def test_manual_content_before_dreaming_sections_preserved(self):
        """Dreaming section 之前的手动内容无条件保留。"""
        manual = (
            "# MEMORY.md\n\n"
            "## 关于用户\n"
            "- 姓名：张三\n\n"
        )
        dreaming = (
            "## Promoted From Short-Term Memory (2026-04-01)\n\n"
            "<!-- openclaw-memory-promotion:memory:f.md:1:5 -->\n"
            "- snippet [score=0.900 recalls=3 avg=0.700 source=f.md:1-5]\n\n"
        )
        md = manual + dreaming

        new_content, stats = build_cleaned_content(md, {"memory:f.md:1:5"})

        assert "关于用户" in new_content
        assert "张三" in new_content
        assert stats.deleted == 1

    def test_real_fixture_manual_content_preserved_after_full_delete(self):
        """真实 fixture：删除全部 item 后手动内容（关于小萌等）仍然存在。"""
        if not REAL_MEMORY_MD.exists():
            pytest.skip("tests/fixtures/real 不存在")

        original = REAL_MEMORY_MD.read_text(encoding="utf-8")
        all_keys = {
            "memory:memory/2026-04-09.md:1:35",
            "memory:memory/2026-04-12.md:1:35",
        }
        new_content, stats = build_cleaned_content(original, all_keys)

        assert "关于小萌" in new_content
        assert "章晓萌" in new_content
        assert "重要事项" in new_content
        assert stats.deleted == 2


# ── 非标准行保留 ──────────────────────────────────────────────────────────────

class TestNonStandardLinesPreserved:
    def test_nonstandard_line_in_section_preserved(self):
        """section 内的非标准行（用户手写内容）保留。"""
        md = (
            "# Long-Term Memory\n\n"
            "## Promoted From Short-Term Memory (2026-04-01)\n\n"
            "手写备注：这是用户自己写的内容\n"
            "<!-- openclaw-memory-promotion:memory:f.md:1:5 -->\n"
            "- snippet [score=0.900 recalls=3 avg=0.700 source=f.md:1-5]\n\n"
        )
        new_content, stats = build_cleaned_content(md, {"memory:f.md:1:5"})

        assert "手写备注" in new_content
        assert stats.deleted == 1

    def test_nonstandard_line_prevents_empty_section_cleanup(self):
        """
        section 内所有 item 被删，但有非标准行 → section header 保留（不算空 section）。
        """
        key = "memory:memory/f.md:1:5"
        md = (
            "# Long-Term Memory\n\n"
            "## Promoted From Short-Term Memory (2026-04-01)\n\n"
            "用户手写内容，不是结构化 item\n"
            f"<!-- openclaw-memory-promotion:{key} -->\n"
            "- snippet [score=0.900 recalls=3 avg=0.700 source=f.md:1-5]\n\n"
        )
        new_content, stats = build_cleaned_content(md, {key})

        # section header 应该保留（因为有非标准行）
        assert "Promoted From Short-Term Memory" in new_content
        assert stats.empty_sections_removed == 0
        assert stats.deleted == 1


# ── 旧格式（无 comment 行）────────────────────────────────────────────────────

class TestFallbackKeyMatching:
    def test_item_without_comment_matched_by_source_coordinates(self):
        """
        无 comment 行的旧格式，通过 source_path:start-end 匹配删除。
        fallback key 格式：{source_path}:{start}-{end}
        """
        md = (
            "# Long-Term Memory\n\n"
            "## Promoted From Short-Term Memory (2026-04-01)\n\n"
            "- old format item [score=0.900 recalls=3 avg=0.700 source=memory/old.md:5-10]\n\n"
        )
        # 用 fallback key（无 "memory:" 前缀，直接是 source path）
        fallback = "memory/old.md:5-10"
        new_content, stats = build_cleaned_content(md, {fallback})

        assert "old format item" not in new_content
        assert stats.deleted == 1

    def test_item_with_comment_not_matched_by_fallback(self):
        """
        有 comment 行的 item，fallback key 不匹配（避免双重删除）。
        comment key 与 fallback key 格式不同，互不干扰。
        """
        comment_key = "memory:memory/f.md:1:5"
        fallback_key = "memory/f.md:1-5"
        md = (
            "# Long-Term Memory\n\n"
            "## Promoted From Short-Term Memory (2026-04-01)\n\n"
            f"<!-- openclaw-memory-promotion:{comment_key} -->\n"
            "- snippet [score=0.900 recalls=3 avg=0.700 source=memory/f.md:1-5]\n\n"
        )
        # 只用 fallback key 删除（不用 comment key）
        new_content, stats = build_cleaned_content(md, {fallback_key})

        # fallback key 能匹配 source，所以也会删除
        assert stats.deleted == 1


# ── 统计数字正确性 ────────────────────────────────────────────────────────────

class TestStats:
    def test_deleted_plus_kept_equals_total(self):
        """deleted + kept = 文件中 item 总数。"""
        keys = [f"memory:memory/f{i}.md:1:5" for i in range(5)]
        items = [{"key": k, "source": f"memory/f{i}.md:1-5"} for i, k in enumerate(keys)]
        md = _make_md([items])

        # 删除前 2 条，保留后 3 条
        _, stats = build_cleaned_content(md, set(keys[:2]))

        assert stats.deleted == 2
        assert stats.kept == 3
        assert stats.deleted + stats.kept == 5

    def test_sections_count_correct(self):
        """sections_before / sections_after 计数正确。"""
        key1 = "memory:memory/a.md:1:5"
        key2 = "memory:memory/b.md:1:5"
        key3 = "memory:memory/c.md:1:5"
        md = _make_md([
            [{"key": key1, "source": "memory/a.md:1-5"}],  # 全删 → empty
            [{"key": key2, "source": "memory/b.md:1-5"}],  # 全删 → empty
            [{"key": key3, "source": "memory/c.md:1-5"}],  # 保留
        ])
        _, stats = build_cleaned_content(md, {key1, key2})

        assert stats.sections_before == 3
        assert stats.sections_after == 1
        assert stats.empty_sections_removed == 2

    def test_returns_cleanup_stats_type(self):
        """返回值第二个是 CleanupStats。"""
        md = _make_md([
            [{"key": "memory:f.md:1:5", "source": "f.md:1-5"}]
        ])
        _, stats = build_cleaned_content(md, set())
        assert isinstance(stats, CleanupStats)


# ── 边界格式 ──────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_file_no_crash(self):
        """空文件不崩溃，返回空字符串（或只有换行）。"""
        new_content, stats = build_cleaned_content("", set())
        assert stats.deleted == 0
        assert stats.kept == 0

    def test_manual_only_file_unchanged(self):
        """纯手动格式（无 Dreaming section）完全不变。"""
        manual = "# MEMORY.md\n\n## 用户信息\n- 姓名：张三\n"
        new_content, stats = build_cleaned_content(manual, {"any_key"})

        assert new_content == manual
        assert stats.deleted == 0
        assert stats.sections_before == 0

    def test_trailing_newline_present(self):
        """输出文本末尾有换行符。"""
        md = _make_md([
            [{"key": "memory:f.md:1:5", "source": "f.md:1-5"}]
        ])
        new_content, _ = build_cleaned_content(md, set())
        assert new_content.endswith("\n")

    def test_delete_nonexistent_key_no_effect(self):
        """删除不存在的 key 不影响任何内容。"""
        md = _make_md([
            [{"key": "memory:f.md:1:5", "source": "f.md:1-5", "snippet": "real item"}]
        ])
        new_content, stats = build_cleaned_content(md, {"memory:nonexistent.md:99:99"})

        assert "real item" in new_content
        assert stats.deleted == 0
        assert stats.kept == 1

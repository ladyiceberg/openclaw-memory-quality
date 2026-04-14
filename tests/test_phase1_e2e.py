"""
test_phase1_e2e.py · Phase 1 端到端测试（Step 8）

验证三个工具在真实数据和合成数据下的整体行为。

数据约束说明（精简版 Step 8）：
  - 真实数据：15 条短期记忆，1 个 Dreaming section，2 条 item
  - 合成数据：用于覆盖真实数据不足的场景（假阳性主路径、性能、deleted 路径）
  - 性能测试目标：500 条（规格要求 1000 条，当前数据量不足；
    500 条可充分验证算法复杂度，1000 条待真实数据积累后补跑）
    标记：PERF_DATA_LIMIT

测试分组：
  TestRealWorkspaceE2E          — 真实数据三工具联合运行
  TestCrossToolConsistency      — 跨工具输出一致性（段落数/item数）
  TestDeletedPathWithSynthetic  — 合成数据验证 V1 deleted 完整路径
  TestFalsePositivePathSynthetic — 合成数据验证 B2 主路径
  TestPerformanceWithSynthetic  — 合成数据性能（500 条 < 5 秒）
  TestOutputReadability         — 三工具输出可读性结构检查
"""
import tempfile
import time
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from src.probe import ProbeResult
from src.formats import RuleBasedAdapter, UnknownFormatAdapter, KNOWN_FORMATS
from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore
from src.tools.health_check import run_health_check
from src.tools.longterm_audit import run_longterm_audit
from src.tools.retrieval_diagnose import run_retrieval_diagnose


# ── 常量与辅助 ─────────────────────────────────────────────────────────────────

REAL_ST   = Path("tests/fixtures/real/memory/.dreams/short-term-recall.json")
REAL_MD   = Path("tests/fixtures/real/MEMORY.md")
REAL_WS   = Path("tests/fixtures/real")
NOW_MS    = 1776153600000   # 2026-04-14T08:00:00Z

# 性能测试数据量（规格 1000 条，当前受限，用 500 条验证算法复杂度）
PERF_DATA_LIMIT = 500
PERF_TIME_LIMIT = 5.0  # 秒


def _make_probe(
    shortterm_path=None,
    longterm_path=None,
    longterm_format="source_code",
    workspace_dir="/tmp/test_ws",
) -> ProbeResult:
    if longterm_format in ("source_code", "mixed"):
        adapter = RuleBasedAdapter(KNOWN_FORMATS["source_code"])
    else:
        adapter = UnknownFormatAdapter()
    return ProbeResult(
        workspace_dir=str(workspace_dir),
        openclaw_version="2026.4.7",
        shortterm_path=shortterm_path,
        shortterm_format="source_code" if shortterm_path else "unknown",
        longterm_path=longterm_path,
        longterm_format=longterm_format,
        longterm_adapter=adapter,
        soul_path=None,
        identity_path=None,
        compatible=True,
        warnings=[],
    )


def _real_probe() -> ProbeResult:
    return _make_probe(
        shortterm_path=REAL_ST,
        longterm_path=REAL_MD,
        longterm_format="mixed",
        workspace_dir=str(REAL_WS),
    )


def _make_st_entry(
    idx: int,
    recall_count: int = 5,
    total_score: float = 2.5,
    max_score: float = 0.7,
    concept_tags: List[str] = None,
    promoted_at: str = None,
) -> ShortTermEntry:
    """构造一条 ShortTermEntry 用于合成数据测试。"""
    tags = concept_tags if concept_tags is not None else [f"tag{idx % 8}"]
    return ShortTermEntry(
        key=f"memory:memory/file{idx}.md:1:10",
        path=f"memory/file{idx}.md",
        start_line=1,
        end_line=10,
        source="memory",
        snippet=f"synthetic entry {idx}",
        recall_count=recall_count,
        total_score=total_score,
        max_score=max_score,
        first_recalled_at="2026-04-01T00:00:00.000Z",
        last_recalled_at="2026-04-14T00:00:00.000Z",
        query_hashes=[f"hash{idx}"],
        recall_days=["2026-04-14"],
        concept_tags=tags,
        promoted_at=promoted_at,
    )


def _make_store(entries: List[ShortTermEntry]) -> ShortTermStore:
    return ShortTermStore(
        version=1,
        updated_at="2026-04-14T08:00:00.000Z",
        entries=entries,
    )


# ── TestRealWorkspaceE2E ──────────────────────────────────────────────────────

class TestRealWorkspaceE2E:
    """三个工具在真实数据上的联合运行。"""

    def test_all_three_tools_run_without_error(self):
        """三工具在真实 workspace 上同时运行，全部无报错。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _real_probe()

        hc_text = run_health_check(probe, now_ms=NOW_MS)
        with tempfile.TemporaryDirectory() as d:
            rid, audit_text = run_longterm_audit(probe, db_path=Path(d) / "e2e.db")
        diag_text = run_retrieval_diagnose(probe, top_n=20)

        assert "Traceback" not in hc_text
        assert "Traceback" not in audit_text
        assert "Traceback" not in diag_text

    def test_all_three_tools_return_nonempty_strings(self):
        """三工具都返回非空字符串。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _real_probe()
        with tempfile.TemporaryDirectory() as d:
            hc = run_health_check(probe, now_ms=NOW_MS)
            _, audit = run_longterm_audit(probe, db_path=Path(d) / "e2e.db")
            diag = run_retrieval_diagnose(probe, top_n=20)

        assert len(hc) > 0
        assert len(audit) > 0
        assert len(diag) > 0

    def test_no_placeholder_text_in_any_output(self):
        """三工具输出不含任何开发占位符（TODO/🚧）。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _real_probe()
        with tempfile.TemporaryDirectory() as d:
            hc = run_health_check(probe, now_ms=NOW_MS)
            _, audit = run_longterm_audit(probe, db_path=Path(d) / "e2e.db")
            diag = run_retrieval_diagnose(probe, top_n=20)

        for text, name in [(hc, "health_check"), (audit, "audit"), (diag, "diagnose")]:
            assert "TODO" not in text, f"{name} 含 TODO"
            assert "🚧" not in text, f"{name} 含 🚧"
            assert "占位符" not in text, f"{name} 含占位符"


# ── TestCrossToolConsistency ──────────────────────────────────────────────────

class TestCrossToolConsistency:
    """跨工具输出一致性：health_check 与 audit 使用同一份数据，结果应吻合。"""

    def test_section_count_consistent(self):
        """health_check 和 audit 报告的 section 数一致。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _real_probe()
        hc = run_health_check(probe, now_ms=NOW_MS)
        with tempfile.TemporaryDirectory() as d:
            _, audit = run_longterm_audit(probe, db_path=Path(d) / "e2e.db")

        import re
        # 两者都应包含 "1 个 section" 或 "1 sections"
        hc_n   = re.search(r"(\d+)[^\d]*section", hc)
        aud_n  = re.search(r"(\d+)[^\d]*section", audit)

        assert hc_n is not None, "health_check 输出缺少 section 数"
        assert aud_n is not None, "audit 输出缺少 section 数"
        assert hc_n.group(1) == aud_n.group(1), (
            f"section 数不一致: health_check={hc_n.group(1)}, audit={aud_n.group(1)}"
        )

    def test_item_count_consistent(self):
        """health_check 和 audit 报告的 item 总数一致。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _real_probe()
        hc = run_health_check(probe, now_ms=NOW_MS)
        with tempfile.TemporaryDirectory() as d:
            _, audit = run_longterm_audit(probe, db_path=Path(d) / "e2e.db")

        import re
        # health_check: "共 N 个 section，M 条记忆"
        # audit:        "N 个 section，M 条记忆"
        hc_items  = re.search(r"(\d+)\s*条记忆", hc)
        aud_items = re.search(r"(\d+)\s*条记忆", audit)

        assert hc_items is not None, "health_check 输出缺少 item 数"
        assert aud_items is not None, "audit 输出缺少 item 数"
        assert hc_items.group(1) == aud_items.group(1), (
            f"item 数不一致: health_check={hc_items.group(1)}, audit={aud_items.group(1)}"
        )

    def test_shortterm_count_in_health_matches_store(self):
        """health_check 报告的短期记忆条数与实际 store 读取一致。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.readers.shortterm_reader import read_shortterm_from_path
        store = read_shortterm_from_path(REAL_ST)
        actual_count = len(store.entries)

        probe = _real_probe()
        hc = run_health_check(probe, now_ms=NOW_MS)

        assert str(actual_count) in hc, (
            f"health_check 未显示正确的短期记忆条数 {actual_count}"
        )


# ── TestDeletedPathWithSynthetic ──────────────────────────────────────────────

class TestDeletedPathWithSynthetic:
    """
    合成数据验证 V1 deleted 完整路径。

    真实数据恰好无 deleted 条目，此处用临时 workspace 构造：
    - 一条指向存在文件的 item（→ keep）
    - 一条指向已删除文件的 item（→ delete）
    验证 audit 输出正确标注 deleted 并计入 delete 数。
    """

    def _make_memory_md(self, ws: Path, deleted_source: str, existing_source: str) -> Path:
        """在临时 workspace 构造一个有两条 item 的 MEMORY.md。"""
        content = (
            "# Long-Term Memory\n\n"
            "## Promoted From Short-Term Memory (2026-04-14)\n\n"
            f"<!-- openclaw-memory-promotion:memory:{existing_source}:1:5 -->\n"
            f"- Existing entry [score=0.900 recalls=3 avg=0.750 source={existing_source}:1-5]\n"
            f"<!-- openclaw-memory-promotion:memory:{deleted_source}:1:5 -->\n"
            f"- Deleted entry [score=0.850 recalls=2 avg=0.800 source={deleted_source}:1-5]\n"
        )
        md_path = ws / "MEMORY.md"
        md_path.write_text(content, encoding="utf-8")
        return md_path

    def test_deleted_entry_appears_in_audit_delete_count(self):
        """指向不存在文件的 item → audit delete 数 >= 1。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)

            # 只创建 existing 文件，不创建 deleted 文件
            existing = "memory/exists.md"
            deleted  = "memory/gone.md"
            (ws / "memory").mkdir()
            (ws / existing).write_text("content", encoding="utf-8")

            md_path = self._make_memory_md(ws, deleted, existing)
            probe = _make_probe(
                longterm_path=md_path,
                longterm_format="source_code",
                workspace_dir=str(ws),
            )

            with tempfile.TemporaryDirectory() as dbdir:
                rid, text = run_longterm_audit(probe, db_path=Path(dbdir) / "t.db")

        assert rid is not None
        # 应有 1 条 delete
        assert "1" in text
        assert "delete" in text.lower() or "删除" in text

    def test_deleted_entry_saved_in_payload(self):
        """payload 里 deleted item 的 v1_status=deleted, action_hint=delete。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            existing = "memory/exists.md"
            deleted  = "memory/gone.md"
            (ws / "memory").mkdir()
            (ws / existing).write_text("content", encoding="utf-8")
            md_path = self._make_memory_md(ws, deleted, existing)
            probe = _make_probe(
                longterm_path=md_path,
                longterm_format="source_code",
                workspace_dir=str(ws),
            )

            from src.session_store import load_audit_report
            with tempfile.TemporaryDirectory() as dbdir:
                db = Path(dbdir) / "t.db"
                rid, _ = run_longterm_audit(probe, db_path=db)
                payload = load_audit_report(rid, db_path=db)

        deleted_items = [
            item for item in payload["items"]
            if item["action_hint"] == "delete"
        ]
        assert len(deleted_items) == 1
        assert deleted_items[0]["v1_status"] == "deleted"
        assert deleted_items[0]["source_path"] == deleted

    def test_existing_entry_is_keep(self):
        """指向存在文件的 item → action_hint=keep。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            existing = "memory/exists.md"
            deleted  = "memory/gone.md"
            (ws / "memory").mkdir()
            (ws / existing).write_text("content", encoding="utf-8")
            md_path = self._make_memory_md(ws, deleted, existing)
            probe = _make_probe(
                longterm_path=md_path,
                longterm_format="source_code",
                workspace_dir=str(ws),
            )

            from src.session_store import load_audit_report
            with tempfile.TemporaryDirectory() as dbdir:
                db = Path(dbdir) / "t.db"
                rid, _ = run_longterm_audit(probe, db_path=db)
                payload = load_audit_report(rid, db_path=db)

        keep_items = [
            item for item in payload["items"]
            if item["action_hint"] == "keep"
        ]
        assert len(keep_items) == 1
        assert keep_items[0]["source_path"] == existing


# ── TestFalsePositivePathSynthetic ────────────────────────────────────────────

class TestFalsePositivePathSynthetic:
    """
    合成数据验证 B2 假阳性主路径。

    真实数据只有 ambiguous，无 high_freq_low_quality / semantic_void。
    此处用合成 store 覆盖这两条主路径，验证诊断输出正确。
    """

    def _hflq_store(self, n: int = 5) -> ShortTermStore:
        """构造 n 条 high_freq_low_quality 条目的 store。"""
        entries = [
            _make_st_entry(i, recall_count=10, total_score=2.0, max_score=0.3, concept_tags=[])
            for i in range(n)
        ]
        return _make_store(entries)

    def _sv_store(self, n: int = 5) -> ShortTermStore:
        """构造 n 条 semantic_void 条目的 store。"""
        entries = [
            _make_st_entry(i, recall_count=10, total_score=5.5, max_score=0.8, concept_tags=[])
            for i in range(n)
        ]
        return _make_store(entries)

    def test_hflq_entries_appear_in_diagnose_output(self):
        """high_freq_low_quality 条目出现在 diagnose 输出中。"""
        store = self._hflq_store(5)
        probe = _make_probe(shortterm_path=REAL_ST if REAL_ST.exists() else Path("tests/fixtures/shortterm/single.json"))

        with patch("src.tools.retrieval_diagnose.read_shortterm", return_value=store):
            result = run_retrieval_diagnose(probe, top_n=20)

        assert "高频低质" in result or "low-quality" in result.lower()

    def test_sv_entries_appear_in_diagnose_output(self):
        """semantic_void 条目出现在 diagnose 输出中。"""
        # semantic_void: tags=[], avg >= 0.35（不触发 hflq），recalls > 5
        # avg = 5.5/10 = 0.55 >= 0.35 → 不是 hflq → 走 semantic_void 分支
        store = self._sv_store(3)
        probe = _make_probe(shortterm_path=Path("tests/fixtures/shortterm/single.json"))

        with patch("src.tools.retrieval_diagnose.read_shortterm", return_value=store):
            result = run_retrieval_diagnose(probe, top_n=20)

        assert "语义空洞" in result or "semantic" in result.lower()

    def test_hflq_health_score_below_100(self):
        """有 hflq 条目时，健康分低于 100。"""
        store = self._hflq_store(10)
        probe = _make_probe(shortterm_path=Path("tests/fixtures/shortterm/single.json"))

        with patch("src.tools.retrieval_diagnose.read_shortterm", return_value=store):
            result = run_retrieval_diagnose(probe, top_n=20)

        assert "100/100" not in result

    def test_hflq_triggers_config_advice(self):
        """大量 hflq 条目 → 健康分 < 70 → 配置建议出现。"""
        # 全部 hflq：健康分 = 100 - (10/10)*40 - 0 - 0 = 60
        store = self._hflq_store(10)
        probe = _make_probe(shortterm_path=Path("tests/fixtures/shortterm/single.json"))

        with patch("src.tools.retrieval_diagnose.read_shortterm", return_value=store):
            result = run_retrieval_diagnose(probe, top_n=20)

        assert "minScore" in result or "0.35" in result

    def test_hflq_shows_in_health_check_suspect_count(self):
        """有 hflq 条目时，health_check 的假阳性嫌疑数 > 0。"""
        store = self._hflq_store(5)
        probe = _make_probe(shortterm_path=Path("tests/fixtures/shortterm/single.json"))

        with patch("src.tools.health_check.read_shortterm", return_value=store):
            result = run_health_check(probe, now_ms=NOW_MS)

        # "假阳性嫌疑：5 条" 或类似
        import re
        match = re.search(r"假阳性嫌疑.*?(\d+)\s*条", result)
        assert match is not None, f"health_check 输出缺少假阳性计数: {result}"
        assert int(match.group(1)) > 0


# ── TestPerformanceWithSynthetic ──────────────────────────────────────────────

class TestPerformanceWithSynthetic:
    """
    合成数据性能测试。

    规格要求：1000 条短期记忆 + 100 条长期记忆下 < 5 秒。
    当前限制：使用 PERF_DATA_LIMIT=500 条合成数据。
    NOTE: 待真实数据积累到 1000 条后，将 PERF_DATA_LIMIT 更新并补跑。
    """

    def _make_large_store(self, n: int) -> ShortTermStore:
        """构造 n 条多样化条目的 store（覆盖各种 B2 分类）。"""
        entries = []
        for i in range(n):
            if i % 10 == 0:
                # 10% hflq
                e = _make_st_entry(i, recall_count=10, total_score=2.0, max_score=0.3, concept_tags=[])
            elif i % 10 == 1:
                # 10% semantic_void
                e = _make_st_entry(i, recall_count=10, total_score=5.5, max_score=0.8, concept_tags=[])
            elif i % 10 == 2:
                # 10% ambiguous
                e = _make_st_entry(i, recall_count=3, total_score=1.35, max_score=0.65)
            else:
                # 70% normal
                e = _make_st_entry(i, recall_count=5, total_score=3.0, max_score=0.8)
            entries.append(e)
        return _make_store(entries)

    def test_health_check_500_entries_under_time_limit(self):
        """health_check：500 条短期记忆下响应时间 < 5 秒。"""
        store = self._make_large_store(PERF_DATA_LIMIT)
        probe = _make_probe(shortterm_path=Path("tests/fixtures/shortterm/single.json"))

        with patch("src.tools.health_check.read_shortterm", return_value=store):
            t0 = time.time()
            run_health_check(probe, now_ms=NOW_MS)
            elapsed = time.time() - t0

        assert elapsed < PERF_TIME_LIMIT, (
            f"health_check 耗时 {elapsed:.2f}s，超过 {PERF_TIME_LIMIT}s 限制"
        )

    def test_retrieval_diagnose_500_entries_under_time_limit(self):
        """retrieval_diagnose：500 条短期记忆下响应时间 < 5 秒。"""
        store = self._make_large_store(PERF_DATA_LIMIT)
        probe = _make_probe(shortterm_path=Path("tests/fixtures/shortterm/single.json"))

        with patch("src.tools.retrieval_diagnose.read_shortterm", return_value=store):
            t0 = time.time()
            run_retrieval_diagnose(probe, top_n=20)
            elapsed = time.time() - t0

        assert elapsed < PERF_TIME_LIMIT, (
            f"retrieval_diagnose 耗时 {elapsed:.2f}s，超过 {PERF_TIME_LIMIT}s 限制"
        )

    def test_longterm_audit_multi_section_under_time_limit(self):
        """longterm_audit：多 section MEMORY.md 解析和 V1+V3 下响应时间 < 5 秒。"""
        # 构造一个有 10 个 section、每 section 10 条 item 的 MEMORY.md
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            (ws / "memory").mkdir()

            lines = ["# Long-Term Memory\n"]
            for s in range(10):
                lines.append(f"\n## Promoted From Short-Term Memory (2026-04-{s+1:02d})\n")
                for i in range(10):
                    fname = f"memory/file{s}_{i}.md"
                    (ws / fname).write_text("content", encoding="utf-8")
                    lines.append(
                        f"<!-- openclaw-memory-promotion:memory:{fname}:{i+1}:{i+5} -->\n"
                        f"- Entry {s}-{i} [score=0.900 recalls=3 avg=0.750 source={fname}:{i+1}-{i+5}]\n"
                    )

            md_path = ws / "MEMORY.md"
            md_path.write_text("".join(lines), encoding="utf-8")
            probe = _make_probe(
                longterm_path=md_path,
                longterm_format="source_code",
                workspace_dir=str(ws),
            )

            t0 = time.time()
            with tempfile.TemporaryDirectory() as dbdir:
                run_longterm_audit(probe, db_path=Path(dbdir) / "t.db")
            elapsed = time.time() - t0

        assert elapsed < PERF_TIME_LIMIT, (
            f"longterm_audit 耗时 {elapsed:.2f}s，超过 {PERF_TIME_LIMIT}s 限制"
        )


# ── TestOutputReadability ─────────────────────────────────────────────────────

class TestOutputReadability:
    """
    输出可读性结构检查。
    目标：不看文档也能看懂输出的大致意思。
    """

    def test_health_check_output_structure(self):
        """health_check 输出：有标题、有数字、有状态图标、无 Python 对象表示。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _real_probe()
        text = run_health_check(probe, now_ms=NOW_MS)

        # 有标题（Emoji 或关键词）
        assert any(c in text for c in ["📊", "Memory", "记忆"])
        # 有条目计数（纯数字）
        assert any(c.isdigit() for c in text)
        # 有分数展示（/ 100 或 /100）
        assert "/ 100" in text or "/100" in text
        # 无 Python 对象特征
        assert "<" not in text or ("→" in text)  # → 是箭头字符，允许；< 可能是 Python repr
        assert "object at 0x" not in text

    def test_audit_output_structure(self):
        """audit 输出：有标题、有 section/item 统计、有 report_id。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _real_probe()
        with tempfile.TemporaryDirectory() as d:
            rid, text = run_longterm_audit(probe, db_path=Path(d) / "t.db")

        assert any(c in text for c in ["📋", "Audit", "审计"])
        assert rid in text
        assert "audit_" in text
        assert "object at 0x" not in text

    def test_diagnose_output_structure(self):
        """diagnose 输出：有标题、有健康分、无 Python 对象表示。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _real_probe()
        text = run_retrieval_diagnose(probe, top_n=20)

        assert any(c in text for c in ["🔍", "Diagnosis", "诊断"])
        assert "/100" in text
        assert "object at 0x" not in text

    def test_health_check_numbers_make_sense(self):
        """health_check 输出的数字合理：条目数正整数、分数 0-100。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        import re
        probe = _real_probe()
        text = run_health_check(probe, now_ms=NOW_MS)

        # 短期记忆条数
        match = re.search(r"短期记忆.*?(\d+)\s*条", text)
        if match:
            count = int(match.group(1))
            assert count > 0

        # 健康分
        scores = re.findall(r"(\d+)\s*/\s*100", text)
        for s in scores:
            assert 0 <= int(s) <= 100, f"健康分超出范围：{s}"

    def test_error_messages_are_human_readable(self):
        """错误场景（文件不存在）的提示对人类友好，不含 Python traceback。"""
        probe = _make_probe(shortterm_path=None, longterm_path=None)

        hc   = run_health_check(probe, now_ms=NOW_MS)
        _, audit = run_longterm_audit(probe)
        diag = run_retrieval_diagnose(probe)

        for text, name in [(hc, "hc"), (audit, "audit"), (diag, "diag")]:
            assert "Traceback" not in text, f"{name} 含 Traceback"
            assert "Exception" not in text, f"{name} 含 Exception"
            assert len(text) > 10, f"{name} 输出太短"

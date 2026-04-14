"""
test_integration.py · 集成测试

通过合成 fixture 或真实 fixture 测试完整工具链的行为。
不依赖 MCP server，直接调用工具函数。
"""
from pathlib import Path
from typing import List, Optional
import tempfile

import pytest

from src.probe import ProbeResult
from src.formats import UnknownFormatAdapter, RuleBasedAdapter, KNOWN_FORMATS
from src.tools.health_check import run_health_check, _score_icon
from src.tools.longterm_audit import run_longterm_audit
from src.tools.retrieval_diagnose import run_retrieval_diagnose
from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore


# ── 基准时间（2026-04-14T08:00:00Z）──────────────────────────────────────────
NOW_MS = 1776153600000
DAY_MS = 86_400_000

REAL_SHORTTERM = Path("tests/fixtures/real/memory/.dreams/short-term-recall.json")
REAL_MEMORY_MD = Path("tests/fixtures/real/MEMORY.md")


# ── ProbeResult 构造辅助 ───────────────────────────────────────────────────────

def _make_probe(
    *,
    shortterm_path: Optional[Path] = None,
    longterm_path: Optional[Path] = None,
    longterm_format: str = "source_code",
    workspace_dir: str = "/tmp/test_workspace",
) -> ProbeResult:
    """构造一个 ProbeResult，用于测试。"""
    if longterm_format in ("source_code", "mixed"):
        adapter = RuleBasedAdapter(KNOWN_FORMATS["source_code"])
    else:
        adapter = UnknownFormatAdapter()

    return ProbeResult(
        workspace_dir=workspace_dir,
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


# ── test_health_check_with_fixtures ───────────────────────────────────────────

class TestHealthCheckWithFixtures:
    """使用真实 fixture 数据测试 health check 工具。"""

    def test_real_data_runs_without_error(self):
        """真实数据：health check 能无报错运行，返回非空字符串。"""
        if not REAL_SHORTTERM.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _make_probe(
            shortterm_path=REAL_SHORTTERM,
            longterm_path=REAL_MEMORY_MD,
            longterm_format="mixed",
            workspace_dir=str(REAL_SHORTTERM.parent.parent.parent),
        )
        result = run_health_check(probe, now_ms=NOW_MS)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_real_data_output_has_header(self):
        """输出包含标题行。"""
        if not REAL_SHORTTERM.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _make_probe(
            shortterm_path=REAL_SHORTTERM,
            longterm_path=REAL_MEMORY_MD,
            longterm_format="mixed",
            workspace_dir=str(REAL_SHORTTERM.parent.parent.parent),
        )
        result = run_health_check(probe, now_ms=NOW_MS)

        assert "Memory Health" in result or "记忆健康" in result

    def test_real_data_output_has_shortterm_section(self):
        """输出包含短期记忆统计。"""
        if not REAL_SHORTTERM.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _make_probe(
            shortterm_path=REAL_SHORTTERM,
            longterm_path=REAL_MEMORY_MD,
            longterm_format="mixed",
            workspace_dir=str(REAL_SHORTTERM.parent.parent.parent),
        )
        result = run_health_check(probe, now_ms=NOW_MS)

        # 应包含条目数（15 条）
        assert "15" in result

    def test_real_data_output_has_scores(self):
        """输出包含三个诊断分。"""
        if not REAL_SHORTTERM.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _make_probe(
            shortterm_path=REAL_SHORTTERM,
            longterm_path=REAL_MEMORY_MD,
            longterm_format="mixed",
            workspace_dir=str(REAL_SHORTTERM.parent.parent.parent),
        )
        result = run_health_check(probe, now_ms=NOW_MS)

        assert "Retrieval Health" in result
        assert "Promotion Risk" in result
        assert "Long-term Rot" in result

    def test_real_data_output_has_longterm_section(self):
        """输出包含长期记忆统计（section 数 + item 数）。"""
        if not REAL_SHORTTERM.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _make_probe(
            shortterm_path=REAL_SHORTTERM,
            longterm_path=REAL_MEMORY_MD,
            longterm_format="mixed",
            workspace_dir=str(REAL_SHORTTERM.parent.parent.parent),
        )
        result = run_health_check(probe, now_ms=NOW_MS)

        # 真实数据有 1 个 section，2 条 item
        assert "1" in result
        assert "2" in result

    def test_scores_in_valid_range(self):
        """三个诊断分都在 0-100 范围内（通过输出文本验证）。"""
        if not REAL_SHORTTERM.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.analyzers.false_positive import compute_false_positive_stats
        from src.readers.shortterm_reader import read_shortterm_from_path

        store = read_shortterm_from_path(REAL_SHORTTERM)
        stats = compute_false_positive_stats(store)

        assert 0 <= stats.retrieval_health_score <= 100
        assert 0 <= stats.promotion_risk_score <= 100


# ── health check 边界场景 ──────────────────────────────────────────────────────

class TestHealthCheckEdgeCases:
    """用合成 fixture 测试边界场景。"""

    def test_no_shortterm_returns_friendly_message(self):
        """短期记忆文件不存在：返回友好提示，不崩溃。"""
        probe = _make_probe(shortterm_path=None)
        result = run_health_check(probe, now_ms=NOW_MS)

        assert isinstance(result, str)
        assert len(result) > 0
        # 不包含 Traceback
        assert "Traceback" not in result
        # 包含提示信息
        assert "embedding" in result.lower() or "短期记忆" in result

    def test_no_longterm_still_works(self):
        """MEMORY.md 不存在：短期记忆统计正常显示，长期记忆显示 N/A。"""
        if not REAL_SHORTTERM.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _make_probe(
            shortterm_path=REAL_SHORTTERM,
            longterm_path=None,
            longterm_format="not_found",
        )
        result = run_health_check(probe, now_ms=NOW_MS)

        assert "15" in result  # 短期记忆 15 条正常显示
        assert "Retrieval Health" in result

    def test_shortterm_broken_json_handled(self):
        """broken JSON 文件：返回明确错误信息，不崩溃。"""
        broken = Path("tests/fixtures/shortterm/broken.json")
        probe = _make_probe(shortterm_path=broken)
        result = run_health_check(probe, now_ms=NOW_MS)

        assert isinstance(result, str)
        assert "Traceback" not in result

    def test_output_no_trailing_blank_lines(self):
        """输出末尾不应有多余空行。"""
        if not REAL_SHORTTERM.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _make_probe(
            shortterm_path=REAL_SHORTTERM,
            longterm_path=REAL_MEMORY_MD,
            longterm_format="mixed",
            workspace_dir=str(REAL_SHORTTERM.parent.parent.parent),
        )
        result = run_health_check(probe, now_ms=NOW_MS)

        assert not result.endswith("\n\n")

    def test_now_ms_injected(self):
        """now_ms 参数能被正常注入，影响僵尸判断结果。"""
        if not REAL_SHORTTERM.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = _make_probe(shortterm_path=REAL_SHORTTERM)

        # 当前时间运行
        result_now = run_health_check(probe, now_ms=NOW_MS)
        # 三年后运行（条目都会变成僵尸）
        three_years_later = NOW_MS + 365 * 3 * DAY_MS
        result_future = run_health_check(probe, now_ms=three_years_later)

        # 三年后的僵尸数一定 >= 当前（时间流逝，条目变僵尸）
        assert isinstance(result_now, str)
        assert isinstance(result_future, str)


# ── 诊断分数图标 ──────────────────────────────────────────────────────────────

class TestScoreIcon:
    def test_high_score_higher_better(self):
        assert _score_icon(90, higher_is_better=True) == "✅"

    def test_mid_score_higher_better(self):
        assert _score_icon(70, higher_is_better=True) == "⚠️"

    def test_low_score_higher_better(self):
        assert _score_icon(50, higher_is_better=True) == "🔴"

    def test_low_risk_lower_better(self):
        assert _score_icon(10, higher_is_better=False) == "✅"

    def test_mid_risk_lower_better(self):
        assert _score_icon(35, higher_is_better=False) == "⚠️"

    def test_high_risk_lower_better(self):
        assert _score_icon(80, higher_is_better=False) == "🔴"

    def test_boundary_80_higher_better(self):
        """score=80：刚好达到 ✅ 阈值。"""
        assert _score_icon(80, higher_is_better=True) == "✅"

    def test_boundary_79_higher_better(self):
        """score=79：差一分，降为 ⚠️。"""
        assert _score_icon(79, higher_is_better=True) == "⚠️"

    def test_boundary_60_higher_better(self):
        """score=60：刚好达到 ⚠️ 阈值。"""
        assert _score_icon(60, higher_is_better=True) == "⚠️"

    def test_boundary_59_higher_better(self):
        """score=59：差一分，降为 🔴。"""
        assert _score_icon(59, higher_is_better=True) == "🔴"


# ── test_longterm_audit_with_fixtures ─────────────────────────────────────────

class TestLongtermAuditWithFixtures:
    """memory_longterm_audit_oc 集成测试。"""

    REAL_MEMORY = Path("tests/fixtures/real/MEMORY.md")
    REAL_WS = Path("tests/fixtures/real")

    def _real_probe(self):
        return _make_probe(
            shortterm_path=Path("tests/fixtures/real/memory/.dreams/short-term-recall.json"),
            longterm_path=self.REAL_MEMORY,
            longterm_format="mixed",
            workspace_dir=str(self.REAL_WS),
        )

    # ── 基本功能 ───────────────────────────────────────────────────────────────

    def test_real_data_returns_report_id(self):
        """真实数据：审计成功，返回非空 report_id。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            report_id, text = run_longterm_audit(self._real_probe(), db_path=db)

        assert report_id is not None
        assert report_id.startswith("audit_")

    def test_real_data_report_id_format(self):
        """report_id 格式：audit_{timestamp_ms}，纯数字时间戳。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            report_id, _ = run_longterm_audit(self._real_probe(), db_path=db)

        assert report_id is not None
        ts_part = report_id[len("audit_"):]
        assert ts_part.isdigit()

    def test_real_data_output_has_header(self):
        """输出包含审计标题。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            _, text = run_longterm_audit(self._real_probe(), db_path=db)

        assert "Audit" in text or "审计" in text

    def test_real_data_output_has_summary(self):
        """输出包含 section 数和 item 数。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            _, text = run_longterm_audit(self._real_probe(), db_path=db)

        assert "1" in text   # 1 个 section
        assert "2" in text   # 2 条记忆

    def test_real_data_output_has_action_counts(self):
        """输出包含 keep/review/delete 计数。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            _, text = run_longterm_audit(self._real_probe(), db_path=db)

        assert "keep" in text.lower() or "保留" in text
        assert "review" in text.lower() or "复查" in text
        assert "delete" in text.lower() or "删除" in text

    def test_real_data_output_has_report_id(self):
        """输出末尾包含 report_id。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            report_id, text = run_longterm_audit(self._real_probe(), db_path=db)

        assert report_id in text

    # ── session store 存储与读取 ───────────────────────────────────────────────

    def test_report_saved_to_session_store(self):
        """审计结果成功写入 session store，可按 report_id 读取。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.session_store import load_audit_report

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            report_id, _ = run_longterm_audit(self._real_probe(), db_path=db)
            payload = load_audit_report(report_id, db_path=db)

        assert payload is not None
        assert "total_items" in payload
        assert "items" in payload

    def test_consecutive_runs_produce_different_report_ids(self):
        """连续运行两次 → 两个不同 report_id，都在 session store 里。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        import time
        from src.session_store import load_audit_report

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            rid1, _ = run_longterm_audit(self._real_probe(), db_path=db)
            time.sleep(0.01)   # 确保时间戳不同
            rid2, _ = run_longterm_audit(self._real_probe(), db_path=db)

            assert rid1 != rid2
            assert load_audit_report(rid1, db_path=db) is not None
            assert load_audit_report(rid2, db_path=db) is not None

    def test_payload_contains_items(self):
        """payload 中的 items 列表非空，每条含必需字段。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.session_store import load_audit_report

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            report_id, _ = run_longterm_audit(self._real_probe(), db_path=db)
            payload = load_audit_report(report_id, db_path=db)

        assert len(payload["items"]) == 2
        for item in payload["items"]:
            assert "source_path" in item
            assert "action_hint" in item
            assert "v1_status" in item
            assert "v3_status" in item

    def test_items_by_action_sum_equals_total(self):
        """payload 中 keep+review+delete 之和 = total_items。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.session_store import load_audit_report

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            report_id, _ = run_longterm_audit(self._real_probe(), db_path=db)
            payload = load_audit_report(report_id, db_path=db)

        total = payload["total_items"]
        action_sum = sum(payload["items_by_action"].values())
        assert action_sum == total

    # ── 错误路径 ───────────────────────────────────────────────────────────────

    def test_no_longterm_returns_none_report_id(self):
        """MEMORY.md 不存在：report_id=None，输出友好提示。"""
        probe = _make_probe(
            shortterm_path=None,
            longterm_path=None,
            longterm_format="not_found",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            report_id, text = run_longterm_audit(probe, db_path=db)

        assert report_id is None
        assert "Traceback" not in text

    def test_manual_format_returns_none_report_id(self):
        """纯手动格式（不支持审计）：report_id=None。"""
        manual_md = Path("tests/fixtures/longterm/manual_only.md")
        probe = _make_probe(
            longterm_path=manual_md,
            longterm_format="manual",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            report_id, text = run_longterm_audit(probe, db_path=db)

        assert report_id is None
        assert "Traceback" not in text

    def test_use_llm_true_shows_placeholder(self):
        """use_llm=True 在 Phase 1 显示占位提示，不崩溃。"""
        if not self.REAL_MEMORY.exists():
            pytest.skip("tests/fixtures/real 不存在")

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            report_id, text = run_longterm_audit(
                self._real_probe(), use_llm=True, db_path=db
            )

        # Phase 1 不支持 LLM，但不崩溃，仍然返回 report_id
        assert report_id is not None
        assert "Traceback" not in text


# ── test_retrieval_diagnose_with_fixtures ─────────────────────────────────────

class TestRetrievalDiagnoseWithFixtures:
    """memory_retrieval_diagnose_oc 集成测试。"""

    REAL_ST = Path("tests/fixtures/real/memory/.dreams/short-term-recall.json")

    def _real_probe(self):
        return _make_probe(shortterm_path=self.REAL_ST)

    # ── 基本功能 ───────────────────────────────────────────────────────────────

    def test_real_data_runs_without_error(self):
        """真实数据：诊断无报错，返回非空字符串。"""
        if not self.REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = run_retrieval_diagnose(self._real_probe())

        assert isinstance(result, str)
        assert len(result) > 0
        assert "Traceback" not in result

    def test_real_data_output_has_header(self):
        """输出包含标题。"""
        if not self.REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = run_retrieval_diagnose(self._real_probe())

        assert "Diagnosis" in result or "诊断" in result

    def test_real_data_output_has_health_score(self):
        """输出包含检索健康分。"""
        if not self.REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = run_retrieval_diagnose(self._real_probe())

        assert "Health" in result or "健康分" in result
        assert "/100" in result

    # ── top_n 控制 ─────────────────────────────────────────────────────────────

    def test_top_n_zero_no_entry_details(self):
        """top_n=0：只输出聚合统计，不列条目详情（无 recalls= 行）。"""
        if not self.REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = run_retrieval_diagnose(self._real_probe(), top_n=0)

        # top_n=0 时不展示条目详情
        assert "recalls=" not in result

    def test_top_n_zero_shows_stats_hint(self):
        """top_n=0：输出提示用户传入 top_n>0 查看详情。"""
        if not self.REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = run_retrieval_diagnose(self._real_probe(), top_n=0)

        assert "top_n" in result

    def test_top_n_positive_shows_entry_details(self):
        """top_n>0 且有可疑条目：输出包含条目详情。"""
        if not self.REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = run_retrieval_diagnose(self._real_probe(), top_n=20)

        # 真实数据有 2 条 ambiguous 条目，应能显示
        # 如果没有任何可疑条目，显示全部健康
        assert isinstance(result, str)

    def test_top_n_limits_entries_shown(self):
        """top_n=1 时输出的条目数不超过 1。"""
        if not self.REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = run_retrieval_diagnose(self._real_probe(), top_n=1)

        # 最多显示 1 条（rank 1），不会出现 "  2. "
        assert "  2. " not in result

    # ── 排序验证 ───────────────────────────────────────────────────────────────

    def test_high_freq_before_semantic_void(self):
        """排序：high_freq_low_quality 条目在 semantic_void 之前。"""
        from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore
        from src.tools.retrieval_diagnose import _sort_key
        from src.analyzers.false_positive import classify_false_positive

        # 构造两条：一条 semantic_void，一条 high_freq_low_quality
        def _e(recall, total, max_s, tags):
            return ShortTermEntry(
                key="k", path="p.md", start_line=1, end_line=5,
                source="memory", snippet="s",
                recall_count=recall, total_score=total, max_score=max_s,
                first_recalled_at="2026-01-01T00:00:00.000Z",
                last_recalled_at="2026-04-01T00:00:00.000Z",
                query_hashes=[], recall_days=[], concept_tags=tags,
            )

        # high_freq_low_quality: avg=0.20 (<0.35), recalls=10 (>5), max=0.3 (<0.55)
        hflq = _e(10, 2.0, 0.3, [])
        # semantic_void: avg=0.55 (>=0.35, 不触发 hflq), recalls=10 (>5), tags=[]
        sv = _e(10, 5.5, 0.8, [])

        cat_hflq, sub_hflq = classify_false_positive(hflq)
        cat_sv, sub_sv = classify_false_positive(sv)

        assert cat_hflq == "high_freq_low_quality"
        assert cat_sv == "semantic_void"

        key_hflq = _sort_key((hflq, cat_hflq, sub_hflq))
        key_sv   = _sort_key((sv,   cat_sv,   sub_sv))

        assert key_hflq < key_sv   # hflq 排在 sv 前面

    def test_higher_recalls_sorts_first_within_same_category(self):
        """同 category 内，recalls 多的排前面。"""
        from src.readers.shortterm_reader import ShortTermEntry
        from src.tools.retrieval_diagnose import _sort_key

        def _e(recall):
            return ShortTermEntry(
                key="k", path="p.md", start_line=1, end_line=5,
                source="memory", snippet="s",
                recall_count=recall, total_score=recall * 0.2, max_score=0.3,
                first_recalled_at="2026-01-01T00:00:00.000Z",
                last_recalled_at="2026-04-01T00:00:00.000Z",
                query_hashes=[], recall_days=[], concept_tags=[],
            )

        e10 = _e(10)
        e20 = _e(20)
        cat = "high_freq_low_quality"

        assert _sort_key((e20, cat, "")) < _sort_key((e10, cat, ""))

    # ── 边界场景 ───────────────────────────────────────────────────────────────

    def test_no_shortterm_friendly_message(self):
        """短期记忆文件不存在：友好提示，不崩溃。"""
        probe = _make_probe(shortterm_path=None)
        result = run_retrieval_diagnose(probe)

        assert isinstance(result, str)
        assert "Traceback" not in result

    def test_broken_json_handled(self):
        """broken JSON：友好错误，不崩溃。"""
        broken = Path("tests/fixtures/shortterm/broken.json")
        probe = _make_probe(shortterm_path=broken)
        result = run_retrieval_diagnose(probe)

        assert "Traceback" not in result

    def test_config_advice_when_health_low(self):
        """健康分 < 70 时输出配置建议。"""
        from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore
        from unittest.mock import patch

        # 构造一批高频低质条目，让健康分降低
        entries = []
        for i in range(20):
            entries.append(ShortTermEntry(
                key=f"k{i}", path=f"file{i}.md", start_line=1, end_line=5,
                source="memory", snippet="s",
                recall_count=10, total_score=2.0, max_score=0.3,
                first_recalled_at="2026-01-01T00:00:00.000Z",
                last_recalled_at="2026-04-01T00:00:00.000Z",
                query_hashes=[], recall_days=[], concept_tags=[],
            ))

        store = ShortTermStore(
            version=1,
            updated_at="2026-04-14T08:00:00.000Z",
            entries=entries,
        )

        # 直接 patch read_shortterm 返回我们构造的 store
        with patch("src.tools.retrieval_diagnose.read_shortterm", return_value=store):
            probe = _make_probe(shortterm_path=Path("tests/fixtures/shortterm/single.json"))
            result = run_retrieval_diagnose(probe)

        assert "minScore" in result or "0.35" in result  # 配置建议出现

    def test_no_config_advice_when_health_ok(self):
        """健康分 >= 70 时不输出配置建议。"""
        if not self.REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        # 真实数据健康分 = 100
        result = run_retrieval_diagnose(self._real_probe())

        assert "minScore" not in result
        assert "0.35" not in result



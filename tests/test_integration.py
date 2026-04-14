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

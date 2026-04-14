"""
test_config_doctor.py · memory_config_doctor_oc 核心逻辑测试

纯只读工具，测试重点：
  - 四条推断的触发/不触发（边界值）
  - D1 触发时 D4 被跳过
  - 触发任何推断时 JSON5 配置片段出现
  - 全部健康时 all-good 提示
  - 真实数据回归
"""
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

import pytest

from src.formats import RuleBasedAdapter, KNOWN_FORMATS, UnknownFormatAdapter
from src.probe import ProbeResult
from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore
from src.tools.config_doctor import (
    FTS_AVG_THRESHOLD,
    FTS_EMPTY_TAG_RATIO,
    HFLQ_RATIO_THRESHOLD,
    MMR_MIN_OVERLAP_PAIRS,
    EMB_AVG_LOW,
    EMB_AVG_HIGH,
    EMB_HIGH_SCORE_MIN_RATIO,
    _diagnose_embedding,
    _diagnose_fts,
    _diagnose_minscore,
    _diagnose_mmr,
    run_config_doctor,
)

REAL_ST = Path("tests/fixtures/real/memory/.dreams/short-term-recall.json")


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _entry(
    idx: int = 0,
    recall: int = 5,
    total: float = 2.5,
    max_score: float = 0.7,
    tags: Optional[List[str]] = None,
    path: str = "memory/f.md",
    start: int = 1,
    end: int = 10,
) -> ShortTermEntry:
    return ShortTermEntry(
        key=f"k{idx}", path=path, start_line=start, end_line=end,
        source="memory", snippet="s",
        recall_count=recall, total_score=total, max_score=max_score,
        first_recalled_at="2026-01-01T00:00:00.000Z",
        last_recalled_at="2026-04-01T00:00:00.000Z",
        query_hashes=[], recall_days=[],
        concept_tags=tags if tags is not None else ["tag1"],
    )


def _store(entries: List[ShortTermEntry]) -> ShortTermStore:
    return ShortTermStore(
        version=1, updated_at="2026-04-14T00:00:00.000Z",
        entries=entries,
    )


def _probe_with_store(store: ShortTermStore) -> ProbeResult:
    """构造一个 probe，patch read_shortterm 返回给定 store。"""
    return ProbeResult(
        workspace_dir="/tmp",
        openclaw_version=None,
        shortterm_path=Path("tests/fixtures/shortterm/single.json"),
        shortterm_format="source_code",
        longterm_path=None, longterm_format="not_found",
        longterm_adapter=UnknownFormatAdapter(),
        soul_path=None, identity_path=None,
        compatible=True, warnings=[],
    )


# ── D1：FTS 降级 ──────────────────────────────────────────────────────────────

class TestDiagnoseFTS:
    def test_triggered_when_both_conditions_met(self):
        """avg < 0.45 AND empty_tag > 40% → 触发。"""
        # avg = 0.2 < 0.45，全空标签 → 100% > 40%
        entries = [_entry(i, recall=10, total=2.0, tags=[]) for i in range(10)]
        result = _diagnose_fts(entries)
        assert result.triggered is True
        assert result.code == "fts"

    def test_not_triggered_when_avg_ok(self):
        """avg >= 0.45 → 不触发（即使 empty_tag 高）。"""
        entries = [_entry(i, recall=5, total=5.0, tags=[]) for i in range(10)]
        # avg = 1.0 >= 0.45
        result = _diagnose_fts(entries)
        assert result.triggered is False

    def test_not_triggered_when_tags_ok(self):
        """空标签占比 <= 40% → 不触发（即使 avg 低）。"""
        # 5 个空标签，5 个有标签 → 50% → 50% > 40%，改为 3 空 7 有
        entries = (
            [_entry(i, recall=10, total=1.0, tags=[]) for i in range(3)] +
            [_entry(i+3, recall=10, total=1.0, tags=["t"]) for i in range(7)]
        )
        # empty_ratio = 30% <= 40%，avg = 0.1 < 0.45
        result = _diagnose_fts(entries)
        assert result.triggered is False

    def test_empty_entries_not_triggered(self):
        """空列表不触发。"""
        result = _diagnose_fts([])
        assert result.triggered is False

    def test_signal_data_populated(self):
        """触发时 signal_data 包含 avg 和 empty_pct。"""
        entries = [_entry(i, recall=10, total=2.0, tags=[]) for i in range(10)]
        result = _diagnose_fts(entries)
        assert "avg" in result.signal_data
        assert "empty_pct" in result.signal_data
        assert result.signal_data["avg"] == pytest.approx(0.2)


# ── D2：minScore 过低 ────────────────────────────────────────────────────────

class TestDiagnoseMinScore:
    def test_triggered_when_hflq_high(self):
        """高频低质占比 > 15% → 触发。"""
        from src.analyzers.false_positive import compute_false_positive_stats
        # 全部是高频低质（avg=0.2 <0.35, recalls=10 >5, max=0.3 <0.55）
        entries = [_entry(i, recall=10, total=2.0, max_score=0.3, tags=[]) for i in range(10)]
        fp_stats = compute_false_positive_stats(_store(entries))
        result = _diagnose_minscore(entries, fp_stats)
        assert result.triggered is True

    def test_not_triggered_when_hflq_low(self):
        """高频低质占比 <= 15% → 不触发。"""
        from src.analyzers.false_positive import compute_false_positive_stats
        # 只有 1/10 是高频低质
        entries = (
            [_entry(0, recall=10, total=2.0, max_score=0.3, tags=[])] +
            [_entry(i+1, recall=3, total=2.5, tags=["t"]) for i in range(9)]
        )
        fp_stats = compute_false_positive_stats(_store(entries))
        result = _diagnose_minscore(entries, fp_stats)
        assert result.triggered is False

    def test_empty_entries_not_triggered(self):
        from src.analyzers.false_positive import compute_false_positive_stats
        fp_stats = compute_false_positive_stats(_store([]))
        result = _diagnose_minscore([], fp_stats)
        assert result.triggered is False


# ── D3：MMR 未开启 ────────────────────────────────────────────────────────────

class TestDiagnoseMMR:
    def test_triggered_when_many_overlap_pairs(self):
        """同一文件 >= 3 对重叠 → 触发。"""
        # 同一个文件（f.md），4 条条目，行号互相重叠
        entries = [
            _entry(0, path="memory/f.md", start=1,  end=20),
            _entry(1, path="memory/f.md", start=10, end=30),
            _entry(2, path="memory/f.md", start=15, end=35),
            _entry(3, path="memory/f.md", start=5,  end=25),
        ]
        result = _diagnose_mmr(entries)
        assert result.triggered is True
        assert result.signal_data["pairs"] >= MMR_MIN_OVERLAP_PAIRS

    def test_not_triggered_when_few_overlaps(self):
        """重叠对数 < 3 → 不触发。"""
        # 只有 2 条，1 对重叠
        entries = [
            _entry(0, path="memory/f.md", start=1,  end=10),
            _entry(1, path="memory/f.md", start=5,  end=15),
        ]
        result = _diagnose_mmr(entries)
        assert result.triggered is False

    def test_not_triggered_when_different_files(self):
        """不同文件的行号重叠不算。"""
        entries = [
            _entry(0, path="memory/a.md", start=1, end=20),
            _entry(1, path="memory/b.md", start=5, end=25),
            _entry(2, path="memory/c.md", start=10, end=30),
        ]
        result = _diagnose_mmr(entries)
        assert result.triggered is False

    def test_not_triggered_adjacent_ranges(self):
        """相邻但不重叠的范围不计入。"""
        entries = [
            _entry(0, path="memory/f.md", start=1,  end=10),
            _entry(1, path="memory/f.md", start=11, end=20),
            _entry(2, path="memory/f.md", start=21, end=30),
        ]
        result = _diagnose_mmr(entries)
        assert result.triggered is False

    def test_empty_entries_not_triggered(self):
        result = _diagnose_mmr([])
        assert result.triggered is False


# ── D4：embedding 质量不足 ────────────────────────────────────────────────────

class TestDiagnoseEmbedding:
    def test_triggered_in_ambiguous_range(self):
        """avg ∈ [0.40, 0.55) AND 高分占比 < 10% → 触发。"""
        # avg = 0.48（在区间内），全部低于 0.70 高分阈值
        entries = [_entry(i, recall=5, total=0.48*5) for i in range(20)]
        result = _diagnose_embedding(entries)
        assert result.triggered is True

    def test_not_triggered_when_avg_high(self):
        """avg >= 0.55 → 不触发。"""
        entries = [_entry(i, recall=5, total=0.60*5) for i in range(10)]
        result = _diagnose_embedding(entries)
        assert result.triggered is False

    def test_not_triggered_when_avg_low(self):
        """avg < 0.40 → 不触发（D1 的信号区间，D4 不管）。"""
        entries = [_entry(i, recall=10, total=2.0) for i in range(10)]
        # avg = 0.2 < 0.40
        result = _diagnose_embedding(entries)
        assert result.triggered is False

    def test_not_triggered_when_many_high_scores(self):
        """avg 在区间但高分占比 >= 10% → 不触发。"""
        # 5/10 条 avg > 0.70 → 50% >= 10%，不触发
        entries = (
            [_entry(i, recall=5, total=0.80*5) for i in range(5)] +  # avg=0.80 高分
            [_entry(i+5, recall=5, total=0.45*5) for i in range(5)]  # avg=0.45 中等
        )
        result = _diagnose_embedding(entries)
        assert result.triggered is False

    def test_empty_entries_not_triggered(self):
        result = _diagnose_embedding([])
        assert result.triggered is False


# ── D1 触发时 D4 被跳过 ───────────────────────────────────────────────────────

class TestD1SkipsD4:
    def test_fts_triggered_d4_not_in_output(self):
        """D1（FTS）触发时，D4（embedding）不出现在输出中。"""
        # avg=0.20, tags 全空 → D1 触发；avg 也在 [0.40,0.55) 但 D4 应被跳过
        entries = [_entry(i, recall=10, total=2.0, tags=[]) for i in range(20)]
        store = _store(entries)
        probe = _probe_with_store(store)

        with patch("src.tools.config_doctor.read_shortterm", return_value=store):
            result = run_config_doctor(probe)

        assert "FTS" in result or "降级" in result
        # D4 的关键词不应出现
        assert "embedding 模型语义质量" not in result
        assert "Embedding model" not in result


# ── 全局集成：run_config_doctor ───────────────────────────────────────────────

class TestRunConfigDoctor:
    def test_all_good_when_healthy(self):
        """全部健康时返回 all-good 消息。"""
        # 每条 entry 用不同 path，避免触发 D3（MMR）
        entries = [
            _entry(i, recall=3, total=2.5, max_score=0.8, path=f"memory/f{i}.md")
            for i in range(10)
        ]
        store = _store(entries)
        probe = _probe_with_store(store)

        with patch("src.tools.config_doctor.read_shortterm", return_value=store):
            result = run_config_doctor(probe)

        assert "✅" in result
        # all-good 时不应出现"发现 N 个问题"这样的措辞
        assert "发现" not in result or "未发现" in result

    def test_no_shortterm_error_message(self):
        """短期记忆不存在时友好提示，不崩溃。"""
        probe = ProbeResult(
            workspace_dir="/tmp", openclaw_version=None,
            shortterm_path=None, shortterm_format="unknown",
            longterm_path=None, longterm_format="not_found",
            longterm_adapter=UnknownFormatAdapter(),
            soul_path=None, identity_path=None,
            compatible=False, warnings=[],
        )
        result = run_config_doctor(probe)
        assert "❌" in result
        assert "Traceback" not in result

    def test_config_snippet_appears_when_triggered(self):
        """任何推断触发时，JSON5 配置片段出现在输出中。"""
        # D2（minScore）触发
        entries = [
            _entry(i, recall=10, total=2.0, max_score=0.3, tags=[])
            for i in range(10)
        ]
        store = _store(entries)
        probe = _probe_with_store(store)

        with patch("src.tools.config_doctor.read_shortterm", return_value=store):
            result = run_config_doctor(probe)

        assert "openclaw.json" in result
        assert "minScore" in result

    def test_no_config_snippet_when_all_good(self):
        """全部健康时不显示 JSON5 配置片段。"""
        # 每条 entry 用不同 path，避免触发 D3（MMR）
        entries = [
            _entry(i, recall=3, total=2.5, max_score=0.8, path=f"memory/f{i}.md")
            for i in range(10)
        ]
        store = _store(entries)
        probe = _probe_with_store(store)

        with patch("src.tools.config_doctor.read_shortterm", return_value=store):
            result = run_config_doctor(probe)

        assert "agents:" not in result

    def test_output_has_header(self):
        """输出包含标题。"""
        entries = [_entry(0)]
        store = _store(entries)
        probe = _probe_with_store(store)

        with patch("src.tools.config_doctor.read_shortterm", return_value=store):
            result = run_config_doctor(probe)

        assert "🩺" in result or "Config" in result or "配置" in result

    def test_no_traceback_on_any_path(self):
        """所有路径不含 Traceback。"""
        entries = [_entry(0)]
        store = _store(entries)
        probe = _probe_with_store(store)

        with patch("src.tools.config_doctor.read_shortterm", return_value=store):
            result = run_config_doctor(probe)

        assert "Traceback" not in result


# ── 真实数据回归 ───────────────────────────────────────────────────────────────

class TestRealFixture:
    def test_real_data_runs_without_error(self):
        """真实数据：诊断无报错，返回非空字符串。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.probe import probe_workspace
        probe = probe_workspace(str(REAL_ST.parent.parent.parent))
        result = run_config_doctor(probe)

        assert isinstance(result, str)
        assert len(result) > 0
        assert "Traceback" not in result

    def test_real_data_output_has_header(self):
        """真实数据输出包含标题。"""
        if not REAL_ST.exists():
            pytest.skip("tests/fixtures/real 不存在")

        from src.probe import probe_workspace
        probe = probe_workspace(str(REAL_ST.parent.parent.parent))
        result = run_config_doctor(probe)

        assert "🩺" in result or "Config" in result or "配置" in result

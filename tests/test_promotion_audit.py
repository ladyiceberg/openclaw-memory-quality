"""
test_promotion_audit.py · memory_promotion_audit_oc 工具集成测试

测试完整工具流程：读取短期记忆 → 关卡 1-4 → 格式化输出。
所有文件操作使用临时目录，不触及真实 workspace。
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.formats import UnknownFormatAdapter
from src.probe import ProbeResult
from src.tools.promotion_audit import run_promotion_audit_tool


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _iso(days_ago: float = 0) -> str:
    from datetime import datetime, timezone, timedelta
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat().replace("+00:00", "Z")


def _make_entry(
    key: str,
    path: str,
    start: int = 1,
    end: int = 5,
    snippet: str = "Gateway binds loopback and port 18789",
    recall_count: int = 5,
    total_score: float = 4.0,
    max_score: float = 0.92,
    promoted_at=None,
) -> dict:
    return {
        "key": key,
        "path": path,
        "startLine": start,
        "endLine": end,
        "source": "memory",
        "snippet": snippet,
        "recallCount": recall_count,
        "totalScore": total_score,
        "maxScore": max_score,
        "firstRecalledAt": _iso(10),
        "lastRecalledAt": _iso(1),
        "queryHashes": ["h1", "h2", "h3"],
        "recallDays": ["2026-04-14"],
        "conceptTags": ["gateway", "port"],
        **({"promotedAt": promoted_at} if promoted_at else {}),
    }


class TempWorkspace:
    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name)
        self.memory_dir = self.path / "memory"
        self.memory_dir.mkdir()
        self._entries: dict = {}

    def add_entry(self, key: str, path: str, **kwargs) -> "TempWorkspace":
        """添加一条短期记忆条目，自动创建来源文件。"""
        entry = _make_entry(key, path, **kwargs)
        self._entries[key] = entry
        # 创建来源文件
        src = self.path / path
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("def func(): return 42\n")
        return self

    def add_missing_source_entry(self, key: str, path: str, **kwargs) -> "TempWorkspace":
        """添加一条来源文件不存在的条目（不创建文件）。"""
        entry = _make_entry(key, path, **kwargs)
        self._entries[key] = entry
        return self

    def write_shortterm(self) -> Path:
        """写入 short-time-recall.json，返回路径。"""
        data = {
            "version": 1,
            "updatedAt": _iso(0),
            "entries": self._entries,
        }
        p = self.memory_dir / "short-time-recall.json"
        p.write_text(json.dumps(data))
        return p

    def make_probe(self) -> ProbeResult:
        st_path = self.write_shortterm()
        return ProbeResult(
            workspace_dir=str(self.path),
            openclaw_version="2026.4.7",
            shortterm_path=st_path,
            shortterm_format="v2026",
            longterm_path=None,
            longterm_format="not_found",
            longterm_adapter=UnknownFormatAdapter(),
            soul_path=None,
            identity_path=None,
            compatible=True,
            warnings=[],
        )

    def cleanup(self):
        self._td.cleanup()


# ── 基本功能 ──────────────────────────────────────────────────────────────────

class TestBasicFunctionality:
    def test_returns_string(self):
        """返回字符串。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md")
            result = run_promotion_audit_tool(ws.make_probe())
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            ws.cleanup()

    def test_output_has_header(self):
        """输出包含标题。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md")
            result = run_promotion_audit_tool(ws.make_probe())
            assert "🛡️" in result or "Pre-Promotion" in result or "晋升前" in result
        finally:
            ws.cleanup()

    def test_no_traceback(self):
        """正常运行不含 Traceback。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md")
            result = run_promotion_audit_tool(ws.make_probe())
            assert "Traceback" not in result
        finally:
            ws.cleanup()

    def test_no_shortterm_file_friendly_error(self):
        """short-term 文件不存在 → 友好提示，不崩溃。"""
        probe = ProbeResult(
            workspace_dir="/tmp",
            openclaw_version=None,
            shortterm_path=None, shortterm_format="unknown",
            longterm_path=None, longterm_format="not_found",
            longterm_adapter=UnknownFormatAdapter(),
            soul_path=None, identity_path=None,
            compatible=False, warnings=[],
        )
        result = run_promotion_audit_tool(probe)
        assert "❌" in result
        assert "Traceback" not in result

    def test_empty_store_shows_no_candidates(self):
        """无候选条目时显示相应提示。"""
        ws = TempWorkspace()
        try:
            # 不加任何条目（空 entries）
            result = run_promotion_audit_tool(ws.make_probe())
            assert "Traceback" not in result
            # 空或无候选时有对应提示
            assert "候选" in result or "candidate" in result.lower() or "暂无" in result
        finally:
            ws.cleanup()


# ── 关卡输出验证 ──────────────────────────────────────────────────────────────

class TestGateOutputs:
    def test_pass_count_in_output(self):
        """通过的条目数显示在输出中。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md")
            result = run_promotion_audit_tool(ws.make_probe())
            assert "通过" in result or "Pass" in result
        finally:
            ws.cleanup()

    def test_skip_source_deleted_shown(self):
        """来源文件不存在的条目显示在'建议跳过'中。"""
        ws = TempWorkspace()
        try:
            ws.add_missing_source_entry("k1", "memory/missing.md")
            result = run_promotion_audit_tool(ws.make_probe())
            assert "skip" in result.lower() or "跳过" in result or "不存在" in result
        finally:
            ws.cleanup()

    def test_skip_import_only_shown(self):
        """import only 条目显示在'建议跳过'中。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md",
                         snippet="import os")
            result = run_promotion_audit_tool(ws.make_probe())
            assert "import" in result.lower() or "跳过" in result
        finally:
            ws.cleanup()

    def test_flag_false_positive_shown(self):
        """假阳性信号条目显示在'需关注'中。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md",
                         recall_count=5, total_score=0.4, max_score=0.30)
            result = run_promotion_audit_tool(ws.make_probe())
            assert "关注" in result or "flag" in result.lower() or "假阳性" in result or "avg" in result
        finally:
            ws.cleanup()

    def test_all_pass_shows_healthy_message(self):
        """全部通过时显示健康提示。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md",
                         recall_count=5, total_score=4.0, max_score=0.92)
            result = run_promotion_audit_tool(ws.make_probe())
            assert "通过" in result or "Pass" in result or "✓" in result or "✅" in result
        finally:
            ws.cleanup()

    def test_score_note_always_present(self):
        """评分近似值声明始终出现。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md")
            result = run_promotion_audit_tool(ws.make_probe())
            assert "近似" in result or "approximate" in result.lower() or "consolidation" in result
        finally:
            ws.cleanup()


# ── top_n 参数 ────────────────────────────────────────────────────────────────

class TestTopN:
    def test_top_n_limits_candidates_shown(self):
        """top_n 参数影响输出中的候选条目数。"""
        ws = TempWorkspace()
        try:
            for i in range(15):
                ws.add_entry(f"k{i}", f"memory/f{i}.md",
                             recall_count=i+1, total_score=float(i+1)*0.8)
            result = run_promotion_audit_tool(ws.make_probe(), top_n=3)
            assert "Top 3" in result or "top_n=3" in result or "3" in result
        finally:
            ws.cleanup()

    def test_summary_shows_total_and_top_n(self):
        """摘要同时显示总候选数和 top_n。"""
        ws = TempWorkspace()
        try:
            for i in range(5):
                ws.add_entry(f"k{i}", f"memory/f{i}.md")
            result = run_promotion_audit_tool(ws.make_probe(), top_n=3)
            assert "5" in result   # 总候选数
            assert "3" in result   # top_n
        finally:
            ws.cleanup()


# ── use_llm=False 时的提示 ────────────────────────────────────────────────────

class TestUseLlmFalse:
    def test_llm_hint_shown_when_use_llm_false(self):
        """use_llm=False 且有 pass/flag 条目时，显示启用 LLM 的提示。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md")
            result = run_promotion_audit_tool(ws.make_probe(), use_llm=False)
            assert "use_llm=True" in result or "LLM" in result
        finally:
            ws.cleanup()


# ── use_llm=True 集成（mock）─────────────────────────────────────────────────

class TestUseLlmIntegration:
    def test_use_llm_true_with_mock_no_crash(self):
        """use_llm=True + mock LLM → 不崩溃，输出 LLM advisory 区域。"""
        from src.analyzers.llm_promotion_evaluator import (
            LLMPromotionEvalResult, LongTermValueAdvisory,
        )
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md")
            mock_eval = LLMPromotionEvalResult(advisories={
                "k1": LongTermValueAdvisory("k1", "long_term_knowledge", "稳定设计事实"),
            })
            with patch("src.tools.promotion_audit._run_llm_eval",
                       return_value=mock_eval):
                result = run_promotion_audit_tool(ws.make_probe(), use_llm=True)
            assert "Traceback" not in result
            assert "long_term" in result.lower() or "长期" in result or "LLM" in result
        finally:
            ws.cleanup()

    def test_use_llm_true_api_key_error_graceful(self):
        """API key 未配置 → 输出友好提示，不崩溃。"""
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md")
            with patch("llm_client.create_client",
                       side_effect=ValueError("No API key")):
                result = run_promotion_audit_tool(ws.make_probe(), use_llm=True)
            assert "Traceback" not in result
            assert isinstance(result, str)
        finally:
            ws.cleanup()

    def test_use_llm_true_with_one_time_context(self):
        """LLM 判断 one_time_context → 输出中显示一次性上下文条目。"""
        from src.analyzers.llm_promotion_evaluator import (
            LLMPromotionEvalResult, LongTermValueAdvisory,
        )
        ws = TempWorkspace()
        try:
            ws.add_entry("k1", "memory/f.md")
            mock_eval = LLMPromotionEvalResult(advisories={
                "k1": LongTermValueAdvisory("k1", "one_time_context", "临时上下文"),
            })
            with patch("src.tools.promotion_audit._run_llm_eval",
                       return_value=mock_eval):
                result = run_promotion_audit_tool(ws.make_probe(), use_llm=True)
            assert "Traceback" not in result
            assert "one_time" in result.lower() or "一次性" in result or "临时" in result
        finally:
            ws.cleanup()


# ── 真实 fixture 回归 ──────────────────────────────────────────────────────────

class TestRealFixture:
    def test_real_workspace_no_crash(self):
        """真实 workspace（如存在）→ 不崩溃。"""
        from pathlib import Path as _P
        from src.probe import probe_workspace
        real_ws = _P("tests/fixtures/real")
        if not real_ws.exists():
            pytest.skip("tests/fixtures/real 不存在")

        probe = probe_workspace(str(real_ws))
        result = run_promotion_audit_tool(probe, top_n=5)
        assert isinstance(result, str)
        assert "Traceback" not in result

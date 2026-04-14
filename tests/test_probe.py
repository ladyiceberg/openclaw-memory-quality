"""
test_probe.py · workspace probe 探测测试
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.probe import ProbeResult, probe_workspace, format_probe_summary
from src.formats import UnknownFormatAdapter


def _make_workspace(base: Path, *, with_shortterm: bool = False,
                    shortterm_name: str = "memory/short-time-recall.json",
                    with_longterm: bool = False,
                    longterm_content: str = "",
                    with_soul: bool = False) -> Path:
    """辅助函数：在临时目录创建 workspace 结构。"""
    ws = base / "workspace"
    ws.mkdir(parents=True, exist_ok=True)

    if with_shortterm:
        st_path = ws / shortterm_name
        st_path.parent.mkdir(parents=True, exist_ok=True)
        st_path.write_text(
            json.dumps({
                "version": 1,
                "updatedAt": "2026-04-14T08:00:00.000Z",
                "entries": {}
            }),
            encoding="utf-8"
        )

    if with_longterm:
        (ws / "MEMORY.md").write_text(longterm_content, encoding="utf-8")

    if with_soul:
        (ws / "SOUL.md").write_text("# SOUL.md\n## Core Truths\nBe helpful.", encoding="utf-8")

    return ws


class TestProbeWorkspace:
    def test_workspace_not_found(self, tmp_path):
        """workspace 不存在时返回 compatible=False，warnings 非空，不抛异常。"""
        non_exist = str(tmp_path / "nowhere")
        result = probe_workspace(non_exist)

        assert isinstance(result, ProbeResult)
        assert result.compatible is False
        assert len(result.warnings) > 0
        assert result.shortterm_path is None
        assert result.longterm_path is None

    def test_shortterm_source_code_detected(self, tmp_path):
        """探测到 .dreams/short-term-recall.json 时，格式识别为 source_code。"""
        ws = _make_workspace(tmp_path, with_shortterm=True,
                             shortterm_name="memory/.dreams/short-term-recall.json")
        result = probe_workspace(str(ws))

        assert result.has_shortterm
        assert result.shortterm_format == "source_code"

    def test_shortterm_not_found_warning(self, tmp_path):
        """短期记忆文件不存在时，warnings 中有相关提示。"""
        ws = _make_workspace(tmp_path)
        result = probe_workspace(str(ws))

        assert not result.has_shortterm
        assert any("短期记忆" in w or "short" in w.lower() for w in result.warnings)

    def test_longterm_manual_format(self, tmp_path):
        """纯手动维护格式的 MEMORY.md 被识别为 manual，不支持审计。"""
        content = "# MEMORY.md - Max's Long-term Memory\n\n## 关于小萌\n- 名字: 章晓萌\n"
        ws = _make_workspace(tmp_path, with_longterm=True, longterm_content=content)
        result = probe_workspace(str(ws))

        assert result.has_longterm
        assert result.longterm_format == "manual"
        assert not result.supports_longterm_audit

    def test_longterm_dreaming_format(self, tmp_path):
        """Dreaming 格式的 MEMORY.md 被正确识别。"""
        content = (
            "# Long-Term Memory\n\n"
            "## Promoted From Short-Term Memory (2026-04-14)\n\n"
            "- some snippet [score=0.890 recalls=3 avg=0.750 source=memory/2026-04-14.md:1-2]\n"
        )
        ws = _make_workspace(tmp_path, with_longterm=True, longterm_content=content)
        result = probe_workspace(str(ws))

        assert result.has_longterm
        assert result.longterm_format == "source_code"
        assert result.supports_longterm_audit

    def test_longterm_unknown_format_warning(self, tmp_path):
        """无法识别结构的 MEMORY.md 被标记为 manual，不抛异常，不支持审计。"""
        content = "# Some Unknown Format\n\nSomething here.\n"
        ws = _make_workspace(tmp_path, with_longterm=True, longterm_content=content)
        result = probe_workspace(str(ws))

        assert result.has_longterm
        # 有内容但无 Dreaming section → manual，不支持审计
        assert result.longterm_format == "manual"
        assert not result.supports_longterm_audit
        assert isinstance(result.longterm_adapter, UnknownFormatAdapter)

    def test_soul_detected(self, tmp_path):
        """SOUL.md 存在时被正确探测到。"""
        ws = _make_workspace(tmp_path, with_soul=True)
        result = probe_workspace(str(ws))

        assert result.has_soul
        assert result.soul_path is not None

    def test_soul_not_found(self, tmp_path):
        """SOUL.md 不存在时 soul_path 为 None，不抛异常。"""
        ws = _make_workspace(tmp_path)
        result = probe_workspace(str(ws))

        assert not result.has_soul
        assert result.soul_path is None

    def test_format_probe_summary_no_crash(self, tmp_path):
        """format_probe_summary 在各种状态下不崩溃。"""
        ws = _make_workspace(tmp_path, with_shortterm=True, with_soul=True)
        result = probe_workspace(str(ws))
        summary = format_probe_summary(result)

        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_real_workspace_if_exists(self):
        """如果真实 workspace 存在，探测结果应合理（不崩溃，字段有值）。"""
        real = Path.home() / ".openclaw" / "workspace"
        if not real.exists():
            pytest.skip("真实 workspace 不存在，跳过集成测试")

        result = probe_workspace(str(real))
        assert isinstance(result, ProbeResult)
        assert result.workspace_dir != ""


class TestProbeWithRealFixtures:
    """使用 tests/fixtures/real 里的真实数据做集成测试。"""

    FIXTURE_DIR = Path(__file__).parent / "fixtures" / "real"

    def test_fixture_dir_exists(self):
        """fixtures/real 目录存在（真实数据已就绪）。"""
        if not self.FIXTURE_DIR.exists():
            pytest.skip("tests/fixtures/real 不存在，跳过真实数据测试")
        assert self.FIXTURE_DIR.is_dir()

    def test_real_shortterm_detected(self):
        """真实 short-term-recall.json 被正确探测。"""
        if not self.FIXTURE_DIR.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = probe_workspace(str(self.FIXTURE_DIR))

        assert result.has_shortterm, "短期记忆文件应该存在"
        assert result.shortterm_format == "source_code"
        assert result.shortterm_path.name == "short-term-recall.json"

    def test_real_longterm_mixed_format(self):
        """真实 MEMORY.md 是手动+Dreaming 混合格式。"""
        if not self.FIXTURE_DIR.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = probe_workspace(str(self.FIXTURE_DIR))

        assert result.has_longterm, "MEMORY.md 应该存在"
        # 真实数据是手动 + Dreaming 混合格式
        assert result.longterm_format == "mixed"
        assert result.supports_longterm_audit, "mixed 格式应支持审计（含 Dreaming section）"

    def test_real_soul_detected(self):
        """真实 SOUL.md 被正确探测。"""
        if not self.FIXTURE_DIR.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = probe_workspace(str(self.FIXTURE_DIR))

        assert result.has_soul
        assert result.soul_path.name == "SOUL.md"

    def test_real_probe_summary_no_crash(self):
        """format_probe_summary 在真实数据上不崩溃，输出合理。"""
        if not self.FIXTURE_DIR.exists():
            pytest.skip("tests/fixtures/real 不存在")

        result = probe_workspace(str(self.FIXTURE_DIR))
        summary = format_probe_summary(result)

        assert isinstance(summary, str)
        assert "short-term-recall.json" in summary or "短期记忆" in summary

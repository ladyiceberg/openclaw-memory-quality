"""
test_shortterm_cleanup.py · memory_cleanup_shortterm_oc 核心逻辑测试

所有写操作测试在临时目录进行，绝不接触真实 workspace。
使用合成数据构造僵尸/假阳性条目，验证 dry_run 和实际执行两个模式。
"""
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pytest

from src.formats import RuleBasedAdapter, KNOWN_FORMATS, UnknownFormatAdapter
from src.probe import ProbeResult
from src.safety.backup_manager import backup_dir
from src.tools.shortterm_cleanup import run_shortterm_cleanup

# 基准时间：2026-04-14T08:00:00Z
NOW_MS = 1776153600000
DAY_MS = 86_400_000

REAL_ST = Path("tests/fixtures/real/memory/.dreams/short-term-recall.json")


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _iso(offset_days: float = 0.0) -> str:
    ts_ms = NOW_MS - int(offset_days * DAY_MS)
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _st_entry(
    key: str,
    recall_count: int = 3,
    total_score: float = 1.5,
    max_score: float = 0.7,
    concept_tags: Optional[List[str]] = None,
    last_recalled_days_ago: float = 10.0,
    promoted_at: Optional[str] = None,
) -> dict:
    """构造一条 short-term-recall.json 格式的 entry。"""
    tags = concept_tags if concept_tags is not None else ["tag1"]
    return {
        "key": key,
        "path": key.split(":")[1] if ":" in key else "memory/f.md",
        "startLine": 1,
        "endLine": 5,
        "source": "memory",
        "snippet": f"snippet {key}",
        "recallCount": recall_count,
        "dailyCount": 0,
        "groundedCount": 0,
        "totalScore": total_score,
        "maxScore": max_score,
        "firstRecalledAt": _iso(last_recalled_days_ago),
        "lastRecalledAt": _iso(last_recalled_days_ago),
        "queryHashes": ["hash1"],
        "recallDays": [_iso(last_recalled_days_ago)[:10]],
        "conceptTags": tags,
        "promotedAt": promoted_at,
    }


def _make_store_json(entries: dict) -> str:
    return json.dumps({
        "version": 1,
        "updatedAt": _iso(0),
        "entries": entries,
    }, indent=2, ensure_ascii=False) + "\n"


class TempWorkspace:
    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name)
        (self.path / "memory" / ".dreams").mkdir(parents=True)

    @property
    def st_path(self) -> Path:
        return self.path / "memory" / ".dreams" / "short-term-recall.json"

    def write_store(self, entries: dict) -> None:
        self.st_path.write_text(_make_store_json(entries), encoding="utf-8")

    def read_store(self) -> dict:
        return json.loads(self.st_path.read_text())

    def make_probe(self) -> ProbeResult:
        return ProbeResult(
            workspace_dir=str(self.path),
            openclaw_version="2026.4.7",
            shortterm_path=self.st_path,
            shortterm_format="source_code",
            longterm_path=None,
            longterm_format="not_found",
            longterm_adapter=UnknownFormatAdapter(),
            soul_path=None, identity_path=None,
            compatible=True, warnings=[],
        )

    def cleanup(self):
        self._td.cleanup()


# ── dry_run 模式 ───────────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_does_not_modify_file(self):
        """dry_run=True 时文件内容不变。"""
        ws = TempWorkspace()
        try:
            # 构造一个僵尸条目（recallCount=1, 91 天前）
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
            }
            ws.write_store(entries)
            original = ws.st_path.read_text()

            run_shortterm_cleanup(ws.make_probe(), dry_run=True, now_ms=NOW_MS)

            assert ws.st_path.read_text() == original
        finally:
            ws.cleanup()

    def test_dry_run_shows_would_delete_count(self):
        """dry_run=True 时输出包含"将删除 N 条"。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
                "k2": _st_entry("k2", recall_count=1, last_recalled_days_ago=91),
            }
            ws.write_store(entries)

            result = run_shortterm_cleanup(ws.make_probe(), dry_run=True, now_ms=NOW_MS)

            assert "2" in result
        finally:
            ws.cleanup()

    def test_dry_run_no_backup_created(self):
        """dry_run=True 时不创建备份。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
            }
            ws.write_store(entries)

            run_shortterm_cleanup(ws.make_probe(), dry_run=True, now_ms=NOW_MS)

            bak_files = list(backup_dir(ws.path).glob("*.bak")) if backup_dir(ws.path).exists() else []
            assert len(bak_files) == 0
        finally:
            ws.cleanup()

    def test_dry_run_hint_present(self):
        """dry_run=True 时输出包含提示用户传 dry_run=False。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
            }
            ws.write_store(entries)

            result = run_shortterm_cleanup(ws.make_probe(), dry_run=True, now_ms=NOW_MS)

            assert "dry_run" in result or "False" in result
        finally:
            ws.cleanup()


# ── 实际执行模式 ───────────────────────────────────────────────────────────────

class TestActualExecution:
    def test_zombie_entries_removed(self):
        """dry_run=False：僵尸条目从文件中消失。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k_zombie": _st_entry("k_zombie", recall_count=1, last_recalled_days_ago=91),
                "k_healthy": _st_entry("k_healthy", recall_count=5, last_recalled_days_ago=5),
            }
            ws.write_store(entries)

            run_shortterm_cleanup(ws.make_probe(), dry_run=False, now_ms=NOW_MS)

            data = ws.read_store()
            assert "k_zombie" not in data["entries"]
            assert "k_healthy" in data["entries"]
        finally:
            ws.cleanup()

    def test_backup_created_before_write(self):
        """dry_run=False：备份文件存在，内容与原始一致。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
            }
            ws.write_store(entries)
            original = ws.st_path.read_text()

            run_shortterm_cleanup(ws.make_probe(), dry_run=False, now_ms=NOW_MS)

            bak_files = list(backup_dir(ws.path).glob("short-term-recall.json.*.bak"))
            assert len(bak_files) == 1
            assert bak_files[0].read_text(encoding="utf-8") == original
        finally:
            ws.cleanup()

    def test_output_shows_deleted_count(self):
        """dry_run=False：输出包含实际删除数。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
                "k2": _st_entry("k2", recall_count=1, last_recalled_days_ago=91),
            }
            ws.write_store(entries)

            result = run_shortterm_cleanup(ws.make_probe(), dry_run=False, now_ms=NOW_MS)

            assert "2" in result
            assert "✅" in result or "Complete" in result or "完成" in result
        finally:
            ws.cleanup()

    def test_output_shows_backup_path(self):
        """dry_run=False：输出包含备份路径。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
            }
            ws.write_store(entries)

            result = run_shortterm_cleanup(ws.make_probe(), dry_run=False, now_ms=NOW_MS)

            assert ".bak" in result
        finally:
            ws.cleanup()

    def test_result_is_valid_json(self):
        """干净执行后，写入文件是合法 JSON。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
                "k2": _st_entry("k2", recall_count=5, last_recalled_days_ago=5),
            }
            ws.write_store(entries)

            run_shortterm_cleanup(ws.make_probe(), dry_run=False, now_ms=NOW_MS)

            data = ws.read_store()
            assert isinstance(data, dict)
            assert "entries" in data
        finally:
            ws.cleanup()

    def test_updated_at_refreshed(self):
        """dry_run=False：写入后 updatedAt 被更新。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
            }
            ws.write_store(entries)
            old_updated = json.loads(ws.st_path.read_text())["updatedAt"]

            import time
            time.sleep(0.01)
            run_shortterm_cleanup(ws.make_probe(), dry_run=False, now_ms=NOW_MS + 5000)

            new_updated = ws.read_store()["updatedAt"]
            assert new_updated != old_updated
        finally:
            ws.cleanup()


# ── cleanup_types 控制 ────────────────────────────────────────────────────────

class TestCleanupTypes:
    def test_default_only_zombie(self):
        """默认 cleanup_types=["zombie"]，不删假阳性。"""
        ws = TempWorkspace()
        try:
            # k_zombie：recallCount=1, 91天 → zombie
            # k_fp：高频低质假阳性（avg<0.35, recalls>5）→ false_positive
            entries = {
                "k_zombie": _st_entry("k_zombie", recall_count=1, last_recalled_days_ago=91),
                "k_fp": _st_entry(
                    "k_fp",
                    recall_count=10, total_score=2.0, max_score=0.3,
                    concept_tags=[], last_recalled_days_ago=5
                ),
            }
            ws.write_store(entries)

            # 默认只清理 zombie
            run_shortterm_cleanup(
                ws.make_probe(), cleanup_types=["zombie"],
                dry_run=False, now_ms=NOW_MS,
            )

            data = ws.read_store()
            assert "k_zombie" not in data["entries"]
            assert "k_fp" in data["entries"]     # 假阳性未被删
        finally:
            ws.cleanup()

    def test_explicit_false_positive_cleanup(self):
        """显式指定 false_positive 时，假阳性条目被删除。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k_fp": _st_entry(
                    "k_fp",
                    recall_count=10, total_score=2.0, max_score=0.3,
                    concept_tags=[], last_recalled_days_ago=5
                ),
                "k_healthy": _st_entry("k_healthy", recall_count=3, last_recalled_days_ago=5),
            }
            ws.write_store(entries)

            run_shortterm_cleanup(
                ws.make_probe(), cleanup_types=["false_positive"],
                dry_run=False, now_ms=NOW_MS,
            )

            data = ws.read_store()
            assert "k_fp" not in data["entries"]
            assert "k_healthy" in data["entries"]
        finally:
            ws.cleanup()

    def test_both_types_cleans_all_suspect(self):
        """cleanup_types=["zombie","false_positive"]：两类都删。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k_zombie": _st_entry("k_zombie", recall_count=1, last_recalled_days_ago=91),
                "k_fp": _st_entry(
                    "k_fp", recall_count=10, total_score=2.0, max_score=0.3,
                    concept_tags=[], last_recalled_days_ago=5
                ),
                "k_keep": _st_entry("k_keep", recall_count=5, last_recalled_days_ago=5),
            }
            ws.write_store(entries)

            run_shortterm_cleanup(
                ws.make_probe(), cleanup_types=["zombie", "false_positive"],
                dry_run=False, now_ms=NOW_MS,
            )

            data = ws.read_store()
            assert "k_zombie" not in data["entries"]
            assert "k_fp" not in data["entries"]
            assert "k_keep" in data["entries"]
        finally:
            ws.cleanup()


# ── 无需清理 / 错误路径 ────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_no_suspects_friendly_message(self):
        """没有僵尸或假阳性条目 → 友好提示，文件不变。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=5, last_recalled_days_ago=5),
            }
            ws.write_store(entries)
            original = ws.st_path.read_text()

            result = run_shortterm_cleanup(ws.make_probe(), dry_run=False, now_ms=NOW_MS)

            assert "ℹ️" in result or "Nothing" in result or "没有" in result
            assert ws.st_path.read_text() == original
        finally:
            ws.cleanup()

    def test_no_shortterm_file_friendly_error(self):
        """shortterm 文件不存在 → 友好提示，不崩溃。"""
        from src.probe import ProbeResult
        probe = ProbeResult(
            workspace_dir="/tmp/nonexistent",
            openclaw_version=None,
            shortterm_path=None,
            shortterm_format="unknown",
            longterm_path=None,
            longterm_format="not_found",
            longterm_adapter=UnknownFormatAdapter(),
            soul_path=None, identity_path=None,
            compatible=False, warnings=[],
        )
        result = run_shortterm_cleanup(probe, dry_run=True, now_ms=NOW_MS)
        assert "❌" in result
        assert "Traceback" not in result

    def test_no_tmp_files_remain_after_execution(self):
        """执行完成后不留 .tmp 临时文件。"""
        ws = TempWorkspace()
        try:
            entries = {
                "k1": _st_entry("k1", recall_count=1, last_recalled_days_ago=91),
            }
            ws.write_store(entries)

            run_shortterm_cleanup(ws.make_probe(), dry_run=False, now_ms=NOW_MS)

            tmp_files = list(ws.path.glob("**/*.tmp"))
            assert len(tmp_files) == 0
        finally:
            ws.cleanup()

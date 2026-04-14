"""
test_longterm_cleanup.py · memory_longterm_cleanup_oc 核心逻辑测试

所有写操作测试在临时目录进行，绝不接触真实 workspace。

覆盖场景：
  - 正常清理流程（删 1 条，保留 1 条）
  - 无需删除时友好提示
  - report_id 不存在时报错
  - mtime 不一致时中止
  - 80% 安全阀触发时中止
  - 备份文件存在且内容与原文件一致
  - 清理后新文件内容正确（被删条目消失，保留条目存在）
  - 清理后 section 被清空时 header 也删除
  - 错误路径不崩溃
"""
import tempfile
import time
from pathlib import Path
from typing import Optional

import pytest

from src.formats import RuleBasedAdapter, KNOWN_FORMATS
from src.probe import ProbeResult
from src.safety.backup_manager import backup_dir
from src.session_store import save_audit_report
from src.tools.longterm_cleanup import run_longterm_cleanup


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

class TempWorkspace:
    """临时 workspace，包含完整的目录结构。"""

    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name)
        (self.path / "memory" / ".dreams").mkdir(parents=True)
        self.db = self.path / "test.db"

    @property
    def memory_md(self) -> Path:
        return self.path / "MEMORY.md"

    def write_memory_md(self, content: str) -> float:
        """写入 MEMORY.md，返回 mtime。"""
        self.memory_md.write_text(content, encoding="utf-8")
        return self.memory_md.stat().st_mtime

    def create_source_file(self, rel_path: str, content: str = "content\n") -> Path:
        p = self.path / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def save_audit(
        self,
        report_id: str,
        items: list[dict],
        mtime: Optional[float] = None,
        non_standard: int = 0,
    ) -> None:
        payload = {
            "total_items": len(items),
            "sections_count": 1,
            "items_by_action": {
                "keep":   sum(1 for i in items if i["action_hint"] == "keep"),
                "review": sum(1 for i in items if i["action_hint"] == "review"),
                "delete": sum(1 for i in items if i["action_hint"] == "delete"),
            },
            "non_standard_sections": non_standard,
            "memory_md_mtime": mtime,
            "items": items,
        }
        save_audit_report(report_id, str(self.path), len(items), payload, db_path=self.db)

    def make_probe(self) -> ProbeResult:
        return ProbeResult(
            workspace_dir=str(self.path),
            openclaw_version="2026.4.7",
            shortterm_path=None,
            shortterm_format="unknown",
            longterm_path=self.memory_md,
            longterm_format="source_code",
            longterm_adapter=RuleBasedAdapter(KNOWN_FORMATS["source_code"]),
            soul_path=None,
            identity_path=None,
            compatible=True,
            warnings=[],
        )

    def cleanup(self):
        self._td.cleanup()


def _make_item(
    source_path: str,
    start: int = 1,
    end: int = 5,
    action: str = "delete",
    key: Optional[str] = None,
) -> dict:
    if key is None:
        key = f"memory:{source_path}:{start}:{end}"
    return {
        "source_path": source_path,
        "source_start": start,
        "source_end": end,
        "promotion_key": key,
        "action_hint": action,
        "v1_status": "deleted" if action == "delete" else "exists",
        "v3_status": "ok",
        "snippet": f"snippet from {source_path}",
        "score": 0.9,
    }


def _md_with_items(items: list[dict]) -> str:
    """根据 item 列表构造一个标准的 MEMORY.md 文本。"""
    lines = ["# Long-Term Memory\n", "\n",
             "## Promoted From Short-Term Memory (2026-04-14)\n", "\n"]
    for item in items:
        key = item.get("promotion_key", "")
        sp = item["source_path"]
        ss = item["source_start"]
        se = item["source_end"]
        snippet = item.get("snippet", "test snippet")
        lines.append(f"<!-- openclaw-memory-promotion:{key} -->\n")
        lines.append(
            f"- {snippet} [score=0.900 recalls=3 avg=0.700"
            f" source={sp}:{ss}-{se}]\n"
        )
    lines.append("\n")
    return "".join(lines)


# ── 正常清理流程 ───────────────────────────────────────────────────────────────

class TestNormalCleanup:
    def test_deleted_entry_removed_from_file(self):
        """被标记 delete 的条目从 MEMORY.md 中消失。"""
        ws = TempWorkspace()
        try:
            item_del  = _make_item("memory/del.md",  action="delete")
            item_keep = _make_item("memory/keep.md", action="keep")

            mtime = ws.write_memory_md(_md_with_items([item_del, item_keep]))
            ws.save_audit("rid1", [item_del, item_keep], mtime=mtime)

            result = run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            assert "✅" in result or "Complete" in result or "完成" in result
            new_content = ws.memory_md.read_text()
            assert "snippet from memory/del.md" not in new_content
            assert "snippet from memory/keep.md" in new_content
        finally:
            ws.cleanup()

    def test_backup_file_created(self):
        """清理后备份文件存在，内容与清理前原文件一致。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/del.md", action="delete")
            original_content = _md_with_items([item])
            mtime = ws.write_memory_md(original_content)
            ws.save_audit("rid1", [item], mtime=mtime)

            run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            bak_files = list(backup_dir(ws.path).glob("MEMORY.md.*.bak"))
            assert len(bak_files) == 1
            assert bak_files[0].read_text(encoding="utf-8") == original_content
        finally:
            ws.cleanup()

    def test_output_contains_deleted_count(self):
        """输出包含删除条数。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/del.md", action="delete")
            mtime = ws.write_memory_md(_md_with_items([item]))
            ws.save_audit("rid1", [item], mtime=mtime)

            result = run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            assert "1" in result
            assert "delete" in result.lower() or "删除" in result
        finally:
            ws.cleanup()

    def test_output_contains_backup_path(self):
        """输出包含备份文件路径。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/del.md", action="delete")
            mtime = ws.write_memory_md(_md_with_items([item]))
            ws.save_audit("rid1", [item], mtime=mtime)

            result = run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            assert ".bak" in result
        finally:
            ws.cleanup()

    def test_empty_section_header_removed(self):
        """所有 item 被删后，section header 也消失。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/del.md", action="delete")
            mtime = ws.write_memory_md(_md_with_items([item]))
            ws.save_audit("rid1", [item], mtime=mtime)

            run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            new_content = ws.memory_md.read_text()
            assert "Promoted From Short-Term Memory" not in new_content
        finally:
            ws.cleanup()

    def test_multiple_deletes(self):
        """同时删除多条 item，只保留 action=keep 的。"""
        ws = TempWorkspace()
        try:
            del1  = _make_item("memory/del1.md", action="delete")
            del2  = _make_item("memory/del2.md", action="delete")
            keep1 = _make_item("memory/keep1.md", action="keep")
            keep2 = _make_item("memory/keep2.md", action="keep")

            mtime = ws.write_memory_md(_md_with_items([del1, del2, keep1, keep2]))
            ws.save_audit("rid1", [del1, del2, keep1, keep2], mtime=mtime)

            run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            new = ws.memory_md.read_text()
            assert "snippet from memory/del1.md" not in new
            assert "snippet from memory/del2.md" not in new
            assert "snippet from memory/keep1.md" in new
            assert "snippet from memory/keep2.md" in new
        finally:
            ws.cleanup()

    def test_manual_content_preserved(self):
        """mixed 格式：手动内容无条件保留。"""
        ws = TempWorkspace()
        try:
            manual = "# MEMORY.md\n\n## 用户手写内容\n- 手写备注\n\n"
            item = _make_item("memory/del.md", action="delete")
            dreaming = _md_with_items([item]).replace("# Long-Term Memory\n\n", "")
            full = manual + dreaming

            mtime = ws.write_memory_md(full)
            ws.save_audit("rid1", [item], mtime=mtime)

            run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            new = ws.memory_md.read_text()
            assert "手写备注" in new
        finally:
            ws.cleanup()


# ── 无需删除 ───────────────────────────────────────────────────────────────────

class TestNoDeletionNeeded:
    def test_no_delete_items_returns_info_message(self):
        """payload 中无 delete 条目 → 友好提示，不修改文件。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/keep.md", action="keep")
            original = _md_with_items([item])
            mtime = ws.write_memory_md(original)
            ws.save_audit("rid1", [item], mtime=mtime)

            result = run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            # 提示无需操作
            assert "ℹ️" in result or "Nothing" in result or "没有" in result
            # 文件未被修改
            assert ws.memory_md.read_text() == original
        finally:
            ws.cleanup()

    def test_no_delete_items_no_backup_created(self):
        """无需删除时不创建备份。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/keep.md", action="keep")
            mtime = ws.write_memory_md(_md_with_items([item]))
            ws.save_audit("rid1", [item], mtime=mtime)

            run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            bak_files = list(backup_dir(ws.path).glob("*.bak")) if backup_dir(ws.path).exists() else []
            assert len(bak_files) == 0
        finally:
            ws.cleanup()


# ── 错误路径：Step 0 ──────────────────────────────────────────────────────────

class TestStep0Errors:
    def test_unknown_report_id_returns_error(self):
        """找不到 report_id → 返回错误提示，不修改文件。"""
        ws = TempWorkspace()
        try:
            mtime = ws.write_memory_md("# Long-Term Memory\n")

            result = run_longterm_cleanup(ws.make_probe(), "nonexistent_rid", db_path=ws.db)

            assert "❌" in result
            assert "nonexistent_rid" in result
        finally:
            ws.cleanup()


# ── 错误路径：Step 1（mtime 守护）────────────────────────────────────────────

class TestStep1MtimeGuard:
    def test_mtime_mismatch_aborts(self):
        """MEMORY.md 在 audit 后被修改（mtime 变化）→ 中止，不修改文件。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/del.md", action="delete")
            original = _md_with_items([item])
            old_mtime = ws.write_memory_md(original)

            # 保存 audit 时用旧 mtime
            ws.save_audit("rid1", [item], mtime=old_mtime)

            # 模拟 MEMORY.md 被修改（设置不同 mtime）
            import os
            new_mtime = old_mtime + 10.0
            os.utime(ws.memory_md, (new_mtime, new_mtime))

            result = run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            assert "❌" in result
            # 文件内容未被修改（触发中止）
            assert ws.memory_md.read_text() == original
        finally:
            ws.cleanup()

    def test_mtime_match_proceeds(self):
        """mtime 一致（在 1 秒误差内）→ 正常执行清理。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/del.md", action="delete")
            mtime = ws.write_memory_md(_md_with_items([item]))
            ws.save_audit("rid1", [item], mtime=mtime)

            result = run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            assert "❌" not in result
            assert "✅" in result or "完成" in result or "Complete" in result
        finally:
            ws.cleanup()

    def test_null_mtime_in_payload_skips_check(self):
        """audit payload 里 memory_md_mtime=None → 跳过 mtime 检查，正常执行。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/del.md", action="delete")
            ws.write_memory_md(_md_with_items([item]))
            # mtime=None → 跳过 mtime 校验
            ws.save_audit("rid1", [item], mtime=None)

            result = run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            assert "❌" not in result
        finally:
            ws.cleanup()


# ── 错误路径：Step 3（安全阀）────────────────────────────────────────────────

class TestStep3SafetyValve:
    def test_safety_valve_aborts_and_no_backup(self):
        """解析率 < 80% 时中止，不创建备份，原文件不变。"""
        ws = TempWorkspace()
        try:
            # 构造一个 section 内全是无法解析的内容的 MEMORY.md
            bad_content = (
                "# Long-Term Memory\n\n"
                "## Promoted From Short-Term Memory (2026-04-14)\n\n"
                "This line cannot be parsed as a memory item.\n"
                "Neither can this one, completely unrecognized.\n"
                "Third unparseable line here.\n"
                "Fourth unparseable line here.\n"
                "Fifth unparseable line here.\n\n"
            )
            mtime = ws.write_memory_md(bad_content)

            item = _make_item("memory/del.md", action="delete")
            ws.save_audit("rid1", [item], mtime=mtime)

            result = run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            assert "❌" in result
            # 无备份
            bak_files = list(backup_dir(ws.path).glob("*.bak")) if backup_dir(ws.path).exists() else []
            assert len(bak_files) == 0
            # 原文件未变
            assert ws.memory_md.read_text() == bad_content
        finally:
            ws.cleanup()


# ── 完整流程不变性校验 ────────────────────────────────────────────────────────

class TestInvariants:
    def test_no_tmp_files_remain_after_cleanup(self):
        """清理完成后不留 .tmp 临时文件。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/del.md", action="delete")
            mtime = ws.write_memory_md(_md_with_items([item]))
            ws.save_audit("rid1", [item], mtime=mtime)

            run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            tmp_files = list(ws.path.glob("**/*.tmp"))
            assert len(tmp_files) == 0
        finally:
            ws.cleanup()

    def test_file_ends_with_newline_after_cleanup(self):
        """清理后的文件末尾有换行符。"""
        ws = TempWorkspace()
        try:
            item = _make_item("memory/del.md", action="delete")
            keep = _make_item("memory/keep.md", action="keep")
            mtime = ws.write_memory_md(_md_with_items([item, keep]))
            ws.save_audit("rid1", [item, keep], mtime=mtime)

            run_longterm_cleanup(ws.make_probe(), "rid1", db_path=ws.db)

            new_content = ws.memory_md.read_text()
            assert new_content.endswith("\n")
        finally:
            ws.cleanup()

    def test_no_traceback_in_any_error_output(self):
        """所有错误路径输出不含 Traceback。"""
        ws = TempWorkspace()
        try:
            mtime = ws.write_memory_md("# Long-Term Memory\n")

            # 错误路径 1：report_id 不存在
            r1 = run_longterm_cleanup(ws.make_probe(), "no_such_id", db_path=ws.db)
            assert "Traceback" not in r1

            # 错误路径 2：MEMORY.md 不存在的 probe
            from src.probe import ProbeResult
            from src.formats import UnknownFormatAdapter
            bad_probe = ProbeResult(
                workspace_dir=str(ws.path),
                openclaw_version=None,
                shortterm_path=None, shortterm_format="unknown",
                longterm_path=None, longterm_format="not_found",
                longterm_adapter=UnknownFormatAdapter(),
                soul_path=None, identity_path=None,
                compatible=False, warnings=[],
            )
            item = _make_item("memory/del.md", action="delete")
            ws.save_audit("rid_bad", [item], mtime=mtime)
            r2 = run_longterm_cleanup(bad_probe, "rid_bad", db_path=ws.db)
            assert "Traceback" not in r2
        finally:
            ws.cleanup()

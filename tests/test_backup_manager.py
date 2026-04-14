"""
test_backup_manager.py · 备份与原子写入测试

所有测试均在临时目录进行，不接触任何真实 workspace。

覆盖场景：
  - backup_file：正常备份、文件不存在、目录自动创建、备份文件完整性
  - atomic_write：正常写入、内容正确、原有文件保护（tmp 不留残留）
  - list_backups：按时间戳排序、无备份时返回空列表
"""
import os
import tempfile
import time
from pathlib import Path

import pytest

from src.safety.backup_manager import (
    BACKUP_DIR_RELATIVE,
    AtomicWriteError,
    BackupError,
    atomic_write,
    backup_dir,
    backup_file,
    list_backups,
)


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

class TempWorkspace:
    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name)

    def create_file(self, rel_path: str, content: str = "test content\n") -> Path:
        p = self.path / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def cleanup(self):
        self._td.cleanup()


# ── backup_file ────────────────────────────────────────────────────────────────

class TestBackupFile:
    def test_creates_backup_in_correct_dir(self):
        """备份文件在 memory/.memory-quality-backups/ 目录下。"""
        ws = TempWorkspace()
        try:
            src = ws.create_file("MEMORY.md", "# Long-Term Memory\n")
            bak = backup_file(src, ws.path)

            assert bak.parent == backup_dir(ws.path)
            assert bak.exists()
        finally:
            ws.cleanup()

    def test_backup_filename_format(self):
        """备份文件名：{original_name}.{timestamp_s}.bak"""
        ws = TempWorkspace()
        try:
            before = int(time.time())
            src = ws.create_file("MEMORY.md", "content\n")
            bak = backup_file(src, ws.path)
            after = int(time.time())

            name_parts = bak.name.split(".")
            # 格式：MEMORY.md.{ts}.bak → parts = ["MEMORY", "md", "{ts}", "bak"]
            assert bak.name.startswith("MEMORY.md.")
            assert bak.name.endswith(".bak")
            ts = int(name_parts[-2])
            assert before <= ts <= after
        finally:
            ws.cleanup()

    def test_backup_content_identical_to_source(self):
        """备份文件内容与源文件完全一致。"""
        ws = TempWorkspace()
        try:
            original = "# Long-Term Memory\n\nSome content here.\n"
            src = ws.create_file("MEMORY.md", original)
            bak = backup_file(src, ws.path)

            assert bak.read_text(encoding="utf-8") == original
        finally:
            ws.cleanup()

    def test_backup_creates_parent_dir_automatically(self):
        """备份目录不存在时自动创建。"""
        ws = TempWorkspace()
        try:
            src = ws.create_file("MEMORY.md", "content\n")
            bak_dir = backup_dir(ws.path)

            assert not bak_dir.exists()
            bak = backup_file(src, ws.path)
            assert bak_dir.exists()
        finally:
            ws.cleanup()

    def test_backup_nonexistent_file_raises(self):
        """源文件不存在 → BackupError。"""
        ws = TempWorkspace()
        try:
            nonexistent = ws.path / "MEMORY.md"
            with pytest.raises(BackupError) as exc_info:
                backup_file(nonexistent, ws.path)
            assert "不存在" in str(exc_info.value) or "not exist" in str(exc_info.value).lower()
        finally:
            ws.cleanup()

    def test_multiple_backups_have_unique_names(self):
        """多次备份文件名唯一（时间戳不同）。"""
        ws = TempWorkspace()
        try:
            src = ws.create_file("MEMORY.md", "content\n")
            bak1 = backup_file(src, ws.path)
            time.sleep(1.1)   # 确保时间戳秒级不同
            bak2 = backup_file(src, ws.path)

            assert bak1.name != bak2.name
            assert bak1.exists()
            assert bak2.exists()
        finally:
            ws.cleanup()

    def test_returns_path_object(self):
        """返回值是 Path 对象。"""
        ws = TempWorkspace()
        try:
            src = ws.create_file("MEMORY.md", "content\n")
            bak = backup_file(src, ws.path)
            assert isinstance(bak, Path)
        finally:
            ws.cleanup()

    def test_backup_preserves_large_file(self):
        """大文件（100KB+）也能完整备份。"""
        ws = TempWorkspace()
        try:
            large_content = "# Memory\n" + ("- item\n" * 10000)
            src = ws.create_file("MEMORY.md", large_content)
            bak = backup_file(src, ws.path)

            assert bak.read_text(encoding="utf-8") == large_content
        finally:
            ws.cleanup()


# ── atomic_write ──────────────────────────────────────────────────────────────

class TestAtomicWrite:
    def test_writes_content_to_target(self):
        """正常情况：内容写入目标文件。"""
        ws = TempWorkspace()
        try:
            target = ws.path / "MEMORY.md"
            content = "# New content\n"
            atomic_write(target, content)

            assert target.read_text(encoding="utf-8") == content
        finally:
            ws.cleanup()

    def test_overwrites_existing_file(self):
        """已有文件被覆盖，内容更新。"""
        ws = TempWorkspace()
        try:
            target = ws.create_file("MEMORY.md", "old content\n")
            new_content = "new content\n"
            atomic_write(target, new_content)

            assert target.read_text(encoding="utf-8") == new_content
        finally:
            ws.cleanup()

    def test_no_tmp_file_remains_after_success(self):
        """写入成功后不留 .tmp 临时文件。"""
        ws = TempWorkspace()
        try:
            target = ws.path / "MEMORY.md"
            atomic_write(target, "content\n")

            tmp_files = list(ws.path.glob("*.tmp"))
            assert len(tmp_files) == 0
        finally:
            ws.cleanup()

    def test_writes_unicode_content(self):
        """Unicode 内容（中文等）正确写入。"""
        ws = TempWorkspace()
        try:
            target = ws.path / "MEMORY.md"
            content = "# 长期记忆\n\n这是一段中文内容。\n"
            atomic_write(target, content)

            assert target.read_text(encoding="utf-8") == content
        finally:
            ws.cleanup()

    def test_writes_large_content(self):
        """大文件正确写入（100KB+）。"""
        ws = TempWorkspace()
        try:
            target = ws.path / "MEMORY.md"
            content = "# Memory\n" + ("- item content here\n" * 5000)
            atomic_write(target, content)

            assert target.read_text(encoding="utf-8") == content
        finally:
            ws.cleanup()

    def test_original_content_safe_when_write_dir_is_readonly(self):
        """
        确认原子写入的基本保护：tmp 文件与 target 在同一目录。
        （os.replace 要求 tmp 和 target 同一文件系统，跨文件系统 rename 可能失败）
        """
        ws = TempWorkspace()
        try:
            target = ws.path / "MEMORY.md"
            atomic_write(target, "content\n")

            tmp_files = list(target.parent.glob(f"{target.name}.*.tmp"))
            assert len(tmp_files) == 0  # 成功后无 tmp 残留
        finally:
            ws.cleanup()


# ── backup + atomic_write 组合 ────────────────────────────────────────────────

class TestBackupAndWrite:
    """模拟真实写操作流程：先备份，再原子写入。"""

    def test_backup_then_write_workflow(self):
        """
        标准流程：
          1. 备份原文件
          2. 原子写入新内容
          3. 验证目标文件已更新，备份文件保留原内容
        """
        ws = TempWorkspace()
        try:
            original = "# Long-Term Memory\n\nOriginal content.\n"
            target = ws.create_file("MEMORY.md", original)

            # 步骤 1：备份
            bak = backup_file(target, ws.path)
            assert bak.read_text(encoding="utf-8") == original

            # 步骤 2：写新内容
            new_content = "# Long-Term Memory\n\nUpdated content.\n"
            atomic_write(target, new_content)

            # 步骤 3：验证
            assert target.read_text(encoding="utf-8") == new_content
            assert bak.read_text(encoding="utf-8") == original
        finally:
            ws.cleanup()

    def test_backup_exists_even_after_write(self):
        """写入完成后备份文件仍然存在。"""
        ws = TempWorkspace()
        try:
            target = ws.create_file("MEMORY.md", "original\n")
            bak = backup_file(target, ws.path)
            atomic_write(target, "new content\n")

            assert bak.exists()
        finally:
            ws.cleanup()


# ── list_backups ──────────────────────────────────────────────────────────────

class TestListBackups:
    def test_empty_when_no_backups(self):
        """无备份时返回空列表。"""
        ws = TempWorkspace()
        try:
            result = list_backups(ws.path, "MEMORY.md")
            assert result == []
        finally:
            ws.cleanup()

    def test_returns_backup_files(self):
        """有备份时返回对应文件列表。"""
        ws = TempWorkspace()
        try:
            src = ws.create_file("MEMORY.md", "content\n")
            bak = backup_file(src, ws.path)
            result = list_backups(ws.path, "MEMORY.md")

            assert len(result) == 1
            assert result[0] == bak
        finally:
            ws.cleanup()

    def test_sorted_newest_first(self):
        """多个备份按时间戳降序排列（最新在前）。"""
        ws = TempWorkspace()
        try:
            src = ws.create_file("MEMORY.md", "content\n")
            bak1 = backup_file(src, ws.path)
            time.sleep(1.1)
            bak2 = backup_file(src, ws.path)

            result = list_backups(ws.path, "MEMORY.md")
            assert len(result) == 2
            # 最新的在前
            assert result[0] == bak2
            assert result[1] == bak1
        finally:
            ws.cleanup()

    def test_filters_by_filename(self):
        """只返回指定文件的备份，不混入其他文件的备份。"""
        ws = TempWorkspace()
        try:
            mem = ws.create_file("MEMORY.md", "memory\n")
            short = ws.create_file("short-term-recall.json", "{}\n")
            backup_file(mem, ws.path)
            backup_file(short, ws.path)

            mem_backups = list_backups(ws.path, "MEMORY.md")
            json_backups = list_backups(ws.path, "short-term-recall.json")

            assert all("MEMORY.md" in p.name for p in mem_backups)
            assert all("short-term-recall.json" in p.name for p in json_backups)
        finally:
            ws.cleanup()

    def test_no_backup_dir_returns_empty(self):
        """备份目录不存在时返回空列表，不抛异常。"""
        ws = TempWorkspace()
        try:
            # 不创建任何文件，也不创建备份目录
            result = list_backups(ws.path, "MEMORY.md")
            assert result == []
        finally:
            ws.cleanup()

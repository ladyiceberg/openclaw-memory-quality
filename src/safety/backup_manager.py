from __future__ import annotations
"""
backup_manager.py · 备份与原子写入

Phase 2 写操作的两个核心安全保障：

1. backup_file(src, workspace_dir)
   → 复制到 {workspaceDir}/memory/.memory-quality-backups/{name}.{ts}.bak
   → 备份失败时抛 BackupError，调用方必须中止写操作

2. atomic_write(target, content, workspace_dir)
   → 先写 {target}.{pid}.{ts_ms}.tmp
   → 再 os.replace(tmp, target)  ← POSIX rename，原子，中途崩溃不破坏原文件
   → 写失败时清理 .tmp 文件

设计原则（来自产品规格文档 7.1）：
  - 备份不可省略：永远先备份，再写入
  - 原子写入：中途失败不破坏原文件
  - 所有写操作测试必须在临时目录进行（规范要求）
"""

import os
import shutil
import time
from pathlib import Path


# ── 备份目录 ───────────────────────────────────────────────────────────────────

BACKUP_DIR_RELATIVE = "memory/.memory-quality-backups"


def backup_dir(workspace_dir: Path) -> Path:
    return workspace_dir / BACKUP_DIR_RELATIVE


# ── 自定义异常 ────────────────────────────────────────────────────────────────

class BackupError(Exception):
    """备份操作失败。写操作必须在备份成功后才能执行。"""
    pass


class AtomicWriteError(Exception):
    """原子写入失败。"""
    pass


# ── 核心函数 ───────────────────────────────────────────────────────────────────

def backup_file(src: Path, workspace_dir: Path) -> Path:
    """
    备份文件到 {workspace_dir}/memory/.memory-quality-backups/。

    备份文件名：{original_name}.{timestamp_s}.bak
    例：MEMORY.md.1712534892.bak

    Args:
        src           : 要备份的文件（绝对路径）
        workspace_dir : OpenClaw workspace 根目录

    Returns:
        备份文件的绝对路径

    Raises:
        BackupError: 备份失败（文件不存在、磁盘空间不足等）
    """
    if not src.exists():
        raise BackupError(f"源文件不存在，无法备份：{src}")

    bak_dir = backup_dir(workspace_dir)
    try:
        bak_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise BackupError(f"无法创建备份目录 {bak_dir}：{e}") from e

    ts = int(time.time())
    bak_name = f"{src.name}.{ts}.bak"
    bak_path = bak_dir / bak_name

    try:
        shutil.copy2(src, bak_path)   # copy2 保留元数据（mtime 等）
    except OSError as e:
        raise BackupError(f"备份失败 {src} → {bak_path}：{e}") from e

    return bak_path


def atomic_write(target: Path, content: str) -> None:
    """
    原子写入：先写临时文件，再 rename 替换目标文件。

    临时文件名：{target}.{pid}.{timestamp_ms}.tmp
    rename 是 POSIX 原子操作，中途崩溃不会破坏原文件。

    Args:
        target  : 目标文件路径（绝对路径）
        content : 要写入的文本内容

    Raises:
        AtomicWriteError: 写入或 rename 失败
    """
    pid    = os.getpid()
    ts_ms  = int(time.time() * 1000)
    tmp    = target.parent / f"{target.name}.{pid}.{ts_ms}.tmp"

    try:
        tmp.write_text(content, encoding="utf-8")
    except OSError as e:
        # 清理残留的 tmp 文件
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise AtomicWriteError(f"写入临时文件失败 {tmp}：{e}") from e

    try:
        os.replace(tmp, target)   # POSIX rename，原子
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise AtomicWriteError(f"原子替换失败 {tmp} → {target}：{e}") from e


def list_backups(workspace_dir: Path, filename: str) -> list[Path]:
    """
    列出指定文件的所有备份，按时间戳降序排列（最新在前）。

    Args:
        workspace_dir : OpenClaw workspace 根目录
        filename      : 原始文件名，如 "MEMORY.md"

    Returns:
        备份文件路径列表（可能为空）
    """
    bak_dir = backup_dir(workspace_dir)
    if not bak_dir.exists():
        return []

    backups = [
        p for p in bak_dir.iterdir()
        if p.name.startswith(f"{filename}.") and p.name.endswith(".bak")
    ]
    # 按时间戳排序（文件名里的数字部分）
    def _ts(p: Path) -> int:
        try:
            return int(p.name.split(".")[-2])
        except (IndexError, ValueError):
            return 0

    return sorted(backups, key=_ts, reverse=True)

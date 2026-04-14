from __future__ import annotations
"""
shortterm_cleanup.py · memory_cleanup_shortterm_oc 工具的核心逻辑

与 MCP 层解耦：只接收 ProbeResult，返回格式化文本字符串。

shortterm cleanup 不需要 report_id（与 longterm cleanup 不同）：
  - short-term-recall.json 体积小，实时重算规则开销可以忽略
  - zombie/false_positive 判断是纯规则，无需保存中间结果
  - 用户可以随时独立调用

执行流程：
  1. 读取 short-term-recall.json
  2. 实时重算 B1（zombie）和/或 B2（false_positive）
  3. dry_run=True（默认）：只输出预览，不修改文件
  4. dry_run=False：获取锁 → 备份 → 原子写入 → 释放锁

注意：false_positive 类型默认不在清理范围内，需用户显式指定
     cleanup_types=["zombie", "false_positive"]
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.probe import ProbeResult
from src.readers.shortterm_reader import (
    ShortTermEntry,
    ShortTermReadError,
    ShortTermStore,
    read_shortterm,
)
from src.analyzers.zombie_detector import is_zombie
from src.analyzers.false_positive import classify_false_positive
from src.writers.shortterm_writer import build_cleaned_json
from src.safety.lock_manager import acquire_lock, LockTimeoutError
from src.safety.backup_manager import backup_file, BackupError, atomic_write, AtomicWriteError
from i18n import t


def run_shortterm_cleanup(
    probe: ProbeResult,
    cleanup_types: Optional[list] = None,
    dry_run: bool = True,
    now_ms: Optional[int] = None,
) -> str:
    """
    执行短期记忆清理，返回格式化文本。

    Args:
        probe         : probe_workspace() 的返回值
        cleanup_types : 清理类型列表，默认 ["zombie"]
                        可选值："zombie"、"false_positive"
        dry_run       : True（默认）只预览，不修改文件；False 实际执行
        now_ms        : 当前时间毫秒戳（测试用注入，不传则取系统时间）

    Returns:
        格式化的执行结果文本
    """
    if cleanup_types is None:
        cleanup_types = ["zombie"]
    if now_ms is None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    do_zombie = "zombie" in cleanup_types
    do_fp     = "false_positive" in cleanup_types

    # ── 前置检查 ───────────────────────────────────────────────────────────────
    if not probe.has_shortterm:
        return t("cleanup.st.err_no_shortterm")

    st_result = read_shortterm(probe)
    if isinstance(st_result, ShortTermReadError):
        return t("cleanup.st.err_read", msg=st_result.message)

    store: ShortTermStore = st_result

    # ── 分类：找出要删除的 key ─────────────────────────────────────────────────
    zombie_keys: set[str] = set()
    fp_keys: set[str] = set()

    for entry in store.entries:
        if do_zombie:
            flag, _ = is_zombie(entry, now_ms)
            if flag:
                zombie_keys.add(entry.key)
        if do_fp:
            cat, _ = classify_false_positive(entry)
            if cat in ("high_freq_low_quality", "semantic_void"):
                fp_keys.add(entry.key)

    all_keys_to_delete = zombie_keys | fp_keys

    # ── 无需删除 ───────────────────────────────────────────────────────────────
    if not all_keys_to_delete:
        return t("cleanup.st.no_delete")

    # ── dry_run 预览 ───────────────────────────────────────────────────────────
    if dry_run:
        lines = [
            t("cleanup.st.dry_run_header"),
            "━" * 30,
            "",
            t(
                "cleanup.st.would_delete",
                n=len(all_keys_to_delete),
                zombie=len(zombie_keys),
                fp=len(fp_keys),
            ),
            "",
            t("cleanup.st.dry_run_hint"),
        ]
        return "\n".join(lines)

    # ── 实际执行：锁 → 备份 → 写入 ────────────────────────────────────────────
    workspace_dir = Path(probe.workspace_dir)
    shortterm_path = probe.shortterm_path

    try:
        with acquire_lock(workspace_dir):
            return _execute_shortterm_within_lock(
                shortterm_path=shortterm_path,
                workspace_dir=workspace_dir,
                keys_to_delete=all_keys_to_delete,
                zombie_count=len(zombie_keys),
                fp_count=len(fp_keys),
                now_ms=now_ms,
            )
    except LockTimeoutError:
        return t("cleanup.st.err_lock")


def _execute_shortterm_within_lock(
    shortterm_path: Path,
    workspace_dir: Path,
    keys_to_delete: set[str],
    zombie_count: int,
    fp_count: int,
    now_ms: int,
) -> str:
    """锁内执行：备份 → 重建 JSON → 原子写入。"""

    original_json = shortterm_path.read_text(encoding="utf-8")

    # 备份
    try:
        bak_path = backup_file(shortterm_path, workspace_dir)
    except BackupError as e:
        return t("cleanup.st.err_backup", msg=str(e))

    # 重建 JSON
    now_iso = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    new_json, stats = build_cleaned_json(original_json, keys_to_delete, now_iso=now_iso)

    # 原子写入
    try:
        atomic_write(shortterm_path, new_json)
    except AtomicWriteError as e:
        return t("cleanup.st.err_write", msg=str(e)) if hasattr(t, "__call__") else str(e)

    # 格式化结果
    try:
        bak_rel = bak_path.relative_to(workspace_dir)
    except ValueError:
        bak_rel = bak_path

    lines = [
        t("cleanup.st.header"),
        "━" * 20,
        "",
        t("cleanup.st.deleted", n=stats.deleted, zombie=zombie_count, fp=fp_count),
        t("cleanup.st.kept", n=stats.kept),
        t("cleanup.st.backup", path=str(bak_rel)),
    ]
    return "\n".join(lines)

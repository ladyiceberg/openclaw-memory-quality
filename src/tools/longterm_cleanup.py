from __future__ import annotations
"""
longterm_cleanup.py · memory_longterm_cleanup_oc 工具的核心逻辑

与 MCP 层解耦：只接收 ProbeResult + report_id，返回格式化文本字符串。
测试可直接调用，不需要启动 MCP server。

严格按产品规格文档 7.2 的 7 步流程执行，任何步骤失败立即中止：

  Step 0: 从 session store 读取 report_id
  Step 1: mtime 守护（校验 MEMORY.md 在 audit 后未被修改）
  Step 2: 获取并发锁
  Step 3: 内容完整性预检（80% 安全阀）
  Step 4: 备份原文件
  Step 5: 构建新文件内容
  Step 6: 原子写入 + 释放锁
  Step 7: 返回结果
"""

from pathlib import Path
from typing import Optional

from src.probe import ProbeResult
from src.readers.longterm_reader import read_longterm_from_path, LongTermReadError
from src.writers.longterm_writer import build_cleaned_content
from src.safety.lock_manager import acquire_lock, LockTimeoutError
from src.safety.backup_manager import backup_file, BackupError, atomic_write, AtomicWriteError
from src.session_store import load_audit_report
from i18n import t


def run_longterm_cleanup(
    probe: ProbeResult,
    report_id: str,
    db_path: Optional[Path] = None,
) -> str:
    """
    执行长期记忆清理，返回格式化文本。

    Args:
        probe     : probe_workspace() 的返回值
        report_id : audit 时生成的 report_id（必填）
        db_path   : 测试用，覆盖默认 SQLite 路径

    Returns:
        格式化的执行结果文本
    """
    # ── Step 0：读取 audit 结果 ─────────────────────────────────────────────
    payload = load_audit_report(report_id, db_path=db_path)
    if payload is None:
        return t("cleanup.lt.err_no_report", report_id=report_id)

    # 提取要删除的 key 集合
    keys_to_delete: set[str] = {
        item["promotion_key"]
        for item in payload.get("items", [])
        if item.get("action_hint") == "delete" and item.get("promotion_key")
    }
    # 同时加入 fallback key（source_path:start-end）以支持无 comment 行的旧格式
    for item in payload.get("items", []):
        if item.get("action_hint") == "delete":
            sp = item.get("source_path", "")
            ss = item.get("source_start", "")
            se = item.get("source_end", "")
            if sp and ss and se:
                keys_to_delete.add(f"{sp}:{ss}-{se}")

    audit_mtime: Optional[float] = payload.get("memory_md_mtime")
    non_standard_sections: int = payload.get("non_standard_sections", 0)

    # 没有需要删除的条目 → 友好提示，不执行写操作
    delete_count_in_payload = sum(
        1 for item in payload.get("items", [])
        if item.get("action_hint") == "delete"
    )
    if delete_count_in_payload == 0:
        return t("cleanup.lt.no_delete")

    # ── Step 1：mtime 守护 ──────────────────────────────────────────────────
    if not probe.has_longterm:
        return t("cleanup.lt.err_no_longterm")

    longterm_path = probe.longterm_path
    current_mtime = longterm_path.stat().st_mtime

    if audit_mtime is not None and abs(current_mtime - audit_mtime) > 1.0:
        # 允许 1 秒误差（不同文件系统 mtime 精度不同）
        return t("cleanup.lt.err_mtime")

    workspace_dir = Path(probe.workspace_dir)

    # ── Step 2 & 3 & 4 & 5 & 6：在锁内执行 ─────────────────────────────────
    try:
        with acquire_lock(workspace_dir):
            return _execute_within_lock(
                longterm_path=longterm_path,
                workspace_dir=workspace_dir,
                keys_to_delete=keys_to_delete,
                non_standard_sections=non_standard_sections,
            )
    except LockTimeoutError:
        return t("cleanup.lt.err_lock")


def _execute_within_lock(
    longterm_path: Path,
    workspace_dir: Path,
    keys_to_delete: set[str],
    non_standard_sections: int,
) -> str:
    """锁内执行：完整性预检 → 备份 → 构建 → 原子写入。"""

    # ── Step 3：内容完整性预检（80% 安全阀）─────────────────────────────────
    original = longterm_path.read_text(encoding="utf-8")
    store_result = read_longterm_from_path(longterm_path, "source_code")
    if isinstance(store_result, LongTermReadError):
        if store_result.error_code == "safety_valve":
            return t(
                "cleanup.lt.err_safety_valve",
                ratio=0.0,
            )
        # 其他读取错误
        return t("cleanup.lt.err_safety_valve", ratio=0.0)

    if store_result.dreaming_section_chars > 100 and store_result.parsed_ratio < 0.80:
        return t(
            "cleanup.lt.err_safety_valve",
            ratio=store_result.parsed_ratio,
        )

    # ── Step 4：备份原文件 ─────────────────────────────────────────────────
    try:
        bak_path = backup_file(longterm_path, workspace_dir)
    except BackupError as e:
        return t("cleanup.lt.err_backup", msg=str(e))

    # ── Step 5：构建新内容 ────────────────────────────────────────────────
    new_content, stats = build_cleaned_content(original, keys_to_delete)

    # ── Step 6：原子写入 ─────────────────────────────────────────────────
    try:
        atomic_write(longterm_path, new_content)
    except AtomicWriteError as e:
        return t("cleanup.lt.err_write", msg=str(e))

    # ── Step 7：格式化结果 ────────────────────────────────────────────────
    lines = [
        t("cleanup.lt.header"),
        "━" * 20,
        "",
        t("cleanup.lt.deleted", n=stats.deleted),
    ]

    manual_note = ""
    if non_standard_sections > 0:
        manual_note = t("cleanup.lt.manual_note", n=non_standard_sections)
    lines.append(t("cleanup.lt.kept", n=stats.kept, manual_note=manual_note))

    # 备份路径（相对于 workspace_dir）
    try:
        bak_rel = bak_path.relative_to(workspace_dir)
    except ValueError:
        bak_rel = bak_path
    lines.append(t("cleanup.lt.backup", path=str(bak_rel)))
    lines.append("")
    lines.append(t(
        "cleanup.lt.sections",
        before=stats.sections_before,
        after=stats.sections_after,
    ))

    return "\n".join(lines)

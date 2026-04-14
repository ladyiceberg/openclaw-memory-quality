from __future__ import annotations
"""
soul_check.py · memory_soul_check_oc 工具的核心逻辑

与 MCP 层解耦：只接收 ProbeResult，返回格式化文本字符串。
测试可直接调用，不需要启动 MCP server。

执行流程（来自产品规格文档 9.5）：
  1. 检查 SOUL.md 是否存在
  2. 读取 SOUL.md 内容
  3. 从 session cache 读取上次快照（C3 对比用）
  4. 运行 soul_auditor（C1 + C2 规则层 + C3）
  5. 将当前快照写入 session cache
  6. 格式化输出
  7. use_llm=True：Phase 3 占位提示

设计原则：
  - 永远不写 SOUL.md，只读取和分析
  - session cache 只存快照元数据（hash/char_count/directive_count），不存全文
"""

import time
from pathlib import Path
from typing import Optional

from src.probe import ProbeResult
from src.analyzers.soul_auditor import audit_soul, SoulAuditResult
from src.session_store import save_soul_snapshot, load_last_soul_snapshot
from i18n import t


def run_soul_check(
    probe: ProbeResult,
    use_llm: bool = False,
    db_path: Optional[Path] = None,
) -> str:
    """
    执行 SOUL.md 健康检查，返回格式化文本。

    Args:
        probe   : probe_workspace() 的返回值
        use_llm : Phase 3 功能，目前输出占位提示
        db_path : 测试用，覆盖默认 SQLite 路径

    Returns:
        格式化的健康检查报告
    """
    lines: list[str] = []
    lines.append(t("soul.header"))
    lines.append("━" * 22)
    lines.append("")

    # ── 检查 SOUL.md 是否存在 ──────────────────────────────────────────────
    if not probe.has_soul:
        lines.append(t("soul.no_soul"))
        return "\n".join(lines)

    soul_path = probe.soul_path
    content = soul_path.read_text(encoding="utf-8")

    # ── 文件信息 ───────────────────────────────────────────────────────────
    try:
        rel = soul_path.relative_to(probe.workspace_dir)
    except ValueError:
        rel = soul_path
    lines.append(t("soul.file_info", path=str(rel), size=f"{len(content):,}"))

    # ── 读取上次快照（C3 对比用）───────────────────────────────────────────
    previous_snapshot = load_last_soul_snapshot(probe.workspace_dir, db_path=db_path)
    is_first_run = previous_snapshot is None

    # 上次检查时间提示
    if is_first_run:
        lines.append(t("soul.last_check_never"))
    else:
        ago = _format_ago(previous_snapshot["checked_at"])
        from src.analyzers.soul_auditor import compute_snapshot
        current_hash = compute_snapshot(content).content_hash
        changed = previous_snapshot["content_hash"] != current_hash
        changed_str = t("soul.changed_flag") if changed else ""
        lines.append(t("soul.last_check_ago", ago=ago, changed=changed_str))

    lines.append("")

    # ── 运行 soul_auditor ─────────────────────────────────────────────────
    result: SoulAuditResult = audit_soul(content, previous_snapshot=previous_snapshot)

    # ── 将当前快照写入 session cache ──────────────────────────────────────
    snap = result.snapshot
    save_soul_snapshot(
        workspace=probe.workspace_dir,
        char_count=snap.char_count,
        content_hash=snap.content_hash,
        directive_count=snap.directive_count,
        sections=snap.sections,
        db_path=db_path,
    )

    # ── 格式化各 section ───────────────────────────────────────────────────
    c1_flags = [f for f in result.risk_flags if f.check == "C1"]
    c2_flags = [f for f in result.risk_flags if f.check == "C2"]
    c3_flags = [f for f in result.risk_flags if f.check == "C3"]

    # C1
    lines.append(t("soul.c1_header"))
    if c1_flags:
        for flag in c1_flags:
            lines.append(t("soul.flag_line", desc=flag.description))
            if flag.line_hint:
                lines.append(f"   → {flag.line_hint}")
    else:
        lines.append(t("soul.section_ok"))
    lines.append("")

    # C2
    lines.append(t("soul.c2_header"))
    c2_has_content = c2_flags or result.missing_sections
    if c2_has_content:
        for flag in c2_flags:
            lines.append(t("soul.flag_line", desc=flag.description))
        if result.c2_suspicious_paragraphs and not use_llm:
            lines.append(f"   → {len(result.c2_suspicious_paragraphs)} 处段落待 LLM 精判（use_llm=True 时启用）")
    else:
        lines.append(t("soul.section_ok"))
    lines.append("")

    # C3
    lines.append(t("soul.c3_header"))
    if is_first_run:
        lines.append(t("soul.first_run_note"))
    elif c3_flags:
        for flag in c3_flags:
            lines.append(t("soul.flag_line", desc=flag.description))
    else:
        lines.append(t("soul.section_ok"))
    lines.append("")

    # C4 占位
    lines.append(t("soul.c4_header"))
    lines.append(t("soul.c4_disabled"))
    lines.append("")

    # ── 总结 ───────────────────────────────────────────────────────────────
    lines.append(t("soul.summary_header"))
    risk_key = {
        "ok":     "soul.risk_ok",
        "low":    "soul.risk_low",
        "medium": "soul.risk_medium",
        "high":   "soul.risk_high",
    }.get(result.risk_level, "soul.risk_ok")
    lines.append(t(risk_key))

    # 有中/高风险时建议 LLM 检查
    if result.risk_level in ("medium", "high") and not use_llm:
        lines.append(t("soul.suggest_llm"))

    # 去掉末尾多余空行
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def _format_ago(ts: float) -> str:
    """将时间戳格式化为'N 天前'/'N 小时前'等形式。"""
    secs = time.time() - ts
    if secs < 60:
        return "刚刚" if _is_zh() else "just now"
    if secs < 3600:
        n = int(secs / 60)
        return f"{n} 分钟" if _is_zh() else f"{n}m"
    if secs < 86400:
        n = int(secs / 3600)
        return f"{n} 小时" if _is_zh() else f"{n}h"
    n = int(secs / 86400)
    return f"{n} 天" if _is_zh() else f"{n}d"


def _is_zh() -> bool:
    from config import detect_language
    return detect_language() == "zh"

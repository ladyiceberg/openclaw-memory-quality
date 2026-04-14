from __future__ import annotations
"""
longterm_audit.py · memory_longterm_audit_oc 工具的核心逻辑

与 MCP 层解耦：只接收 ProbeResult，返回 (report_id, 格式化文本)。
测试可直接调用，不需要启动 MCP server。

执行流程：
  1. 读取并解析 MEMORY.md（longterm_reader）
  2. 运行 V1 + V3 核查（longterm_auditor）
  3. 序列化结果，生成 report_id，存入 session_store（SQLite）
  4. 格式化输出文本

Phase 1：use_llm=True 暂不实现，占位提示。
"""

from dataclasses import asdict
from pathlib import Path
from typing import Optional

from src.probe import ProbeResult
from src.readers.longterm_reader import (
    LongTermReadError,
    LongTermStore,
    read_longterm,
)
from src.analyzers.longterm_auditor import (
    AuditedItem,
    LongtermAuditResult,
    run_audit,
)
from src.session_store import make_report_id, save_audit_report
from i18n import t


def run_longterm_audit(
    probe: ProbeResult,
    use_llm: bool = False,
    db_path: Optional[Path] = None,
) -> tuple[Optional[str], str]:
    """
    执行长期记忆审计，返回 (report_id, 格式化文本)。

    Args:
        probe   : probe_workspace() 的返回值
        use_llm : 是否启用 LLM 语义评估（Phase 1 暂不支持）
        db_path : 测试用，覆盖默认 SQLite 路径

    Returns:
        (report_id, text)
        report_id 为 None 表示审计未成功执行（无法生成报告）
    """
    lines: list[str] = []

    # ── 标题 ───────────────────────────────────────────────────────────────────
    lines.append(t("audit.header"))
    lines.append("━" * 26)
    lines.append("")

    # ── 前置检查 ───────────────────────────────────────────────────────────────
    if not probe.has_longterm:
        lines.append(t("audit.no_longterm"))
        return None, "\n".join(lines)

    if not probe.supports_longterm_audit:
        lines.append(t("audit.format_unsupported"))
        return None, "\n".join(lines)

    # ── 读取并解析 MEMORY.md ───────────────────────────────────────────────────
    lt_result = read_longterm(probe)

    if isinstance(lt_result, LongTermReadError):
        lines.append(t("audit.parse_error", msg=lt_result.message))
        return None, "\n".join(lines)

    store: LongTermStore = lt_result

    # ── V1 + V3 核查 ───────────────────────────────────────────────────────────
    audit_result: LongtermAuditResult = run_audit(
        store=store,
        workspace_dir=probe.workspace_dir,
        memory_md_path=probe.longterm_path,
    )

    # ── 格式化输出 ─────────────────────────────────────────────────────────────
    total = audit_result.total_items

    lines.append(t(
        "audit.summary",
        sections=audit_result.sections_count,
        items=total,
    ))
    lines.append("")
    lines.append(t("audit.results_header"))

    def _pct(n: int) -> str:
        return f"{n / total * 100:.0f}" if total > 0 else "0"

    keep_n   = audit_result.items_by_action.get("keep", 0)
    review_n = audit_result.items_by_action.get("review", 0)
    delete_n = audit_result.items_by_action.get("delete", 0)

    lines.append(t("audit.keep",   n=keep_n,   pct=_pct(keep_n)))
    lines.append(t("audit.review", n=review_n, pct=_pct(review_n)))
    lines.append(t("audit.delete", n=delete_n, pct=_pct(delete_n)))

    # ── 删除原因细分 ───────────────────────────────────────────────────────────
    if delete_n > 0:
        lines.append("")
        lines.append(t("audit.delete_reasons_header"))
        deleted_v1   = sum(1 for a in audit_result.items if a.action_hint == "delete" and a.v1_status == "deleted")
        deleted_dup  = sum(1 for a in audit_result.items if a.action_hint == "delete" and a.v3_status == "duplicate_loser")
        if deleted_v1:
            lines.append(t("audit.reason_deleted",   n=deleted_v1))
        if deleted_dup:
            lines.append(t("audit.reason_duplicate", n=deleted_dup))

    # ── 非标准段落警告 ─────────────────────────────────────────────────────────
    if audit_result.non_standard_sections > 0:
        lines.append("")
        lines.append(t("audit.non_standard_warn", n=audit_result.non_standard_sections))

    # ── LLM 提示（use_llm=False 且有 review 条目）─────────────────────────────
    if not use_llm and review_n > 0:
        lines.append("")
        lines.append(t("audit.llm_hint", n=review_n))

    if use_llm:
        lines.append("")
        lines.append(t("audit.llm_disabled"))

    # ── 生成 report_id，存入 session store ────────────────────────────────────
    report_id = make_report_id()
    payload = _serialize_audit_result(audit_result, store)
    save_audit_report(
        report_id=report_id,
        workspace=probe.workspace_dir,
        total_items=total,
        payload=payload,
        db_path=db_path,
    )

    lines.append("")
    lines.append(t("audit.report_id_line", report_id=report_id))

    # 去掉末尾多余空行
    while lines and lines[-1] == "":
        lines.pop()

    return report_id, "\n".join(lines)


# ── 序列化辅助 ────────────────────────────────────────────────────────────────

def _serialize_audit_result(
    result: LongtermAuditResult,
    store: LongTermStore,
) -> dict:
    """
    将 LongtermAuditResult 序列化为 JSON 可存储的 dict。

    保留 cleanup 所需的最小信息：
      - 每条 item 的 action_hint、v1/v3 状态、source 路径和行号
      - sections 计数、mtime（供写操作安全校验）
    """
    items_list = []
    for audited in result.items:
        item = audited.item
        items_list.append({
            "snippet": item.snippet,
            "source_path": item.source_path,
            "source_start": item.source_start,
            "source_end": item.source_end,
            "score": item.score,
            "promotion_key": item.promotion_key,
            "v1_status": audited.v1_status,
            "v3_status": audited.v3_status,
            "action_hint": audited.action_hint,
        })

    return {
        "total_items": result.total_items,
        "sections_count": result.sections_count,
        "items_by_action": result.items_by_action,
        "non_standard_sections": result.non_standard_sections,
        "memory_md_mtime": result.memory_md_mtime,
        "items": items_list,
    }

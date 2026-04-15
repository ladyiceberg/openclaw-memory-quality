from __future__ import annotations
"""
longterm_audit.py · memory_longterm_audit_oc 工具的核心逻辑

与 MCP 层解耦：只接收 ProbeResult，返回 (report_id, 格式化文本)。
测试可直接调用，不需要启动 MCP server。

执行流程：
  1. 读取并解析 MEMORY.md（longterm_reader）
  2. 运行 V1 + V3 核查（longterm_auditor）
  3. use_llm=True：运行 LLM 语义评估（llm_longterm_evaluator）
     - 任务 A：review 条目语义有效性复审（still_valid/outdated/uncertain）
     - 任务 B：语义去重建议
  4. 序列化结果，生成 report_id，存入 session_store（SQLite）
  5. 格式化输出文本
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
        use_llm : 是否启用 LLM 语义评估
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

    # ── LLM 语义评估（use_llm=True 时执行）────────────────────────────────────
    llm_eval = None
    if use_llm:
        llm_eval = _run_llm_eval(audit_result.items, probe.workspace_dir, lines)
        if llm_eval is not None:
            # 将 LLM 结果合并回 audit_items，更新 action_hint
            from src.analyzers.llm_longterm_evaluator import apply_llm_results
            audit_result = _rebuild_audit_result(
                audit_result,
                apply_llm_results(audit_result.items, llm_eval),
            )

    # ── 格式化规则层结果 ───────────────────────────────────────────────────────
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

    # ── LLM 结果格式化（use_llm=True 且评估成功）──────────────────────────────
    if use_llm and llm_eval is not None:
        _format_llm_results(lines, llm_eval, review_n)
    elif not use_llm and review_n > 0:
        lines.append("")
        lines.append(t("audit.llm_hint", n=review_n))

    # ── 生成 report_id，存入 session store ────────────────────────────────────
    report_id = make_report_id()
    payload = _serialize_audit_result(audit_result, store, llm_eval)
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


# ── LLM 评估辅助 ─────────────────────────────────────────────────────────────

def _run_llm_eval(
    audit_items: list[AuditedItem],
    workspace_dir: str,
    lines: list[str],
):
    """
    尝试运行 LLM 评估。返回 LLMEvalResult 或 None（API key 未配置）。
    失败时向 lines 追加错误提示，不抛异常。
    """
    from src.analyzers.llm_longterm_evaluator import run_llm_evaluation
    try:
        from llm_client import create_client
        llm = create_client()
    except ValueError as e:
        lines.append("")
        lines.append(t("audit.llm_cost_warning"))
        return None
    except Exception as e:
        lines.append("")
        lines.append(t("audit.llm_error", msg=str(e)))
        return None

    try:
        return run_llm_evaluation(audit_items, Path(workspace_dir), llm)
    except Exception as e:
        lines.append("")
        lines.append(t("audit.llm_error", msg=str(e)))
        return None


def _format_llm_results(lines: list[str], llm_eval, review_count: int) -> None:
    """格式化 LLM 评估结果，追加到 lines。"""
    lines.append("")
    lines.append(t("audit.llm_header", n=review_count))
    lines.append("━" * 38)
    lines.append("")

    # 统计各判断数量
    verdicts = [v.verdict for v in llm_eval.validity_results.values()]
    still_valid = verdicts.count("still_valid")
    outdated    = verdicts.count("outdated")
    uncertain   = verdicts.count("uncertain")

    lines.append(t("audit.llm_validity_header"))
    lines.append(t("audit.llm_still_valid", n=still_valid))
    lines.append(t("audit.llm_outdated",    n=outdated))
    lines.append(t("audit.llm_uncertain",   n=uncertain))

    # 语义去重建议
    if llm_eval.merge_suggestions:
        lines.append("")
        lines.append(t("audit.llm_dedup_header", n=len(llm_eval.merge_suggestions)))
        for i, sug in enumerate(llm_eval.merge_suggestions, start=1):
            lines.append(t(
                "audit.llm_dedup_pair",
                i=i,
                a=sug.item_a_source,
                b=sug.item_b_source,
                suggestion=sug.merge_suggestion,
            ))
    else:
        lines.append("")
        lines.append(t("audit.llm_no_dedup"))


def _rebuild_audit_result(
    original: LongtermAuditResult,
    updated_items: list[AuditedItem],
) -> LongtermAuditResult:
    """用更新后的 items 重建 LongtermAuditResult，重新计算 items_by_action。"""
    items_by_action: dict[str, int] = {"keep": 0, "review": 0, "delete": 0}
    for a in updated_items:
        items_by_action[a.action_hint] = items_by_action.get(a.action_hint, 0) + 1

    return LongtermAuditResult(
        total_items=original.total_items,
        sections_count=original.sections_count,
        items_by_action=items_by_action,
        non_standard_sections=original.non_standard_sections,
        items=updated_items,
        memory_md_mtime=original.memory_md_mtime,
    )


# ── 序列化辅助 ────────────────────────────────────────────────────────────────

def _serialize_audit_result(
    result: LongtermAuditResult,
    store: LongTermStore,
    llm_eval=None,
) -> dict:
    """
    将 LongtermAuditResult 序列化为 JSON 可存储的 dict。
    LLM 评估结果也一并存入，供 cleanup 和看板使用。
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

    payload = {
        "total_items": result.total_items,
        "sections_count": result.sections_count,
        "items_by_action": result.items_by_action,
        "non_standard_sections": result.non_standard_sections,
        "memory_md_mtime": result.memory_md_mtime,
        "items": items_list,
    }

    # LLM 评估结果（可选）
    if llm_eval is not None:
        payload["llm_eval"] = {
            "validity": {
                k: {"verdict": v.verdict, "reason": v.reason}
                for k, v in llm_eval.validity_results.items()
            },
            "merge_suggestions": [
                {
                    "item_a": s.item_a_source,
                    "item_b": s.item_b_source,
                    "suggestion": s.merge_suggestion,
                }
                for s in llm_eval.merge_suggestions
            ],
        }

    return payload

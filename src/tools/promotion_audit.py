from __future__ import annotations
"""
promotion_audit.py · memory_promotion_audit_oc 工具的核心逻辑

与 MCP 层解耦：只接收 ProbeResult，返回格式化文本字符串。
测试可直接调用，不需要启动 MCP server。

执行流程：
  1. 读取 short-term-recall.json（shortterm_reader）
  2. 读取 MEMORY.md（longterm_reader，可选，用于关卡 3）
  3. 运行 promotion_auditor（关卡 1-4）
  4. use_llm=True：运行 llm_promotion_evaluator（关卡 5）
  5. 格式化输出
"""

from pathlib import Path
from typing import Optional

from src.probe import ProbeResult
from src.readers.shortterm_reader import (
    ShortTermReadError,
    ShortTermStore,
    read_shortterm,
)
from src.readers.longterm_reader import (
    LongTermReadError,
    LongTermStore,
    read_longterm,
)
from src.analyzers.promotion_auditor import (
    PromotionAuditResult,
    PromotionCandidate,
    run_promotion_audit,
)
from i18n import t


# ── 关卡原因 → i18n key 映射 ──────────────────────────────────────────────────

_SKIP_REASON_KEYS = {
    "source_deleted":    "promo.skip_reason_source_deleted",
    "import_only":       "promo.skip_reason_import_only",
    "comments_only":     "promo.skip_reason_comments_only",
    "boilerplate":       "promo.skip_reason_boilerplate",
    "debug_code":        "promo.skip_reason_debug_code",
    "already_promoted":  "promo.skip_reason_already_promoted",
}


def run_promotion_audit_tool(
    probe: ProbeResult,
    top_n: int = 10,
    use_llm: bool = False,
) -> str:
    """
    执行晋升前质量预检，返回格式化文本。

    Args:
        probe   : probe_workspace() 的返回值
        top_n   : 检查评分最高的前 N 条候选（默认 10）
        use_llm : 是否启用关卡 5 LLM 长期价值 advisory

    Returns:
        格式化的预检报告
    """
    lines: list[str] = []
    lines.append(t("promo.header"))
    lines.append("━" * 38)
    lines.append("")

    # ── 读取短期记忆 ────────────────────────────────────────────────────────
    st_result = read_shortterm(probe)
    if isinstance(st_result, ShortTermReadError):
        lines.append(t("promo.no_shortterm"))
        return "\n".join(lines)

    store: ShortTermStore = st_result

    # ── 读取长期记忆（可选，供关卡 3 用）──────────────────────────────────
    lt_store: Optional[LongTermStore] = None
    if probe.has_longterm and probe.supports_longterm_audit:
        lt_result = read_longterm(probe)
        if isinstance(lt_result, LongTermStore):
            lt_store = lt_result

    # ── 运行关卡 1-4 ────────────────────────────────────────────────────────
    audit: PromotionAuditResult = run_promotion_audit(
        store=store,
        workspace_dir=probe.workspace_dir,
        lt_store=lt_store,
        top_n=top_n,
    )

    if audit.total_unpromotted == 0:
        lines.append(t("promo.no_candidates"))
        return "\n".join(lines)

    # ── 摘要 ───────────────────────────────────────────────────────────────
    lines.append(t("promo.summary",
                   total=audit.total_unpromotted,
                   top_n=audit.top_n))
    lines.append("")
    lines.append(t("promo.results_header"))
    lines.append(t("promo.pass", n=audit.pass_count))
    lines.append(t("promo.skip", n=audit.skip_count))
    lines.append(t("promo.flag", n=audit.flag_count))

    # ── 建议跳过列表 ────────────────────────────────────────────────────────
    skip_items = [c for c in audit.candidates if c.verdict == "skip"]
    if skip_items:
        lines.append("")
        lines.append(t("promo.skip_section_header"))
        for idx, cand in enumerate(skip_items, start=1):
            entry = cand.entry
            lines.append(t("promo.candidate_line",
                           idx=idx,
                           path=entry.path,
                           start=entry.start_line,
                           end=entry.end_line,
                           score=cand.score.composite))
            reason = cand.skip_reason or ""
            reason_key = _SKIP_REASON_KEYS.get(reason, "promo.skip_reason_unknown")
            if reason_key == "promo.skip_reason_unknown":
                lines.append(t(reason_key, reason=reason))
            else:
                lines.append(t(reason_key))

    # ── 需关注列表（假阳性信号）────────────────────────────────────────────
    flag_items = [c for c in audit.candidates if c.verdict == "flag"]
    if flag_items:
        lines.append("")
        lines.append(t("promo.flag_section_header"))
        for idx, cand in enumerate(flag_items, start=1):
            entry = cand.entry
            lines.append(t("promo.candidate_line",
                           idx=idx,
                           path=entry.path,
                           start=entry.start_line,
                           end=entry.end_line,
                           score=cand.score.composite))
            lines.append(t("promo.flag_reason_fp",
                           avg=cand.score.avg_score,
                           max=entry.max_score))

    # ── 全部通过时简洁提示 ─────────────────────────────────────────────────
    if audit.skip_count == 0 and audit.flag_count == 0:
        lines.append("")
        lines.append(t("promo.all_pass"))

    # ── 评分近似值声明 ────────────────────────────────────────────────────
    lines.append("")
    lines.append(t("promo.score_note"))

    # ── 关卡 5：LLM 长期价值 advisory ──────────────────────────────────────
    if use_llm:
        llm_eval = _run_llm_eval(audit.candidates, lines)
        if llm_eval is not None:
            _format_llm_results(lines, llm_eval)
    elif audit.pass_count + audit.flag_count > 0:
        lines.append("")
        lines.append(t("promo.llm_hint"))

    # 去掉末尾多余空行
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


# ── LLM 评估辅助 ─────────────────────────────────────────────────────────────

def _run_llm_eval(candidates: list[PromotionCandidate], lines: list[str]):
    """
    尝试运行关卡 5 LLM 评估。
    返回 LLMPromotionEvalResult 或 None（API key 未配置时）。
    """
    from src.analyzers.llm_promotion_evaluator import run_llm_promotion_evaluation
    try:
        from llm_client import create_client
        llm = create_client()
    except ValueError as e:
        lines.append("")
        lines.append(t("promo.llm_error", msg=str(e)))
        return None
    except Exception as e:
        lines.append("")
        lines.append(t("promo.llm_error", msg=str(e)))
        return None

    try:
        return run_llm_promotion_evaluation(candidates, llm)
    except Exception as e:
        lines.append("")
        lines.append(t("promo.llm_error", msg=str(e)))
        return None


def _format_llm_results(lines: list[str], llm_eval) -> None:
    """格式化 LLM 关卡 5 结果，追加到 lines。"""
    lines.append("")
    lines.append(t("promo.llm_header"))
    lines.append("")
    lines.append(t("promo.llm_long_term", n=llm_eval.long_term_count))
    lines.append(t("promo.llm_one_time",  n=llm_eval.one_time_count))
    lines.append(t("promo.llm_uncertain", n=llm_eval.uncertain_count))

    # 列出 one_time_context 条目供用户参考
    one_time = [
        a for a in llm_eval.advisories.values()
        if a.verdict == "one_time_context"
    ]
    if one_time:
        lines.append("")
        lines.append(t("promo.llm_one_time_detail_header"))
        for idx, adv in enumerate(one_time, start=1):
            hint = adv.entry_key[:50] + ("…" if len(adv.entry_key) > 50 else "")
            lines.append(t("promo.llm_advisory_item",
                           idx=idx,
                           verdict=adv.verdict,
                           hint=hint,
                           reason=adv.reason))

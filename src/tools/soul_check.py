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
  6. use_llm=True：运行 LLM 语义评估（C2 精判 + C4-a + C4-b）
  7. 格式化输出

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
        use_llm : 是否启用 LLM 语义评估（C2 精判 + C4 冲突检测）
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

    # C4 冲突检测（use_llm=True 时运行 LLM；否则显示占位提示）
    lines.append(t("soul.c4_header"))
    if use_llm:
        llm_result = _run_llm_soul_eval(
            soul_content=content,
            suspicious_paragraphs=result.c2_suspicious_paragraphs,
            probe=probe,
        )
        _format_c4_results(lines, llm_result)
    else:
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


# ── LLM 评估辅助 ─────────────────────────────────────────────────────────────

def _run_llm_soul_eval(
    soul_content: str,
    suspicious_paragraphs: list,
    probe: ProbeResult,
):
    """
    尝试运行 LLM 评估。返回 LLMSoulEvalResult 或 None（API key 未配置时）。
    失败时优雅降级（返回带 llm_error 的结果），不抛异常。
    """
    from src.analyzers.llm_soul_evaluator import (
        LLMSoulEvalResult,
        run_llm_soul_evaluation,
    )
    # 读取 IDENTITY.md 内容（可选）
    identity_content = ""
    if probe.identity_path is not None:
        try:
            identity_content = probe.identity_path.read_text(encoding="utf-8")
        except Exception:
            pass

    try:
        from llm_client import create_client
        llm = create_client()
    except ValueError:
        result = LLMSoulEvalResult()
        result.llm_error = "API key not configured"
        return result
    except Exception as e:
        result = LLMSoulEvalResult()
        result.llm_error = str(e)
        return result

    try:
        return run_llm_soul_evaluation(
            soul_content=soul_content,
            suspicious_paragraphs=suspicious_paragraphs,
            identity_content=identity_content,
            llm_client=llm,
        )
    except Exception as e:
        result = LLMSoulEvalResult()
        result.llm_error = str(e)
        return result


def _format_c4_results(lines: list, llm_result) -> None:
    """格式化 LLM soul 评估结果，追加到 lines。"""
    from src.analyzers.llm_soul_evaluator import LLMSoulEvalResult

    if llm_result is None:
        lines.append(t("soul.c4_disabled"))
        return

    if llm_result.llm_error:
        lines.append(t("soul.c4_llm_error", msg=llm_result.llm_error))
        return

    has_issues = False

    # C2 精判结果
    if llm_result.c2_classifications:
        lines.append(t("soul.c4_c2_precision_header", n=len(llm_result.c2_classifications)))
        task_count = 0
        for c in llm_result.c2_classifications:
            lines.append(t(
                "soul.c4_c2_item",
                classification=c.classification,
                hint=c.paragraph_hint,
                reason=c.reason,
            ))
            if c.classification in ("task_instruction", "mixed"):
                task_count += 1
        if task_count > 0:
            lines.append(t("soul.c4_c2_task_warning", n=task_count))
            has_issues = True

    # C4-a 内部冲突
    if llm_result.c4_conflicts:
        has_issues = True
        lines.append(t("soul.c4_conflicts_header", n=len(llm_result.c4_conflicts)))
        for c in llm_result.c4_conflicts:
            lines.append(t(
                "soul.c4_conflict_item",
                severity=c.severity,
                a=c.statement_a,
                b=c.statement_b,
                reason=c.reason,
            ))

    # C4-b IDENTITY 不一致
    if llm_result.c4_mismatches:
        has_issues = True
        lines.append(t("soul.c4_mismatches_header", n=len(llm_result.c4_mismatches)))
        for m in llm_result.c4_mismatches:
            lines.append(t(
                "soul.c4_mismatch_item",
                severity=m.severity,
                soul=m.soul_description,
                ident=m.identity_description,
                reason=m.reason,
            ))

    if not has_issues:
        lines.append(t("soul.c4_no_issues"))


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

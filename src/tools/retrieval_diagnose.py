from __future__ import annotations
"""
retrieval_diagnose.py · memory_retrieval_diagnose_oc 工具的核心逻辑

与 MCP 层解耦：只接收 ProbeResult + top_n，返回格式化文本字符串。
测试可直接调用，不需要启动 MCP server。

执行流程：
  1. 读取并解析 short-term-recall.json
  2. 对所有条目运行 B2 分类（classify_false_positive）
  3. 按风险程度排序：high_freq_low_quality > semantic_void > ambiguous
     同类别内按 recalls 倒序（高频更危险）
  4. 输出前 top_n 条详情 + 聚合统计 + 配置建议

top_n=0：只输出聚合统计，不列条目（适合快速概览）
health < 70：触发配置建议
"""

from typing import Optional

from src.probe import ProbeResult
from src.readers.shortterm_reader import (
    ShortTermEntry,
    ShortTermReadError,
    ShortTermStore,
    read_shortterm,
)
from src.analyzers.false_positive import (
    classify_false_positive,
    compute_avg_score,
    compute_false_positive_stats,
)
from i18n import t


# ── 风险排序权重（数字越小排越前）────────────────────────────────────────────

_CATEGORY_ORDER = {
    "high_freq_low_quality": 0,
    "semantic_void": 1,
    "ambiguous": 2,
    "": 3,
}


def _sort_key(item: tuple[ShortTermEntry, str, str]) -> tuple:
    """
    排序键：(category_priority, -recalls)
    高风险 category 排前面；同 category 内 recalls 多的排前面。
    """
    entry, cat, _sub = item
    return (_CATEGORY_ORDER.get(cat, 3), -entry.recall_count)


def run_retrieval_diagnose(
    probe: ProbeResult,
    top_n: int = 20,
) -> str:
    """
    执行检索质量诊断，返回格式化文本。

    Args:
        probe : probe_workspace() 的返回值
        top_n : 展示风险最高的前 N 条（0 = 只输出聚合统计）

    Returns:
        格式化的诊断报告（多行文本）
    """
    lines: list[str] = []

    # ── 标题 ───────────────────────────────────────────────────────────────────
    lines.append(t("diagnose.header"))
    lines.append("━" * 28)
    lines.append("")

    # ── 前置检查 ───────────────────────────────────────────────────────────────
    if not probe.has_shortterm:
        lines.append(t("diagnose.no_shortterm"))
        return "\n".join(lines)

    # ── 读取短期记忆 ───────────────────────────────────────────────────────────
    st_result = read_shortterm(probe)
    if isinstance(st_result, ShortTermReadError):
        lines.append(t("diagnose.read_error", msg=st_result.message))
        return "\n".join(lines)

    store: ShortTermStore = st_result

    # ── B2 分类 + 排序 ─────────────────────────────────────────────────────────
    classified: list[tuple[ShortTermEntry, str, str]] = []
    for entry in store.entries:
        cat, sub = classify_false_positive(entry)
        classified.append((entry, cat, sub))

    # 只对非正常条目排序展示；正常条目不在列表中
    suspect = [(e, c, s) for e, c, s in classified if c != ""]
    suspect.sort(key=_sort_key)

    # 按 category 分组统计
    hflq  = [(e, c, s) for e, c, s in suspect if c == "high_freq_low_quality"]
    sv    = [(e, c, s) for e, c, s in suspect if c == "semantic_void"]
    ambig = [(e, c, s) for e, c, s in suspect if c == "ambiguous"]

    # ── 聚合统计 ───────────────────────────────────────────────────────────────
    fp_stats = compute_false_positive_stats(store)

    # ── 各分类详情（top_n > 0 时才展示）──────────────────────────────────────
    shown = 0
    if top_n > 0:
        shown = _render_category_section(
            lines=lines,
            entries=hflq,
            section_key="diagnose.high_freq_section",
            top_n=top_n,
            already_shown=shown,
        )
        shown = _render_category_section(
            lines=lines,
            entries=sv,
            section_key="diagnose.semantic_void_section",
            top_n=top_n,
            already_shown=shown,
        )
        shown = _render_category_section(
            lines=lines,
            entries=ambig,
            section_key="diagnose.ambiguous_section",
            top_n=top_n,
            already_shown=shown,
        )

        if shown == 0:
            lines.append(t("diagnose.all_healthy"))
            lines.append("")
    else:
        # top_n=0：只展示各分类条目数，不展示详情
        if hflq:
            lines.append(t("diagnose.high_freq_section", n=len(hflq)))
        if sv:
            lines.append(t("diagnose.semantic_void_section", n=len(sv)))
        if ambig:
            lines.append(t("diagnose.ambiguous_section", n=len(ambig)))
        if not (hflq or sv or ambig):
            lines.append(t("diagnose.all_healthy"))
        lines.append("")
        lines.append(t("diagnose.stats_only_hint"))
        lines.append("")

    # ── 健康分 + 配置建议 ──────────────────────────────────────────────────────
    score = fp_stats.retrieval_health_score
    total = fp_stats.total

    def _pct(n: int) -> str:
        return f"{n / total * 100:.1f}" if total > 0 else "0.0"

    if score < 70:
        lines.append(t(
            "diagnose.health_score",
            score=score,
            hflq_pct=_pct(fp_stats.high_freq_low_quality_count),
            sv_pct=_pct(fp_stats.semantic_void_count),
        ))
        lines.append("")
        lines.append(t("diagnose.config_advice_header"))
        lines.append(t("diagnose.config_minscore"))
        lines.append(t("diagnose.config_embedding"))
        lines.append(t("diagnose.config_mmr"))
    else:
        lines.append(t("diagnose.health_score_ok", score=score))

    # 去掉末尾多余空行
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


# ── 辅助：渲染单个分类的条目列表 ─────────────────────────────────────────────

def _render_category_section(
    lines: list[str],
    entries: list[tuple[ShortTermEntry, str, str]],
    section_key: str,
    top_n: int,
    already_shown: int,
) -> int:
    """
    渲染一个分类的条目列表，最多展示到 top_n 条（跨分类共享上限）。

    Returns:
        更新后的 already_shown 计数
    """
    if not entries:
        return already_shown

    lines.append(t(section_key, n=len(entries)))

    remaining = top_n - already_shown
    to_show = entries[:remaining]
    rank_start = already_shown + 1

    for rank, (entry, cat, sub) in enumerate(to_show, start=rank_start):
        avg = compute_avg_score(entry)
        tags_str = ", ".join(f'"{tag}"' for tag in entry.concept_tags[:5])
        if len(entry.concept_tags) > 5:
            tags_str += ", ..."

        lines.append(t(
            "diagnose.entry_line",
            rank=rank,
            source=entry.path,
            start=entry.start_line,
            end=entry.end_line,
        ))
        lines.append(t(
            "diagnose.entry_stats",
            recalls=entry.recall_count,
            avg=f"{avg:.3f}",
            max_score=f"{entry.max_score:.3f}",
            tags=tags_str,
        ))

        # 原因说明
        if cat == "high_freq_low_quality":
            if sub == "never_truly_relevant":
                lines.append(t("diagnose.reason_never_relevant"))
            else:
                lines.append(t("diagnose.reason_occasional_hit"))
        elif cat == "semantic_void":
            lines.append(t("diagnose.reason_semantic_void"))
        elif cat == "ambiguous":
            lines.append(t("diagnose.reason_ambiguous"))

    shown_now = already_shown + len(to_show)

    # 截断提示：该分类有更多条目但已达到 top_n
    if len(entries) > len(to_show) and shown_now >= top_n:
        lines.append(t(
            "diagnose.truncated",
            shown=len(to_show),
            total=len(entries),
        ))

    lines.append("")
    return shown_now

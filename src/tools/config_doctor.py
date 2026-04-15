from __future__ import annotations
"""
config_doctor.py · memory_config_doctor_oc 工具的核心逻辑

纯只读，基于短期记忆的行为数据推断 OpenClaw 配置问题。
不直接读取 OpenClaw 配置文件（规避路径不确定风险）。

四条推断（按优先级排列）：
  D1  FTS 降级模式      avg均值 < 0.45 AND 空标签占比 > 40%
  D2  minScore 过低     高频低质条目占比 > 15%
  D3  MMR 未开启        同一文件内存在大量行号重叠的条目对
  D4  embedding 质量不足 avg均值 ∈ [0.40, 0.55) AND 高分条目占比 < 10%

优先级规则：D1 命中时跳过 D4（FTS 降级已说明无 embedding，D4 不再有意义）

输出：
  - 每条推断的信号描述 + 具体建议
  - 触发任何推断时，附上可直接粘贴的 JSON5 配置片段
  - 全部健康时：简洁的 all-good 提示
"""

from dataclasses import dataclass, field
from typing import Optional

from src.probe import ProbeResult
from src.readers.shortterm_reader import (
    ShortTermEntry,
    ShortTermReadError,
    ShortTermStore,
    read_shortterm,
)
from src.analyzers.false_positive import compute_avg_score, compute_false_positive_stats
from src.session_store import save_config_snapshot
from i18n import t


# ── 阈值常量 ───────────────────────────────────────────────────────────────────

# D1：FTS 降级
FTS_AVG_THRESHOLD    = 0.45
FTS_EMPTY_TAG_RATIO  = 0.40

# D2：minScore 过低
HFLQ_RATIO_THRESHOLD = 0.15   # 高频低质占比 > 15%

# D3：MMR
MMR_MIN_OVERLAP_PAIRS = 3     # 同一文件至少 N 对重叠才触发

# D4：embedding 质量
EMB_AVG_LOW   = 0.40
EMB_AVG_HIGH  = 0.55
EMB_HIGH_SCORE_THRESHOLD = 0.70   # avgScore > 0.70 视为"高分"
EMB_HIGH_SCORE_MIN_RATIO = 0.10  # 高分条目占比 < 10% 才触发


# ── 推断结果 ───────────────────────────────────────────────────────────────────

@dataclass
class DiagnosisResult:
    """单条推断结果。"""
    code: str             # "fts" / "minscore" / "mmr" / "embedding"
    triggered: bool
    signal_data: dict = field(default_factory=dict)   # 供格式化使用的信号数据


# ── 各推断函数 ────────────────────────────────────────────────────────────────

def _diagnose_fts(entries: list[ShortTermEntry]) -> DiagnosisResult:
    """D1：FTS 降级模式推断。"""
    if not entries:
        return DiagnosisResult(code="fts", triggered=False)

    avg_scores = [compute_avg_score(e) for e in entries]
    mean_avg = sum(avg_scores) / len(avg_scores)
    empty_tag_count = sum(1 for e in entries if len(e.concept_tags) == 0)
    empty_ratio = empty_tag_count / len(entries)

    triggered = mean_avg < FTS_AVG_THRESHOLD and empty_ratio > FTS_EMPTY_TAG_RATIO
    return DiagnosisResult(
        code="fts",
        triggered=triggered,
        signal_data={"avg": mean_avg, "empty_pct": empty_ratio * 100},
    )


def _diagnose_minscore(entries: list[ShortTermEntry], fp_stats) -> DiagnosisResult:
    """D2：minScore 可能过低。"""
    if not entries:
        return DiagnosisResult(code="minscore", triggered=False)

    hflq_ratio = fp_stats.high_freq_low_quality_count / len(entries)
    triggered = hflq_ratio > HFLQ_RATIO_THRESHOLD
    return DiagnosisResult(
        code="minscore",
        triggered=triggered,
        signal_data={"pct": hflq_ratio * 100},
    )


def _diagnose_mmr(entries: list[ShortTermEntry]) -> DiagnosisResult:
    """D3：MMR 可能未开启（同一文件大量行号重叠条目对）。"""
    if not entries:
        return DiagnosisResult(code="mmr", triggered=False)

    # 按 source_path 分组，统计每个文件内的重叠对数
    from collections import defaultdict
    by_path: dict[str, list[ShortTermEntry]] = defaultdict(list)
    for e in entries:
        by_path[e.path].append(e)

    total_overlap_pairs = 0
    for path_entries in by_path.values():
        if len(path_entries) < 2:
            continue
        # O(n²) 检查重叠，实际 MEMORY.md 条目数有限，可接受
        for i in range(len(path_entries)):
            for j in range(i + 1, len(path_entries)):
                a, b = path_entries[i], path_entries[j]
                overlap_start = max(a.start_line, b.start_line)
                overlap_end   = min(a.end_line, b.end_line)
                if overlap_start <= overlap_end:
                    total_overlap_pairs += 1

    triggered = total_overlap_pairs >= MMR_MIN_OVERLAP_PAIRS
    return DiagnosisResult(
        code="mmr",
        triggered=triggered,
        signal_data={"pairs": total_overlap_pairs},
    )


def _diagnose_embedding(entries: list[ShortTermEntry]) -> DiagnosisResult:
    """D4：embedding 质量可能不足（avg 均值在中低区间，无高分聚集）。"""
    if not entries:
        return DiagnosisResult(code="embedding", triggered=False)

    avg_scores = [compute_avg_score(e) for e in entries]
    mean_avg = sum(avg_scores) / len(avg_scores)

    high_score_count = sum(1 for a in avg_scores if a > EMB_HIGH_SCORE_THRESHOLD)
    high_score_ratio = high_score_count / len(entries)

    triggered = (
        EMB_AVG_LOW <= mean_avg < EMB_AVG_HIGH
        and high_score_ratio < EMB_HIGH_SCORE_MIN_RATIO
    )
    return DiagnosisResult(
        code="embedding",
        triggered=triggered,
        signal_data={"avg": mean_avg, "high_pct": high_score_ratio * 100},
    )


# ── JSON5 配置片段构建 ────────────────────────────────────────────────────────

def _build_config_snippet(
    suggest_embedding: bool,
    suggest_minscore: bool,
    suggest_mmr: bool,
) -> str:
    """根据触发的推断，构建建议的 JSON5 配置片段。"""
    inner_lines = []

    if suggest_embedding:
        inner_lines.append('        provider: "voyage",')
        inner_lines.append('        model: "voyage-code-3",')

    query_lines = []
    if suggest_minscore:
        query_lines.append('          minScore: 0.50,')

    if suggest_mmr:
        query_lines.append('          hybrid: {')
        query_lines.append('            mmr: {')
        query_lines.append('              enabled: true,')
        query_lines.append('              lambda: 0.7')
        query_lines.append('            }')
        query_lines.append('          }')

    if query_lines:
        inner_lines.append('        query: {')
        inner_lines.extend(query_lines)
        inner_lines.append('        }')

    if not inner_lines:
        return ""

    lines = [
        "// 建议的 openclaw 配置修改",
        "// 文件位置：~/.openclaw/openclaw.json（JSON5 格式，支持注释）",
        "{",
        "  agents: {",
        "    defaults: {",
        "      memorySearch: {",
    ] + inner_lines + [
        "      }",
        "    }",
        "  }",
        "}",
    ]
    return "\n".join(lines)


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run_config_doctor(probe: ProbeResult, db_path=None) -> str:
    """
    执行配置诊断，返回格式化文本。

    Args:
        probe   : probe_workspace() 的返回值
        db_path : 测试用，覆盖默认 SQLite 路径

    Returns:
        格式化的配置诊断报告
    """
    lines: list[str] = []
    lines.append(t("doctor.header"))
    lines.append("━" * 26)
    lines.append("")

    # 前置检查
    if not probe.has_shortterm:
        lines.append(t("doctor.no_shortterm"))
        return "\n".join(lines)

    st_result = read_shortterm(probe)
    if isinstance(st_result, ShortTermReadError):
        lines.append(f"❌ {st_result.message}")
        return "\n".join(lines)

    store: ShortTermStore = st_result
    entries = store.entries

    if not entries:
        lines.append(t("doctor.all_good"))
        return "\n".join(lines)

    # 运行各推断
    fp_stats = compute_false_positive_stats(store)

    d1_fts       = _diagnose_fts(entries)
    d2_minscore  = _diagnose_minscore(entries, fp_stats)
    d3_mmr       = _diagnose_mmr(entries)
    # D4：D1 已命中时跳过（FTS 降级说明根本无 embedding，D4 无意义）
    d4_embedding = _diagnose_embedding(entries) if not d1_fts.triggered else DiagnosisResult("embedding", False)

    triggered = [d for d in [d1_fts, d2_minscore, d3_mmr, d4_embedding] if d.triggered]

    if not triggered:
        lines.append(t("doctor.all_good"))
        try:
            save_config_snapshot(
                workspace=probe.workspace_dir,
                payload={"all_good": True, "issues": []},
                db_path=db_path,
            )
        except Exception:
            pass
        return "\n".join(lines)

    lines.append(t("doctor.issues_found", n=len(triggered)))
    lines.append("")

    issue_num = 1
    suggest_embedding = False
    suggest_minscore  = False
    suggest_mmr       = False

    if d1_fts.triggered:
        lines.append(t("doctor.fts_title"))
        lines.append(t("doctor.fts_signal",
                       avg=d1_fts.signal_data["avg"],
                       empty_pct=d1_fts.signal_data["empty_pct"]))
        lines.append(t("doctor.fts_advice"))
        lines.append("")
        suggest_embedding = True
        issue_num += 1

    if d2_minscore.triggered:
        lines.append(t("doctor.minscore_title", n=issue_num))
        lines.append(t("doctor.minscore_signal", pct=d2_minscore.signal_data["pct"]))
        lines.append(t("doctor.minscore_advice"))
        lines.append("")
        suggest_minscore = True
        issue_num += 1

    if d3_mmr.triggered:
        lines.append(t("doctor.mmr_title", n=issue_num))
        lines.append(t("doctor.mmr_signal", pairs=d3_mmr.signal_data["pairs"]))
        lines.append(t("doctor.mmr_advice"))
        lines.append("")
        suggest_mmr = True
        issue_num += 1

    if d4_embedding.triggered:
        lines.append(t("doctor.embedding_title", n=issue_num))
        lines.append(t("doctor.embedding_signal",
                       avg=d4_embedding.signal_data["avg"],
                       high_pct=d4_embedding.signal_data["high_pct"]))
        lines.append(t("doctor.embedding_advice"))
        lines.append("")
        suggest_embedding = True
        issue_num += 1

    # JSON5 配置片段
    snippet = _build_config_snippet(suggest_embedding, suggest_minscore, suggest_mmr)
    if snippet:
        lines.append(t("doctor.config_snippet_header"))
        lines.append("")
        lines.append(snippet)

    # ── 存入 session_store（供 Dashboard 读取）──────────────────────────────
    try:
        issues_payload = [
            {
                "code":        d.code,
                "triggered":   d.triggered,
                "signal_data": d.signal_data,
            }
            for d in [d1_fts, d2_minscore, d3_mmr, d4_embedding]
            if d.triggered
        ]
        save_config_snapshot(
            workspace=probe.workspace_dir,
            payload={"all_good": False, "issues": issues_payload},
            db_path=db_path,
        )
    except Exception:
        pass  # 存储失败不影响主流程

    # 去掉末尾多余空行
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)

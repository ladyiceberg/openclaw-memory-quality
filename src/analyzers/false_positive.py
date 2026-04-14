from __future__ import annotations
"""
false_positive.py · B2 假阳性检测

短期记忆中的"假阳性"：被反复命中但实际上与查询无关的条目。
根源是 OpenClaw 默认 minScore=0.35 过低，FTS 字面命中混入向量命中池。

核心信号：avgScore（= totalScore / recallCount）+ maxScore
  - avgScore 反映每次命中的平均质量
  - maxScore 反映历史上最好的一次命中质量
  - 两者组合可区分"从未真正相关"和"偶尔相关但通常不是"

不用 queryHashes 多样性作为主信号（见产品规格文档 5.2 说明）。

分类结果（category, sub_reason）：
  "high_freq_low_quality" / "never_truly_relevant"  — avg<0.35 AND recalls>5 AND max<0.55
  "high_freq_low_quality" / "occasional_hit"        — avg<0.35 AND recalls>5 AND max>=0.55
  "semantic_void"         / ""                      — tags==[] AND recalls>5
  "ambiguous"             / ""                      — avg∈[0.35,0.55) AND max∈[0.55,0.75)
  ""                      / ""                      — 正常，不标记

设计原则：
  - 分类规则的优先级：高频低质 > 语义空洞 > 模糊区间
  - 阈值集中定义为常量，不在业务逻辑里硬编码
  - 聚合分（0-100）越高代表越健康（与直觉一致）
"""

from dataclasses import dataclass, field
from typing import Optional

from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore


# ── 阈值常量 ───────────────────────────────────────────────────────────────────

# 清晰假阳性阈值（规则直接判定，不触发 LLM）
CLEAR_FP_AVG_THRESHOLD: float = 0.35      # avg 低于此值为低质
CLEAR_FP_MAX_THRESHOLD: float = 0.55      # max 低于此值为"从未真正相关"

# 模糊区间（Phase 3 可选 LLM 复核）
AMBIGUOUS_AVG_LOW: float = 0.35
AMBIGUOUS_AVG_HIGH: float = 0.55
AMBIGUOUS_MAX_LOW: float = 0.55
AMBIGUOUS_MAX_HIGH: float = 0.75

# 高频阈值（recalls 需 > 此值才算"高频"）
HIGH_FREQ_MIN_RECALLS: int = 5            # recalls > 5，即至少 6 次

# FTS 降级推断阈值（启发式）
FTS_SAMPLE_SIZE: int = 20
FTS_AVG_THRESHOLD: float = 0.45
FTS_EMPTY_TAGS_RATIO: float = 0.40


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def compute_avg_score(entry: ShortTermEntry) -> float:
    """计算平均命中分（totalScore / recallCount），召回 0 次返回 0.0。"""
    if entry.recall_count == 0:
        return 0.0
    return entry.total_score / entry.recall_count


# ── 单条分类 ───────────────────────────────────────────────────────────────────

def classify_false_positive(entry: ShortTermEntry) -> tuple[str, str]:
    """
    对单条短期记忆进行假阳性分类。

    Returns:
        (category, sub_reason)
        category 为空字符串 "" 表示正常条目

    优先级（从高到低）：
        1. high_freq_low_quality（最确定的假阳性）
        2. semantic_void（次确定）
        3. ambiguous（模糊区间）
        4. "" 正常
    """
    avg = compute_avg_score(entry)
    high_freq = entry.recall_count > HIGH_FREQ_MIN_RECALLS

    # 优先级 1：高频低质（清晰假阳性）
    if avg < CLEAR_FP_AVG_THRESHOLD and high_freq:
        if entry.max_score < CLEAR_FP_MAX_THRESHOLD:
            # max 也低：从未有过一次真正高质量的命中
            return "high_freq_low_quality", "never_truly_relevant"
        else:
            # max 达标：偶尔相关，但通常不是目标内容
            return "high_freq_low_quality", "occasional_hit"

    # 优先级 2：语义空洞高频（无概念标签 + 高频 = 可能是 FTS 字面命中）
    if len(entry.concept_tags) == 0 and high_freq:
        return "semantic_void", ""

    # 优先级 3：模糊区间（avg 中等偏低 + max 中等偏低）
    avg_in_ambiguous = AMBIGUOUS_AVG_LOW <= avg < AMBIGUOUS_AVG_HIGH
    max_in_ambiguous = AMBIGUOUS_MAX_LOW <= entry.max_score < AMBIGUOUS_MAX_HIGH
    if avg_in_ambiguous and max_in_ambiguous:
        return "ambiguous", ""

    # 正常
    return "", ""


# ── 聚合统计 ───────────────────────────────────────────────────────────────────

@dataclass
class FalsePositiveStats:
    """
    B2 聚合统计结果，供 health_check / retrieval_diagnose 工具使用。
    """
    total: int
    high_freq_low_quality_count: int    # 清晰假阳性条目数
    semantic_void_count: int            # 语义空洞高频条目数
    ambiguous_count: int                # 模糊区间条目数
    suspect_count: int                  # 可疑总数（high_freq + semantic_void）
    suspect_ratio: float                # 可疑占比（0.0-1.0）

    # 三个诊断分（0-100，越高越健康）
    retrieval_health_score: int         # 检索健康分
    promotion_risk_score: int           # 晋升风险分（越高=风险越大，与其他分反向）
    fts_degradation_suspected: bool     # 是否推断处于 FTS 降级模式


def compute_false_positive_stats(store: ShortTermStore) -> FalsePositiveStats:
    """
    对整个 ShortTermStore 执行 B2 统计，并计算三个聚合诊断分。

    Args:
        store: 短期记忆全量数据

    Returns:
        FalsePositiveStats
    """
    total = len(store.entries)
    if total == 0:
        return FalsePositiveStats(
            total=0,
            high_freq_low_quality_count=0,
            semantic_void_count=0,
            ambiguous_count=0,
            suspect_count=0,
            suspect_ratio=0.0,
            retrieval_health_score=100,
            promotion_risk_score=0,
            fts_degradation_suspected=False,
        )

    high_freq_lq = 0
    semantic_void = 0
    ambiguous = 0

    for entry in store.entries:
        cat, _ = classify_false_positive(entry)
        if cat == "high_freq_low_quality":
            high_freq_lq += 1
        elif cat == "semantic_void":
            semantic_void += 1
        elif cat == "ambiguous":
            ambiguous += 1

    suspect_count = high_freq_lq + semantic_void
    suspect_ratio = suspect_count / total

    # ── Retrieval Health Score（0-100，越高越好）──────────────────────────────
    # 公式来自产品规格文档 5.2：
    #   base=100
    #   - (高频低质 / 总) × 40
    #   - (语义空洞 / 总) × 30
    #   - FTS 降级惩罚 × 30
    fts_suspected = _detect_fts_degradation(store.entries)
    fts_penalty = 30 if fts_suspected else 0

    raw_score = (
        100
        - (high_freq_lq / total) * 40
        - (semantic_void / total) * 30
        - fts_penalty
    )
    retrieval_health = max(0, min(100, round(raw_score)))

    # ── Promotion Risk Score（0-100，越高=风险越大）────────────────────────────
    # 统计尚未晋升的条目（promotedAt is None）中，假阳性比例
    # 这代表"如果现在触发 Dreaming，这些低质量内容进入 MEMORY.md 的风险"
    unpromoted = [e for e in store.entries if e.promoted_at is None]
    if unpromoted:
        unpromoted_suspect = sum(
            1 for e in unpromoted
            if classify_false_positive(e)[0] in ("high_freq_low_quality", "semantic_void")
        )
        promotion_risk = round((unpromoted_suspect / len(unpromoted)) * 100)
    else:
        promotion_risk = 0

    return FalsePositiveStats(
        total=total,
        high_freq_low_quality_count=high_freq_lq,
        semantic_void_count=semantic_void,
        ambiguous_count=ambiguous,
        suspect_count=suspect_count,
        suspect_ratio=suspect_ratio,
        retrieval_health_score=retrieval_health,
        promotion_risk_score=promotion_risk,
        fts_degradation_suspected=fts_suspected,
    )


# ── FTS 降级推断（启发式）────────────────────────────────────────────────────

def _detect_fts_degradation(entries: list[ShortTermEntry]) -> bool:
    """
    启发式判断检索系统是否处于 FTS 降级模式。

    方法：从高 recallCount 条目中抽样，检查平均 avgScore 和空标签比例。
    两个条件同时满足才认为"可能降级"，单一条件不足以判断。
    """
    if not entries:
        return False

    # 取 recallCount 最高的 FTS_SAMPLE_SIZE 条（代表"最被频繁命中的"）
    high_recall = sorted(entries, key=lambda e: e.recall_count, reverse=True)
    sample = high_recall[:FTS_SAMPLE_SIZE]

    if not sample:
        return False

    # 条件 1：样本平均 avgScore < FTS_AVG_THRESHOLD
    avg_scores = [compute_avg_score(e) for e in sample]
    mean_avg = sum(avg_scores) / len(avg_scores)
    if mean_avg >= FTS_AVG_THRESHOLD:
        return False

    # 条件 2：样本中空标签条目占比 > FTS_EMPTY_TAGS_RATIO
    empty_tags_count = sum(1 for e in sample if len(e.concept_tags) == 0)
    empty_ratio = empty_tags_count / len(sample)
    if empty_ratio <= FTS_EMPTY_TAGS_RATIO:
        return False

    return True

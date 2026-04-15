from __future__ import annotations
"""
promotion_auditor.py · Layer 2 晋升前候选质量预检

对 short-term-recall.json 中未晋升的候选条目执行五道关卡审查：

关卡 1：来源文件存在性
  source 文件不存在 → skip: source_deleted

关卡 2：内容有效性（低价值内容）
  片段只有 import 语句   → skip: import_only
  片段只有注释行         → skip: comments_only
  片段只有空行/括号      → skip: boilerplate
  片段含调试输出代码     → skip: debug_code

关卡 3：与 MEMORY.md 重复
  (source_path, startLine, endLine) 已在 MEMORY.md 中存在 → skip: already_promoted

关卡 4：假阳性信号
  avg < 0.45 AND maxScore < 0.65 → flag: potential_false_positive
  （建议人工确认，不直接跳过）

关卡 5（可选，use_llm=True）：LLM 长期价值 advisory
  → 见 llm_promotion_evaluator.py

设计原则：
  - 纯函数：不做 IO，不读写文件，所有依赖由调用方注入
  - 关卡 1-3 为 skip（一旦触发不再检查后续关卡）
  - 关卡 4 为 flag（advisory，不影响晋升流程）
  - 评分为近似值（跳过 consolidation 分量，占原始权重 10%）
"""

import math
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from src.readers.shortterm_reader import ShortTermEntry, ShortTermStore, days_since_iso
from src.readers.longterm_reader import LongTermStore


# ── 常量 ──────────────────────────────────────────────────────────────────────

# 六维评分权重（跳过 consolidation=0.10，归一化到 0.90）
_W_FREQUENCY  = 0.24
_W_RELEVANCE  = 0.30
_W_DIVERSITY  = 0.15
_W_RECENCY    = 0.15
_W_CONCEPTUAL = 0.06
_W_TOTAL_USED = _W_FREQUENCY + _W_RELEVANCE + _W_DIVERSITY + _W_RECENCY + _W_CONCEPTUAL

# 新鲜度半衰期（天）
_RECENCY_HALF_LIFE_DAYS = 14

# 多样性归一化分母
_DIVERSITY_NORM = 5

# 概念丰富度归一化分母
_CONCEPTUAL_NORM = 6

# 关卡 4 假阳性阈值
_FP_AVG_THRESHOLD = 0.45
_FP_MAX_THRESHOLD = 0.65


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class PromotionScore:
    """候选条目的估算晋升评分（各维度分量 + 综合分）。"""
    composite:  float    # 综合分（归一化后，近似值）
    frequency:  float    # 频率分量
    relevance:  float    # 相关性分量（avgScore）
    diversity:  float    # 多样性分量
    recency:    float    # 新鲜度分量
    conceptual: float    # 概念丰富度分量
    avg_score:  float    # 平均分（totalScore / recallCount），供关卡 4 使用


@dataclass
class PromotionCandidate:
    """经过审查的单条晋升候选。"""
    entry:       ShortTermEntry
    score:       PromotionScore
    verdict:     str             # "pass" / "skip" / "flag"
    skip_reason: Optional[str] = None   # 关卡 1-3：skip 的原因
    flag_reason: Optional[str] = None   # 关卡 4：flag 的原因


@dataclass
class PromotionAuditResult:
    """promotion_auditor 的完整输出。"""
    candidates:          list[PromotionCandidate]   # top_n 候选（含审查结果）
    total_unpromotted:   int     # 过滤 top_n 前的未晋升条目总数
    top_n:               int     # 本次审查的 top_n 参数

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.candidates if c.verdict == "pass")

    @property
    def skip_count(self) -> int:
        return sum(1 for c in self.candidates if c.verdict == "skip")

    @property
    def flag_count(self) -> int:
        return sum(1 for c in self.candidates if c.verdict == "flag")


# ── 评分计算 ──────────────────────────────────────────────────────────────────

def estimate_promotion_score(
    entry: ShortTermEntry,
    now_ms: Optional[int] = None,
) -> PromotionScore:
    """
    估算 OpenClaw 六维评分（近似值，跳过 consolidation 分量）。

    Args:
        entry:  ShortTermEntry
        now_ms: 当前时间戳（毫秒），None 时使用系统时间。供测试注入。

    Returns:
        PromotionScore，composite 为归一化综合分。
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    # 平均分：totalScore / recallCount
    avg_score = (
        entry.total_score / entry.recall_count
        if entry.recall_count > 0
        else 0.0
    )

    # 频率分量：log(recallCount + 1) / log(11)
    frequency = math.log(entry.recall_count + 1) / math.log(11)

    # 相关性分量：avgScore
    relevance = avg_score

    # 多样性分量：min(1.0, uniqueQueries / 5)
    diversity = min(1.0, len(entry.query_hashes) / _DIVERSITY_NORM)

    # 新鲜度分量：指数衰减，半衰期 14 天
    try:
        age_days = days_since_iso(entry.last_recalled_at, now_ms)
    except Exception:
        age_days = 0.0
    lam = math.log(2) / _RECENCY_HALF_LIFE_DAYS
    recency = math.exp(-lam * age_days)

    # 概念丰富度分量：min(1.0, len(conceptTags) / 6)
    conceptual = min(1.0, len(entry.concept_tags) / _CONCEPTUAL_NORM)

    # 综合分（归一化，跳过 consolidation 0.10 权重）
    raw = (
        _W_FREQUENCY  * frequency
        + _W_RELEVANCE  * relevance
        + _W_DIVERSITY  * diversity
        + _W_RECENCY    * recency
        + _W_CONCEPTUAL * conceptual
    )
    composite = raw / _W_TOTAL_USED

    return PromotionScore(
        composite=composite,
        frequency=frequency,
        relevance=relevance,
        diversity=diversity,
        recency=recency,
        conceptual=conceptual,
        avg_score=avg_score,
    )


# ── 关卡实现 ──────────────────────────────────────────────────────────────────

def check_gate1_source(
    entry: ShortTermEntry,
    workspace_dir: str,
) -> Optional[str]:
    """
    关卡 1：来源文件存在性。
    返回 skip_reason 或 None（通过）。
    """
    from pathlib import Path
    source_path = Path(workspace_dir) / entry.path
    if not source_path.exists():
        return "source_deleted"
    return None


# 关卡 2 辅助正则
_IMPORT_RE    = re.compile(r"^(import\s|from\s+\S+\s+import\s)", re.IGNORECASE)
_COMMENT_RE   = re.compile(r"^(#|//|/\*|\*\s|\*$|<!--)")
_DEBUG_RE     = re.compile(
    r"\bconsole\.(log|warn|error|debug|info)\s*\("
    r"|\bprint\s*\("
    r"|\bdebugger\b"
    r"|\bpdb\.set_trace\b"
    r"|\bbreakpoint\s*\(",
    re.IGNORECASE,
)
# boilerplate：仅含括号/空白/分号
_BOILERPLATE_RE = re.compile(r"^[\s\{\}\[\]\(\);,]*$")


def check_gate2_content(entry: ShortTermEntry) -> Optional[str]:
    """
    关卡 2：内容有效性（低价值内容检测）。

    snippet 已被 OpenClaw normalizeSnippet() 处理为单行，
    用空格分隔了原始多行内容。这里对 snippet 的各"伪行"进行判断。

    返回 skip_reason 或 None（通过）。
    """
    snippet = entry.snippet.strip()
    if not snippet:
        return "boilerplate"

    # 调试代码优先检测（无论其他内容）
    if _DEBUG_RE.search(snippet):
        return "debug_code"

    # boilerplate：去掉空格后全是括号/分号/逗号
    if _BOILERPLATE_RE.match(snippet):
        return "boilerplate"

    # 把 snippet 按空格分割成伪 token 组，粗略判断每个"语句片段"
    # 策略：取前 N 个非空 token 判断主体性质
    # 先尝试按常见语句分隔符分割（JS/Python import 等通常在行首）
    # 由于 normalizeSnippet 把换行变成空格，多行内容已被压平
    # 这里用简单的前缀判断：如果 snippet 整体以 import/from 开头
    first_token = snippet.split()[0] if snippet.split() else ""

    # import_only：整条 snippet 全是 import 语句
    # 判断方式：snippet 匹配 import/from ... import ...（宽松匹配）
    # 只有单 import 语句或整条内容都是 import 时才标记
    if _IMPORT_RE.match(snippet):
        # 进一步验证：没有其他实质性内容（函数/变量定义等）
        non_import_indicators = re.search(
            r"\b(def |class |function |const |let |var |return |if |for |while )\b",
            snippet,
        )
        if not non_import_indicators:
            return "import_only"

    # comments_only：以注释符号开头，且没有实质性代码
    if _COMMENT_RE.match(snippet):
        # 去掉各种注释符号
        stripped = re.sub(r"^(//|/\*|\*/|#)\s*", "", snippet).strip()
        # 去掉行内 HTML 注释
        stripped = re.sub(r"<!--.*?-->", "", stripped).strip()
        # 如果剩余内容没有任何代码特征（括号、等号、分号、def/function等），认为是纯注释
        has_code = bool(re.search(r"[=\(\);{}]|\bdef \b|\bfunction \b|\bclass \b|\breturn \b", stripped))
        if not has_code:
            return "comments_only"

    return None


def check_gate3_duplicate(
    entry: ShortTermEntry,
    promoted_set: frozenset,
) -> Optional[str]:
    """
    关卡 3：与 MEMORY.md 重复。

    promoted_set: frozenset of (source_path, start_line, end_line) tuples。
    返回 skip_reason 或 None（通过）。
    """
    key = (entry.path, entry.start_line, entry.end_line)
    if key in promoted_set:
        return "already_promoted"
    return None


def check_gate4_false_positive(
    entry: ShortTermEntry,
    avg_score: float,
) -> Optional[str]:
    """
    关卡 4：假阳性信号（flag，不是 skip）。

    条件：avg < 0.45 AND maxScore < 0.65
    返回 flag_reason 或 None（通过）。
    """
    if avg_score < _FP_AVG_THRESHOLD and entry.max_score < _FP_MAX_THRESHOLD:
        return "potential_false_positive"
    return None


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def build_promoted_set(lt_store: Optional[LongTermStore]) -> frozenset:
    """
    从 LongTermStore 提取已晋升条目的 (path, start, end) 集合。
    lt_store 为 None 时返回空集合（MEMORY.md 不存在时跳过关卡 3）。
    """
    if lt_store is None:
        return frozenset()
    result = set()
    for section in lt_store.sections:
        for item in section.items:
            result.add((item.source_path, item.source_start, item.source_end))
    return frozenset(result)


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run_promotion_audit(
    store: ShortTermStore,
    workspace_dir: str,
    lt_store: Optional[LongTermStore] = None,
    top_n: int = 10,
    now_ms: Optional[int] = None,
) -> PromotionAuditResult:
    """
    对短期记忆候选池执行晋升前质量预检。

    Args:
        store:         ShortTermStore（短期记忆全量）
        workspace_dir: workspace 根目录路径（关卡 1 文件存在性检查用）
        lt_store:      LongTermStore（可选，None 时跳过关卡 3）
        top_n:         审查评分最高的前 N 条候选
        now_ms:        当前时间戳（毫秒），None 时使用系统时间（供测试注入）

    Returns:
        PromotionAuditResult
    """
    # 1. 过滤：只看未晋升的条目
    unpromotted = [e for e in store.entries if e.promoted_at is None]
    total_unpromotted = len(unpromotted)

    # 2. 评分 + 排序
    scored: list[tuple[ShortTermEntry, PromotionScore]] = []
    for entry in unpromotted:
        score = estimate_promotion_score(entry, now_ms=now_ms)
        scored.append((entry, score))
    scored.sort(key=lambda x: x[1].composite, reverse=True)

    # 3. 取前 top_n
    top = scored[:top_n]

    # 4. 构建已晋升集合（关卡 3 用）
    promoted_set = build_promoted_set(lt_store)

    # 5. 对每个候选执行关卡 1-4
    candidates: list[PromotionCandidate] = []
    for entry, score in top:
        verdict = "pass"
        skip_reason = None
        flag_reason = None

        # 关卡 1
        reason = check_gate1_source(entry, workspace_dir)
        if reason:
            verdict = "skip"
            skip_reason = reason
        else:
            # 关卡 2
            reason = check_gate2_content(entry)
            if reason:
                verdict = "skip"
                skip_reason = reason
            else:
                # 关卡 3
                reason = check_gate3_duplicate(entry, promoted_set)
                if reason:
                    verdict = "skip"
                    skip_reason = reason
                else:
                    # 关卡 4（flag，不是 skip）
                    reason = check_gate4_false_positive(entry, score.avg_score)
                    if reason:
                        verdict = "flag"
                        flag_reason = reason

        candidates.append(PromotionCandidate(
            entry=entry,
            score=score,
            verdict=verdict,
            skip_reason=skip_reason,
            flag_reason=flag_reason,
        ))

    return PromotionAuditResult(
        candidates=candidates,
        total_unpromotted=total_unpromotted,
        top_n=top_n,
    )

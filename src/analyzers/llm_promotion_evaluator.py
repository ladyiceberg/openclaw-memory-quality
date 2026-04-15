from __future__ import annotations
"""
llm_promotion_evaluator.py · Layer 2 关卡 5 — LLM 长期价值 advisory

对晋升候选执行 LLM 语义评估，判断条目的长期保留价值。

输出三类判断（advisory，不是 veto）：
  long_term_knowledge  → 抽象经验 / 稳定设计事实，适合长期保留
  one_time_context     → 偶发片段 / 一次性上下文，晋升价值存疑
  uncertain            → 上下文不足，无法判断

设计原则：
  - 只对 pass 和 flag 条目执行（skip 条目已有明确结论，不浪费 API）
  - 纯函数：不做 IO，所有依赖由调用方注入
  - LLM 调用失败 → 返回 uncertain，不抛异常
  - advisory 不改变关卡 1-4 的 verdict，用户自行决定
"""

from dataclasses import dataclass, field
from typing import Optional

from src.analyzers.promotion_auditor import PromotionCandidate


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class LongTermValueAdvisory:
    """单条候选的 LLM 长期价值评估结果。"""
    entry_key:  str     # ShortTermEntry.key
    verdict:    str     # "long_term_knowledge" / "one_time_context" / "uncertain"
    reason:     str     # LLM 给出的理由（< 80 字）


@dataclass
class LLMPromotionEvalResult:
    """关卡 5 的完整输出。"""
    advisories: dict[str, LongTermValueAdvisory] = field(default_factory=dict)
    # key: entry.key → advisory

    @property
    def long_term_count(self) -> int:
        return sum(1 for a in self.advisories.values()
                   if a.verdict == "long_term_knowledge")

    @property
    def one_time_count(self) -> int:
        return sum(1 for a in self.advisories.values()
                   if a.verdict == "one_time_context")

    @property
    def uncertain_count(self) -> int:
        return sum(1 for a in self.advisories.values()
                   if a.verdict == "uncertain")


# ── Prompt 模板 ────────────────────────────────────────────────────────────────

_SYSTEM = """\
你是 AI Agent 记忆系统的质量审查专家。你的任务是评估一条代码/文本片段是否值得长期保留在 Agent 的长期记忆（MEMORY.md）中。

判断标准：
- long_term_knowledge（适合长期保留）：
  抽象经验、稳定的设计决策、跨项目通用的知识、不会快速过时的事实
  示例："Gateway 绑定 loopback 地址和 18789 端口"
  示例："数据库连接池默认大小为 10，超过会触发排队"

- one_time_context（晋升价值存疑）：
  一次性的上下文、临时变量/调试痕迹、高度依赖特定时间点的内容
  示例："今天把旧认证代码迁移到了新模块"
  示例："本次会议决定先不处理 edge case"

- uncertain（上下文不足）：
  片段太短或太碎片化，无法判断价值

只做\"评估长期价值\"，不评判代码质量。
请严格按 JSON schema 输出。"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["long_term_knowledge", "one_time_context", "uncertain"]
        },
        "reason": {
            "type": "string",
            "description": "判断理由，中文，不超过 80 字"
        }
    },
    "required": ["verdict", "reason"]
}


# ── 核心函数 ───────────────────────────────────────────────────────────────────

def evaluate_long_term_value(
    candidate: PromotionCandidate,
    llm_client,
) -> LongTermValueAdvisory:
    """
    对单条候选执行 LLM 长期价值评估。
    LLM 调用失败时返回 uncertain，不抛异常。
    """
    entry = candidate.entry
    snippet = entry.snippet

    user_msg = (
        f"请判断以下代码/文本片段是否值得长期保留在 Agent 的记忆中：\n\n"
        f"片段内容：{snippet}\n"
        f"来源文件：{entry.path}（第 {entry.start_line}-{entry.end_line} 行）\n"
        f"召回次数：{entry.recall_count}，平均分：{candidate.score.avg_score:.2f}"
    )

    try:
        resp = llm_client.complete(
            system=_SYSTEM,
            user=user_msg,
            json_schema=_SCHEMA,
            max_tokens=200,
        )
        parsed = resp.parsed
        if not parsed or "verdict" not in parsed:
            return LongTermValueAdvisory(
                entry_key=entry.key,
                verdict="uncertain",
                reason="",
            )
        return LongTermValueAdvisory(
            entry_key=entry.key,
            verdict=parsed["verdict"],
            reason=parsed.get("reason", ""),
        )
    except Exception:
        return LongTermValueAdvisory(
            entry_key=entry.key,
            verdict="uncertain",
            reason="",
        )


def run_llm_promotion_evaluation(
    candidates: list[PromotionCandidate],
    llm_client,
) -> LLMPromotionEvalResult:
    """
    对候选列表中的 pass/flag 条目执行关卡 5 LLM 长期价值评估。
    skip 条目已有明确结论，跳过不处理。

    Args:
        candidates:  PromotionCandidate 列表（来自 run_promotion_audit）
        llm_client:  LLMClient 实例

    Returns:
        LLMPromotionEvalResult
    """
    result = LLMPromotionEvalResult()

    for cand in candidates:
        if cand.verdict == "skip":
            continue  # skip 条目不需要 LLM advisory

        advisory = evaluate_long_term_value(cand, llm_client)
        result.advisories[cand.entry.key] = advisory

    return result

from __future__ import annotations
"""
llm_longterm_evaluator.py · MEMORY.md 语义评估层（Phase 3）

对规则层标记为 review 的条目执行两类 LLM 判断：

任务 A：语义有效性复审
  输入：snippet（已 normalize 单行）+ 来源文件当前内容（±10 行上下文）
  输出：still_valid / outdated / uncertain
  升级逻辑：
    still_valid → action_hint 升级为 keep
    outdated    → action_hint 升级为 delete（加入 llm_reason）
    uncertain   → 维持 review

任务 B：语义去重建议
  输入：review 条目 + keep 条目的 snippet 列表（不超过 40 条）
  输出：潜在重复对列表（各含 merge_suggestion）
  注意：只输出建议，不改 action_hint

设计原则：
  - 纯函数：不做 IO，不读写文件，所有依赖由调用方注入
  - LLM 调用失败（网络/API 错误）→ 该条目保持原 action_hint，不抛异常
  - 每条 review 条目独立调用（任务 A），失败不影响其他条目
  - 任务 B 批量调用，一次失败整组跳过（记录警告）
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.analyzers.longterm_auditor import AuditedItem, normalize_snippet
from src.readers.longterm_reader import MemoryItem


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class SemanticValidity:
    """任务 A：单条 review 条目的语义有效性判断结果。"""
    verdict: str             # "still_valid" / "outdated" / "uncertain"
    reason: str              # LLM 给出的简短理由（中文，< 80 字）
    upgraded_action: str     # 升级后的 action_hint


@dataclass
class MergeSuggestion:
    """任务 B：一对潜在重复条目的合并建议。"""
    item_a_source: str       # "memory/2026-03-01.md:5-8"
    item_b_source: str       # "memory/2026-03-15.md:12-14"
    both_snippets: str       # 两条 snippet 的摘要（供格式化输出用）
    merge_suggestion: str    # LLM 建议的合并后表述（中文，< 120 字）


@dataclass
class LLMEvalResult:
    """LLM 评估层的完整结果。"""
    validity_results: dict[str, SemanticValidity] = field(default_factory=dict)
    # key = promotion_key 或 "source_path:start-end"
    merge_suggestions: list[MergeSuggestion] = field(default_factory=list)
    llm_error: Optional[str] = None      # 发生严重错误时记录


# ── Prompt 模板 ────────────────────────────────────────────────────────────────

_VALIDITY_SYSTEM = """\
你是一个专业的代码记忆审计助手。你的任务是判断一条 AI Agent 的长期记忆是否仍然适用。

判断标准：
- still_valid：记忆描述的结论/事实在当前代码中仍然成立（即使代码有细微变化）
- outdated：记忆描述的内容已经失效（相关代码被删除、重构、或功能被替换）
- uncertain：上下文信息不足以判断，无法确定

重要原则：
1. 你只判断"这条记忆说的事情，在当前代码里还成不成立"
2. 不要判断这条记忆重不重要——那是用户的决定
3. 不要因为代码有变化就判断 outdated——要看变化是否使记忆失效
4. 如果来源文件不存在（内容为空），判断 outdated

请严格按 JSON schema 输出。\
"""

_VALIDITY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["still_valid", "outdated", "uncertain"],
            "description": "判断结果"
        },
        "reason": {
            "type": "string",
            "description": "简短理由，中文，不超过 80 字"
        }
    },
    "required": ["verdict", "reason"]
}

_DEDUP_SYSTEM = """\
你是一个专业的代码记忆去重助手。你的任务是找出在语义上描述同一个设计事实的记忆条目对。

判断标准：
- 两条记忆来自不同来源（不同文件或不同行号）
- 但实质上描述的是同一个设计决策、架构事实、或行为模式
- 表述不同但内涵相同

注意：
- 只找真正重复的，不要为了凑数乱配对
- 如果没有重复，返回空数组
- 合并建议应该综合两条的精华，用中文表述

请严格按 JSON schema 输出。\
"""

_DEDUP_SCHEMA = {
    "type": "object",
    "properties": {
        "duplicates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index_a": {"type": "integer", "description": "第一条的索引（从0开始）"},
                    "index_b": {"type": "integer", "description": "第二条的索引（从0开始）"},
                    "merge_suggestion": {
                        "type": "string",
                        "description": "建议合并后的表述，中文，不超过 120 字"
                    }
                },
                "required": ["index_a", "index_b", "merge_suggestion"]
            }
        }
    },
    "required": ["duplicates"]
}


# ── 来源文件读取辅助 ───────────────────────────────────────────────────────────

def _read_source_context(
    workspace_dir: Path,
    source_path: str,
    source_start: int,
    source_end: int,
    context_lines: int = 10,
) -> str:
    """
    读取来源文件在指定行号范围（±context_lines）的内容。
    文件不存在或读取失败时返回空字符串。
    """
    abs_path = workspace_dir / source_path
    if not abs_path.exists():
        return ""

    try:
        lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    # 1-based → 0-based，扩展上下文
    start_idx = max(0, source_start - 1 - context_lines)
    end_idx   = min(len(lines), source_end + context_lines)

    excerpt = lines[start_idx:end_idx]
    # 标注目标行范围
    result_lines = []
    for i, line in enumerate(excerpt):
        lineno = start_idx + i + 1   # 1-based
        marker = ">>>" if source_start <= lineno <= source_end else "   "
        result_lines.append(f"{marker} {lineno:4d} | {line}")

    return "\n".join(result_lines)


# ── 任务 A：语义有效性复审 ────────────────────────────────────────────────────

def evaluate_validity_single(
    item: MemoryItem,
    workspace_dir: Path,
    llm_client,
) -> SemanticValidity:
    """
    对单条 review 条目执行语义有效性判断。

    LLM 调用失败时返回 uncertain（不抛异常），调用方继续处理下一条。
    """
    source_context = _read_source_context(
        workspace_dir, item.source_path, item.source_start, item.source_end
    )

    # 构造 user message
    user_msg = f"""## 记忆条目

**存储的记忆（snippet）：**
{item.snippet}

**来源文件：** {item.source_path}（第 {item.source_start}-{item.source_end} 行）
**晋升评分：** score={item.score:.3f}, recalls={item.recalls}, avg={item.avg_score:.3f}

## 来源文件当前内容（>>> 标注的是被记忆覆盖的原始行）

{source_context if source_context else "（文件不存在或无法读取）"}

## 请判断

这条记忆现在是否仍然适用？"""

    try:
        resp = llm_client.complete(
            system=_VALIDITY_SYSTEM,
            user=user_msg,
            json_schema=_VALIDITY_SCHEMA,
            max_tokens=256,
        )
        parsed = resp.parsed
        if not parsed or "verdict" not in parsed:
            return SemanticValidity(
                verdict="uncertain",
                reason="LLM 返回格式异常",
                upgraded_action="review",
            )

        verdict = parsed["verdict"]
        reason  = parsed.get("reason", "")

        # 升级 action_hint
        if verdict == "still_valid":
            upgraded = "keep"
        elif verdict == "outdated":
            upgraded = "delete"
        else:
            upgraded = "review"

        return SemanticValidity(verdict=verdict, reason=reason, upgraded_action=upgraded)

    except Exception as e:
        return SemanticValidity(
            verdict="uncertain",
            reason=f"LLM 调用失败：{type(e).__name__}",
            upgraded_action="review",
        )


# ── 任务 B：语义去重建议 ──────────────────────────────────────────────────────

def evaluate_duplicates_batch(
    review_items: list[AuditedItem],
    keep_items: list[AuditedItem],
    llm_client,
    max_items: int = 40,
) -> list[MergeSuggestion]:
    """
    对 review + keep 条目做跨条目语义去重扫描。

    只取前 max_items 条（控制 prompt 长度和 LLM 成本）。
    LLM 调用失败时返回空列表（不抛异常）。
    """
    # 合并候选列表，review 优先
    candidates = review_items + keep_items
    candidates = candidates[:max_items]

    if len(candidates) < 2:
        return []

    # 构造条目列表（供 LLM 扫描）
    entries_text = []
    for i, audited in enumerate(candidates):
        item = audited.item
        source_label = f"{item.source_path}:{item.source_start}-{item.source_end}"
        entries_text.append(
            f"[{i}] {source_label}\n    {item.snippet[:120]}"
        )

    user_msg = (
        "以下是从 MEMORY.md 中提取的记忆条目列表，"
        "请找出语义上描述同一设计事实的条目对：\n\n"
        + "\n\n".join(entries_text)
    )

    try:
        resp = llm_client.complete(
            system=_DEDUP_SYSTEM,
            user=user_msg,
            json_schema=_DEDUP_SCHEMA,
            max_tokens=1024,
        )
        parsed = resp.parsed
        if not parsed or "duplicates" not in parsed:
            return []

        results = []
        for dup in parsed["duplicates"]:
            idx_a = dup.get("index_a")
            idx_b = dup.get("index_b")
            suggestion = dup.get("merge_suggestion", "")

            # 边界检查
            if idx_a is None or idx_b is None:
                continue
            if not (0 <= idx_a < len(candidates) and 0 <= idx_b < len(candidates)):
                continue
            if idx_a == idx_b:
                continue

            item_a = candidates[idx_a].item
            item_b = candidates[idx_b].item

            results.append(MergeSuggestion(
                item_a_source=f"{item_a.source_path}:{item_a.source_start}-{item_a.source_end}",
                item_b_source=f"{item_b.source_path}:{item_b.source_start}-{item_b.source_end}",
                both_snippets=(
                    f"{item_a.snippet[:60]}…\n    {item_b.snippet[:60]}…"
                ),
                merge_suggestion=suggestion,
            ))

        return results

    except Exception:
        return []


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run_llm_evaluation(
    audit_items: list[AuditedItem],
    workspace_dir: Path,
    llm_client,
) -> LLMEvalResult:
    """
    对规则层审计结果执行完整的 LLM 语义评估。

    Args:
        audit_items   : run_audit() 返回的全量 AuditedItem 列表
        workspace_dir : workspace 根目录（读取来源文件用）
        llm_client    : LLMClient 实例

    Returns:
        LLMEvalResult
    """
    result = LLMEvalResult()

    review_items = [a for a in audit_items if a.action_hint == "review"]
    keep_items   = [a for a in audit_items if a.action_hint == "keep"]

    if not review_items:
        return result  # 无 review 条目，直接返回

    # ── 任务 A：逐条评估语义有效性 ────────────────────────────────────────────
    for audited in review_items:
        item = audited.item
        key = item.promotion_key or f"{item.source_path}:{item.source_start}-{item.source_end}"

        validity = evaluate_validity_single(item, workspace_dir, llm_client)
        result.validity_results[key] = validity

    # ── 任务 B：语义去重扫描 ────────────────────────────────────────────────
    merge_suggestions = evaluate_duplicates_batch(review_items, keep_items, llm_client)
    result.merge_suggestions = merge_suggestions

    return result


def apply_llm_results(
    audit_items: list[AuditedItem],
    eval_result: LLMEvalResult,
) -> list[AuditedItem]:
    """
    将 LLM 评估结果合并回 AuditedItem 列表，更新 action_hint。

    注意：只更新 action_hint 为 "review" 且有 LLM 判断的条目。
    原本是 keep/delete 的条目不受影响。

    Returns:
        更新后的 AuditedItem 列表（新列表，不改原对象）
    """
    from dataclasses import replace

    updated = []
    for audited in audit_items:
        if audited.action_hint != "review":
            updated.append(audited)
            continue

        item = audited.item
        key = item.promotion_key or f"{item.source_path}:{item.source_start}-{item.source_end}"

        validity = eval_result.validity_results.get(key)
        if validity is None or validity.verdict == "uncertain":
            updated.append(audited)
            continue

        # 更新 action_hint
        updated.append(replace(audited, action_hint=validity.upgraded_action))

    return updated

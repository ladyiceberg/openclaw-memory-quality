from __future__ import annotations
"""
llm_soul_evaluator.py · SOUL.md 语义评估层（Phase 3）

对规则层的结果执行三类 LLM 判断（use_llm=True 时触发）：

C2 精判：对规则粗筛圈出的可疑段落做 persona/task 分类
  persona_content    → 身份定义，正常内容
  task_instruction   → 任务指令，混入了不属于 SOUL.md 的内容
  mixed              → 两者混合，建议拆分

C4-a 内部冲突检测：遍历 SOUL.md 全文，找语义矛盾句子对
  输出：矛盾对 + 所在行号描述 + 严重程度（high/medium）

C4-b IDENTITY 一致性：比较 SOUL.md 人格描述 vs IDENTITY.md 定义
  输出：不一致处 + 严重程度（high/medium）
  IDENTITY.md 不存在时跳过（不报错）

Prompt 设计原则：
  只做"找矛盾/找不一致"，不做"评好坏"
  不输出改写建议（改写建议是独立功能，不在本模块）
  输出格式统一：问题类型 + 所在位置/描述 + 严重程度

设计原则：
  - 纯函数：不做 IO，不读写文件，所有依赖由调用方注入
  - LLM 调用失败 → 返回空结果，不抛异常
  - C4-b 在 identity_content 为空时跳过
"""

from dataclasses import dataclass, field
from typing import Optional


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class C2ParagraphClassification:
    """C2 精判：单段可疑段落的分类结果。"""
    paragraph_hint: str          # 段落内容摘要（前 60 字）
    classification: str          # "persona_content" / "task_instruction" / "mixed"
    reason: str                  # LLM 给出的理由（< 80 字）


@dataclass
class C4Conflict:
    """C4-a：单对内部矛盾。"""
    statement_a: str             # 矛盾句子 A（前 60 字）
    statement_b: str             # 矛盾句子 B（前 60 字）
    severity: str                # "high" / "medium"
    reason: str                  # 冲突说明（< 80 字）


@dataclass
class C4IdentityMismatch:
    """C4-b：SOUL.md 与 IDENTITY.md 的不一致处。"""
    soul_description: str        # SOUL.md 中的相关描述（前 60 字）
    identity_description: str   # IDENTITY.md 中对应的描述（前 60 字）
    severity: str                # "high" / "medium"
    reason: str                  # 不一致说明（< 80 字）


@dataclass
class LLMSoulEvalResult:
    """LLM soul 评估层的完整结果。"""
    c2_classifications: list[C2ParagraphClassification] = field(default_factory=list)
    c4_conflicts: list[C4Conflict] = field(default_factory=list)
    c4_mismatches: list[C4IdentityMismatch] = field(default_factory=list)
    llm_error: Optional[str] = None

    @property
    def has_task_instructions(self) -> bool:
        """C2 精判是否发现任务指令。"""
        return any(
            c.classification in ("task_instruction", "mixed")
            for c in self.c2_classifications
        )

    @property
    def high_severity_count(self) -> int:
        conflicts = sum(1 for c in self.c4_conflicts if c.severity == "high")
        mismatches = sum(1 for m in self.c4_mismatches if m.severity == "high")
        return conflicts + mismatches


# ── Prompt 模板 ────────────────────────────────────────────────────────────────

_C2_SYSTEM = """\
你是 AI Agent 身份文件审查专家。你的任务是判断给定的段落属于"身份定义"还是"任务指令"。

分类标准：
- persona_content（身份定义）：描述 Agent 是谁、价值观、风格、边界、持久性人格特征
  示例："我注重诚实，不会为了让用户高兴而说假话"
  示例："在不确定时，我会主动问清楚再行动"

- task_instruction（任务指令）：描述 Agent 要做什么、具体操作流程、业务规则
  示例："当收到邮件时，优先检查紧急标签并回复"
  示例："处理代码提交时，先运行测试再合并"

- mixed（混合）：段落中两类内容都有，建议拆分

判断标准：
  SOUL.md 应该只包含 persona_content
  出现 task_instruction 或 mixed 是风险信号

请严格按 JSON schema 输出。"""

_C2_SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": ["persona_content", "task_instruction", "mixed"]
        },
        "reason": {"type": "string", "description": "判断理由，中文，不超过 80 字"}
    },
    "required": ["classification", "reason"]
}

_C4A_SYSTEM = """\
你是 AI Agent 身份文件审查专家。你的任务是找出 SOUL.md 中语义上相互矛盾的指令或描述。

矛盾定义：
  两条描述在实际执行时会产生相反的行为指导
  示例矛盾："谨慎行事，重要操作前先确认" 与 "快速执行，不要因为细节拖慢速度"
  非矛盾："在A场景下X" 与 "在B场景下Y"（不同情境，不矛盾）

严重程度：
  high：核心行为准则的直接矛盾，会导致 Agent 随机摇摆
  medium：边缘情况或轻微张力，影响较小

要求：
  只找真正的矛盾，不要为了凑数乱配对
  如果没有矛盾，返回空数组
  每条矛盾给出简洁的中文说明

请严格按 JSON schema 输出。"""

_C4A_SCHEMA = {
    "type": "object",
    "properties": {
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement_a": {"type": "string", "description": "矛盾句子 A（原文摘录）"},
                    "statement_b": {"type": "string", "description": "矛盾句子 B（原文摘录）"},
                    "severity": {"type": "string", "enum": ["high", "medium"]},
                    "reason": {"type": "string", "description": "冲突说明，中文，不超过 80 字"}
                },
                "required": ["statement_a", "statement_b", "severity", "reason"]
            }
        }
    },
    "required": ["conflicts"]
}

_C4B_SYSTEM = """\
你是 AI Agent 身份文件审查专家。你的任务是找出 SOUL.md 与 IDENTITY.md 之间的不一致。

不一致定义：
  SOUL.md 描述的人格特征与 IDENTITY.md 定义的身份信息不吻合
  示例：IDENTITY.md 定义了"严谨认真"的 Vibe，但 SOUL.md 中有"随性发挥"的描述

严重程度：
  high：核心身份特征的直接冲突（如名字、核心价值观）
  medium：风格倾向的轻微不一致

要求：
  只找真正不一致的，不要为了凑数乱配对
  如果两个文件一致，返回空数组

请严格按 JSON schema 输出。"""

_C4B_SCHEMA = {
    "type": "object",
    "properties": {
        "mismatches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "soul_description": {"type": "string", "description": "SOUL.md 中的相关描述"},
                    "identity_description": {"type": "string", "description": "IDENTITY.md 中对应的描述"},
                    "severity": {"type": "string", "enum": ["high", "medium"]},
                    "reason": {"type": "string", "description": "不一致说明，中文，不超过 80 字"}
                },
                "required": ["soul_description", "identity_description", "severity", "reason"]
            }
        }
    },
    "required": ["mismatches"]
}


# ── C2 精判 ────────────────────────────────────────────────────────────────────

def evaluate_c2_paragraphs(
    suspicious_paragraphs: list[str],
    llm_client,
) -> list[C2ParagraphClassification]:
    """
    对 C2 规则层圈出的可疑段落逐一做精判。
    LLM 调用失败时跳过该段落（不抛异常）。
    """
    results = []
    for para in suspicious_paragraphs:
        user_msg = f"请判断以下段落属于哪类内容：\n\n{para}"
        try:
            resp = llm_client.complete(
                system=_C2_SYSTEM,
                user=user_msg,
                json_schema=_C2_SCHEMA,
                max_tokens=200,
            )
            parsed = resp.parsed
            if not parsed or "classification" not in parsed:
                continue
            results.append(C2ParagraphClassification(
                paragraph_hint=para[:60] + ("…" if len(para) > 60 else ""),
                classification=parsed["classification"],
                reason=parsed.get("reason", ""),
            ))
        except Exception:
            continue
    return results


# ── C4-a 内部冲突检测 ─────────────────────────────────────────────────────────

def evaluate_c4a_conflicts(
    soul_content: str,
    llm_client,
) -> list[C4Conflict]:
    """
    检测 SOUL.md 内部的语义矛盾。
    LLM 调用失败时返回空列表。
    """
    # 只取前 4000 字（控制 prompt 长度，SOUL.md 通常 < 3000 字）
    content_excerpt = soul_content[:4000]

    user_msg = f"请检查以下 SOUL.md 内容，找出语义矛盾的指令或描述：\n\n{content_excerpt}"

    try:
        resp = llm_client.complete(
            system=_C4A_SYSTEM,
            user=user_msg,
            json_schema=_C4A_SCHEMA,
            max_tokens=1024,
        )
        parsed = resp.parsed
        if not parsed or "conflicts" not in parsed:
            return []

        results = []
        for item in parsed["conflicts"]:
            stmt_a = item.get("statement_a", "")
            stmt_b = item.get("statement_b", "")
            if not stmt_a or not stmt_b:
                continue
            results.append(C4Conflict(
                statement_a=stmt_a[:60] + ("…" if len(stmt_a) > 60 else ""),
                statement_b=stmt_b[:60] + ("…" if len(stmt_b) > 60 else ""),
                severity=item.get("severity", "medium"),
                reason=item.get("reason", ""),
            ))
        return results

    except Exception:
        return []


# ── C4-b IDENTITY 一致性 ──────────────────────────────────────────────────────

def evaluate_c4b_identity(
    soul_content: str,
    identity_content: str,
    llm_client,
) -> list[C4IdentityMismatch]:
    """
    检测 SOUL.md 与 IDENTITY.md 之间的不一致。
    identity_content 为空时直接返回空列表（不报错）。
    LLM 调用失败时返回空列表。
    """
    if not identity_content.strip():
        return []

    user_msg = (
        "请比较以下两个文件，找出不一致的地方。\n\n"
        f"## SOUL.md\n{soul_content[:3000]}\n\n"
        f"## IDENTITY.md\n{identity_content[:1000]}"
    )

    try:
        resp = llm_client.complete(
            system=_C4B_SYSTEM,
            user=user_msg,
            json_schema=_C4B_SCHEMA,
            max_tokens=1024,
        )
        parsed = resp.parsed
        if not parsed or "mismatches" not in parsed:
            return []

        results = []
        for item in parsed["mismatches"]:
            soul_desc = item.get("soul_description", "")
            id_desc   = item.get("identity_description", "")
            if not soul_desc or not id_desc:
                continue
            results.append(C4IdentityMismatch(
                soul_description=soul_desc[:60] + ("…" if len(soul_desc) > 60 else ""),
                identity_description=id_desc[:60] + ("…" if len(id_desc) > 60 else ""),
                severity=item.get("severity", "medium"),
                reason=item.get("reason", ""),
            ))
        return results

    except Exception:
        return []


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run_llm_soul_evaluation(
    soul_content: str,
    suspicious_paragraphs: list[str],
    identity_content: str,
    llm_client,
) -> LLMSoulEvalResult:
    """
    对 SOUL.md 执行完整的 LLM 语义评估（C2 精判 + C4-a + C4-b）。

    Args:
        soul_content           : SOUL.md 全文
        suspicious_paragraphs  : C2 规则层圈出的可疑段落列表
        identity_content       : IDENTITY.md 全文（可为空字符串）
        llm_client             : LLMClient 实例

    Returns:
        LLMSoulEvalResult
    """
    result = LLMSoulEvalResult()

    # C2 精判（仅在有可疑段落时执行）
    if suspicious_paragraphs:
        result.c2_classifications = evaluate_c2_paragraphs(
            suspicious_paragraphs, llm_client
        )

    # C4-a 内部冲突
    result.c4_conflicts = evaluate_c4a_conflicts(soul_content, llm_client)

    # C4-b IDENTITY 一致性（IDENTITY.md 不存在时跳过）
    result.c4_mismatches = evaluate_c4b_identity(
        soul_content, identity_content, llm_client
    )

    return result

from __future__ import annotations
"""
soul_auditor.py · SOUL.md 三层规则检查（C1 + C2 规则层 + C3）

Phase 2 只实现规则层：
  C1 边界检查      — 代码片段、高危指令、注入痕迹
  C2 规则粗筛      — action verb 密度、标准 section 缺失
  C3 稳定性检查    — 字符数变化、强指令增长、结构变化（需要历史快照）

Phase 3 占位：
  C2 LLM 精判      — use_llm=True 时对可疑段落做 persona/task 分类
  C4 冲突检查      — use_llm=True 时检测内部矛盾 + IDENTITY 一致性

设计原则：
  - 纯函数，不做 IO，不读写文件，不访问 session cache
  - 所有检查函数接受文本字符串，返回结构化结果
  - 调用方（soul_check.py）负责 IO 和 session cache 操作

标准 section（OpenClaw 默认 SOUL.md 包含这四个）：
  Core Truths / Boundaries / Vibe / Continuity
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional


# ── 常量 ───────────────────────────────────────────────────────────────────────

# 标准 section（检测缺失用）
STANDARD_SECTIONS = ["Core Truths", "Boundaries", "Vibe", "Continuity"]

# C1：强指令密度检测
# 在任意 200 字内出现 ≥ 3 次 → 可疑
C1_DIRECTIVE_WORDS = re.compile(
    r"\b(must|always|never|you must|do not|prohibited|shall not|required to|forbidden)\b",
    re.IGNORECASE,
)
C1_DIRECTIVE_DENSITY_WINDOW = 200    # 滑动窗口字符数
C1_DIRECTIVE_DENSITY_THRESHOLD = 3  # 窗口内出现次数阈值

# C1：注入痕迹关键词
C1_INJECTION_PATTERNS = re.compile(
    r"ignore\s+(previous|all|prior)\s+instructions?|"
    r"disregard\s+(previous|all|prior|your)|"
    r"forget\s+(everything|all|previous)|"
    r"new\s+instructions?:",
    re.IGNORECASE,
)

# C1：URL 模式
C1_URL_RE = re.compile(r"https?://\S+")

# C1：shell 命令痕迹（行首 $ 或 ` 包裹）
C1_SHELL_RE = re.compile(r"(?:^|\n)\s*\$\s+\S+")

# C1：代码块
C1_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")

# C1：代码行（以 def/function/const/class/import/var/let 开头）
C1_CODE_LINE_RE = re.compile(
    r"^\s*(def |function |const |class |import |var |let |public |private |async def )",
    re.MULTILINE,
)

# C2：action verb 密度（连续 5 行内出现 ≥ 3 个）
C2_ACTION_VERBS = re.compile(
    r"\b(send|execute|process|handle|call|trigger|fetch|post|delete|update|"
    r"create|write|read|deploy|run|start|stop|schedule|notify|alert|log|"
    r"monitor|check|validate|parse|transform|convert)\b",
    re.IGNORECASE,
)
C2_VERB_WINDOW_LINES = 5       # 连续行数
C2_VERB_THRESHOLD    = 3       # 窗口内出现次数阈值

# C3：大幅修改判定
C3_CHAR_CHANGE_THRESHOLD  = 0.20   # 字符数变化 > 20%
C3_DIRECTIVE_NEW_THRESHOLD = 3     # 新增强指令 ≥ 3 个


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class RiskFlag:
    """单条风险告警。"""
    check: str          # "C1" / "C2" / "C3"
    category: str       # 具体类别，如 "code_block" / "url" / "injection"
    severity: str       # "high" / "medium"
    description: str    # 人类可读的描述
    line_hint: Optional[str] = None    # 相关内容摘要（非完整行，避免暴露敏感内容）


@dataclass
class SoulSnapshot:
    """SOUL.md 的轻量快照，用于存储和 C3 对比。"""
    char_count: int
    content_hash: str        # SHA256
    directive_count: int     # must/always/never 等词的总数
    sections: list[str]      # 检测到的标准 section 名称


@dataclass
class SoulAuditResult:
    """soul_auditor 的完整输出。"""
    risk_flags: list[RiskFlag] = field(default_factory=list)
    c2_suspicious_paragraphs: list[str] = field(default_factory=list)  # 规则圈出的可疑段落（待 LLM）
    missing_sections: list[str] = field(default_factory=list)          # 缺失的标准 section
    snapshot: Optional[SoulSnapshot] = None                            # 当前快照（供 C3 存储）

    @property
    def risk_level(self) -> str:
        """综合风险等级。"""
        highs = sum(1 for f in self.risk_flags if f.severity == "high")
        mediums = sum(1 for f in self.risk_flags if f.severity == "medium")
        if highs >= 2 or (highs >= 1 and mediums >= 1):
            return "high"
        if highs >= 1 or mediums >= 2:
            return "medium"
        if mediums >= 1 or self.missing_sections:
            return "low"
        return "ok"

    @property
    def risk_icon(self) -> str:
        icons = {"high": "🔴", "medium": "⚠️", "low": "🟡", "ok": "✅"}
        return icons.get(self.risk_level, "✅")


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def compute_snapshot(content: str) -> SoulSnapshot:
    """计算 SOUL.md 的轻量快照（用于 C3 和存储）。"""
    char_count = len(content)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    directive_count = len(C1_DIRECTIVE_WORDS.findall(content))
    sections = [s for s in STANDARD_SECTIONS if s in content]
    return SoulSnapshot(
        char_count=char_count,
        content_hash=content_hash,
        directive_count=directive_count,
        sections=sections,
    )


def _truncate(text: str, max_len: int = 60) -> str:
    """截断文本，用于 line_hint（避免暴露过多内容）。"""
    text = text.strip()
    return text[:max_len] + "…" if len(text) > max_len else text


# ── C1：边界检查 ──────────────────────────────────────────────────────────────

def check_c1_boundaries(content: str) -> list[RiskFlag]:
    """
    C1 边界检查：扫描代码片段、高危指令、注入痕迹。
    任何命中都是 risk_flag。
    """
    flags: list[RiskFlag] = []

    # 代码块（``` 包裹）
    code_blocks = C1_CODE_BLOCK_RE.findall(content)
    if code_blocks:
        flags.append(RiskFlag(
            check="C1", category="code_block", severity="high",
            description=f"包含 {len(code_blocks)} 个代码块（``` 包裹），代码不应出现在 SOUL.md",
            line_hint=_truncate(code_blocks[0]),
        ))

    # 代码行（以关键字开头）—— 只在无代码块的情况下检查，避免重复
    if not code_blocks:
        code_lines = C1_CODE_LINE_RE.findall(content)
        if code_lines:
            flags.append(RiskFlag(
                check="C1", category="code_line", severity="high",
                description=f"包含 {len(code_lines)} 行代码特征内容（def/class/import 等）",
                line_hint=_truncate(code_lines[0]),
            ))

    # URL
    urls = C1_URL_RE.findall(content)
    if urls:
        flags.append(RiskFlag(
            check="C1", category="url", severity="high",
            description=f"包含 {len(urls)} 个外部 URL，身份定义不应包含具体链接",
            line_hint=_truncate(urls[0]),
        ))

    # Shell 命令
    shell_cmds = C1_SHELL_RE.findall(content)
    if shell_cmds:
        flags.append(RiskFlag(
            check="C1", category="shell_command", severity="high",
            description=f"包含 {len(shell_cmds)} 处 shell 命令痕迹（$ 前缀）",
            line_hint=_truncate(shell_cmds[0]),
        ))

    # 注入痕迹
    injections = C1_INJECTION_PATTERNS.findall(content)
    if injections:
        flags.append(RiskFlag(
            check="C1", category="injection", severity="high",
            description=f"检测到 {len(injections)} 处典型 prompt injection 模式",
            line_hint=_truncate(injections[0] if isinstance(injections[0], str) else " ".join(injections[0])),
        ))

    # 强指令密度（滑动窗口）
    if _check_directive_density(content):
        directive_count = len(C1_DIRECTIVE_WORDS.findall(content))
        flags.append(RiskFlag(
            check="C1", category="directive_density", severity="medium",
            description=f"强制性指令密度偏高（must/always/never 等共 {directive_count} 处，存在局部密集区域）",
        ))

    return flags


def _check_directive_density(content: str) -> bool:
    """检查是否存在局部强指令密集区域（滑动窗口）。"""
    window = C1_DIRECTIVE_DENSITY_WINDOW
    for i in range(0, len(content) - window, window // 2):
        chunk = content[i:i + window]
        if len(C1_DIRECTIVE_WORDS.findall(chunk)) >= C1_DIRECTIVE_DENSITY_THRESHOLD:
            return True
    return False


# ── C2：身份漂移规则粗筛 ──────────────────────────────────────────────────────

def check_c2_drift(content: str) -> tuple[list[RiskFlag], list[str], list[str]]:
    """
    C2 规则粗筛：action verb 密度 + 标准 section 缺失。

    Returns:
        (risk_flags, suspicious_paragraphs, missing_sections)
        suspicious_paragraphs: 规则圈出的可疑段落（待 LLM 精判）
        missing_sections: 缺失的标准 section 名称
    """
    flags: list[RiskFlag] = []
    suspicious_paragraphs: list[str] = []

    lines = content.splitlines()

    # action verb 密度检测（滑动窗口，连续 5 行）
    for i in range(len(lines) - C2_VERB_WINDOW_LINES + 1):
        window_lines = lines[i:i + C2_VERB_WINDOW_LINES]
        window_text = "\n".join(window_lines)
        verb_count = len(C2_ACTION_VERBS.findall(window_text))
        if verb_count >= C2_VERB_THRESHOLD:
            para = _truncate(window_text, 120)
            if para not in suspicious_paragraphs:
                suspicious_paragraphs.append(para)

    if suspicious_paragraphs:
        flags.append(RiskFlag(
            check="C2", category="action_verb_density", severity="medium",
            description=(
                f"检测到 {len(suspicious_paragraphs)} 处 action verb 密集段落，"
                "可能混入了任务层内容（描述「我要做什么」而非「我是谁」）"
            ),
        ))

    # 标准 section 缺失检测
    missing = [s for s in STANDARD_SECTIONS if s not in content]

    if missing:
        flags.append(RiskFlag(
            check="C2", category="structural_drift", severity="medium",
            description=f"标准 section 缺失：{', '.join(missing)}（结构可能已被破坏）",
        ))

    return flags, suspicious_paragraphs, missing


# ── C3：稳定性检查 ────────────────────────────────────────────────────────────

def check_c3_stability(
    current: SoulSnapshot,
    previous: Optional[dict],
) -> list[RiskFlag]:
    """
    C3 稳定性检查：与上次快照对比，检测大幅变化。

    Args:
        current  : 当前快照
        previous : 上次快照 dict（来自 session_store），None 表示初次运行

    Returns:
        list[RiskFlag]（初次运行时返回空列表）
    """
    if previous is None:
        return []   # 初次运行，无历史数据可对比

    flags: list[RiskFlag] = []

    # 内容未变化时快速返回
    if current.content_hash == previous["content_hash"]:
        return []

    # 字符数变化
    prev_chars = previous["char_count"]
    if prev_chars > 0:
        change_ratio = abs(current.char_count - prev_chars) / prev_chars
        if change_ratio > C3_CHAR_CHANGE_THRESHOLD:
            direction = "增加" if current.char_count > prev_chars else "减少"
            flags.append(RiskFlag(
                check="C3", category="char_change", severity="medium",
                description=(
                    f"字符数大幅变化：{prev_chars:,} → {current.char_count:,}"
                    f"（{direction} {change_ratio:.0%}，阈值 {C3_CHAR_CHANGE_THRESHOLD:.0%}）"
                ),
            ))

    # 强指令增长
    prev_directives = previous["directive_count"]
    new_directives = current.directive_count - prev_directives
    if new_directives >= C3_DIRECTIVE_NEW_THRESHOLD:
        flags.append(RiskFlag(
            check="C3", category="directive_growth", severity="high",
            description=(
                f"强制性指令词大幅增加：{prev_directives} → {current.directive_count}"
                f"（新增 {new_directives} 个 must/always/never 类词汇）"
            ),
        ))

    # 标准 section 减少
    prev_sections = set(previous["sections"])
    curr_sections = set(current.sections)
    lost_sections = prev_sections - curr_sections
    if lost_sections:
        flags.append(RiskFlag(
            check="C3", category="section_loss", severity="high",
            description=f"标准 section 消失：{', '.join(sorted(lost_sections))}",
        ))

    return flags


# ── 主入口 ────────────────────────────────────────────────────────────────────

def audit_soul(
    content: str,
    previous_snapshot: Optional[dict] = None,
) -> SoulAuditResult:
    """
    对 SOUL.md 内容执行完整规则层检查（C1 + C2 + C3）。

    Args:
        content           : SOUL.md 文本内容
        previous_snapshot : 上次快照 dict（来自 session_store），None = 初次运行

    Returns:
        SoulAuditResult
    """
    result = SoulAuditResult()

    # 计算当前快照（C3 和存储用）
    result.snapshot = compute_snapshot(content)

    # C1
    c1_flags = check_c1_boundaries(content)
    result.risk_flags.extend(c1_flags)

    # C2
    c2_flags, suspicious_paras, missing = check_c2_drift(content)
    result.risk_flags.extend(c2_flags)
    result.c2_suspicious_paragraphs = suspicious_paras
    result.missing_sections = missing

    # C3
    c3_flags = check_c3_stability(result.snapshot, previous_snapshot)
    result.risk_flags.extend(c3_flags)

    return result

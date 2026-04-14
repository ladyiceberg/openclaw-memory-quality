from __future__ import annotations
"""
formats.py · 已知格式注册表 + FormatAdapter 抽象基类

设计原则：不假设，要探测（probe first, don't assert）。

OpenClaw 更新频繁，文件路径和格式随版本变化是真实风险。
新版本出现时，在 KNOWN_FORMATS 里加一条记录即可，业务逻辑不动。

已知格式：
  v2026_4_x  : v2026.4.x 实测，short-time-recall.json，MEMORY.md 手动格式
  source_code: 源码版本，short-term-recall.json，MEMORY.md Dreaming 格式
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ── 短期记忆路径候选（按优先级，找到第一个存在的即停止）──────────────────────

SHORT_TERM_CANDIDATES: list[str] = [
    "memory/short-time-recall.json",             # v2026.4.x 实测
    "memory/.dreams/short-term-recall.json",     # 源码版本
    "memory/short-term-recall.json",             # 备选变体
]

# ── 并发锁路径候选（与短期记忆路径对应）──────────────────────────────────────

LOCK_CANDIDATES: list[str] = [
    "memory/.dreams/short-term-promotion.lock",  # 源码版本（实测路径待确认）
]

# ── MEMORY.md 格式识别正则 ────────────────────────────────────────────────────

# 格式 A：Dreaming 自动晋升（源码版本）
LONGTERM_DREAMING_HEADER_RE = re.compile(
    r"^## Promoted From Short-Term Memory \(\d{4}-\d{2}-\d{2}\)$"
)
LONGTERM_DREAMING_ITEM_RE = re.compile(
    r"^- .+ \[score=[\d.]+ recalls=\d+ avg=[\d.]+ source=.+:\d+-\d+\]$"
)
LONGTERM_FILE_HEADER_DREAMING = "# Long-Term Memory"

# 格式 B：Agent 手动维护（v2026.4.x 实测）
LONGTERM_MANUAL_HEADER_RE = re.compile(r"^# MEMORY\.md")

# Issue 链接（未知格式时引导用户反馈）
ISSUE_URL = "https://github.com/ladyiceberg/openclaw-memory-quality/issues"


# ── 格式注册表 ────────────────────────────────────────────────────────────────

@dataclass
class FormatSpec:
    """描述一个已知的 OpenClaw 格式版本。"""
    name: str                          # 格式名，如 "v2026_4_x"
    shortterm_paths: list[str]         # 短期记忆文件路径候选
    longterm_header_pattern: str | None  # MEMORY.md 文件头正则（None = 未知）
    promotion_header_pattern: str | None  # Dreaming section header 正则（None = 无）
    notes: str = ""                    # 备注


KNOWN_FORMATS: dict[str, FormatSpec] = {
    "v2026_4_x": FormatSpec(
        name="v2026_4_x",
        shortterm_paths=["memory/short-time-recall.json"],
        longterm_header_pattern=r"^# MEMORY\.md",
        promotion_header_pattern=None,  # Dreaming 格式待真实触发后确认
        notes="v2026.4.x 实测版本",
    ),
    "source_code": FormatSpec(
        name="source_code",
        shortterm_paths=["memory/.dreams/short-term-recall.json"],
        longterm_header_pattern=r"^# Long-Term Memory",
        promotion_header_pattern=r"^## Promoted From Short-Term Memory \(\d{4}-\d{2}-\d{2}\)$",
        notes="源码版本（extensions/memory-core/src/short-term-promotion.ts）",
    ),
}


# ── FormatAdapter 抽象基类 ────────────────────────────────────────────────────

class FormatAdapter(ABC):
    """
    所有 format adapter 的基类。

    每个已知格式版本对应一个 RuleBasedAdapter 实现。
    未知格式时使用 LLMFormatAdapter（Phase 3 预留，当前为 stub）。
    """

    @property
    @abstractmethod
    def format_name(self) -> str:
        """格式名称，如 'v2026_4_x'。"""
        ...

    @property
    @abstractmethod
    def supports_longterm_audit(self) -> bool:
        """是否支持长期记忆审计（即 MEMORY.md 有可解析的结构）。"""
        ...


class RuleBasedAdapter(FormatAdapter):
    """
    规则解析 adapter，用于已知格式。
    具体解析逻辑在 readers/ 模块中实现，adapter 只提供格式元信息。
    """

    def __init__(self, spec: FormatSpec) -> None:
        self._spec = spec

    @property
    def format_name(self) -> str:
        return self._spec.name

    @property
    def supports_longterm_audit(self) -> bool:
        return self._spec.promotion_header_pattern is not None

    @property
    def spec(self) -> FormatSpec:
        return self._spec


class UnknownFormatAdapter(FormatAdapter):
    """
    未知格式的 adapter。
    规则解析失败时使用，功能受限，引导用户反馈。

    Phase 3 预留：未来升级为 LLMFormatAdapter，
    用 LLM 理解任意格式的 Markdown，提取核心字段。
    """

    @property
    def format_name(self) -> str:
        return "unknown"

    @property
    def supports_longterm_audit(self) -> bool:
        return False


# ── 格式识别函数 ───────────────────────────────────────────────────────────────

def detect_longterm_format(content: str) -> tuple[str, FormatAdapter]:
    """
    根据 MEMORY.md 内容识别格式，返回 (格式名, adapter)。

    识别逻辑：
      1. 检查文件头是否匹配已知格式
      2. 检查是否包含 Dreaming section header
      3. 都不匹配 → UnknownFormatAdapter
    """
    first_lines = content[:500]  # 只看文件开头

    # 格式 A：Dreaming 格式（源码版本）
    if LONGTERM_FILE_HEADER_DREAMING in first_lines:
        spec = KNOWN_FORMATS["source_code"]
        return "source_code", RuleBasedAdapter(spec)

    # 格式 B：手动维护格式（v2026.4.x 实测）
    if LONGTERM_MANUAL_HEADER_RE.search(first_lines):
        # 进一步检查是否同时包含 Dreaming section（两种格式共存）
        if LONGTERM_DREAMING_HEADER_RE.search(content):
            # 混合格式：手动 + Dreaming 追加
            spec = KNOWN_FORMATS["source_code"]
            return "mixed", RuleBasedAdapter(spec)
        spec = KNOWN_FORMATS["v2026_4_x"]
        return "v2026_4_x", RuleBasedAdapter(spec)

    # 兜底：未知格式
    return "unknown", UnknownFormatAdapter()

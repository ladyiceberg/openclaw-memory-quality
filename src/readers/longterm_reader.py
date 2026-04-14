from __future__ import annotations
"""
longterm_reader.py · 长期记忆文件读取与解析

读取 {workspaceDir}/MEMORY.md
返回 LongTermStore，包含：
  - 所有 Dreaming 晋升 section（MemorySection）
  - 每个 section 内的 MemoryItem 列表
  - 手动内容统计（字符数、行数）
  - 80% 安全阀：解析字符量 / 文件总字符量 < 80% → 返回错误

设计原则：
  - 返回错误对象，不抛异常（与 shortterm_reader.py 风格一致）
  - 兼容 mixed 格式（手动内容 + Dreaming section 共存）
  - 兼容有/无 <!-- openclaw-memory-promotion:... --> 注释行的格式
  - metadata 从行尾反向解析，防止 snippet 中含 [ ] 干扰
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.probe import ProbeResult


# ── 元数据正则（从行尾反向匹配，防止 snippet 中 [ ] 干扰）────────────────────
#
# 目标行格式：
#   - {snippet} [score={X.XXX} recalls={N} avg={X.XXX} source={path}:{L}-{L}]
#
# 关键设计：[score=...source=path:L-L] 整块在行的最末尾
# source 格式：{relative_path}:{start_line}-{end_line}，如 memory/2026-04-09.md:1-35

_ITEM_META_RE = re.compile(
    r"^- (.+?) "                             # snippet（非贪婪，到 meta 块为止）
    r"\[score=([\d.]+) "                     # score
    r"recalls=(\d+) "                        # recalls
    r"avg=([\d.]+) "                         # avg
    r"source=(.+?):(\d+)-(\d+)\]$"          # source_path, start, end
)

# HTML 注释行：<!-- openclaw-memory-promotion:{key} -->
_PROMOTION_COMMENT_RE = re.compile(
    r"^<!--\s*openclaw-memory-promotion:(.+?)\s*-->$"
)

# Dreaming section header：## Promoted From Short-Term Memory (YYYY-MM-DD)
_SECTION_HEADER_RE = re.compile(
    r"^## Promoted From Short-Term Memory \((\d{4}-\d{2}-\d{2})\)$"
)


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class MemoryItem:
    """
    MEMORY.md 中单条晋升记忆。
    对应 Dreaming 写入的一对两行：
      <!-- openclaw-memory-promotion:{key} -->
      - {snippet} [score=... source=...]
    """
    snippet: str               # normalizeSnippet 处理后的单行文本
    score: float               # 晋升时的总分
    recalls: int               # 晋升时的 recall 次数
    avg_score: float           # 晋升时的平均分
    source_path: str           # 来源文件相对路径，如 memory/2026-04-09.md
    source_start: int          # 来源文件起始行（1-based）
    source_end: int            # 来源文件结束行（1-based）
    promotion_key: Optional[str] = None  # <!-- --> 注释行的 key，可能为 None（旧版无注释行）


@dataclass
class MemorySection:
    """
    MEMORY.md 中一个 Dreaming 晋升 section。
    对应 ## Promoted From Short-Term Memory (YYYY-MM-DD) 块。
    """
    date: str                  # 晋升日期，如 "2026-04-14"
    items: list[MemoryItem] = field(default_factory=list)
    non_standard_lines: int = 0  # section 内无法解析的非空行数


@dataclass
class LongTermStore:
    """MEMORY.md 的解析结果。"""
    sections: list[MemorySection]      # 所有 Dreaming section（时间顺序）
    total_items: int                   # 所有 section 内 item 总数
    manual_content_lines: int          # Dreaming section 外的非空行数（手动内容）
    manual_content_chars: int          # Dreaming section 外的字符数
    has_manual_content: bool           # 是否有手动内容（mixed 格式）
    format_name: str                   # "source_code" / "mixed" / "manual"
    raw_char_count: int                # 文件原始字符数
    parsed_char_count: int             # Dreaming section 内成功解析的行字符数
    dreaming_section_chars: int = 0   # Dreaming section 内全部行的字符总数（安全阀分母）

    @property
    def parsed_ratio(self) -> float:
        """
        Dreaming section 内成功解析的字符占 section 内总字符的比例。
        用于 80% 安全阀校验。

        使用 section 内字符作为分母（而非全文），避免 mixed 格式因手动
        内容字符多而误触发。无 Dreaming section 时返回 1.0（不触发）。
        """
        if self.dreaming_section_chars == 0:
            return 1.0
        return self.parsed_char_count / self.dreaming_section_chars


@dataclass
class LongTermReadError:
    """读取/解析失败时的错误描述，不抛异常，由调用方处理。"""
    error_code: str    # "file_not_found" / "safety_valve" / "unknown"
    message: str
    path: str


# ── 核心读取函数 ───────────────────────────────────────────────────────────────

def read_longterm(
    probe: ProbeResult,
) -> LongTermStore | LongTermReadError:
    """
    读取并解析长期记忆文件。

    Args:
        probe: probe_workspace() 的返回值，提供实际文件路径。

    Returns:
        LongTermStore: 解析成功
        LongTermReadError: 失败（文件不存在 / 安全阀触发）
    """
    if probe.longterm_path is None:
        return LongTermReadError(
            error_code="file_not_found",
            message="MEMORY.md 不存在。",
            path=str(probe.workspace_dir),
        )
    return _read_from_path(probe.longterm_path, probe.longterm_format)


def read_longterm_from_path(
    path: Path,
    format_name: str = "source_code",
) -> LongTermStore | LongTermReadError:
    """
    直接从路径读取，供测试使用。

    Args:
        path: MEMORY.md 的绝对路径。
        format_name: 格式名，默认 "source_code"。
    """
    return _read_from_path(path, format_name)


# ── 内部实现 ───────────────────────────────────────────────────────────────────

def _read_from_path(
    path: Path,
    format_name: str,
) -> LongTermStore | LongTermReadError:
    """内部实现：从给定路径读取并解析。"""
    if not path.exists():
        return LongTermReadError(
            error_code="file_not_found",
            message=f"文件不存在：{path}",
            path=str(path),
        )

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        return LongTermReadError(
            error_code="unknown",
            message=f"文件读取失败：{e}",
            path=str(path),
        )

    return _parse_content(content, format_name, str(path))


def _parse_content(
    content: str,
    format_name: str,
    path_str: str,
) -> LongTermStore | LongTermReadError:
    """
    解析 MEMORY.md 内容。

    扫描策略（行级状态机）：
      - 遇到 "## Promoted From ..." → 开始新 section
      - 遇到 "<!-- openclaw-memory-promotion:..." → 记录 pending_key
      - 遇到 "- ... [score=...]" → 解析为 MemoryItem，消耗 pending_key
      - 其他行（在 section 内）→ 计入 non_standard_lines
      - section 外的非空行 → 计入 manual_content_lines/chars
    """
    raw_char_count = len(content)
    lines = content.splitlines()

    sections: list[MemorySection] = []
    current_section: Optional[MemorySection] = None
    pending_key: Optional[str] = None   # 上一行读到的 <!-- --> key

    manual_lines = 0
    manual_chars = 0
    parsed_chars = 0        # section 内成功解析的行字符数（包含整行，不只 snippet）
    dreaming_chars = 0      # section 内全部行字符总数（安全阀分母）

    for line in lines:
        # ── Dreaming section header ────────────────────────────────────────────
        m_section = _SECTION_HEADER_RE.match(line)
        if m_section:
            current_section = MemorySection(date=m_section.group(1))
            sections.append(current_section)
            pending_key = None
            # section header 行：计入 dreaming_chars 也计入 parsed_chars
            dreaming_chars += len(line)
            parsed_chars += len(line)
            continue

        # ── section 内的所有行（含空行）计入 dreaming_chars ────────────────────
        # 放在各具体分支之前，统一计入分母；空行后续不会匹配任何分支，自然跳过
        if current_section is not None:
            dreaming_chars += len(line)

        # ── HTML 注释行（promotion marker）────────────────────────────────────
        m_comment = _PROMOTION_COMMENT_RE.match(line)
        if m_comment:
            pending_key = m_comment.group(1).strip()
            # 注释行：属于 section 内，计入 parsed_chars
            if current_section is not None:
                parsed_chars += len(line)
            continue

        # ── MemoryItem（列表项 + metadata）────────────────────────────────────
        if current_section is not None and line.startswith("- "):
            m_item = _ITEM_META_RE.match(line)
            if m_item:
                item = MemoryItem(
                    snippet=m_item.group(1),
                    score=float(m_item.group(2)),
                    recalls=int(m_item.group(3)),
                    avg_score=float(m_item.group(4)),
                    source_path=m_item.group(5),
                    source_start=int(m_item.group(6)),
                    source_end=int(m_item.group(7)),
                    promotion_key=pending_key,
                )
                current_section.items.append(item)
                parsed_chars += len(line)   # 整行计入，而非只有 snippet
                pending_key = None
                continue
            else:
                # 以 "- " 开头但解析失败（非标准行）
                if line.strip():
                    current_section.non_standard_lines += 1
                pending_key = None
                continue

        # ── section 内其他非空行（non_standard）────────────────────────────────
        if current_section is not None:
            if line.strip():
                current_section.non_standard_lines += 1
            pending_key = None
            continue

        # ── section 外的行（手动内容）──────────────────────────────────────────
        # H1 标题（# ...）是文件级标头（如 "# Long-Term Memory"），
        # 不归入"手动内容"，只计有实质内容的行（## 及以下、列表、正文等）
        stripped = line.strip()
        if stripped and not stripped.startswith("# ") and stripped != "#":
            manual_lines += 1
            manual_chars += len(line)

    # ── 统计 ───────────────────────────────────────────────────────────────────
    total_items = sum(len(s.items) for s in sections)
    has_manual = manual_lines > 0

    # 格式名修正：有 Dreaming section 又有手动内容 → mixed
    if sections and has_manual:
        effective_format = "mixed"
    elif sections:
        effective_format = "source_code"
    elif has_manual:
        effective_format = "manual"
    else:
        effective_format = format_name   # 空文件，保留传入值

    store = LongTermStore(
        sections=sections,
        total_items=total_items,
        manual_content_lines=manual_lines,
        manual_content_chars=manual_chars,
        has_manual_content=has_manual,
        format_name=effective_format,
        raw_char_count=raw_char_count,
        parsed_char_count=parsed_chars,
        dreaming_section_chars=dreaming_chars,
    )

    # ── 80% 安全阀（仅对有 Dreaming section 的文件检查）──────────────────────
    # 分母用 dreaming_section_chars（section 内字符），而非全文，
    # 避免 mixed 格式因手动内容字符多而误触发。
    # 触发条件：section 内有足够内容（> 100 字符），但解析率 < 80%。
    if sections and dreaming_chars > 100 and store.parsed_ratio < 0.80:
        return LongTermReadError(
            error_code="safety_valve",
            message=(
                f"MEMORY.md 解析率偏低（{store.parsed_ratio:.1%}），"
                f"解析可能不完整，已中止。"
                f"（Dreaming section 内 {parsed_chars} / {dreaming_chars} 字符被识别）"
            ),
            path=path_str,
        )

    return store

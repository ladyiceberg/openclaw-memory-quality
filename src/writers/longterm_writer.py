from __future__ import annotations
"""
longterm_writer.py · MEMORY.md 重建（从原始文本删除指定 item）

阶段 B 写操作模块。与 longterm_reader.py 配套使用：
  reader 解析 → auditor 审计 → writer 重建

设计要点：
  1. 不依赖行号，逐行重扫描原始文本决定保留/删除
     （比行号更健壮，不怕文件有微小变化）
  2. 删除单位是"comment 行 + item 行"这一对，原子处理
  3. 非标准行（用户手写）无条件保留
  4. 某 section 内所有 item 被删且无非标准内容 → 删 section header
  5. 手动内容（section 外）无条件保留
  6. 本模块只做"构建新文本"，不做 IO；
     IO（备份 + 原子写入 + 加锁）由调用方负责

函数签名：
  build_cleaned_content(original, keys_to_delete) → (new_content, stats)
"""

import re
from dataclasses import dataclass
from typing import Optional


# ── 正则（与 longterm_reader.py 保持一致）────────────────────────────────────

_SECTION_HEADER_RE = re.compile(
    r"^## Promoted From Short-Term Memory \((\d{4}-\d{2}-\d{2})\)$"
)
_PROMOTION_COMMENT_RE = re.compile(
    r"^<!--\s*openclaw-memory-promotion:(.+?)\s*-->$"
)
_ITEM_META_RE = re.compile(
    r"^- (.+?) "
    r"\[score=([\d.]+) "
    r"recalls=(\d+) "
    r"avg=([\d.]+) "
    r"source=(.+?):(\d+)-(\d+)\]$"
)


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class CleanupStats:
    """重建结果统计，供上层工具格式化输出。"""
    deleted: int               # 实际删除的 item 数
    kept: int                  # 保留的 item 数
    sections_before: int       # 重建前 Dreaming section 数
    sections_after: int        # 重建后 Dreaming section 数（空 section 被删）
    empty_sections_removed: int  # 因全空而被删的 section 数
    backup_path: Optional[str] = None  # 备份文件路径（由调用方写入）


# ── 核心函数 ───────────────────────────────────────────────────────────────────

def build_cleaned_content(
    original: str,
    keys_to_delete: set[str],
) -> tuple[str, CleanupStats]:
    """
    从原始 MEMORY.md 文本中删除指定 key 的 item，重建新文本。

    Args:
        original       : MEMORY.md 原始文本
        keys_to_delete : 要删除的 promotion_key 集合
                         格式：如 "memory:memory/2026-04-09.md:1:35"
                         若某 item 无 promotion_key（旧格式），
                         可用 "source_path:start-end" 作为 fallback key

    Returns:
        (new_content, stats)
        new_content : 重建后的文本（末尾带换行符）
        stats       : 删除/保留统计

    注意：
        - 只删除 comment 行 + 对应的 item 行这一对
        - 非标准行、手动内容无条件保留
        - 空 section（所有 item 已删且无非标准内容）的 header 也一并删除
    """
    lines = original.splitlines(keepends=True)

    # ── 第一轮：逐行扫描，标记每行的保留/删除决定 ──────────────────────────

    # 最终输出行（None 表示删除）
    result_lines: list[Optional[str]] = []

    # 状态机变量
    in_section = False
    pending_delete_next_item = False  # 上一行是要删除的 comment → 下一行 item 也删
    sections_before = 0

    # 收集每个 section 的信息，用于第二轮清理空 section
    # section_ranges[i] = (header_line_idx, [item_kept_flags], has_nonstandard)
    section_infos: list[dict] = []  # 每个 section 的元信息
    current_section_info: Optional[dict] = None

    deleted = 0
    kept = 0

    for line_idx, line in enumerate(lines):
        raw_line = line.rstrip("\r\n")

        # ── section header ─────────────────────────────────────────────────
        m_sec = _SECTION_HEADER_RE.match(raw_line)
        if m_sec:
            in_section = True
            pending_delete_next_item = False
            sections_before += 1
            current_section_info = {
                "header_idx": len(result_lines),  # 在 result_lines 中的位置
                "any_kept": False,
                "has_nonstandard": False,
            }
            section_infos.append(current_section_info)
            result_lines.append(line)
            continue

        # ── section 内 ────────────────────────────────────────────────────
        if in_section:
            # comment 行
            m_comment = _PROMOTION_COMMENT_RE.match(raw_line)
            if m_comment:
                key = m_comment.group(1).strip()
                if key in keys_to_delete:
                    pending_delete_next_item = True
                    result_lines.append(None)   # 删除 comment 行
                else:
                    pending_delete_next_item = False
                    result_lines.append(line)
                continue

            # item 行
            if raw_line.startswith("- "):
                m_item = _ITEM_META_RE.match(raw_line)
                if m_item:
                    if pending_delete_next_item:
                        # 对应的 comment 已标记删除 → 删除此 item 行
                        result_lines.append(None)
                        deleted += 1
                        pending_delete_next_item = False
                    else:
                        # 没有关联的删除 comment，也尝试用 source 坐标匹配
                        source_path  = m_item.group(5)
                        source_start = m_item.group(6)
                        source_end   = m_item.group(7)
                        fallback_key = f"{source_path}:{source_start}-{source_end}"
                        if fallback_key in keys_to_delete:
                            result_lines.append(None)
                            deleted += 1
                        else:
                            result_lines.append(line)
                            kept += 1
                            if current_section_info:
                                current_section_info["any_kept"] = True
                        pending_delete_next_item = False
                    continue
                else:
                    # 以 "- " 开头但不匹配 metadata → 非标准行，保留
                    pending_delete_next_item = False
                    if raw_line.strip():
                        if current_section_info:
                            current_section_info["has_nonstandard"] = True
                    result_lines.append(line)
                    continue

            # 空行或其他行（section 内）
            pending_delete_next_item = False
            if raw_line.strip():
                # 非空非 item 非 comment → 非标准内容，保留
                if current_section_info:
                    current_section_info["has_nonstandard"] = True
            result_lines.append(line)
            continue

        # ── section 外（手动内容）─────────────────────────────────────────
        result_lines.append(line)

    # ── 第二轮：删除空 section 的 header ─────────────────────────────────

    empty_sections_removed = 0
    for info in section_infos:
        if not info["any_kept"] and not info["has_nonstandard"]:
            # 这个 section 内没有任何保留的 item，也没有非标准行 → 删 header
            header_idx = info["header_idx"]
            result_lines[header_idx] = None
            empty_sections_removed += 1

    # ── 组装最终文本 ───────────────────────────────────────────────────────

    new_content = "".join(line for line in result_lines if line is not None)

    # 确保末尾有且只有一个换行符
    if new_content and not new_content.endswith("\n"):
        new_content += "\n"

    sections_after = sections_before - empty_sections_removed

    stats = CleanupStats(
        deleted=deleted,
        kept=kept,
        sections_before=sections_before,
        sections_after=sections_after,
        empty_sections_removed=empty_sections_removed,
    )

    return new_content, stats

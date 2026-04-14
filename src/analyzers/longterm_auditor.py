from __future__ import annotations
"""
longterm_auditor.py · MEMORY.md 三项核查（V1 + V3）

V1 — 来源文件存在性：
  对每条 MemoryItem 检查 workspaceDir / source_path 是否存在。
  - exists        : 文件在原路径
  - possibly_moved: 文件不在原路径，但同名文件在 workspace 其他位置（启发式）
  - deleted       : 文件彻底消失 → action_hint = delete

V3 — 重复检测：
  以 (source_path, source_start, source_end) 分组：
  - duplicate_loser : 同一 key 出现 >= 2 次，score 非最高的那些 → delete
  - overlap         : 同文件行号区间相交（非完全重合）→ review
  - ok              : 无重复

辅助函数（V2 备用）：
  normalize_snippet(text)      — 复现 OpenClaw normalizeSnippet()，多行→单行
  char_level_similarity(a, b)  — 字符级相似度（difflib.SequenceMatcher）

设计原则：
  - run_audit() 接收 LongTermStore + workspace_dir，返回 LongtermAuditResult
  - 不抛异常，错误路径通过返回值体现
  - 每条 item 的 action_hint 由 V1 + V3 合并决定（优先级见代码注释）
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from src.readers.longterm_reader import LongTermStore, MemoryItem


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class AuditedItem:
    """单条 MemoryItem 的完整审计结果。"""
    item: MemoryItem
    v1_status: str      # "exists" / "possibly_moved" / "deleted" / "skipped"
    v3_status: str      # "duplicate_loser" / "overlap" / "ok"
    action_hint: str    # "keep" / "review" / "delete"


@dataclass
class LongtermAuditResult:
    """V1 + V3 审计结果汇总。report_id 由 Step 6（MCP 工具层）注入。"""
    total_items: int
    sections_count: int
    items_by_action: dict[str, int]     # {"keep": N, "review": N, "delete": N}
    non_standard_sections: int          # section 内有 non_standard_lines 的数量
    items: list[AuditedItem]
    memory_md_mtime: Optional[float]    # 文件修改时间（供写操作校验用）


# ── 辅助函数（V2 备用）─────────────────────────────────────────────────────────

def normalize_snippet(text: str) -> str:
    """
    复现 OpenClaw 的 normalizeSnippet() 行为：
    所有空白符（含换行）替换为单个空格，首尾去空格。

    MEMORY.md 里存储的 snippet 已经过这个处理，
    V2 比较时来源文件内容必须先经过同样处理才能正确对比。
    """
    return re.sub(r"\s+", " ", text.strip())


def char_level_similarity(a: str, b: str) -> float:
    """
    字符级相似度，基于 difflib.SequenceMatcher。
    返回 0.0（完全不同）到 1.0（完全相同）。

    空字符串的处理：
      - 两个都空 → 1.0（视为相同）
      - 一个空一个不空 → 0.0（完全不同）
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ── V1：来源文件存在性 ────────────────────────────────────────────────────────

def _check_v1_single(item: MemoryItem, workspace_dir: Path) -> str:
    """
    对单条 MemoryItem 做 V1 检查。

    Returns:
        "exists"         — 文件在原路径
        "possibly_moved" — 原路径不存在，但同名文件在 workspace 其他位置
        "deleted"        — 找不到文件
    """
    abs_path = workspace_dir / item.source_path
    if abs_path.exists():
        return "exists"

    # 启发式：在 workspace 内搜索同名文件
    basename = Path(item.source_path).name
    try:
        matches = list(workspace_dir.rglob(basename))
        # 过滤掉原路径本身（虽然不存在，但防止 rglob 有意外）
        matches = [m for m in matches if m != abs_path]
        if matches:
            return "possibly_moved"
    except (OSError, PermissionError):
        pass  # 搜索失败不影响主流程

    return "deleted"


# ── V3：重复检测 ──────────────────────────────────────────────────────────────

def _check_v3_all(items: list[MemoryItem]) -> list[str]:
    """
    对全部 MemoryItem 做 V3 重复检测。

    Returns:
        与 items 等长的列表，每个元素为对应 item 的 v3_status：
        "duplicate_loser" / "overlap" / "ok"

    算法：
      第一轮：精确重复（同一 key）
        按 (source_path, source_start, source_end) 分组
        每组保留 score 最高的（相同 score 取第一个），其余标 duplicate_loser

      第二轮：行号范围重叠（同文件但区间相交，非精确重复）
        仅对第一轮后 status=ok 的 item 检查
        用 O(n²) 扫描：实际 MEMORY.md 条目数通常 < 500，可接受
    """
    n = len(items)
    statuses = ["ok"] * n

    # ── 第一轮：精确重复 ──────────────────────────────────────────────────────
    # key → list of (index, score)
    groups: dict[tuple, list[tuple[int, float]]] = {}
    for i, item in enumerate(items):
        key = (item.source_path, item.source_start, item.source_end)
        groups.setdefault(key, []).append((i, item.score))

    for key, group in groups.items():
        if len(group) < 2:
            continue
        # 保留 score 最高的（相同 score 保留最早出现的）
        winner_idx = max(group, key=lambda t: t[1])[0]
        for idx, _ in group:
            if idx != winner_idx:
                statuses[idx] = "duplicate_loser"

    # ── 第二轮：行号范围重叠 ──────────────────────────────────────────────────
    # 只对 status=ok 的 item 检查
    ok_indices = [i for i in range(n) if statuses[i] == "ok"]

    for i_pos, i in enumerate(ok_indices):
        for j in ok_indices[i_pos + 1:]:
            item_i = items[i]
            item_j = items[j]

            # 必须是同一文件
            if item_i.source_path != item_j.source_path:
                continue

            # 必须不是精确重复（已在第一轮处理）
            if (item_i.source_start == item_j.source_start and
                    item_i.source_end == item_j.source_end):
                continue

            # 行号范围相交：max(start1,start2) <= min(end1,end2)
            overlap_start = max(item_i.source_start, item_j.source_start)
            overlap_end = min(item_i.source_end, item_j.source_end)
            if overlap_start <= overlap_end:
                statuses[i] = "overlap"
                statuses[j] = "overlap"

    return statuses


# ── action_hint 合并 ──────────────────────────────────────────────────────────

def _derive_action(v1_status: str, v3_status: str) -> str:
    """
    从 V1 + V3 结果合并出 action_hint。

    优先级（从高到低）：
      V1 deleted          → delete  （来源消失，最确定）
      V3 duplicate_loser  → delete  （重复，保留更好版本）
      V3 overlap          → review  （范围重叠，人工确认）
      V1 possibly_moved   → review  （文件可能迁移，人工确认）
      其他                → keep
    """
    if v1_status == "deleted":
        return "delete"
    if v3_status == "duplicate_loser":
        return "delete"
    if v3_status == "overlap":
        return "review"
    if v1_status == "possibly_moved":
        return "review"
    return "keep"


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run_audit(
    store: LongTermStore,
    workspace_dir: str | Path,
    memory_md_path: Optional[Path] = None,
) -> LongtermAuditResult:
    """
    对 LongTermStore 执行 V1 + V3 审计。

    Args:
        store          : longterm_reader 解析结果
        workspace_dir  : OpenClaw workspace 根目录（用于 V1 路径拼接）
        memory_md_path : MEMORY.md 的实际路径（用于读取 mtime）

    Returns:
        LongtermAuditResult
    """
    ws = Path(workspace_dir)

    # 收集所有 item，保持顺序（section 顺序 → section 内 item 顺序）
    all_items: list[MemoryItem] = []
    for section in store.sections:
        all_items.extend(section.items)

    total = len(all_items)

    # ── V3（先跑，不依赖文件系统，快）────────────────────────────────────────
    v3_statuses = _check_v3_all(all_items) if total > 0 else []

    # ── V1（后跑，涉及文件系统 IO）────────────────────────────────────────────
    v1_statuses: list[str] = []
    for item in all_items:
        v1_statuses.append(_check_v1_single(item, ws))

    # ── 合并成 AuditedItem ────────────────────────────────────────────────────
    audited: list[AuditedItem] = []
    for i, item in enumerate(all_items):
        v1 = v1_statuses[i]
        v3 = v3_statuses[i]
        action = _derive_action(v1, v3)
        audited.append(AuditedItem(item=item, v1_status=v1, v3_status=v3, action_hint=action))

    # ── 聚合统计 ───────────────────────────────────────────────────────────────
    items_by_action: dict[str, int] = {"keep": 0, "review": 0, "delete": 0}
    for a in audited:
        items_by_action[a.action_hint] = items_by_action.get(a.action_hint, 0) + 1

    non_standard_sections = sum(
        1 for s in store.sections if s.non_standard_lines > 0
    )

    # mtime：读取 MEMORY.md 文件修改时间（供写操作安全校验）
    mtime: Optional[float] = None
    if memory_md_path is not None and memory_md_path.exists():
        try:
            mtime = memory_md_path.stat().st_mtime
        except OSError:
            pass

    return LongtermAuditResult(
        total_items=total,
        sections_count=len(store.sections),
        items_by_action=items_by_action,
        non_standard_sections=non_standard_sections,
        items=audited,
        memory_md_mtime=mtime,
    )

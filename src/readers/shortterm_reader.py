from __future__ import annotations
"""
shortterm_reader.py · 短期记忆文件读取与解析

读取 {workspaceDir}/memory/.dreams/short-term-recall.json
返回 ShortTermStore 包含所有 ShortTermEntry。

设计原则：
  - 接收 ProbeResult 获取路径，不硬编码
  - 所有字段用 .get() + 默认值读取，兼容新旧版本
  - 文件不存在 / JSON 损坏 → 返回明确错误，不抛原始异常
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json

from src.probe import ProbeResult


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class ShortTermEntry:
    """
    单条短期记忆条目。
    字段来自 openclaw-main 3 ShortTermRecallEntry 类型定义。

    ⚠️ 所有字段均用 .get() + 默认值解析，确保旧版本兼容。
    """
    # 核心字段（所有版本都有）
    key: str
    path: str
    start_line: int
    end_line: int
    source: str                      # 固定值 "memory"
    snippet: str                     # normalizeSnippet 处理后的单行文本
    recall_count: int
    total_score: float
    max_score: float
    first_recalled_at: str           # ISO 8601 字符串
    last_recalled_at: str            # ISO 8601 字符串
    query_hashes: list[str]
    recall_days: list[str]
    concept_tags: list[str]

    # 新版新增字段（openclaw-main 3，旧版无，默认值保证兼容）
    daily_count: int = 0
    grounded_count: int = 0
    claim_hash: Optional[str] = None  # 存在时 key 含 claimHash 后缀

    # 可选字段
    promoted_at: Optional[str] = None  # ISO 8601 字符串，未晋升时字段本身不出现


@dataclass
class ShortTermStore:
    """short-term-recall.json 的完整内容。"""
    version: int
    updated_at: str
    entries: list[ShortTermEntry]


@dataclass
class ShortTermReadError:
    """读取失败时的错误描述，不抛异常，由调用方处理。"""
    error_code: str    # "file_not_found" / "json_invalid" / "unknown"
    message: str
    path: str


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def days_since_iso(iso_str: str, now_ms: int) -> float:
    """
    ISO 8601 字符串转换为距今天数。
    供 zombie_detector / false_positive 使用。
    """
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    now_dt = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    return (now_dt - dt).total_seconds() / 86400


def _parse_entry(raw: dict) -> Optional[ShortTermEntry]:
    """
    解析单条 JSON 条目为 ShortTermEntry。
    字段缺失时使用安全默认值（不抛 KeyError）。
    返回 None 表示该条目格式无效，应跳过。
    """
    # 必填字段：缺失则跳过
    key = raw.get("key", "")
    path = raw.get("path", "")
    start_line = raw.get("startLine")
    end_line = raw.get("endLine")
    source = raw.get("source", "")

    if not key or not path or start_line is None or end_line is None or source != "memory":
        return None

    try:
        start_line = int(start_line)
        end_line = int(end_line)
    except (TypeError, ValueError):
        return None

    return ShortTermEntry(
        key=key,
        path=path,
        start_line=start_line,
        end_line=end_line,
        source=source,
        snippet=raw.get("snippet", ""),
        recall_count=int(raw.get("recallCount", 0)),
        total_score=float(raw.get("totalScore", 0.0)),
        max_score=float(raw.get("maxScore", 0.0)),
        first_recalled_at=raw.get("firstRecalledAt", ""),
        last_recalled_at=raw.get("lastRecalledAt", ""),
        query_hashes=list(raw.get("queryHashes", [])),
        recall_days=list(raw.get("recallDays", [])),
        concept_tags=list(raw.get("conceptTags", [])),
        # 新版字段，旧版无，默认值兼容
        daily_count=int(raw.get("dailyCount", 0)),
        grounded_count=int(raw.get("groundedCount", 0)),
        claim_hash=raw.get("claimHash", None),
        # 可选字段，不存在时为 None
        promoted_at=raw.get("promotedAt", None),
    )


# ── 核心读取函数 ───────────────────────────────────────────────────────────────

def read_shortterm(
    probe: ProbeResult,
) -> ShortTermStore | ShortTermReadError:
    """
    读取并解析短期记忆文件。

    Args:
        probe: probe_workspace() 的返回值，提供实际文件路径。

    Returns:
        ShortTermStore: 解析成功
        ShortTermReadError: 失败（文件不存在 / JSON 损坏）
    """
    if probe.shortterm_path is None:
        return ShortTermReadError(
            error_code="file_not_found",
            message="短期记忆文件不存在，Memory Search 可能未配置 embedding provider。",
            path=str(probe.workspace_dir),
        )

    path = probe.shortterm_path
    return _read_from_path(path)


def read_shortterm_from_path(path: Path) -> ShortTermStore | ShortTermReadError:
    """
    直接从路径读取，供测试使用。

    Args:
        path: short-term-recall.json 的绝对路径。
    """
    return _read_from_path(path)


def _read_from_path(path: Path) -> ShortTermStore | ShortTermReadError:
    """内部实现：从给定路径读取并解析。"""
    if not path.exists():
        return ShortTermReadError(
            error_code="file_not_found",
            message=f"文件不存在：{path}",
            path=str(path),
        )

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        return ShortTermReadError(
            error_code="unknown",
            message=f"文件读取失败：{e}",
            path=str(path),
        )

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return ShortTermReadError(
            error_code="json_invalid",
            message=f"JSON 格式错误：{e}",
            path=str(path),
        )

    if not isinstance(data, dict):
        return ShortTermReadError(
            error_code="json_invalid",
            message="JSON 顶层结构不是对象",
            path=str(path),
        )

    # 解析 entries
    raw_entries = data.get("entries", {})
    if not isinstance(raw_entries, dict):
        raw_entries = {}

    entries: list[ShortTermEntry] = []
    for raw_entry in raw_entries.values():
        if not isinstance(raw_entry, dict):
            continue
        entry = _parse_entry(raw_entry)
        if entry is not None:
            entries.append(entry)

    return ShortTermStore(
        version=int(data.get("version", 1)),
        updated_at=data.get("updatedAt", ""),
        entries=entries,
    )

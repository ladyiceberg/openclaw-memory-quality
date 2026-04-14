from __future__ import annotations
"""
shortterm_writer.py · short-term-recall.json 重建（删除指定 key）

从 JSON 对象的 entries 字典中移除指定 key，重建 JSON 文本。

设计要点：
  1. 不修改结构，只移除 entries 中的指定 key
  2. 更新 updatedAt 为当前时间（与 OpenClaw 写入行为一致）
  3. 保留 version 不变
  4. 不做 IO；IO（备份 + 原子写入 + 加锁）由调用方负责
  5. 序列化保持可读格式（indent=2），与 OpenClaw 输出格式一致

函数签名：
  build_cleaned_json(original_json, keys_to_delete) → (new_json_str, stats)
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class ShorttermCleanupStats:
    """短期记忆清理统计。"""
    deleted: int          # 实际删除的条目数
    kept: int             # 保留的条目数
    total_before: int     # 清理前总条目数
    backup_path: Optional[str] = None


# ── 自定义异常 ────────────────────────────────────────────────────────────────

class ShorttermWriteError(Exception):
    """短期记忆重建失败。"""
    pass


# ── 核心函数 ───────────────────────────────────────────────────────────────────

def build_cleaned_json(
    original_json: str,
    keys_to_delete: set[str],
    now_iso: Optional[str] = None,
) -> tuple[str, ShorttermCleanupStats]:
    """
    从 short-term-recall.json 文本中删除指定 key，重建 JSON 文本。

    Args:
        original_json  : 原始 JSON 文本
        keys_to_delete : 要删除的 entry key 集合
                         格式：如 "memory:memory/2026-04-09.md:1:35"
        now_iso        : 写入 updatedAt 的时间（ISO 8601 字符串）；
                         不传则使用当前 UTC 时间（测试可注入以保证确定性）

    Returns:
        (new_json_str, stats)
        new_json_str : 重建后的 JSON 文本（末尾带换行符）
        stats        : 删除/保留统计

    Raises:
        ShorttermWriteError: JSON 格式无效或顶层结构不符合预期
    """
    # ── 解析 ───────────────────────────────────────────────────────────────────
    try:
        data = json.loads(original_json)
    except json.JSONDecodeError as e:
        raise ShorttermWriteError(f"JSON 格式无效：{e}") from e

    if not isinstance(data, dict):
        raise ShorttermWriteError("顶层结构不是 JSON 对象")

    entries = data.get("entries", {})
    if not isinstance(entries, dict):
        raise ShorttermWriteError("entries 字段不是 JSON 对象")

    total_before = len(entries)

    # ── 过滤 ───────────────────────────────────────────────────────────────────
    new_entries = {k: v for k, v in entries.items() if k not in keys_to_delete}
    deleted = total_before - len(new_entries)
    kept = len(new_entries)

    # ── 重建 ───────────────────────────────────────────────────────────────────
    new_data = dict(data)             # 浅拷贝，保留 version 等字段
    new_data["entries"] = new_entries

    # 更新 updatedAt（与 OpenClaw 写入行为一致）
    if now_iso is None:
        now_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    new_data["updatedAt"] = now_iso

    # 序列化（indent=2 与 OpenClaw 输出格式一致）
    new_json = json.dumps(new_data, ensure_ascii=False, indent=2) + "\n"

    stats = ShorttermCleanupStats(
        deleted=deleted,
        kept=kept,
        total_before=total_before,
    )

    return new_json, stats

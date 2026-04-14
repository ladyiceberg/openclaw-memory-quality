from __future__ import annotations
"""
session_store.py · 审计结果本地持久化

解决 memory_longterm_audit_oc() 和 memory_longterm_cleanup_oc() 之间的
状态依赖：audit 生成 report_id，cleanup 凭 report_id 取审计结果，
不依赖 Claude 在对话上下文中记住细节。

存储：~/.openclaw-memhealth/session.db（SQLite）
保留：最近 MAX_REPORTS_KEPT 次，自动清理旧记录

report_id 格式：字符串 "audit_{timestamp_ms}"（如 "audit_1712534892000"）
"""

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ── 常量 ──────────────────────────────────────────────────────────────────────

MAX_REPORTS_KEPT = 10   # 最多保留最近 N 次审计


def get_db_path() -> Path:
    """数据库文件路径：~/.openclaw-memhealth/session.db"""
    db_dir = Path.home() / ".openclaw-memhealth"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "session.db"


# ── 数据库初始化 ───────────────────────────────────────────────────────────────

def _get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """获取数据库连接，自动创建表结构。db_path 可注入（测试用）。"""
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_reports (
            report_id   TEXT PRIMARY KEY,
            created_at  REAL NOT NULL,
            workspace   TEXT NOT NULL,
            total_items INTEGER NOT NULL,
            payload     TEXT NOT NULL    -- JSON: full LongtermAuditResult
        );
    """)
    conn.commit()


# ── 写入 ──────────────────────────────────────────────────────────────────────

def save_audit_report(
    report_id: str,
    workspace: str,
    total_items: int,
    payload: dict,
    db_path: Optional[Path] = None,
) -> None:
    """
    保存一次审计结果。自动清理超过 MAX_REPORTS_KEPT 的旧记录。

    Args:
        report_id  : 唯一 ID，格式 "audit_{timestamp_ms}"
        workspace  : workspace 路径（便于查询归属）
        total_items: 审计的 item 总数
        payload    : 完整审计结果 dict（可被 JSON 序列化）
        db_path    : 测试用，覆盖默认 DB 路径
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO audit_reports
               (report_id, created_at, workspace, total_items, payload)
               VALUES (?, ?, ?, ?, ?)""",
            (report_id, time.time(), workspace, total_items, json.dumps(payload)),
        )
        conn.commit()

        # 清理旧记录：保留最近 MAX_REPORTS_KEPT 条
        conn.execute(
            """DELETE FROM audit_reports WHERE report_id NOT IN (
                SELECT report_id FROM audit_reports
                ORDER BY created_at DESC LIMIT ?
            )""",
            (MAX_REPORTS_KEPT,),
        )
        conn.commit()
    finally:
        conn.close()


# ── 读取 ──────────────────────────────────────────────────────────────────────

def load_audit_report(
    report_id: str,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """
    按 report_id 读取审计结果。不存在时返回 None。

    Returns:
        payload dict（与 save_audit_report 写入的一致），或 None
    """
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT payload FROM audit_reports WHERE report_id = ?",
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])
    finally:
        conn.close()


def load_latest_audit_report(
    db_path: Optional[Path] = None,
) -> Optional[tuple]:
    """
    读取最近一次审计结果。没有记录时返回 None。

    Returns:
        (report_id, payload dict)，或 None
    """
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT report_id, payload FROM audit_reports ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return row["report_id"], json.loads(row["payload"])
    finally:
        conn.close()


def list_audit_reports(
    db_path: Optional[Path] = None,
) -> list:
    """
    列出所有已保存的审计报告摘要（不含 payload）。
    按时间倒序。
    """
    conn = _get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT report_id, created_at, workspace, total_items
               FROM audit_reports ORDER BY created_at DESC"""
        ).fetchall()
        return [
            {
                "report_id": r["report_id"],
                "created_at": r["created_at"],
                "workspace": r["workspace"],
                "total_items": r["total_items"],
            }
            for r in rows
        ]
    finally:
        conn.close()


# ── report_id 生成 ─────────────────────────────────────────────────────────────

def make_report_id() -> str:
    """
    生成唯一 report_id，格式：audit_{timestamp_ms}
    例：audit_1712534892000
    """
    ts_ms = int(time.time() * 1000)
    return f"audit_{ts_ms}"

from __future__ import annotations
"""
session_store.py · 审计结果本地持久化

解决 memory_longterm_audit_oc() 和 memory_longterm_cleanup_oc() 之间的
状态依赖：audit 生成 report_id，cleanup 凭 report_id 取审计结果，
不依赖 Claude 在对话上下文中记住细节。

同时存储各工具的最新运行结果，供 Dashboard 聚合展示：
  - audit_reports     : longterm_audit 完整结果（by report_id）
  - soul_snapshots    : soul_check 快照 + risk_level
  - health_snapshots  : health_check 短期记忆统计 + 诊断分
  - promotion_snapshots: promotion_audit 关卡统计 + 候选列表
  - config_snapshots  : config_doctor 配置问题列表

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

        CREATE TABLE IF NOT EXISTS soul_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace   TEXT NOT NULL,
            checked_at  REAL NOT NULL,
            char_count  INTEGER NOT NULL,
            content_hash TEXT NOT NULL,  -- SHA256 of file content
            directive_count INTEGER NOT NULL,  -- must/always/never count
            sections    TEXT NOT NULL,   -- JSON: list of section names found
            risk_level  TEXT NOT NULL DEFAULT 'ok'  -- ok/low/medium/high
        );

        CREATE TABLE IF NOT EXISTS health_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace       TEXT NOT NULL,
            checked_at      REAL NOT NULL,
            payload         TEXT NOT NULL  -- JSON: health check stats
        );

        CREATE TABLE IF NOT EXISTS promotion_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace   TEXT NOT NULL,
            checked_at  REAL NOT NULL,
            payload     TEXT NOT NULL  -- JSON: promotion audit result
        );

        CREATE TABLE IF NOT EXISTS config_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace   TEXT NOT NULL,
            checked_at  REAL NOT NULL,
            payload     TEXT NOT NULL  -- JSON: config doctor result
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


# ── SOUL.md 快照读写 ───────────────────────────────────────────────────────────

def save_soul_snapshot(
    workspace: str,
    char_count: int,
    content_hash: str,
    directive_count: int,
    sections: list,
    risk_level: str = "ok",
    db_path: Optional[Path] = None,
) -> None:
    """
    保存 SOUL.md 健康检查快照，供下次对比稳定性使用。

    Args:
        workspace       : workspace 路径
        char_count      : 文件字符数
        content_hash    : 文件内容 SHA256
        directive_count : must/always/never 等强指令词数量
        sections        : 检测到的标准 section 名称列表
        risk_level      : 风险等级 ok/low/medium/high
        db_path         : 测试用，覆盖默认 DB 路径
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO soul_snapshots
               (workspace, checked_at, char_count, content_hash,
                directive_count, sections, risk_level)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (workspace, time.time(), char_count, content_hash,
             directive_count, json.dumps(sections), risk_level),
        )
        conn.commit()
        # 只保留该 workspace 最近 20 次快照
        conn.execute(
            """DELETE FROM soul_snapshots WHERE workspace = ? AND id NOT IN (
                SELECT id FROM soul_snapshots
                WHERE workspace = ?
                ORDER BY checked_at DESC LIMIT 20
            )""",
            (workspace, workspace),
        )
        conn.commit()
    finally:
        conn.close()


def load_last_soul_snapshot(
    workspace: str,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """
    读取该 workspace 最近一次 SOUL.md 快照。没有记录时返回 None。

    Returns:
        dict with keys: checked_at, char_count, content_hash,
                        directive_count, sections (list), risk_level
    """
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            """SELECT checked_at, char_count, content_hash, directive_count,
                      sections, risk_level
               FROM soul_snapshots
               WHERE workspace = ?
               ORDER BY checked_at DESC LIMIT 1""",
            (workspace,),
        ).fetchone()
        if row is None:
            return None
        return {
            "checked_at":      row["checked_at"],
            "char_count":      row["char_count"],
            "content_hash":    row["content_hash"],
            "directive_count": row["directive_count"],
            "sections":        json.loads(row["sections"]),
            "risk_level":      row["risk_level"],
        }
    finally:
        conn.close()


# ── health_check 快照读写 ──────────────────────────────────────────────────────

def save_health_snapshot(
    workspace: str,
    payload: dict,
    db_path: Optional[Path] = None,
) -> None:
    """
    保存 health_check 的统计结果，供 Dashboard 读取。

    payload 结构：
    {
        "shortterm_total": int,
        "zombie_count": int,
        "zombie_ratio": float,
        "fp_count": int,
        "fp_ratio": float,
        "retrieval_health": int,    # 0-100
        "promotion_risk": int,      # 0-100
        "fts_degradation": bool,
        "longterm_sections": int,   # 若无则 0
        "longterm_items": int,      # 若无则 0
    }
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO health_snapshots (workspace, checked_at, payload)
               VALUES (?, ?, ?)""",
            (workspace, time.time(), json.dumps(payload)),
        )
        conn.commit()
        # 只保留最近 10 次
        conn.execute(
            """DELETE FROM health_snapshots WHERE workspace = ? AND id NOT IN (
                SELECT id FROM health_snapshots
                WHERE workspace = ?
                ORDER BY checked_at DESC LIMIT 10
            )""",
            (workspace, workspace),
        )
        conn.commit()
    finally:
        conn.close()


def load_last_health_snapshot(
    workspace: str,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """读取该 workspace 最近一次 health_check 快照。"""
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            """SELECT checked_at, payload FROM health_snapshots
               WHERE workspace = ? ORDER BY checked_at DESC LIMIT 1""",
            (workspace,),
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload"])
        data["checked_at"] = row["checked_at"]
        return data
    finally:
        conn.close()


# ── promotion_audit 快照读写 ───────────────────────────────────────────────────

def save_promotion_snapshot(
    workspace: str,
    payload: dict,
    db_path: Optional[Path] = None,
) -> None:
    """
    保存 promotion_audit 的结果，供 Dashboard 读取。

    payload 结构：
    {
        "total_unpromotted": int,
        "top_n": int,
        "pass_count": int,
        "skip_count": int,
        "flag_count": int,
        "candidates": [
            {
                "path": str,
                "start": int,
                "end": int,
                "composite": float,
                "verdict": str,           # pass/skip/flag
                "skip_reason": str|None,
                "flag_reason": str|None,
            },
            ...
        ],
        "llm_eval": {...} | None,          # 可选，use_llm=True 时有
    }
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO promotion_snapshots (workspace, checked_at, payload)
               VALUES (?, ?, ?)""",
            (workspace, time.time(), json.dumps(payload)),
        )
        conn.commit()
        conn.execute(
            """DELETE FROM promotion_snapshots WHERE workspace = ? AND id NOT IN (
                SELECT id FROM promotion_snapshots
                WHERE workspace = ?
                ORDER BY checked_at DESC LIMIT 10
            )""",
            (workspace, workspace),
        )
        conn.commit()
    finally:
        conn.close()


def load_last_promotion_snapshot(
    workspace: str,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """读取该 workspace 最近一次 promotion_audit 快照。"""
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            """SELECT checked_at, payload FROM promotion_snapshots
               WHERE workspace = ? ORDER BY checked_at DESC LIMIT 1""",
            (workspace,),
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload"])
        data["checked_at"] = row["checked_at"]
        return data
    finally:
        conn.close()


# ── config_doctor 快照读写 ─────────────────────────────────────────────────────

def save_config_snapshot(
    workspace: str,
    payload: dict,
    db_path: Optional[Path] = None,
) -> None:
    """
    保存 config_doctor 的诊断结果，供 Dashboard 读取。

    payload 结构：
    {
        "all_good": bool,
        "issues": [
            {"code": str, "triggered": bool, "signal_data": dict},
            ...
        ]
    }
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO config_snapshots (workspace, checked_at, payload)
               VALUES (?, ?, ?)""",
            (workspace, time.time(), json.dumps(payload)),
        )
        conn.commit()
        conn.execute(
            """DELETE FROM config_snapshots WHERE workspace = ? AND id NOT IN (
                SELECT id FROM config_snapshots
                WHERE workspace = ?
                ORDER BY checked_at DESC LIMIT 5
            )""",
            (workspace, workspace),
        )
        conn.commit()
    finally:
        conn.close()


def load_last_config_snapshot(
    workspace: str,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """读取该 workspace 最近一次 config_doctor 快照。"""
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            """SELECT checked_at, payload FROM config_snapshots
               WHERE workspace = ? ORDER BY checked_at DESC LIMIT 1""",
            (workspace,),
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload"])
        data["checked_at"] = row["checked_at"]
        return data
    finally:
        conn.close()


# ── Dashboard 聚合读取 ─────────────────────────────────────────────────────────

def load_dashboard_data(
    workspace: str,
    db_path: Optional[Path] = None,
) -> dict:
    """
    一次性读取 Dashboard 所需的全部最新数据。

    Returns:
        {
            "longterm_audit": (report_id, payload) | None,
            "soul":           snapshot_dict | None,
            "health":         snapshot_dict | None,
            "promotion":      snapshot_dict | None,
            "config":         snapshot_dict | None,
        }
    """
    conn = _get_connection(db_path)
    try:
        # longterm audit：按 workspace 过滤取最近一次
        audit_row = conn.execute(
            """SELECT report_id, payload FROM audit_reports
               WHERE workspace = ? ORDER BY created_at DESC LIMIT 1""",
            (workspace,),
        ).fetchone()
        longterm = None
        if audit_row:
            longterm = (audit_row["report_id"], json.loads(audit_row["payload"]))

        def _load_latest(table: str) -> Optional[dict]:
            row = conn.execute(
                f"""SELECT checked_at, payload FROM {table}
                    WHERE workspace = ? ORDER BY checked_at DESC LIMIT 1""",
                (workspace,),
            ).fetchone()
            if row is None:
                return None
            data = json.loads(row["payload"])
            data["checked_at"] = row["checked_at"]
            return data

        soul_row = conn.execute(
            """SELECT checked_at, char_count, content_hash, directive_count,
                      sections, risk_level
               FROM soul_snapshots WHERE workspace = ?
               ORDER BY checked_at DESC LIMIT 1""",
            (workspace,),
        ).fetchone()
        soul = None
        if soul_row:
            soul = {
                "checked_at":      soul_row["checked_at"],
                "char_count":      soul_row["char_count"],
                "content_hash":    soul_row["content_hash"],
                "directive_count": soul_row["directive_count"],
                "sections":        json.loads(soul_row["sections"]),
                "risk_level":      soul_row["risk_level"],
            }

        return {
            "longterm_audit": longterm,
            "soul":           soul,
            "health":         _load_latest("health_snapshots"),
            "promotion":      _load_latest("promotion_snapshots"),
            "config":         _load_latest("config_snapshots"),
        }
    finally:
        conn.close()

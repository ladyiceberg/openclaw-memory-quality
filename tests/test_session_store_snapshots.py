"""
test_session_store_snapshots.py · 新增快照存储的单元测试

覆盖：health_snapshot、promotion_snapshot、config_snapshot、
      soul_snapshot（risk_level 新增字段）、load_dashboard_data 聚合。
全部使用临时 db_path，不写入真实 ~/.openclaw-memhealth/。
"""
import tempfile
from pathlib import Path

import pytest

from src.session_store import (
    load_dashboard_data,
    load_last_config_snapshot,
    load_last_health_snapshot,
    load_last_promotion_snapshot,
    load_last_soul_snapshot,
    save_config_snapshot,
    save_health_snapshot,
    save_promotion_snapshot,
    save_soul_snapshot,
)


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _tmp_db() -> Path:
    td = tempfile.mkdtemp()
    return Path(td) / "test.db"


WORKSPACE = "/tmp/test_workspace"

HEALTH_PAYLOAD = {
    "shortterm_total":   100,
    "zombie_count":      8,
    "zombie_ratio":      0.08,
    "fp_count":          12,
    "fp_ratio":          0.12,
    "retrieval_health":  72,
    "promotion_risk":    35,
    "fts_degradation":   False,
    "longterm_sections": 5,
    "longterm_items":    42,
}

PROMOTION_PAYLOAD = {
    "total_unpromotted": 50,
    "top_n": 10,
    "pass_count": 7,
    "skip_count": 2,
    "flag_count": 1,
    "candidates": [
        {"path": "memory/f.md", "start": 1, "end": 5,
         "composite": 0.75, "verdict": "pass",
         "skip_reason": None, "flag_reason": None},
        {"path": "memory/g.md", "start": 3, "end": 8,
         "composite": 0.60, "verdict": "skip",
         "skip_reason": "source_deleted", "flag_reason": None},
    ],
    "llm_eval": None,
}

CONFIG_PAYLOAD_ISSUES = {
    "all_good": False,
    "issues": [
        {"code": "fts", "triggered": True,
         "signal_data": {"avg": 0.38, "empty_pct": 52.0}},
    ],
}

CONFIG_PAYLOAD_GOOD = {
    "all_good": True,
    "issues": [],
}


# ── health_snapshot ────────────────────────────────────────────────────────────

class TestHealthSnapshot:
    def test_save_and_load(self):
        """存储后可正确读取。"""
        db = _tmp_db()
        save_health_snapshot(WORKSPACE, HEALTH_PAYLOAD, db_path=db)
        result = load_last_health_snapshot(WORKSPACE, db_path=db)
        assert result is not None
        assert result["shortterm_total"] == 100
        assert result["retrieval_health"] == 72
        assert result["fts_degradation"] is False

    def test_checked_at_populated(self):
        """结果中包含 checked_at 时间戳。"""
        db = _tmp_db()
        save_health_snapshot(WORKSPACE, HEALTH_PAYLOAD, db_path=db)
        result = load_last_health_snapshot(WORKSPACE, db_path=db)
        assert "checked_at" in result
        assert result["checked_at"] > 0

    def test_load_returns_none_when_empty(self):
        """无记录时返回 None。"""
        db = _tmp_db()
        assert load_last_health_snapshot(WORKSPACE, db_path=db) is None

    def test_load_latest_of_multiple(self):
        """多次存储时返回最新一条。"""
        db = _tmp_db()
        payload_old = {**HEALTH_PAYLOAD, "retrieval_health": 50}
        payload_new = {**HEALTH_PAYLOAD, "retrieval_health": 80}
        save_health_snapshot(WORKSPACE, payload_old, db_path=db)
        save_health_snapshot(WORKSPACE, payload_new, db_path=db)
        result = load_last_health_snapshot(WORKSPACE, db_path=db)
        assert result["retrieval_health"] == 80

    def test_different_workspace_isolated(self):
        """不同 workspace 的数据相互隔离。"""
        db = _tmp_db()
        save_health_snapshot("/ws_a", {**HEALTH_PAYLOAD, "retrieval_health": 60}, db_path=db)
        save_health_snapshot("/ws_b", {**HEALTH_PAYLOAD, "retrieval_health": 90}, db_path=db)
        assert load_last_health_snapshot("/ws_a", db_path=db)["retrieval_health"] == 60
        assert load_last_health_snapshot("/ws_b", db_path=db)["retrieval_health"] == 90

    def test_retention_limit_10(self):
        """最多保留 10 条。"""
        db = _tmp_db()
        for i in range(15):
            save_health_snapshot(WORKSPACE, {**HEALTH_PAYLOAD, "retrieval_health": i}, db_path=db)
        # 应该只有最新 10 条（验证不崩溃，latest 是最新的）
        result = load_last_health_snapshot(WORKSPACE, db_path=db)
        assert result["retrieval_health"] == 14


# ── promotion_snapshot ─────────────────────────────────────────────────────────

class TestPromotionSnapshot:
    def test_save_and_load(self):
        """存储后可正确读取。"""
        db = _tmp_db()
        save_promotion_snapshot(WORKSPACE, PROMOTION_PAYLOAD, db_path=db)
        result = load_last_promotion_snapshot(WORKSPACE, db_path=db)
        assert result is not None
        assert result["pass_count"] == 7
        assert result["skip_count"] == 2
        assert result["flag_count"] == 1

    def test_candidates_preserved(self):
        """candidates 列表完整保存。"""
        db = _tmp_db()
        save_promotion_snapshot(WORKSPACE, PROMOTION_PAYLOAD, db_path=db)
        result = load_last_promotion_snapshot(WORKSPACE, db_path=db)
        assert len(result["candidates"]) == 2
        assert result["candidates"][0]["verdict"] == "pass"
        assert result["candidates"][1]["skip_reason"] == "source_deleted"

    def test_llm_eval_none_preserved(self):
        """llm_eval=None 时正确保存/读取。"""
        db = _tmp_db()
        save_promotion_snapshot(WORKSPACE, PROMOTION_PAYLOAD, db_path=db)
        result = load_last_promotion_snapshot(WORKSPACE, db_path=db)
        assert result["llm_eval"] is None

    def test_llm_eval_with_data(self):
        """llm_eval 有数据时正确保存/读取。"""
        db = _tmp_db()
        payload = {**PROMOTION_PAYLOAD, "llm_eval": {
            "long_term_count": 3,
            "one_time_count": 2,
            "uncertain_count": 1,
        }}
        save_promotion_snapshot(WORKSPACE, payload, db_path=db)
        result = load_last_promotion_snapshot(WORKSPACE, db_path=db)
        assert result["llm_eval"]["long_term_count"] == 3

    def test_load_returns_none_when_empty(self):
        db = _tmp_db()
        assert load_last_promotion_snapshot(WORKSPACE, db_path=db) is None

    def test_checked_at_populated(self):
        db = _tmp_db()
        save_promotion_snapshot(WORKSPACE, PROMOTION_PAYLOAD, db_path=db)
        result = load_last_promotion_snapshot(WORKSPACE, db_path=db)
        assert result["checked_at"] > 0


# ── config_snapshot ────────────────────────────────────────────────────────────

class TestConfigSnapshot:
    def test_save_issues_and_load(self):
        """有问题时正确存储读取。"""
        db = _tmp_db()
        save_config_snapshot(WORKSPACE, CONFIG_PAYLOAD_ISSUES, db_path=db)
        result = load_last_config_snapshot(WORKSPACE, db_path=db)
        assert result is not None
        assert result["all_good"] is False
        assert len(result["issues"]) == 1
        assert result["issues"][0]["code"] == "fts"

    def test_save_all_good_and_load(self):
        """全部健康时正确存储。"""
        db = _tmp_db()
        save_config_snapshot(WORKSPACE, CONFIG_PAYLOAD_GOOD, db_path=db)
        result = load_last_config_snapshot(WORKSPACE, db_path=db)
        assert result["all_good"] is True
        assert result["issues"] == []

    def test_load_returns_none_when_empty(self):
        db = _tmp_db()
        assert load_last_config_snapshot(WORKSPACE, db_path=db) is None

    def test_checked_at_populated(self):
        db = _tmp_db()
        save_config_snapshot(WORKSPACE, CONFIG_PAYLOAD_GOOD, db_path=db)
        result = load_last_config_snapshot(WORKSPACE, db_path=db)
        assert result["checked_at"] > 0

    def test_retention_limit_5(self):
        """最多保留 5 条。"""
        db = _tmp_db()
        for i in range(8):
            save_config_snapshot(WORKSPACE, {"all_good": True, "issues": [], "idx": i}, db_path=db)
        result = load_last_config_snapshot(WORKSPACE, db_path=db)
        assert result["idx"] == 7  # 最新的


# ── soul_snapshot（risk_level 新字段）─────────────────────────────────────────

class TestSoulSnapshotRiskLevel:
    def test_risk_level_saved_and_loaded(self):
        """risk_level 正确存储和读取。"""
        db = _tmp_db()
        save_soul_snapshot(
            workspace=WORKSPACE,
            char_count=1200,
            content_hash="abc123",
            directive_count=3,
            sections=["Core Truths", "Boundaries"],
            risk_level="medium",
            db_path=db,
        )
        result = load_last_soul_snapshot(WORKSPACE, db_path=db)
        assert result is not None
        assert result["risk_level"] == "medium"

    def test_risk_level_default_ok(self):
        """不传 risk_level 时默认 ok。"""
        db = _tmp_db()
        save_soul_snapshot(
            workspace=WORKSPACE,
            char_count=1000,
            content_hash="xyz",
            directive_count=1,
            sections=["Core Truths"],
            db_path=db,
        )
        result = load_last_soul_snapshot(WORKSPACE, db_path=db)
        assert result["risk_level"] == "ok"

    def test_all_risk_levels(self):
        """四种 risk_level 都可以存储。"""
        for level in ["ok", "low", "medium", "high"]:
            db = _tmp_db()
            save_soul_snapshot(
                workspace=WORKSPACE,
                char_count=1000,
                content_hash=f"hash_{level}",
                directive_count=1,
                sections=[],
                risk_level=level,
                db_path=db,
            )
            result = load_last_soul_snapshot(WORKSPACE, db_path=db)
            assert result["risk_level"] == level


# ── load_dashboard_data 聚合 ───────────────────────────────────────────────────

class TestLoadDashboardData:
    def test_all_none_when_empty(self):
        """数据库为空时，所有字段都是 None。"""
        db = _tmp_db()
        result = load_dashboard_data(WORKSPACE, db_path=db)
        assert result["longterm_audit"] is None
        assert result["soul"] is None
        assert result["health"] is None
        assert result["promotion"] is None
        assert result["config"] is None

    def test_health_populated(self):
        """存入 health 后，dashboard_data 包含 health 数据。"""
        db = _tmp_db()
        save_health_snapshot(WORKSPACE, HEALTH_PAYLOAD, db_path=db)
        result = load_dashboard_data(WORKSPACE, db_path=db)
        assert result["health"] is not None
        assert result["health"]["retrieval_health"] == 72

    def test_promotion_populated(self):
        """存入 promotion 后，dashboard_data 包含 promotion 数据。"""
        db = _tmp_db()
        save_promotion_snapshot(WORKSPACE, PROMOTION_PAYLOAD, db_path=db)
        result = load_dashboard_data(WORKSPACE, db_path=db)
        assert result["promotion"] is not None
        assert result["promotion"]["pass_count"] == 7

    def test_config_populated(self):
        """存入 config 后，dashboard_data 包含 config 数据。"""
        db = _tmp_db()
        save_config_snapshot(WORKSPACE, CONFIG_PAYLOAD_GOOD, db_path=db)
        result = load_dashboard_data(WORKSPACE, db_path=db)
        assert result["config"] is not None
        assert result["config"]["all_good"] is True

    def test_soul_populated_with_risk_level(self):
        """存入 soul snapshot 后，dashboard_data 包含 risk_level。"""
        db = _tmp_db()
        save_soul_snapshot(
            workspace=WORKSPACE,
            char_count=1500,
            content_hash="soul_hash",
            directive_count=4,
            sections=["Core Truths", "Boundaries", "Vibe"],
            risk_level="low",
            db_path=db,
        )
        result = load_dashboard_data(WORKSPACE, db_path=db)
        assert result["soul"] is not None
        assert result["soul"]["risk_level"] == "low"
        assert result["soul"]["char_count"] == 1500

    def test_workspace_isolation(self):
        """不同 workspace 数据不互相污染。"""
        db = _tmp_db()
        save_health_snapshot("/ws_a", {**HEALTH_PAYLOAD, "retrieval_health": 60}, db_path=db)
        save_health_snapshot("/ws_b", {**HEALTH_PAYLOAD, "retrieval_health": 90}, db_path=db)

        data_a = load_dashboard_data("/ws_a", db_path=db)
        data_b = load_dashboard_data("/ws_b", db_path=db)

        assert data_a["health"]["retrieval_health"] == 60
        assert data_b["health"]["retrieval_health"] == 90
        assert data_a["promotion"] is None
        assert data_b["promotion"] is None

    def test_all_sections_populated(self):
        """所有数据都存入后，dashboard_data 全部非 None。"""
        from src.session_store import save_audit_report, make_report_id
        db = _tmp_db()

        # 存入 longterm audit
        report_id = make_report_id()
        save_audit_report(
            report_id=report_id,
            workspace=WORKSPACE,
            total_items=10,
            payload={"total_items": 10, "items": []},
            db_path=db,
        )
        save_health_snapshot(WORKSPACE, HEALTH_PAYLOAD, db_path=db)
        save_promotion_snapshot(WORKSPACE, PROMOTION_PAYLOAD, db_path=db)
        save_config_snapshot(WORKSPACE, CONFIG_PAYLOAD_GOOD, db_path=db)
        save_soul_snapshot(
            workspace=WORKSPACE,
            char_count=1000,
            content_hash="h",
            directive_count=2,
            sections=["Core Truths"],
            risk_level="ok",
            db_path=db,
        )

        result = load_dashboard_data(WORKSPACE, db_path=db)
        assert result["longterm_audit"] is not None
        assert result["health"] is not None
        assert result["promotion"] is not None
        assert result["config"] is not None
        assert result["soul"] is not None

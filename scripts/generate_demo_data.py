#!/usr/bin/env python3
"""
generate_demo_data.py · 生成演示用看板数据

用法（在项目根目录执行）：
    python3 scripts/generate_demo_data.py [--open] [--lang en|zh]

选项：
    --open      生成后自动在浏览器打开看板
    --lang      看板语言，默认 en（用于 README 截图）
    --ws        写入的 workspace 路径，默认 /demo/openclaw-workspace

角色设定：
    Mavis，产品经理 + 业余开发者，用 OpenClaw 3 个月。
    记忆里有后端开发、产品工作、生活习惯、读书笔记、旅行踩坑…

    最近发生了什么：
    - 把旧 OAuth2 密码流重构成了 PKCE 方案，删了 src/auth/legacy/ 目录
    - 一次 debug 会话留下了大量临时 recall
    - FTS 字面匹配带来了一批假阳性条目
    综合健康分约 70 分——有问题，但有具体的改善路径。
"""

import argparse
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.session_store import (
    make_report_id,
    save_audit_report,
    save_config_snapshot,
    save_health_snapshot,
    save_promotion_snapshot,
    save_soul_snapshot,
    load_dashboard_data,
)
from src.dashboard import generate_dashboard_html, open_dashboard


# ── 固定时间基准（让看板显示"2 小时前"等自然时间）──────────────────────────
_NOW = time.time()
_2H_AGO  = _NOW - 7_200
_3H_AGO  = _NOW - 10_800
_1D_AGO  = _NOW - 86_400
_3D_AGO  = _NOW - 259_200


def _ts(offset_secs: float = 0.0) -> float:
    return _NOW - offset_secs


# ── Section 1：长期记忆审计数据 ───────────────────────────────────────────────

LONGTERM_ITEMS = [
    # ── Keep 18 条 ─────────────────────────────────────────────────────────────

    # 技术知识（6）
    {
        "snippet": "Redis pool bumped to 50 after load test — default 10 caused queue buildup at 200rps",
        "source_path": "memory/2026-02-14.md", "source_start": 12, "source_end": 15,
        "score": 0.934, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-14.md:12:15",
    },
    {
        "snippet": "JWT: 15min access + 7-day refresh, both httpOnly cookies, never localStorage — XSS protection",
        "source_path": "memory/2026-02-21.md", "source_start": 3, "source_end": 6,
        "score": 0.921, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-21.md:3:6",
    },
    {
        "snippet": "Postgres GIN index on tags[] column: query time dropped from 840ms to 11ms on 2M rows",
        "source_path": "memory/2026-03-03.md", "source_start": 7, "source_end": 11,
        "score": 0.908, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-03.md:7:11",
    },
    {
        "snippet": "Docker healthcheck needs 30s grace period — slow-starting FastAPI + Alembic combo",
        "source_path": "memory/2026-03-10.md", "source_start": 22, "source_end": 25,
        "score": 0.887, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-10.md:22:25",
    },
    {
        "snippet": "CORS: allow_credentials=True requires explicit origin list, wildcard * breaks it silently",
        "source_path": "memory/2026-03-17.md", "source_start": 5, "source_end": 8,
        "score": 0.875, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-17.md:5:8",
    },
    {
        "snippet": "Alembic auto-migrates on startup — never DROP TABLE manually in prod, use migration scripts",
        "source_path": "memory/2026-01-28.md", "source_start": 18, "source_end": 21,
        "score": 0.862, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-28.md:18:21",
    },

    # 工作/产品（3）
    {
        "snippet": "Q2 OKR: NPS target 32→45. Lever is retention, not acquisition — focus on week-3 drop-off",
        "source_path": "memory/2026-03-01.md", "source_start": 1, "source_end": 4,
        "score": 0.913, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-01.md:1:4",
    },
    {
        "snippet": "Design review: share Figma link 24h before meeting, not in it. Late share = no feedback",
        "source_path": "memory/2026-02-08.md", "source_start": 9, "source_end": 12,
        "score": 0.856, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-08.md:9:12",
    },
    {
        "snippet": "Async standups (Loom video) work better for distributed team — cuts timezone friction",
        "source_path": "memory/2026-01-15.md", "source_start": 14, "source_end": 17,
        "score": 0.841, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-15.md:14:17",
    },

    # 生活习惯（4）
    {
        "snippet": "Best running time: 7-8am before humidity peaks. After 9am in summer kills pace by 30sec/km",
        "source_path": "memory/2026-02-05.md", "source_start": 3, "source_end": 5,
        "score": 0.878, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-05.md:3:5",
    },
    {
        "snippet": "Oat milk works for latte art, ruins pour-over — too sweet, mutes the floral notes completely",
        "source_path": "memory/2026-01-22.md", "source_start": 7, "source_end": 9,
        "score": 0.834, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-22.md:7:9",
    },
    {
        "snippet": "Sleep quality: no screens 1h before bed + 300mg magnesium glycinate = 90min deep sleep reliably",
        "source_path": "memory/2026-02-18.md", "source_start": 11, "source_end": 14,
        "score": 0.867, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-18.md:11:14",
    },
    {
        "snippet": "Wet market Tuesday + Friday mornings = freshest produce. Weekends overcrowded and picked over",
        "source_path": "memory/2026-01-10.md", "source_start": 2, "source_end": 4,
        "score": 0.821, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-10.md:2:4",
    },

    # 读书/学习（3）
    {
        "snippet": "Thinking Fast and Slow: under time pressure System 1 hijacks — deliberately slow irreversible decisions",
        "source_path": "memory/2026-03-08.md", "source_start": 5, "source_end": 8,
        "score": 0.895, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-08.md:5:8",
    },
    {
        "snippet": "The Mom Test: ask about past behavior, not future hypotheticals. 'Would you use X?' is useless",
        "source_path": "memory/2026-02-25.md", "source_start": 3, "source_end": 6,
        "score": 0.882, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-25.md:3:6",
    },
    {
        "snippet": "Atomic Habits: habit stacking — attach new habit to existing anchor. Morning coffee → 5min journal",
        "source_path": "memory/2026-01-30.md", "source_start": 8, "source_end": 11,
        "score": 0.871, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-30.md:8:11",
    },

    # 个人偏好/踩坑（2）
    {
        "snippet": "AirPods Pro: transparency mode + volume 1 notch = best focus-work setting in noisy cafe",
        "source_path": "memory/2026-02-12.md", "source_start": 1, "source_end": 3,
        "score": 0.829, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-12.md:1:3",
    },
    {
        "snippet": "MUJI A5 notebook beats Moleskine: less ink bleed, better price, doesn't feel precious so actually used",
        "source_path": "memory/2026-01-18.md", "source_start": 6, "source_end": 8,
        "score": 0.816, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-18.md:6:8",
    },

    # ── Review 4 条（来源不确定）─────────────────────────────────────────────

    {
        "snippet": "WebSocket reconnect: exponential backoff starting 1s, cap 30s, jitter ±20% to avoid thundering herd",
        "source_path": "src/utils/ws_helper.py", "source_start": 45, "source_end": 62,
        "score": 0.893, "v1_status": "possibly_moved", "v3_status": "ok", "action_hint": "review",
        "promotion_key": "memory:src/utils/ws_helper.py:45:62",
    },
    {
        "snippet": "Notion team space: meeting notes template pinned, use /meeting shortcut to populate",
        "source_path": "memory/2026-01-08.md", "source_start": 3, "source_end": 5,
        "score": 0.812, "v1_status": "possibly_moved", "v3_status": "ok", "action_hint": "review",
        "promotion_key": "memory:memory/2026-01-08.md:3:5",
    },
    {
        "snippet": "Timemore C2 grinder: 18 clicks for V60, 15 clicks for espresso. Adjust 1 click at a time",
        "source_path": "memory/2025-12-28.md", "source_start": 1, "source_end": 3,
        "score": 0.798, "v1_status": "possibly_moved", "v3_status": "ok", "action_hint": "review",
        "promotion_key": "memory:memory/2025-12-28.md:1:3",
    },
    {
        "snippet": "Tokyo: Yanaka for vintage shops + local soba, skip Shibuya on weekends — Shimokitazawa > Harajuku",
        "source_path": "memory/travel/tokyo-2025.md", "source_start": 8, "source_end": 12,
        "score": 0.785, "v1_status": "possibly_moved", "v3_status": "ok", "action_hint": "review",
        "promotion_key": "memory:memory/travel/tokyo-2025.md:8:12",
    },

    # ── Delete 3 条 ──────────────────────────────────────────────────────────

    {
        "snippet": "OAuth2 password grant flow for legacy /api/v1/token endpoint — client_credentials fallback",
        "source_path": "src/auth/legacy/oauth_password.py", "source_start": 1, "source_end": 38,
        "score": 0.761, "v1_status": "deleted", "v3_status": "ok", "action_hint": "delete",
        "promotion_key": "memory:src/auth/legacy/oauth_password.py:1:38",
    },
    {
        "snippet": "OAuth2 password grant setup — deprecated endpoint notes, migrate to PKCE before Q2",
        "source_path": "src/auth/legacy/oauth_password.py", "source_start": 1, "source_end": 38,
        "score": 0.758, "v1_status": "deleted", "v3_status": "duplicate_loser", "action_hint": "delete",
        "promotion_key": "memory:src/auth/legacy/oauth_password.py:1:38:dup",
    },
    {
        "snippet": "print(f'DEBUG auth: user_id={user.id}, token={token[:8]}..., scopes={scopes}')",
        "source_path": "src/auth/middleware.py", "source_start": 87, "source_end": 87,
        "score": 0.623, "v1_status": "exists", "v3_status": "ok", "action_hint": "delete",
        "promotion_key": "memory:src/auth/middleware.py:87:87",
    },
]

LONGTERM_PAYLOAD = {
    "total_items": len(LONGTERM_ITEMS),
    "sections_count": 3,
    "items_by_action": {"keep": 18, "review": 4, "delete": 3},
    "non_standard_sections": 1,
    "memory_md_mtime": _ts(7_500),   # ~2h 前审计
    "items": LONGTERM_ITEMS,
    "llm_eval": {
        "validity": {
            # keep 条目的 LLM 判断
            "memory:memory/2026-02-14.md:12:15": {"verdict": "still_valid", "reason": "Core infra config, stable"},
            "memory:memory/2026-02-21.md:3:6":   {"verdict": "still_valid", "reason": "Security best practice, evergreen"},
            "memory:memory/2026-03-03.md:7:11":  {"verdict": "still_valid", "reason": "Perf tuning result, durable"},
            "memory:memory/2026-03-10.md:22:25": {"verdict": "still_valid", "reason": "Infra pattern, still relevant"},
            "memory:memory/2026-03-17.md:5:8":   {"verdict": "still_valid", "reason": "CORS gotcha, evergreen"},
            "memory:memory/2026-01-28.md:18:21": {"verdict": "still_valid", "reason": "DB safety rule, always valid"},
            "memory:memory/2026-03-01.md:1:4":   {"verdict": "still_valid", "reason": "OKR context, still active Q2"},
            "memory:memory/2026-02-08.md:9:12":  {"verdict": "still_valid", "reason": "Process improvement, keep"},
            "memory:memory/2026-01-15.md:14:17": {"verdict": "still_valid", "reason": "Team workflow, still in use"},
            "memory:memory/2026-02-05.md:3:5":   {"verdict": "still_valid", "reason": "Lifestyle pattern, personal"},
            "memory:memory/2026-01-22.md:7:9":   {"verdict": "still_valid", "reason": "Preference note, stable"},
            "memory:memory/2026-02-18.md:11:14": {"verdict": "still_valid", "reason": "Health habit, keep tracking"},
            "memory:memory/2026-01-10.md:2:4":   {"verdict": "still_valid", "reason": "Local knowledge, useful"},
            "memory:memory/2026-03-08.md:5:8":   {"verdict": "still_valid", "reason": "Core mental model, evergreen"},
            "memory:memory/2026-02-25.md:3:6":   {"verdict": "still_valid", "reason": "User research principle, keep"},
            "memory:memory/2026-01-30.md:8:11":  {"verdict": "still_valid", "reason": "Behavior design, personal"},
            "memory:memory/2026-02-12.md:1:3":   {"verdict": "still_valid", "reason": "Personal preference, stable"},
            "memory:memory/2026-01-18.md:6:8":   {"verdict": "still_valid", "reason": "Stationery note, personal"},
            # review 条目
            "memory:src/utils/ws_helper.py:45:62":      {"verdict": "still_valid", "reason": "Pattern still correct, source may have moved"},
            "memory:memory/2026-01-08.md:3:5":          {"verdict": "uncertain",    "reason": "Notion workspace may have changed"},
            "memory:memory/2025-12-28.md:1:3":          {"verdict": "still_valid", "reason": "Grinder setting, personal preference"},
            "memory:memory/travel/tokyo-2025.md:8:12":  {"verdict": "still_valid", "reason": "Travel knowledge, still valid for future trips"},
        },
        "merge_suggestions": [
            {
                "item_a": "memory:src/auth/legacy/oauth_password.py:1:38",
                "item_b": "memory:src/auth/legacy/oauth_password.py:1:38:dup",
                "suggestion": "These two entries describe the same deprecated OAuth2 endpoint — merge or delete both",
            }
        ],
    },
}


# ── Section 2：短期记忆健康检查 ───────────────────────────────────────────────

HEALTH_PAYLOAD = {
    "shortterm_total":   312,
    "zombie_count":       24,
    "zombie_ratio":    0.077,
    "fp_count":           38,
    "fp_ratio":        0.122,
    "retrieval_health":   68,
    "promotion_risk":     38,
    "fts_degradation":  False,
    "longterm_sections":   3,
    "longterm_items":     25,
}


# ── Section 3：晋升前预检 ──────────────────────────────────────────────────────

PROMOTION_PAYLOAD = {
    "total_unpromotted": 38,
    "top_n": 10,
    "pass_count":  6,
    "skip_count":  3,
    "flag_count":  1,
    "candidates": [
        # Pass 6 条
        {
            "path": "memory/2026-04-14.md", "start": 1,  "end": 4,
            "composite": 0.831, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        {
            "path": "memory/2026-04-13.md", "start": 8,  "end": 11,
            "composite": 0.814, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        {
            "path": "memory/2026-04-12.md", "start": 15, "end": 18,
            "composite": 0.798, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        {
            "path": "memory/2026-04-11.md", "start": 3,  "end": 6,
            "composite": 0.787, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        {
            "path": "memory/2026-04-10.md", "start": 22, "end": 25,
            "composite": 0.773, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        {
            "path": "memory/2026-04-09.md", "start": 7,  "end": 10,
            "composite": 0.761, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        # Skip 3 条
        {
            "path": "src/api/routers/users.py", "start": 1, "end": 5,
            "composite": 0.743, "verdict": "skip",
            "skip_reason": "import_only", "flag_reason": None,
        },
        {
            "path": "src/frontend/debug.js", "start": 142, "end": 142,
            "composite": 0.721, "verdict": "skip",
            "skip_reason": "debug_code", "flag_reason": None,
        },
        {
            "path": "src/auth/legacy/token_utils.py", "start": 1, "end": 28,
            "composite": 0.698, "verdict": "skip",
            "skip_reason": "source_deleted", "flag_reason": None,
        },
        # Flag 1 条
        {
            "path": "memory/2026-04-07.md", "start": 33, "end": 36,
            "composite": 0.654, "verdict": "flag",
            "skip_reason": None, "flag_reason": "potential_false_positive",
        },
    ],
    "llm_eval": {
        "long_term_count":  5,
        "one_time_count":   1,
        "uncertain_count":  1,
    },
}


# ── Section 4：SOUL.md 快照 ───────────────────────────────────────────────────

SOUL_PAYLOAD = {
    "char_count":      1665,
    "content_hash":    "a3f8c2d914e7b056",
    "directive_count": 4,
    "sections":        ["Core Truths", "Boundaries", "Vibe", "Continuity"],
    "risk_level":      "low",
}


# ── Section 5：配置诊断 ────────────────────────────────────────────────────────

CONFIG_PAYLOAD = {
    "all_good": False,
    "issues": [
        {
            "code": "mmr",
            "triggered": True,
            "signal_data": {"pairs": 12},
        },
    ],
}


# ── 主函数 ────────────────────────────────────────────────────────────────────

def generate(workspace: str, lang: str, open_browser: bool) -> None:
    db_path = Path.home() / ".openclaw-memhealth" / "session.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing demo data to: {db_path}")
    print(f"Workspace key:        {workspace}")
    print(f"Dashboard language:   {lang}")
    print()

    # Section 1: longterm audit
    report_id = make_report_id()
    save_audit_report(
        report_id=report_id,
        workspace=workspace,
        total_items=LONGTERM_PAYLOAD["total_items"],
        payload=LONGTERM_PAYLOAD,
        db_path=db_path,
    )
    print(f"✅ Longterm audit    — {LONGTERM_PAYLOAD['total_items']} items "
          f"(keep={LONGTERM_PAYLOAD['items_by_action']['keep']}, "
          f"review={LONGTERM_PAYLOAD['items_by_action']['review']}, "
          f"delete={LONGTERM_PAYLOAD['items_by_action']['delete']})")

    # Section 2: health snapshot
    import time as _time
    _time.sleep(0.002)   # ensure distinct timestamps
    save_health_snapshot(workspace=workspace, payload=HEALTH_PAYLOAD, db_path=db_path)
    print(f"✅ Health snapshot   — {HEALTH_PAYLOAD['shortterm_total']} shortterm entries, "
          f"RH={HEALTH_PAYLOAD['retrieval_health']}, PR={HEALTH_PAYLOAD['promotion_risk']}")

    # Section 3: promotion snapshot
    _time.sleep(0.002)
    save_promotion_snapshot(workspace=workspace, payload=PROMOTION_PAYLOAD, db_path=db_path)
    print(f"✅ Promotion audit   — pass={PROMOTION_PAYLOAD['pass_count']}, "
          f"skip={PROMOTION_PAYLOAD['skip_count']}, flag={PROMOTION_PAYLOAD['flag_count']}")

    # Section 4: soul snapshot
    _time.sleep(0.002)
    save_soul_snapshot(
        workspace=workspace,
        char_count=SOUL_PAYLOAD["char_count"],
        content_hash=SOUL_PAYLOAD["content_hash"],
        directive_count=SOUL_PAYLOAD["directive_count"],
        sections=SOUL_PAYLOAD["sections"],
        risk_level=SOUL_PAYLOAD["risk_level"],
        db_path=db_path,
    )
    print(f"✅ Soul snapshot     — risk_level={SOUL_PAYLOAD['risk_level']}, "
          f"chars={SOUL_PAYLOAD['char_count']}")

    # Section 5: config snapshot
    _time.sleep(0.002)
    save_config_snapshot(workspace=workspace, payload=CONFIG_PAYLOAD, db_path=db_path)
    issue_codes = [i["code"] for i in CONFIG_PAYLOAD["issues"]]
    print(f"✅ Config snapshot   — issues={issue_codes}")

    # 读回并生成 HTML
    print()
    data = load_dashboard_data(workspace, db_path=db_path)

    missing = [k for k, v in data.items() if v is None]
    if missing:
        print(f"⚠️  Missing sections: {missing}")
    else:
        print("✅ All 5 sections populated")

    # 计算健康分
    from src.dashboard import compute_health_score
    score = compute_health_score(data["longterm_audit"], data["health"], data["soul"])
    print(f"📊 Health score: {score}/100")

    # 生成 HTML
    output_dir = Path.home() / ".openclaw-memhealth"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"dashboard_demo_{lang}.html"

    html = generate_dashboard_html(data, workspace=workspace, lang=lang)
    output_path.write_text(html, encoding="utf-8")
    print(f"📄 Dashboard written: {output_path} ({len(html):,} chars)")

    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{output_path}")
        print("🌐 Opened in browser")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo dashboard data")
    parser.add_argument("--open",   action="store_true", help="Open dashboard in browser after generation")
    parser.add_argument("--lang",   default="en",        help="Dashboard language: en or zh (default: en)")
    parser.add_argument("--ws",     default="/demo/openclaw-workspace", help="Demo workspace path")
    args = parser.parse_args()

    if args.lang not in ("en", "zh"):
        print(f"Error: --lang must be 'en' or 'zh', got '{args.lang}'")
        sys.exit(1)

    generate(workspace=args.ws, lang=args.lang, open_browser=args.open)


if __name__ == "__main__":
    main()

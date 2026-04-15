#!/usr/bin/env python3
"""
generate_demo_data.py · 生成演示用看板数据

用法（在项目根目录执行）：
    python3 scripts/generate_demo_data.py [--open] [--lang en|zh]

选项：
    --open      生成后自动在浏览器打开看板
    --lang      看板语言，默认 en（用于 README 截图）
    --ws        写入的 workspace 路径，默认自动按语言区分

角色设定（英文版）：
    Mavis，产品经理 + 业余开发者，用 OpenClaw 3 个月。
    记忆里有后端开发、产品工作、生活习惯、读书笔记、旅行踩坑…

    最近发生了什么：
    - 把旧 OAuth2 密码流重构成了 PKCE 方案，删了 src/auth/legacy/ 目录
    - 一次 debug 会话留下了大量临时 recall
    - FTS 字面匹配带来了一批假阳性条目
    综合健康分约 70 分——有问题，但有具体的改善路径。

角色设定（中文版）：
    小萌，产品经理 + 副业创业者，住北京胡同四合院，用 OpenClaw 2 个月。
    记忆里有植物养护、做饭研究、骑行路线、音乐节攻略、读书笔记、旅行踩坑…
    技术内容偏少，主要靠 AI 辅助，不算程序员。

    最近发生了什么：
    - 旧内容排期表从 Google Doc 迁移到飞书，原链接全部废了
    - 一次调试前端留下了 console.log，被 OpenClaw 顺手记进了短期记忆
    - 短期记忆里攒了一批重复的「待办碎片」
    综合健康分约 82 分——整体良好，小问题可以清理一下。
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


# ════════════════════════════════════════════════════════════════════════════════
# 中文数据集 · 小萌，北京产品经理 + 副业创业者
# ════════════════════════════════════════════════════════════════════════════════

# ── 中文 Section 1：长期记忆审计 ──────────────────────────────────────────────

LONGTERM_ITEMS_ZH = [
    # ── Keep 19 条 ─────────────────────────────────────────────────────────────

    # 🌱 植物养护（3）
    {
        "snippet": "虎皮兰浇水原则：盆土完全干透再浇，宁可旱不能涝。冬天两周一次就够，浇多了根腐",
        "source_path": "memory/2026-02-10.md", "source_start": 3, "source_end": 5,
        "score": 0.941, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-10.md:3:5",
    },
    {
        "snippet": "绿萝扦插方法：剪10cm枝条插水里，两周生根，换盆前先晾根1小时防腐烂。阳台北侧散光最适合",
        "source_path": "memory/2026-03-05.md", "source_start": 7, "source_end": 10,
        "score": 0.918, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-05.md:7:10",
    },
    {
        "snippet": "多肉夏季休眠要遮光，放到散光处，停水或极少量水。强光直射+浇水=化水必死",
        "source_path": "memory/2026-01-28.md", "source_start": 2, "source_end": 4,
        "score": 0.897, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-28.md:2:4",
    },

    # 🍳 做饭研究（3）
    {
        "snippet": "越南春卷皮要用温水泡5秒，不能泡软再包——半硬时下馅，包完还会继续软。泡太软=破皮漏馅",
        "source_path": "memory/2026-03-18.md", "source_start": 1, "source_end": 4,
        "score": 0.934, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-18.md:1:4",
    },
    {
        "snippet": "炒土豆丝不粘连的秘诀：切完马上泡淡盐水10分钟，沥干，锅要够热，全程大火快炒不超过3分钟",
        "source_path": "memory/2026-02-22.md", "source_start": 8, "source_end": 11,
        "score": 0.912, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-22.md:8:11",
    },
    {
        "snippet": "焦糖布丁的水浴温度：150°C烤40分钟，水盘水深2cm。烤箱温度偏高会出气泡，布丁不够嫩滑",
        "source_path": "memory/2026-01-14.md", "source_start": 5, "source_end": 8,
        "score": 0.886, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-14.md:5:8",
    },

    # 🚴 骑行（2）
    {
        "snippet": "从鼓楼骑到奥森公园约11公里，走鼓楼大街→北四环辅路→林萃路。建议早7点前出发，躲早高峰堵车",
        "source_path": "memory/2026-03-12.md", "source_start": 2, "source_end": 5,
        "score": 0.903, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-12.md:2:5",
    },
    {
        "snippet": "骑行换挡时机：坡前提前降挡，不要在坡中换——链条承压时换挡伤齿盘。平路踏频保持70-80rpm最省力",
        "source_path": "memory/2026-02-28.md", "source_start": 11, "source_end": 14,
        "score": 0.871, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-28.md:11:14",
    },

    # 🎵 音乐/音乐节（2）
    {
        "snippet": "草莓音乐节买票策略：预售第一批最便宜，但阵容不全。第二批价格涨30%但能看完整阵容再决定。",
        "source_path": "memory/2026-03-25.md", "source_start": 1, "source_end": 3,
        "score": 0.858, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-25.md:1:3",
    },
    {
        "snippet": "现场看演出护耳塞推荐Loop Experience：降噪25dB、保留人声和乐器层次，不像普通棉塞听起来像地下室",
        "source_path": "memory/2026-02-16.md", "source_start": 6, "source_end": 8,
        "score": 0.843, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-16.md:6:8",
    },

    # ✈️ 旅行（2）
    {
        "snippet": "大理古城住宿选人民路以北、洱海方向——远离酒吧街但步行可达。避开国庆/五一，平时房价直降60%",
        "source_path": "memory/travel/dali-2026.md", "source_start": 3, "source_end": 7,
        "score": 0.895, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/travel/dali-2026.md:3:7",
    },
    {
        "snippet": "越南河内机场到市区：Grab打车约15万越南盾（约45元），比机场固定价出租车便宜一半",
        "source_path": "memory/travel/hanoi-2025.md", "source_start": 1, "source_end": 4,
        "score": 0.874, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/travel/hanoi-2025.md:1:4",
    },

    # 📚 读书/学习（3）
    {
        "snippet": "《置身事内》：理解中国经济要先理解地方政府的激励机制——土地财政是理解一切的钥匙",
        "source_path": "memory/2026-03-20.md", "source_start": 4, "source_end": 7,
        "score": 0.921, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-20.md:4:7",
    },
    {
        "snippet": "《被讨厌的勇气》：课题分离是核心——别人如何评价你，是别人的课题，不是你的。焦虑来自把别人的课题当自己的",
        "source_path": "memory/2026-02-14.md", "source_start": 9, "source_end": 12,
        "score": 0.908, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-14.md:9:12",
    },
    {
        "snippet": "《纳瓦尔宝典》：做独一无二的自己比努力工作更重要。杠杆来源：代码、媒体、资本——前两种可以不睡觉工作",
        "source_path": "memory/2026-01-20.md", "source_start": 6, "source_end": 9,
        "score": 0.887, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-20.md:6:9",
    },

    # 🌟 个人成长/习惯（2）
    {
        "snippet": "晨间写作效果好于晚上：睡前大脑在整理信息，早起后想法更清晰，杂念少。目标是每天早7点写30分钟",
        "source_path": "memory/2026-03-02.md", "source_start": 3, "source_end": 5,
        "score": 0.869, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-02.md:3:5",
    },
    {
        "snippet": "定期复盘用「三栏法」：做得好的/做得差的/下周要改变的。每次控制在15分钟以内，否则变成自我批判",
        "source_path": "memory/2026-01-25.md", "source_start": 1, "source_end": 4,
        "score": 0.852, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-01-25.md:1:4",
    },

    # 💡 副业/创业（2）
    {
        "snippet": "小红书选品逻辑：搜索词有流量但商业化程度低（笔记少广告）= 机会窗口。反过来全是广告说明红海了",
        "source_path": "memory/2026-03-28.md", "source_start": 2, "source_end": 5,
        "score": 0.916, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-03-28.md:2:5",
    },
    {
        "snippet": "一人公司定价要大胆：价格低会吸引最挑剔的客户，价格高反而省心。服务定价不低于同等时间打工收入的3倍",
        "source_path": "memory/2026-02-08.md", "source_start": 14, "source_end": 17,
        "score": 0.893, "v1_status": "exists", "v3_status": "ok", "action_hint": "keep",
        "promotion_key": "memory:memory/2026-02-08.md:14:17",
    },

    # ── Review 3 条（来源不确定）──────────────────────────────────────────────

    {
        "snippet": "Q2内容排期模板：选题/截止日/发布平台/数据目标。每周一填下周计划，周五复盘上周数据",
        "source_path": "content-plan/q2-schedule.md", "source_start": 1, "source_end": 12,
        "score": 0.841, "v1_status": "possibly_moved", "v3_status": "ok", "action_hint": "review",
        "promotion_key": "memory:content-plan/q2-schedule.md:1:12",
    },
    {
        "snippet": "合伙人沟通原则：有分歧先私下说，不在群里当众质疑。公开场合分歧会固化立场，越说越硬",
        "source_path": "memory/2026-01-12.md", "source_start": 8, "source_end": 11,
        "score": 0.822, "v1_status": "possibly_moved", "v3_status": "ok", "action_hint": "review",
        "promotion_key": "memory:memory/2026-01-12.md:8:11",
    },
    {
        "snippet": "北京朝阳区亲子餐厅推荐：「呆呆屋」适合4-8岁，室内游乐区大，人均80，周末要提前1周订",
        "source_path": "memory/2025-12-20.md", "source_start": 2, "source_end": 5,
        "score": 0.796, "v1_status": "possibly_moved", "v3_status": "ok", "action_hint": "review",
        "promotion_key": "memory:memory/2025-12-20.md:2:5",
    },

    # ── Delete 3 条 ──────────────────────────────────────────────────────────

    {
        "snippet": "Google Doc内容排期表链接：https://docs.google.com/spreadsheets/d/1Bx9... （已迁飞书，链接废弃）",
        "source_path": "content-plan/q1-links.md", "source_start": 3, "source_end": 4,
        "score": 0.712, "v1_status": "deleted", "v3_status": "ok", "action_hint": "delete",
        "promotion_key": "memory:content-plan/q1-links.md:3:4",
    },
    {
        "snippet": "Google Doc内容排期备份入口 - Q1旧版，Q2已重建飞书版本，此条目重复且来源已删除",
        "source_path": "content-plan/q1-links.md", "source_start": 5, "source_end": 6,
        "score": 0.698, "v1_status": "deleted", "v3_status": "duplicate_loser", "action_hint": "delete",
        "promotion_key": "memory:content-plan/q1-links.md:5:6",
    },
    {
        "snippet": "console.log('debug: userId=', userId, 'token=', token.slice(0,8))",
        "source_path": "webapp/src/auth.js", "source_start": 142, "source_end": 142,
        "score": 0.581, "v1_status": "exists", "v3_status": "ok", "action_hint": "delete",
        "promotion_key": "memory:webapp/src/auth.js:142:142",
    },
]

LONGTERM_PAYLOAD_ZH = {
    "total_items": len(LONGTERM_ITEMS_ZH),
    "sections_count": 4,
    "items_by_action": {"keep": 19, "review": 3, "delete": 3},
    "non_standard_sections": 0,
    "memory_md_mtime": _ts(5_400),   # ~1.5h 前审计
    "items": LONGTERM_ITEMS_ZH,
    "llm_eval": {
        "validity": {
            # keep 条目
            "memory:memory/2026-02-10.md:3:5":       {"verdict": "still_valid", "reason": "植物养护经验，长期有效"},
            "memory:memory/2026-03-05.md:7:10":      {"verdict": "still_valid", "reason": "扦插技巧，个人经验"},
            "memory:memory/2026-01-28.md:2:4":       {"verdict": "still_valid", "reason": "多肉护理知识，常青"},
            "memory:memory/2026-03-18.md:1:4":       {"verdict": "still_valid", "reason": "烹饪技巧，个人习惯"},
            "memory:memory/2026-02-22.md:8:11":      {"verdict": "still_valid", "reason": "家常菜技法，长期适用"},
            "memory:memory/2026-01-14.md:5:8":       {"verdict": "still_valid", "reason": "烘焙参数，可复现"},
            "memory:memory/2026-03-12.md:2:5":       {"verdict": "still_valid", "reason": "北京路线，稳定有效"},
            "memory:memory/2026-02-28.md:11:14":     {"verdict": "still_valid", "reason": "骑行技巧，通用"},
            "memory:memory/2026-03-25.md:1:3":       {"verdict": "still_valid", "reason": "购票策略，每年适用"},
            "memory:memory/2026-02-16.md:6:8":       {"verdict": "still_valid", "reason": "设备推荐，个人偏好"},
            "memory:memory/travel/dali-2026.md:3:7": {"verdict": "still_valid", "reason": "旅行经验，近期有效"},
            "memory:memory/travel/hanoi-2025.md:1:4":{"verdict": "still_valid", "reason": "交通信息，短期有效"},
            "memory:memory/2026-03-20.md:4:7":       {"verdict": "still_valid", "reason": "读书洞见，常青"},
            "memory:memory/2026-02-14.md:9:12":      {"verdict": "still_valid", "reason": "心理学原则，长期有效"},
            "memory:memory/2026-01-20.md:6:9":       {"verdict": "still_valid", "reason": "创业思维，个人成长"},
            "memory:memory/2026-03-02.md:3:5":       {"verdict": "still_valid", "reason": "个人习惯，持续践行"},
            "memory:memory/2026-01-25.md:1:4":       {"verdict": "still_valid", "reason": "工作方法，稳定有效"},
            "memory:memory/2026-03-28.md:2:5":       {"verdict": "still_valid", "reason": "平台运营策略，近期有效"},
            "memory:memory/2026-02-08.md:14:17":     {"verdict": "still_valid", "reason": "定价逻辑，个人信条"},
            # review 条目
            "memory:content-plan/q2-schedule.md:1:12": {"verdict": "uncertain",    "reason": "排期文件已迁飞书，原路径可能失效"},
            "memory:memory/2026-01-12.md:8:11":         {"verdict": "still_valid", "reason": "人际沟通原则，长期有效"},
            "memory:memory/2025-12-20.md:2:5":          {"verdict": "still_valid", "reason": "本地生活信息，可能有变"},
        },
        "merge_suggestions": [
            {
                "item_a": "memory:content-plan/q1-links.md:3:4",
                "item_b": "memory:content-plan/q1-links.md:5:6",
                "suggestion": "两条都指向已废弃的 Google Doc 排期链接，可以一并删除",
            }
        ],
    },
}


# ── 中文 Section 2：短期记忆健康检查 ──────────────────────────────────────────

HEALTH_PAYLOAD_ZH = {
    "shortterm_total":   187,
    "zombie_count":       11,
    "zombie_ratio":    0.059,
    "fp_count":           18,
    "fp_ratio":        0.096,
    "retrieval_health":   84,
    "promotion_risk":     22,
    "fts_degradation":  False,
    "longterm_sections":   4,
    "longterm_items":     25,
}


# ── 中文 Section 3：晋升前预检 ────────────────────────────────────────────────

PROMOTION_PAYLOAD_ZH = {
    "total_unpromotted": 23,
    "top_n": 8,
    "pass_count":  5,
    "skip_count":  2,
    "flag_count":  1,
    "candidates": [
        # Pass 5 条
        {
            "path": "memory/2026-04-14.md", "start": 2, "end": 5,
            "composite": 0.856, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        {
            "path": "memory/2026-04-13.md", "start": 6, "end": 9,
            "composite": 0.831, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        {
            "path": "memory/2026-04-11.md", "start": 1, "end": 4,
            "composite": 0.812, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        {
            "path": "memory/2026-04-10.md", "start": 14, "end": 17,
            "composite": 0.794, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        {
            "path": "memory/2026-04-08.md", "start": 9, "end": 12,
            "composite": 0.778, "verdict": "pass",
            "skip_reason": None, "flag_reason": None,
        },
        # Skip 2 条
        {
            "path": "webapp/src/auth.js", "start": 142, "end": 142,
            "composite": 0.701, "verdict": "skip",
            "skip_reason": "debug_code", "flag_reason": None,
        },
        {
            "path": "content-plan/q1-links.md", "start": 1, "end": 8,
            "composite": 0.673, "verdict": "skip",
            "skip_reason": "source_deleted", "flag_reason": None,
        },
        # Flag 1 条
        {
            "path": "memory/2026-04-06.md", "start": 21, "end": 24,
            "composite": 0.638, "verdict": "flag",
            "skip_reason": None, "flag_reason": "potential_false_positive",
        },
    ],
    "llm_eval": {
        "long_term_count":  4,
        "one_time_count":   1,
        "uncertain_count":  0,
    },
}


# ── 中文 Section 4：SOUL.md 快照 ──────────────────────────────────────────────

SOUL_PAYLOAD_ZH = {
    "char_count":      2341,
    "content_hash":    "d7e2a419fc8b3051",
    "directive_count": 5,
    "sections":        ["核心认知", "边界设定", "行动风格", "人际关系", "连续性"],
    "risk_level":      "ok",
}


# ── 中文 Section 5：配置诊断 ──────────────────────────────────────────────────

CONFIG_PAYLOAD_ZH = {
    "all_good": True,
    "issues": [],
}


# ── 主函数 ────────────────────────────────────────────────────────────────────

def generate(workspace: str, lang: str, open_browser: bool) -> None:
    db_path = Path.home() / ".openclaw-memhealth" / "session.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 根据语言选择数据集
    if lang == "zh":
        lt_payload  = LONGTERM_PAYLOAD_ZH
        h_payload   = HEALTH_PAYLOAD_ZH
        pr_payload  = PROMOTION_PAYLOAD_ZH
        so_payload  = SOUL_PAYLOAD_ZH
        cfg_payload = CONFIG_PAYLOAD_ZH
    else:
        lt_payload  = LONGTERM_PAYLOAD
        h_payload   = HEALTH_PAYLOAD
        pr_payload  = PROMOTION_PAYLOAD
        so_payload  = SOUL_PAYLOAD
        cfg_payload = CONFIG_PAYLOAD

    print(f"Writing demo data to: {db_path}")
    print(f"Workspace key:        {workspace}")
    print(f"Dashboard language:   {lang}")
    print()

    # Section 1: longterm audit
    report_id = make_report_id()
    save_audit_report(
        report_id=report_id,
        workspace=workspace,
        total_items=lt_payload["total_items"],
        payload=lt_payload,
        db_path=db_path,
    )
    print(f"✅ Longterm audit    — {lt_payload['total_items']} items "
          f"(keep={lt_payload['items_by_action']['keep']}, "
          f"review={lt_payload['items_by_action']['review']}, "
          f"delete={lt_payload['items_by_action']['delete']})")

    # Section 2: health snapshot
    import time as _time
    _time.sleep(0.002)   # ensure distinct timestamps
    save_health_snapshot(workspace=workspace, payload=h_payload, db_path=db_path)
    print(f"✅ Health snapshot   — {h_payload['shortterm_total']} shortterm entries, "
          f"RH={h_payload['retrieval_health']}, PR={h_payload['promotion_risk']}")

    # Section 3: promotion snapshot
    _time.sleep(0.002)
    save_promotion_snapshot(workspace=workspace, payload=pr_payload, db_path=db_path)
    print(f"✅ Promotion audit   — pass={pr_payload['pass_count']}, "
          f"skip={pr_payload['skip_count']}, flag={pr_payload['flag_count']}")

    # Section 4: soul snapshot
    _time.sleep(0.002)
    save_soul_snapshot(
        workspace=workspace,
        char_count=so_payload["char_count"],
        content_hash=so_payload["content_hash"],
        directive_count=so_payload["directive_count"],
        sections=so_payload["sections"],
        risk_level=so_payload["risk_level"],
        db_path=db_path,
    )
    print(f"✅ Soul snapshot     — risk_level={so_payload['risk_level']}, "
          f"chars={so_payload['char_count']}")

    # Section 5: config snapshot
    _time.sleep(0.002)
    save_config_snapshot(workspace=workspace, payload=cfg_payload, db_path=db_path)
    issue_codes = [i["code"] for i in cfg_payload["issues"]]
    print(f"✅ Config snapshot   — issues={issue_codes if issue_codes else 'none'}")

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
    parser.add_argument("--ws",     default=None,        help="Demo workspace path (default: auto by lang)")
    args = parser.parse_args()

    if args.lang not in ("en", "zh"):
        print(f"Error: --lang must be 'en' or 'zh', got '{args.lang}'")
        sys.exit(1)

    # workspace 默认按语言区分，避免中英文数据互相覆盖
    if args.ws is not None:
        workspace = args.ws
    elif args.lang == "zh":
        workspace = "/demo/openclaw-workspace-zh"
    else:
        workspace = "/demo/openclaw-workspace"

    generate(workspace=workspace, lang=args.lang, open_browser=args.open)


if __name__ == "__main__":
    main()

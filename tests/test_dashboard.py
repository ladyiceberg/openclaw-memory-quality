"""
test_dashboard.py · Dashboard HTML 生成器单元测试

覆盖：compute_health_score、各 Section 渲染（有数据/无数据）、
      综合 HTML 生成、健康分圆环、边界条件。
"""
import tempfile
from pathlib import Path

import pytest

from src.dashboard import (
    COLORS,
    _format_ago,
    _render_config,
    _render_health,
    _render_longterm,
    _render_promotion,
    _render_soul,
    _ring_svg,
    compute_health_score,
    generate_dashboard_html,
)


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

def _longterm_payload(keep=15, review=3, delete_n=2, llm=False):
    items_by_action = {"keep": keep, "review": review, "delete": delete_n}
    total = keep + review + delete_n
    items = [
        {"snippet": "Gateway binds 18789", "source_path": "memory/f.md",
         "source_start": 1, "source_end": 5, "score": 0.923,
         "v1_status": "exists", "v3_status": "ok", "action_hint": "keep"},
        {"snippet": "Old auth deleted", "source_path": "memory/old.md",
         "source_start": 3, "source_end": 8, "score": 0.76,
         "v1_status": "deleted", "v3_status": "ok", "action_hint": "delete"},
    ]
    payload = {
        "total_items": total,
        "sections_count": 4,
        "items_by_action": items_by_action,
        "non_standard_sections": 0,
        "memory_md_mtime": 1744675200.0,
        "items": items,
    }
    if llm:
        payload["llm_eval"] = {
            "validity": {
                "k1": {"verdict": "still_valid", "reason": "ok"},
                "k2": {"verdict": "outdated", "reason": "old"},
            },
            "merge_suggestions": [{"item_a": "k1", "item_b": "k2", "suggestion": "合并"}],
        }
    return ("report_id_test", payload)


def _health_payload(rh=72, pr=35, fts=False):
    return {
        "shortterm_total": 1247, "zombie_count": 89, "zombie_ratio": 0.071,
        "fp_count": 134, "fp_ratio": 0.107,
        "retrieval_health": rh, "promotion_risk": pr, "fts_degradation": fts,
        "longterm_sections": 4, "longterm_items": 23,
        "checked_at": 1744675200.0,
    }


def _promotion_payload(pass_n=7, skip_n=2, flag_n=1, llm=False):
    candidates = [
        {"path": "memory/old.md", "start": 1, "end": 5, "composite": 0.81,
         "verdict": "skip", "skip_reason": "source_deleted", "flag_reason": None},
        {"path": "memory/utils.ts", "start": 1, "end": 8, "composite": 0.76,
         "verdict": "flag", "skip_reason": None, "flag_reason": "potential_false_positive"},
    ]
    payload = {
        "total_unpromotted": 50, "top_n": 10,
        "pass_count": pass_n, "skip_count": skip_n, "flag_count": flag_n,
        "candidates": candidates[:skip_n + flag_n],
        "llm_eval": {"long_term_count": 5, "one_time_count": 1, "uncertain_count": 1} if llm else None,
        "checked_at": 1744675200.0,
    }
    return payload


def _soul_payload(level="low"):
    return {
        "risk_level": level,
        "char_count": 1665,
        "directive_count": 4,
        "sections": ["Core Truths", "Boundaries", "Vibe", "Continuity"],
        "checked_at": 1744675200.0,
    }


def _config_payload(all_good=True):
    if all_good:
        return {"all_good": True, "issues": [], "checked_at": 1744675200.0}
    return {
        "all_good": False,
        "issues": [{"code": "fts", "triggered": True, "signal_data": {"avg": 0.38}}],
        "checked_at": 1744675200.0,
    }


def _full_data(llm=False):
    return {
        "longterm_audit": _longterm_payload(llm=llm),
        "health":    _health_payload(),
        "promotion": _promotion_payload(llm=llm),
        "soul":      _soul_payload(),
        "config":    _config_payload(all_good=False),
    }


def _empty_data():
    return {"longterm_audit": None, "health": None, "promotion": None, "soul": None, "config": None}


# ── compute_health_score ──────────────────────────────────────────────────────

class TestComputeHealthScore:
    def test_all_none_returns_none(self):
        assert compute_health_score(None, None, None) is None

    def test_only_longterm(self):
        """只有 longterm：keep 比例 100% → 归一化后 100。"""
        lt = _longterm_payload(keep=20, review=0, delete_n=0)
        score = compute_health_score(lt, None, None)
        assert score == 100

    def test_only_longterm_half(self):
        """keep 50% → 约 50。"""
        lt = _longterm_payload(keep=10, review=0, delete_n=10)
        score = compute_health_score(lt, None, None)
        assert score == 50

    def test_only_health(self):
        """只有 health：rh=80, pr=20 → combined=80, score=80。"""
        h = _health_payload(rh=80, pr=20)
        score = compute_health_score(None, h, None)
        assert score == 80

    def test_only_health_bad(self):
        """rh=40, pr=80 → combined=(40+20)/2=30。"""
        h = _health_payload(rh=40, pr=80)
        score = compute_health_score(None, h, None)
        assert score == 30

    def test_only_soul_ok(self):
        """soul risk_level=ok → 100。"""
        s = _soul_payload("ok")
        score = compute_health_score(None, None, s)
        assert score == 100

    def test_only_soul_high(self):
        """soul risk_level=high → 25。"""
        s = _soul_payload("high")
        score = compute_health_score(None, None, s)
        assert score == 25

    def test_all_data_combined(self):
        """全部数据组合，结果在 [0,100]。"""
        lt = _longterm_payload(keep=15, review=3, delete_n=2)
        h  = _health_payload(rh=72, pr=35)
        s  = _soul_payload("low")
        score = compute_health_score(lt, h, s)
        assert 0 <= score <= 100

    def test_weight_normalization_partial(self):
        """有 2 个来源时，权重归一化，结果仍在 [0,100]。"""
        lt = _longterm_payload(keep=10, review=0, delete_n=10)  # 50分，权重0.4
        h  = _health_payload(rh=60, pr=40)  # 60分，权重0.4
        score = compute_health_score(lt, h, None)
        # 归一化后各占50%：(50+60)/2 = 55
        assert score == 55

    def test_returns_int(self):
        """返回值是 int。"""
        lt = _longterm_payload()
        score = compute_health_score(lt, None, None)
        assert isinstance(score, int)

    def test_clamped_to_0_100(self):
        """结果始终在 [0,100]。"""
        # 极端值：全删除
        lt = _longterm_payload(keep=0, review=0, delete_n=20)
        score = compute_health_score(lt, None, None)
        assert 0 <= score <= 100

    def test_longterm_zero_total_skipped(self):
        """total_items=0 时 longterm 不参与计算。"""
        lt = ("rid", {"total_items": 0, "items_by_action": {}, "items": []})
        # 只有 soul 参与
        s = _soul_payload("ok")
        score = compute_health_score(lt, None, s)
        assert score == 100


# ── _ring_svg ──────────────────────────────────────────────────────────────────

class TestRingSvg:
    def test_contains_svg(self):
        assert "<svg" in _ring_svg(80)

    def test_none_shows_dash(self):
        svg = _ring_svg(None)
        assert "--" in svg

    def test_score_shown(self):
        svg = _ring_svg(75)
        assert "75" in svg

    def test_zero_score(self):
        svg = _ring_svg(0)
        assert "0" in svg

    def test_hundred_score(self):
        svg = _ring_svg(100)
        assert "100" in svg


# ── _render_longterm ───────────────────────────────────────────────────────────

class TestRenderLongterm:
    def test_none_shows_placeholder(self):
        html = _render_longterm(None)
        assert "placeholder-card" in html
        assert "/memory-cleanup" in html

    def test_shows_keep_review_delete(self):
        html = _render_longterm(_longterm_payload(keep=15, review=3, delete_n=2))
        assert "15" in html  # keep
        assert "3"  in html  # review
        assert "2"  in html  # delete

    def test_sections_count_shown(self):
        html = _render_longterm(_longterm_payload())
        assert "4" in html  # sections_count

    def test_llm_badge_when_llm_eval(self):
        html = _render_longterm(_longterm_payload(llm=True))
        assert "llm-badge" in html
        assert "有效" in html
        assert "过时" in html

    def test_no_llm_badge_without_llm_eval(self):
        html = _render_longterm(_longterm_payload(llm=False))
        assert "llm-badge" not in html

    def test_merge_suggestion_shown(self):
        html = _render_longterm(_longterm_payload(llm=True))
        assert "合并建议 1" in html

    def test_entry_snippet_shown(self):
        html = _render_longterm(_longterm_payload())
        assert "Gateway binds 18789" in html

    def test_delete_group_present(self):
        html = _render_longterm(_longterm_payload())
        assert "建议删除" in html

    def test_keep_group_present(self):
        html = _render_longterm(_longterm_payload())
        assert "状态良好" in html

    def test_v1_status_zh(self):
        html = _render_longterm(_longterm_payload())
        assert "来源已删除" in html  # deleted entry

    def test_non_standard_warn_shown(self):
        _, payload = _longterm_payload()
        payload["non_standard_sections"] = 2
        html = _render_longterm(("rid", payload))
        assert "非标准段落" in html

    def test_non_standard_warn_not_shown_when_zero(self):
        html = _render_longterm(_longterm_payload())
        assert "非标准段落" not in html


# ── _render_health ─────────────────────────────────────────────────────────────

class TestRenderHealth:
    def test_none_shows_placeholder(self):
        html = _render_health(None)
        assert "placeholder-card" in html
        assert "/memory-check" in html

    def test_shows_totals(self):
        html = _render_health(_health_payload())
        assert "1,247" in html  # total formatted with comma

    def test_shows_retrieval_health(self):
        html = _render_health(_health_payload(rh=72))
        assert "Retrieval Health" in html
        assert "72" in html

    def test_shows_promotion_risk(self):
        html = _render_health(_health_payload(pr=35))
        assert "Promotion Risk" in html
        assert "35" in html

    def test_fts_warning_shown_when_true(self):
        html = _render_health(_health_payload(fts=True))
        assert "FTS 降级模式" in html

    def test_fts_warning_not_shown_when_false(self):
        html = _render_health(_health_payload(fts=False))
        assert "FTS 降级模式" not in html

    def test_zombie_count_shown(self):
        html = _render_health(_health_payload())
        assert "89" in html  # zombie_count

    def test_fp_count_shown(self):
        html = _render_health(_health_payload())
        assert "134" in html  # fp_count


# ── _render_promotion ──────────────────────────────────────────────────────────

class TestRenderPromotion:
    def test_none_shows_placeholder(self):
        html = _render_promotion(None)
        assert "placeholder-card" in html
        assert "/memory-promote" in html

    def test_shows_counts(self):
        html = _render_promotion(_promotion_payload(pass_n=7, skip_n=2, flag_n=1))
        assert "7" in html  # pass
        assert "2" in html  # skip
        assert "1" in html  # flag

    def test_skip_reason_zh(self):
        html = _render_promotion(_promotion_payload())
        assert "来源文件已删除" in html

    def test_llm_badge_when_llm_eval(self):
        html = _render_promotion(_promotion_payload(llm=True))
        assert "llm-badge" in html
        assert "长期价值" in html

    def test_no_llm_badge_without_llm_eval(self):
        html = _render_promotion(_promotion_payload(llm=False))
        assert "llm-badge" not in html

    def test_total_unpromotted_shown(self):
        html = _render_promotion(_promotion_payload())
        assert "50" in html  # total_unpromotted


# ── _render_soul ───────────────────────────────────────────────────────────────

class TestRenderSoul:
    def test_none_shows_placeholder(self):
        html = _render_soul(None)
        assert "placeholder-card" in html
        assert "/soul-check" in html

    def test_risk_level_label_zh(self):
        html = _render_soul(_soul_payload("low"))
        assert "低风险" in html

    def test_risk_level_ok(self):
        html = _render_soul(_soul_payload("ok"))
        assert "健康" in html

    def test_risk_level_high(self):
        html = _render_soul(_soul_payload("high"))
        assert "高风险" in html

    def test_char_count_shown(self):
        html = _render_soul(_soul_payload())
        assert "1,665" in html

    def test_directive_count_shown(self):
        html = _render_soul(_soul_payload())
        assert "4 条强指令词" in html

    def test_sections_shown(self):
        html = _render_soul(_soul_payload())
        assert "Core Truths" in html
        assert "Boundaries" in html


# ── _render_config ─────────────────────────────────────────────────────────────

class TestRenderConfig:
    def test_none_shows_placeholder(self):
        html = _render_config(None)
        assert "placeholder-card" in html
        assert "/memory-diagnose" in html

    def test_all_good_shows_healthy(self):
        html = _render_config(_config_payload(all_good=True))
        assert "配置健康" in html
        assert "✅" in html

    def test_issues_shown(self):
        html = _render_config(_config_payload(all_good=False))
        assert "FTS 降级模式" in html

    def test_issue_count_shown(self):
        html = _render_config(_config_payload(all_good=False))
        assert "1 个配置问题" in html


# ── generate_dashboard_html（完整 HTML）────────────────────────────────────────

class TestGenerateDashboardHtml:
    def test_returns_string(self):
        html = generate_dashboard_html(_empty_data())
        assert isinstance(html, str)
        assert len(html) > 1000

    def test_all_5_sections_present(self):
        html = generate_dashboard_html(_full_data())
        assert "长期记忆" in html
        assert "短期记忆概况" in html
        assert "晋升前预检" in html
        assert "SOUL.md 健康" in html
        assert "配置诊断" in html

    def test_5_placeholders_when_no_data(self):
        html = generate_dashboard_html(_empty_data())
        count = html.count('class="section-card placeholder-card"')
        assert count == 5

    def test_0_placeholders_when_all_data(self):
        html = generate_dashboard_html(_full_data())
        count = html.count('class="section-card placeholder-card"')
        assert count == 0

    def test_ring_svg_present(self):
        html = generate_dashboard_html(_full_data())
        assert "ring-svg" in html

    def test_header_present(self):
        html = generate_dashboard_html(_full_data())
        assert "OpenClaw Memory Health" in html

    def test_footer_present(self):
        html = generate_dashboard_html(_full_data())
        assert "openclaw-memhealth" in html

    def test_workspace_name_shown(self):
        html = generate_dashboard_html(_full_data(), workspace="/home/user/myworkspace")
        assert "myworkspace" in html

    def test_no_data_hero_shows_no_data(self):
        html = generate_dashboard_html(_empty_data())
        assert "暂无数据" in html

    def test_good_health_hero_text(self):
        # 全部健康数据 → 良好
        data = {
            "longterm_audit": _longterm_payload(keep=20, review=0, delete_n=0),
            "health": _health_payload(rh=95, pr=5),
            "soul": _soul_payload("ok"),
            "promotion": None, "config": None,
        }
        html = generate_dashboard_html(data)
        assert "状态良好" in html

    def test_bad_health_hero_text(self):
        data = {
            "longterm_audit": _longterm_payload(keep=2, review=0, delete_n=18),
            "health": _health_payload(rh=20, pr=90),
            "soul": _soul_payload("high"),
            "promotion": None, "config": None,
        }
        html = generate_dashboard_html(data)
        assert "需要处理" in html

    def test_valid_html_structure(self):
        html = generate_dashboard_html(_full_data())
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "<style>" in html
        assert "<script>" in html

    def test_no_traceback_on_edge_case_data(self):
        """极端数据不崩溃。"""
        data = {
            "longterm_audit": ("rid", {
                "total_items": 0,
                "sections_count": 0,
                "items_by_action": {},
                "non_standard_sections": 0,
                "items": [],
                "llm_eval": None,
            }),
            "health": _health_payload(rh=0, pr=100),
            "promotion": {"total_unpromotted": 0, "top_n": 10, "pass_count": 0,
                          "skip_count": 0, "flag_count": 0, "candidates": [], "llm_eval": None,
                          "checked_at": 1744675200.0},
            "soul": _soul_payload("high"),
            "config": _config_payload(all_good=False),
        }
        html = generate_dashboard_html(data)
        assert isinstance(html, str)
        assert "Traceback" not in html

    def test_coverage_dots_in_hero(self):
        """Hero 显示数据覆盖情况的圆点。"""
        html = generate_dashboard_html(_full_data())
        assert "coverage-dot" in html


# ── 多语言（lang 参数）────────────────────────────────────────────────────────

class TestI18n:
    """验证 lang 参数正确切换语言，中英文输出互不干扰。"""

    # ── 英文输出验证 ──────────────────────────────────────────────────────────

    def test_en_hero_no_data(self):
        """lang=en，无数据时 hero 显示英文。"""
        html = generate_dashboard_html(_empty_data(), lang="en")
        assert "No data yet" in html
        assert "暂无数据" not in html

    def test_en_hero_healthy(self):
        """lang=en，健康时 hero 显示英文。"""
        data = {
            "longterm_audit": _longterm_payload(keep=20, review=0, delete_n=0),
            "health": _health_payload(rh=95, pr=5),
            "soul": _soul_payload("ok"),
            "promotion": None, "config": None,
        }
        html = generate_dashboard_html(data, lang="en")
        assert "Memory system is healthy" in html
        assert "记忆系统状态良好" not in html

    def test_en_section1_placeholder(self):
        """lang=en，Section1 占位显示英文。"""
        html = generate_dashboard_html(_empty_data(), lang="en")
        assert "Long-term Memory" in html
        assert "长期记忆" not in html

    def test_en_section2_placeholder(self):
        """lang=en，Section2 占位显示英文。"""
        html = generate_dashboard_html(_empty_data(), lang="en")
        assert "Short-term Overview" in html
        assert "短期记忆概况" not in html

    def test_en_section3_placeholder(self):
        """lang=en，Section3 占位显示英文。"""
        html = generate_dashboard_html(_empty_data(), lang="en")
        assert "Pre-promotion Audit" in html
        assert "晋升前预检" not in html

    def test_en_section4_placeholder(self):
        """lang=en，Section4 占位显示英文。"""
        html = generate_dashboard_html(_empty_data(), lang="en")
        assert "SOUL.md Health" in html

    def test_en_section5_placeholder(self):
        """lang=en，Section5 占位显示英文。"""
        html = generate_dashboard_html(_empty_data(), lang="en")
        assert "Config Diagnosis" in html
        assert "配置诊断" not in html

    def test_en_longterm_labels(self):
        """lang=en，长期记忆区块标签显示英文。"""
        html = generate_dashboard_html(_full_data(), lang="en")
        assert "Keep" in html
        assert "Review" in html
        assert "Delete" in html
        assert "保留" not in html

    def test_en_longterm_groups(self):
        """lang=en，折叠分组标题显示英文。"""
        html = generate_dashboard_html(_full_data(), lang="en")
        assert "Suggested for deletion" in html
        assert "建议删除" not in html

    def test_en_soul_risk_label(self):
        """lang=en，SOUL 风险等级显示英文。"""
        html = generate_dashboard_html(_full_data(), lang="en")
        assert "Low Risk" in html
        assert "低风险" not in html

    def test_en_config_issues(self):
        """lang=en，配置问题描述显示英文。"""
        html = generate_dashboard_html(_full_data(), lang="en")
        assert "FTS degradation mode" in html
        assert "FTS 降级模式" not in html

    def test_en_html_lang_attribute(self):
        """lang=en 时 html 标签的 lang 属性为 en。"""
        html = generate_dashboard_html(_empty_data(), lang="en")
        assert 'lang="en"' in html
        assert 'lang="zh-CN"' not in html

    def test_en_footer(self):
        """lang=en，footer 显示英文。"""
        html = generate_dashboard_html(_full_data(), lang="en")
        assert "Generated by" in html
        assert "Report an issue" in html
        assert "由" not in html

    # ── 中文输出验证（回归）──────────────────────────────────────────────────

    def test_zh_is_default(self):
        """不传 lang 时默认中文（detect_language() 返回 zh）。"""
        html = generate_dashboard_html(_empty_data())
        assert "暂无数据" in html
        assert "No data yet" not in html

    def test_zh_explicit(self):
        """lang=zh 显式指定中文。"""
        html = generate_dashboard_html(_empty_data(), lang="zh")
        assert "暂无数据" in html

    def test_zh_html_lang_attribute(self):
        """lang=zh 时 html 标签的 lang 属性为 zh-CN。"""
        html = generate_dashboard_html(_empty_data(), lang="zh")
        assert 'lang="zh-CN"' in html

    # ── Section 渲染函数直接验证 lang 透传 ───────────────────────────────────

    def test_render_health_en(self):
        """_render_health 传 lang=en 输出英文。"""
        html = _render_health(_health_payload(), lang="en")
        assert "Short-term Overview" in html
        assert "Total" in html
        assert "短期记忆概况" not in html

    def test_render_soul_en(self):
        """_render_soul 传 lang=en 输出英文。"""
        html = _render_soul(_soul_payload("high"), lang="en")
        assert "High Risk" in html
        assert "高风险" not in html

    def test_render_config_en_all_good(self):
        """_render_config 传 lang=en，all_good 显示英文。"""
        html = _render_config(_config_payload(all_good=True), lang="en")
        assert "Config healthy" in html
        assert "配置健康" not in html

    def test_render_promotion_en(self):
        """_render_promotion 传 lang=en 显示英文标签。"""
        html = _render_promotion(_promotion_payload(), lang="en")
        assert "Pre-promotion Audit" in html
        assert "Pass" in html
        assert "Skip" in html
        assert "晋升前预检" not in html

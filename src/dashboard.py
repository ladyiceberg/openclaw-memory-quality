from __future__ import annotations
"""
dashboard.py · OpenClaw Memory Health Dashboard HTML 生成器

从 session_store 读取各工具最新运行结果，生成一个完整的 HTML 文件。
苹果极简风格，与 memory-quality-mcp 视觉体系对齐。

设计原则：
  - 苹果 Light 调性：systemGray6 背景、白色卡片、SF Pro 字体栈
  - Summary First：进入页面先看综合健康分，细节折叠展开
  - Section 有数据才展示，无数据显示灰色占位（不报错）
  - 纯 HTML + CSS + 内联 JS，零外部依赖，本地文件即可运行
  - 所有颜色来自苹果官方 HIG 系统色（2024）
"""

import json
import math
import time
import webbrowser
from pathlib import Path
from typing import Optional

from src.session_store import load_dashboard_data


# ── 苹果官方系统色（Light Mode，Apple HIG 2024）────────────────────────────────

COLORS = {
    # 背景层级
    "bg_page":      "#F2F2F7",   # systemGray6 - 页面底色
    "bg_card":      "#FFFFFF",   # systemBackground - 卡片白
    "bg_secondary": "#F2F2F7",   # systemGray6 - 卡片内次级区域
    "bg_tertiary":  "#E5E5EA",   # systemGray5 - 分隔/进度条底色

    # 文字层级
    "text_primary":   "#1D1D1F",  # 苹果标准正文黑
    "text_secondary": "#6E6E73",  # 副文字灰
    "text_tertiary":  "#AEAEB2",  # 时间戳/次要信息
    "text_link":      "#0066CC",  # 苹果链接蓝

    # 边框
    "border":  "rgba(0,0,0,0.08)",
    "divider": "rgba(0,0,0,0.05)",

    # 状态色（苹果官方系统色）
    "green":  "#34C759",  # systemGreen
    "orange": "#FF9500",  # systemOrange
    "red":    "#FF3B30",  # systemRed
    "blue":   "#007AFF",  # systemBlue
    "indigo": "#5856D6",  # systemIndigo - 健康分圆环主色
    "gray":   "#8E8E93",  # systemGray

    # 状态背景（8% 透明度）
    "green_bg":  "rgba(52,199,89,0.08)",
    "orange_bg": "rgba(255,149,0,0.08)",
    "red_bg":    "rgba(255,59,48,0.08)",
    "blue_bg":   "rgba(0,122,255,0.08)",
    "indigo_bg": "rgba(88,86,214,0.08)",
    "gray_bg":   "rgba(142,142,147,0.08)",
}


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def _format_ago(ts: float) -> str:
    """将时间戳格式化为'N 小时前'等形式。"""
    if ts <= 0:
        return "未知"
    secs = time.time() - ts
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{int(secs/60)} 分钟前"
    if secs < 86400:
        return f"{int(secs/3600)} 小时前"
    return f"{int(secs/86400)} 天前"


def _health_color(score: Optional[int]) -> str:
    """根据综合健康分返回颜色。"""
    if score is None:
        return COLORS["gray"]
    if score >= 80:
        return COLORS["green"]
    if score >= 60:
        return COLORS["orange"]
    return COLORS["red"]


def _action_color(action: str) -> str:
    return {"keep": COLORS["green"], "review": COLORS["orange"],
            "delete": COLORS["red"]}.get(action, COLORS["gray"])


def _action_bg(action: str) -> str:
    return {"keep": COLORS["green_bg"], "review": COLORS["orange_bg"],
            "delete": COLORS["red_bg"]}.get(action, COLORS["gray_bg"])


def _action_icon(action: str) -> str:
    return {"keep": "✓", "review": "!", "delete": "×"}.get(action, "?")


def _action_label_zh(action: str) -> str:
    return {"keep": "保留", "review": "复查", "delete": "删除"}.get(action, action)


def _risk_color(level: str) -> str:
    return {"ok": COLORS["green"], "low": COLORS["blue"],
            "medium": COLORS["orange"], "high": COLORS["red"]}.get(level, COLORS["gray"])


def _risk_bg(level: str) -> str:
    return {"ok": COLORS["green_bg"], "low": COLORS["blue_bg"],
            "medium": COLORS["orange_bg"], "high": COLORS["red_bg"]}.get(level, COLORS["gray_bg"])


def _risk_label_zh(level: str) -> str:
    return {"ok": "健康", "low": "低风险", "medium": "中等风险",
            "high": "高风险"}.get(level, level)


def _score_bar(value: int, max_val: int = 100, color: str = "") -> str:
    """生成横向进度条 HTML。"""
    pct = max(0, min(100, int(value / max_val * 100))) if max_val > 0 else 0
    c = color or COLORS["blue"]
    return (
        f'<div class="score-bar-track">'
        f'<div class="score-bar-fill" style="width:{pct}%;background:{c}"></div>'
        f'</div>'
    )


def _v1_status_zh(status: str) -> str:
    return {"exists": "来源存在", "deleted": "来源已删除",
            "possibly_moved": "可能已移动"}.get(status, status)


def _v3_status_zh(status: str) -> str:
    return {"ok": "无重复", "duplicate_winner": "重复保留",
            "duplicate_loser": "重复删除"}.get(status, status)


def _skip_reason_zh(reason: str) -> str:
    return {
        "source_deleted":   "来源文件已删除",
        "import_only":      "仅含 import 语句",
        "comments_only":    "仅含注释行",
        "boilerplate":      "空内容或样板代码",
        "debug_code":       "含调试输出代码",
        "already_promoted": "已存在于 MEMORY.md",
    }.get(reason, reason)


def _config_code_zh(code: str) -> str:
    return {
        "fts":       "FTS 降级模式（未使用语义 embedding）",
        "minscore":  "minScore 过低（噪音条目过多）",
        "mmr":       "MMR 未开启（重复条目多）",
        "embedding": "Embedding 质量不足",
    }.get(code, code)


# ── 综合健康分计算 ─────────────────────────────────────────────────────────────

def compute_health_score(
    longterm: Optional[tuple],
    health: Optional[dict],
    soul: Optional[dict],
) -> Optional[int]:
    """
    综合健康分（0-100）。

    权重：longterm 40% + health 40% + soul 20%
    有哪些数据就纳入哪些，按实际有的归一化权重。
    全部无数据时返回 None。
    """
    parts: list[tuple[float, float]] = []  # (score_0_to_100, weight)

    # longterm：keep 比例
    if longterm is not None:
        _, payload = longterm
        total = payload.get("total_items", 0)
        if total > 0:
            keep_n = payload.get("items_by_action", {}).get("keep", 0)
            parts.append((keep_n / total * 100, 0.40))

    # health：Retrieval Health + (反转) Promotion Risk
    if health is not None:
        rh = health.get("retrieval_health", 50)
        pr = health.get("promotion_risk", 50)
        combined = (rh + (100 - pr)) / 2
        parts.append((combined, 0.40))

    # soul：risk_level → 分值
    if soul is not None:
        soul_score = {"ok": 100, "low": 75, "medium": 50, "high": 25}.get(
            soul.get("risk_level", "ok"), 100
        )
        parts.append((soul_score, 0.20))

    if not parts:
        return None

    total_weight = sum(w for _, w in parts)
    score = sum(v * w for v, w in parts) / total_weight
    return max(0, min(100, int(round(score))))


# ── SVG 圆环组件（来自 memory-quality-mcp，保持一致）──────────────────────────

def _ring_svg(score: Optional[int]) -> str:
    """生成健康分圆环 SVG。score=None 时显示灰色占位圆环。"""
    radius = 54
    circumference = 2 * math.pi * radius  # ≈ 339.3
    color = _health_color(score)

    if score is None:
        display_text = "--"
        progress = 0.0
    else:
        display_text = str(score)
        progress = score / 100 * circumference

    gap = circumference - progress

    return f"""<svg class="ring-svg" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="{radius}" stroke="{COLORS['bg_tertiary']}" stroke-width="8"/>
  <circle cx="60" cy="60" r="{radius}"
    stroke="{color}" stroke-width="8" stroke-linecap="round"
    stroke-dasharray="{progress:.1f} {gap:.1f}"
    transform="rotate(-90 60 60)"
    style="transition: stroke-dasharray 0.8s ease"/>
  <text x="60" y="56" text-anchor="middle" dominant-baseline="middle"
    font-family="-apple-system, SF Pro Display, Helvetica Neue, sans-serif"
    font-size="26" font-weight="700" fill="{color}">{display_text}</text>
  <text x="60" y="74" text-anchor="middle" dominant-baseline="middle"
    font-family="-apple-system, SF Pro Text, Helvetica Neue, sans-serif"
    font-size="10" font-weight="400" fill="{COLORS['text_tertiary']}" letter-spacing="0.5">/ 100</text>
</svg>"""


# ── 占位卡片 ───────────────────────────────────────────────────────────────────

def _placeholder_card(title: str, hint: str) -> str:
    """无数据时的灰色占位卡片。"""
    return f"""<div class="section-card placeholder-card">
  <div class="section-header">
    <span class="section-title" style="color:{COLORS['text_tertiary']}">{title}</span>
  </div>
  <div class="placeholder-body">
    <span class="placeholder-hint">{hint}</span>
  </div>
</div>"""


# ── Section 1：长期记忆 ────────────────────────────────────────────────────────

def _render_longterm(longterm: Optional[tuple]) -> str:
    if longterm is None:
        return _placeholder_card(
            "长期记忆",
            "运行 <code>/memory-cleanup</code> 获取长期记忆分析"
        )

    _, payload = longterm
    total      = payload.get("total_items", 0)
    sections_n = payload.get("sections_count", 0)
    non_std    = payload.get("non_standard_sections", 0)
    by_action  = payload.get("items_by_action", {})
    keep_n     = by_action.get("keep", 0)
    review_n   = by_action.get("review", 0)
    delete_n   = by_action.get("delete", 0)
    items      = payload.get("items", [])
    llm_eval   = payload.get("llm_eval")
    mtime      = payload.get("memory_md_mtime")

    # LLM eval badge
    llm_badge = ""
    if llm_eval:
        validity = llm_eval.get("validity", {})
        still_n    = sum(1 for v in validity.values() if v.get("verdict") == "still_valid")
        outdated_n = sum(1 for v in validity.values() if v.get("verdict") == "outdated")
        uncertain_n = sum(1 for v in validity.values() if v.get("verdict") == "uncertain")
        merge_n    = len(llm_eval.get("merge_suggestions", []))
        blue       = COLORS["blue"]
        merge_span = (
            f'<span class="sep">·</span>'
            f'<span style="color:{blue}">合并建议 {merge_n}</span>'
        ) if merge_n > 0 else ""
        llm_badge = (
            f'<div class="llm-badge">'
            f'<span class="llm-tag">🤖 LLM</span>'
            f'<span>有效 {still_n}</span>'
            f'<span class="sep">·</span>'
            f'<span style="color:{COLORS["red"]}">过时 {outdated_n}</span>'
            f'<span class="sep">·</span>'
            f'<span style="color:{COLORS["gray"]}">不确定 {uncertain_n}</span>'
            f'{merge_span}'
            f'</div>'
        )

    # 非标准段落警告
    non_std_warn = ""
    if non_std > 0:
        non_std_warn = f'<div class="warn-row">⚠️ {non_std} 个非标准段落（用户手写内容，不参与清理）</div>'

    # 条目详情
    delete_items = [i for i in items if i.get("action_hint") == "delete"]
    review_items = [i for i in items if i.get("action_hint") == "review"]
    keep_items   = [i for i in items if i.get("action_hint") == "keep"]

    def _entry_row(item: dict) -> str:
        action  = item.get("action_hint", "keep")
        snippet = item.get("snippet", "")[:60] + ("…" if len(item.get("snippet","")) > 60 else "")
        source  = item.get("source_path", "")
        start   = item.get("source_start", 0)
        end     = item.get("source_end", 0)
        v1      = _v1_status_zh(item.get("v1_status", ""))
        v3      = _v3_status_zh(item.get("v3_status", ""))
        score   = item.get("score", 0.0)
        color   = _action_color(action)
        bg      = _action_bg(action)
        icon    = _action_icon(action)
        label   = _action_label_zh(action)
        return f"""<div class="entry-card" onclick="this.classList.toggle('expanded')">
      <div class="entry-header">
        <div class="entry-left">
          <span class="entry-badge" style="color:{color};background:{bg}">{icon} {label}</span>
          <span class="entry-name">{snippet}</span>
        </div>
        <div class="entry-right">
          <span class="entry-meta muted">{source}</span>
          <svg class="chevron" width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M3 4.5L6 7.5L9 4.5" stroke="{COLORS['text_tertiary']}" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
      </div>
      <div class="entry-detail">
        <div class="detail-row"><span class="detail-label">来源</span> {source}:{start}-{end}</div>
        <div class="detail-row"><span class="detail-label">文件状态</span> {v1}</div>
        <div class="detail-row"><span class="detail-label">重复检测</span> {v3}</div>
        <div class="detail-row"><span class="detail-label">晋升分</span> {score:.3f}</div>
      </div>
    </div>"""

    def _group(title: str, action: str, group_items: list, default_open: bool) -> str:
        if not group_items:
            return ""
        open_attr = "open" if default_open else ""
        color = _action_color(action)
        rows  = "\n".join(_entry_row(i) for i in group_items)
        return f"""<details class="group-details" {open_attr}>
    <summary class="group-summary">
      <span style="color:{color}">{_action_icon(action)} {title}</span>
      <span class="group-count" style="color:{color}">{len(group_items)}</span>
      <svg class="section-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M3.5 5.25L7 8.75L10.5 5.25" stroke="{COLORS['text_secondary']}" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </summary>
    <div class="group-body">{rows}</div>
  </details>"""

    delete_group = _group("建议删除", "delete", delete_items, default_open=True)
    review_group = _group("建议复查", "review", review_items, default_open=True)
    keep_group   = _group("状态良好", "keep",   keep_items,   default_open=False)

    return f"""<div class="section-card">
  <div class="section-header">
    <span class="section-title">长期记忆</span>
    <span class="section-meta">{sections_n} 个 section · {total} 条记忆</span>
  </div>
  <div class="stats-row">
    <div class="stat-item">
      <div class="stat-number" style="color:{COLORS['green']}">{keep_n}</div>
      <div class="stat-label">保留</div>
    </div>
    <div class="stat-item">
      <div class="stat-number" style="color:{COLORS['orange']}">{review_n}</div>
      <div class="stat-label">复查</div>
    </div>
    <div class="stat-item">
      <div class="stat-number" style="color:{COLORS['red']}">{delete_n}</div>
      <div class="stat-label">删除</div>
    </div>
  </div>
  {llm_badge}
  {non_std_warn}
  <div class="groups-container">
    {delete_group}
    {review_group}
    {keep_group}
  </div>
</div>"""


# ── Section 2：短期记忆 ────────────────────────────────────────────────────────

def _render_health(health: Optional[dict]) -> str:
    if health is None:
        return _placeholder_card(
            "短期记忆概况",
            "运行 <code>/memory-check</code> 获取短期记忆概况"
        )

    total   = health.get("shortterm_total", 0)
    zombie  = health.get("zombie_count", 0)
    zratio  = health.get("zombie_ratio", 0.0)
    fp      = health.get("fp_count", 0)
    fpratio = health.get("fp_ratio", 0.0)
    rh      = health.get("retrieval_health", 0)
    pr      = health.get("promotion_risk", 0)
    fts     = health.get("fts_degradation", False)

    rh_color = COLORS["green"] if rh >= 80 else (COLORS["orange"] if rh >= 60 else COLORS["red"])
    pr_color = COLORS["green"] if pr <= 20 else (COLORS["orange"] if pr <= 50 else COLORS["red"])

    fts_warn = ""
    if fts:
        fts_warn = f'<div class="warn-row">⚠️ 检测到 FTS 降级模式，建议配置 embedding provider</div>'

    return f"""<div class="section-card">
  <div class="section-header">
    <span class="section-title">短期记忆概况</span>
  </div>
  <div class="stats-row three-col">
    <div class="stat-item">
      <div class="stat-number">{total:,}</div>
      <div class="stat-label">总条目</div>
    </div>
    <div class="stat-item">
      <div class="stat-number" style="color:{COLORS['orange']}">{zombie:,}</div>
      <div class="stat-label">僵尸 {zratio*100:.1f}%</div>
    </div>
    <div class="stat-item">
      <div class="stat-number" style="color:{COLORS['orange']}">{fp:,}</div>
      <div class="stat-label">假阳性 {fpratio*100:.1f}%</div>
    </div>
  </div>
  <div class="diag-row">
    <div class="diag-item">
      <div class="diag-label">Retrieval Health</div>
      <div class="diag-score" style="color:{rh_color}">{rh}<span class="diag-unit">/100</span></div>
      {_score_bar(rh, 100, rh_color)}
    </div>
    <div class="diag-item">
      <div class="diag-label">Promotion Risk</div>
      <div class="diag-score" style="color:{pr_color}">{pr}<span class="diag-unit">/100</span></div>
      {_score_bar(pr, 100, pr_color)}
    </div>
  </div>
  {fts_warn}
</div>"""


# ── Section 3：晋升前预检 ──────────────────────────────────────────────────────

def _render_promotion(promotion: Optional[dict]) -> str:
    if promotion is None:
        return _placeholder_card(
            "晋升前预检",
            "运行 <code>/memory-promote</code> 获取晋升前预检报告"
        )

    total_unp  = promotion.get("total_unpromotted", 0)
    top_n      = promotion.get("top_n", 10)
    pass_n     = promotion.get("pass_count", 0)
    skip_n     = promotion.get("skip_count", 0)
    flag_n     = promotion.get("flag_count", 0)
    candidates = promotion.get("candidates", [])
    llm_eval   = promotion.get("llm_eval")

    skip_items = [c for c in candidates if c.get("verdict") == "skip"]
    flag_items = [c for c in candidates if c.get("verdict") == "flag"]

    def _cand_row(c: dict) -> str:
        verdict = c.get("verdict", "pass")
        reason  = c.get("skip_reason") or c.get("flag_reason") or ""
        path    = c.get("path", "")
        start   = c.get("start", 0)
        end     = c.get("end", 0)
        score   = c.get("composite", 0.0)
        color   = _action_color("delete" if verdict == "skip" else "review")
        bg      = _action_bg("delete" if verdict == "skip" else "review")
        icon    = "✕" if verdict == "skip" else "⚠"
        reason_zh = _skip_reason_zh(reason) if reason else ""
        return f"""<div class="entry-card">
      <div class="entry-header">
        <div class="entry-left">
          <span class="entry-badge" style="color:{color};background:{bg}">{icon}</span>
          <span class="entry-name">{path}:{start}-{end}</span>
        </div>
        <div class="entry-right">
          <span class="entry-meta muted">≈{score:.2f}</span>
          {f'<span class="entry-meta" style="color:{color}">{reason_zh}</span>' if reason_zh else ""}
        </div>
      </div>
    </div>"""

    skip_section = ""
    if skip_items or flag_items:
        open_attr = "open" if skip_items else ""
        rows = "\n".join(_cand_row(c) for c in (skip_items + flag_items))
        skip_section = f"""<details class="group-details" {open_attr}>
    <summary class="group-summary">
      <span style="color:{COLORS['red']}">需处理条目</span>
      <span class="group-count" style="color:{COLORS['red']}">{len(skip_items)+len(flag_items)}</span>
      <svg class="section-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M3.5 5.25L7 8.75L10.5 5.25" stroke="{COLORS['text_secondary']}" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </summary>
    <div class="group-body">{rows}</div>
  </details>"""

    llm_row = ""
    if llm_eval:
        lt_n  = llm_eval.get("long_term_count", 0)
        ot_n  = llm_eval.get("one_time_count", 0)
        unc_n = llm_eval.get("uncertain_count", 0)
        llm_row = f"""<div class="llm-badge">
    <span class="llm-tag">🤖 LLM</span>
    <span style="color:{COLORS['green']}">长期价值 {lt_n}</span>
    <span class="sep">·</span>
    <span style="color:{COLORS['orange']}">一次性 {ot_n}</span>
    <span class="sep">·</span>
    <span style="color:{COLORS['gray']}">不确定 {unc_n}</span>
  </div>"""

    return f"""<div class="section-card">
  <div class="section-header">
    <span class="section-title">晋升前预检</span>
    <span class="section-meta">共 {total_unp} 条候选 · 检查 Top {top_n}</span>
  </div>
  <div class="stats-row">
    <div class="stat-item">
      <div class="stat-number" style="color:{COLORS['green']}">{pass_n}</div>
      <div class="stat-label">通过</div>
    </div>
    <div class="stat-item">
      <div class="stat-number" style="color:{COLORS['red']}">{skip_n}</div>
      <div class="stat-label">建议跳过</div>
    </div>
    <div class="stat-item">
      <div class="stat-number" style="color:{COLORS['orange']}">{flag_n}</div>
      <div class="stat-label">需关注</div>
    </div>
  </div>
  {llm_row}
  <div class="groups-container">
    {skip_section}
  </div>
</div>"""


# ── Section 4：SOUL.md ─────────────────────────────────────────────────────────

def _render_soul(soul: Optional[dict]) -> str:
    if soul is None:
        return _placeholder_card(
            "SOUL.md 健康",
            "运行 <code>/soul-check</code> 获取 SOUL.md 健康报告"
        )

    level     = soul.get("risk_level", "ok")
    char_cnt  = soul.get("char_count", 0)
    dir_cnt   = soul.get("directive_count", 0)
    sections  = soul.get("sections", [])
    color     = _risk_color(level)
    bg        = _risk_bg(level)
    label     = _risk_label_zh(level)

    section_tags = " ".join(
        f'<span class="section-tag">{s}</span>' for s in sections
    ) if sections else f'<span style="color:{COLORS["text_tertiary"]}">无标准 section</span>'

    return f"""<div class="section-card">
  <div class="section-header">
    <span class="section-title">SOUL.md 健康</span>
  </div>
  <div class="soul-summary">
    <span class="risk-badge" style="color:{color};background:{bg}">{label}</span>
    <span class="soul-meta">{char_cnt:,} 字符</span>
    <span class="sep">·</span>
    <span class="soul-meta">{dir_cnt} 条强指令词</span>
  </div>
  <div class="section-tags">
    {section_tags}
  </div>
</div>"""


# ── Section 5：配置诊断 ────────────────────────────────────────────────────────

def _render_config(config: Optional[dict]) -> str:
    if config is None:
        return _placeholder_card(
            "配置诊断",
            "运行 <code>/memory-diagnose</code> 获取配置诊断报告"
        )

    all_good = config.get("all_good", True)
    issues   = config.get("issues", [])

    if all_good:
        return f"""<div class="section-card">
  <div class="section-header">
    <span class="section-title">配置诊断</span>
  </div>
  <div class="config-good">
    <span style="color:{COLORS['green']}">✅</span>
    <span>配置健康，未发现问题</span>
  </div>
</div>"""

    issue_rows = "\n".join(
        f"""<div class="issue-row">
      <span class="issue-badge" style="color:{COLORS['orange']};background:{COLORS['orange_bg']}">⚠</span>
      <span class="issue-text">{_config_code_zh(i.get('code',''))}</span>
    </div>"""
        for i in issues
    )

    return f"""<div class="section-card">
  <div class="section-header">
    <span class="section-title">配置诊断</span>
  </div>
  <details class="group-details" open>
    <summary class="group-summary">
      <span style="color:{COLORS['orange']}">发现 {len(issues)} 个配置问题</span>
      <svg class="section-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M3.5 5.25L7 8.75L10.5 5.25" stroke="{COLORS['text_secondary']}" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </summary>
    <div class="group-body">{issue_rows}</div>
  </details>
</div>"""


# ── CSS ────────────────────────────────────────────────────────────────────────

def _build_css() -> str:
    C = COLORS
    return f"""
/* ── Reset & Base ─────────────────────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
  background: {C['bg_page']};
  color: {C['text_primary']};
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}}

/* ── Layout ──────────────────────────────────────────────────────── */
.page {{ max-width: 700px; margin: 0 auto; padding: 48px 20px 80px; }}

/* ── Header ──────────────────────────────────────────────────────── */
.header {{ margin-bottom: 28px; }}
.header-top {{
  display: flex; align-items: center;
  justify-content: space-between; margin-bottom: 4px;
}}
.header-title {{
  font-size: 22px; font-weight: 700; letter-spacing: -0.3px;
}}
.header-badge {{
  font-size: 11px; font-weight: 500; color: {C['text_tertiary']};
  background: {C['bg_card']}; border: 1px solid {C['border']};
  border-radius: 20px; padding: 3px 10px;
}}
.header-sub {{ font-size: 13px; color: {C['text_tertiary']}; }}

/* ── Hero Card ───────────────────────────────────────────────────── */
.hero-card {{
  background: {C['bg_card']};
  border-radius: 16px;
  box-shadow: 0 1px 0 {C['border']}, 0 4px 20px rgba(0,0,0,0.05);
  padding: 32px 28px 28px;
  margin-bottom: 12px;
  display: flex; align-items: center; gap: 32px;
}}
.ring-svg {{ width: 120px; height: 120px; flex-shrink: 0; }}
.hero-right {{ flex: 1; min-width: 0; }}
.hero-headline {{
  font-size: 20px; font-weight: 700; letter-spacing: -0.3px;
  margin-bottom: 4px;
}}
.hero-sub {{
  font-size: 14px; color: {C['text_secondary']};
  margin-bottom: 16px; line-height: 1.4;
}}
.hero-coverage {{
  font-size: 12px; color: {C['text_tertiary']};
}}
.coverage-dot {{ display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}

/* ── Section Cards ───────────────────────────────────────────────── */
.section-card {{
  background: {C['bg_card']};
  border-radius: 14px;
  box-shadow: 0 1px 0 {C['border']}, 0 2px 10px rgba(0,0,0,0.04);
  margin-bottom: 10px;
  overflow: hidden;
}}
.section-header {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 18px 12px;
}}
.section-title {{ font-size: 15px; font-weight: 600; }}
.section-meta {{ font-size: 12px; color: {C['text_tertiary']}; }}

/* ── Placeholder Card ────────────────────────────────────────────── */
.placeholder-card {{ border: 1.5px dashed {C['bg_tertiary']}; box-shadow: none; }}
.placeholder-body {{ padding: 16px 18px 18px; }}
.placeholder-hint {{
  font-size: 13px; color: {C['text_tertiary']};
}}
.placeholder-hint code {{
  font-family: "SF Mono", Menlo, monospace;
  font-size: 12px; background: {C['bg_secondary']};
  border-radius: 4px; padding: 1px 5px;
  color: {C['text_secondary']};
}}

/* ── Stats Row ───────────────────────────────────────────────────── */
.stats-row {{
  display: flex; gap: 0;
  border: 1px solid {C['border']}; border-radius: 10px;
  overflow: hidden; margin: 0 18px 14px;
}}
.stat-item {{
  flex: 1; padding: 10px 0; text-align: center;
  border-right: 1px solid {C['border']};
}}
.stat-item:last-child {{ border-right: none; }}
.stat-number {{
  font-size: 22px; font-weight: 700; letter-spacing: -0.5px;
  line-height: 1; margin-bottom: 3px;
}}
.stat-label {{ font-size: 11px; color: {C['text_tertiary']}; }}

/* ── Diagnostic Row (Section 2) ──────────────────────────────────── */
.diag-row {{
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 10px; padding: 0 18px 14px;
}}
.diag-item {{
  background: {C['bg_secondary']}; border-radius: 10px; padding: 12px 14px;
}}
.diag-label {{
  font-size: 11px; color: {C['text_tertiary']}; margin-bottom: 4px;
}}
.diag-score {{
  font-size: 22px; font-weight: 700; letter-spacing: -0.5px;
  line-height: 1; margin-bottom: 8px;
}}
.diag-unit {{
  font-size: 12px; font-weight: 400; color: {C['text_tertiary']};
}}
.score-bar-track {{
  height: 3px; background: {C['bg_tertiary']};
  border-radius: 2px; overflow: hidden;
}}
.score-bar-fill {{
  height: 100%; border-radius: 2px; transition: width 0.6s ease;
}}

/* ── SOUL Section ────────────────────────────────────────────────── */
.soul-summary {{
  display: flex; align-items: center; gap: 10px;
  padding: 0 18px 12px; flex-wrap: wrap;
}}
.risk-badge {{
  font-size: 12px; font-weight: 600; border-radius: 6px; padding: 3px 9px;
}}
.soul-meta {{ font-size: 13px; color: {C['text_secondary']}; }}
.sep {{ color: {C['text_tertiary']}; }}
.section-tags {{
  display: flex; flex-wrap: wrap; gap: 6px;
  padding: 0 18px 16px;
}}
.section-tag {{
  font-size: 11px; background: {C['bg_secondary']};
  border-radius: 5px; padding: 2px 8px;
  color: {C['text_secondary']};
}}

/* ── Config Section ──────────────────────────────────────────────── */
.config-good {{
  display: flex; align-items: center; gap: 8px;
  padding: 12px 18px 16px; font-size: 14px; color: {C['text_secondary']};
}}
.issue-row {{
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px;
}}
.issue-badge {{
  font-size: 11px; font-weight: 600; border-radius: 5px; padding: 2px 7px;
  flex-shrink: 0;
}}
.issue-text {{ font-size: 13px; color: {C['text_secondary']}; }}

/* ── LLM Badge ───────────────────────────────────────────────────── */
.llm-badge {{
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin: 0 18px 12px;
  background: {C['indigo_bg']}; border-radius: 8px; padding: 7px 12px;
  font-size: 12px; color: {C['text_secondary']};
}}
.llm-tag {{
  font-size: 11px; font-weight: 600;
  color: {C['indigo']}; background: rgba(88,86,214,0.12);
  border-radius: 4px; padding: 2px 7px;
}}

/* ── Warn Row ────────────────────────────────────────────────────── */
.warn-row {{
  margin: 0 18px 12px;
  background: {C['orange_bg']}; border-radius: 8px;
  padding: 7px 12px; font-size: 12px; color: {C['text_secondary']};
}}

/* ── Groups (details/summary) ────────────────────────────────────── */
.groups-container {{ padding: 0 10px 10px; }}
.group-details {{
  border-radius: 10px; overflow: hidden; margin-bottom: 4px;
}}
.group-summary {{
  display: flex; align-items: center; gap: 8px;
  padding: 12px 14px; cursor: pointer; user-select: none;
  list-style: none; font-size: 14px; font-weight: 500;
  transition: background 0.15s;
}}
.group-summary:hover {{ background: {C['bg_page']}; }}
.group-summary::-webkit-details-marker {{ display: none; }}
.group-count {{
  font-size: 13px; font-weight: 600; margin-left: 2px;
}}
.section-chevron {{ margin-left: auto; flex-shrink: 0; transition: transform 0.2s; }}
details[open] .section-chevron {{ transform: rotate(180deg); }}
.group-body {{
  border-top: 1px solid {C['divider']};
  padding: 6px 0 2px; display: flex; flex-direction: column; gap: 2px;
}}

/* ── Entry Card ──────────────────────────────────────────────────── */
.entry-card {{
  border-radius: 8px; padding: 10px 14px;
  cursor: pointer; transition: background 0.15s;
}}
.entry-card:hover {{ background: {C['bg_page']}; }}
.entry-header {{
  display: flex; align-items: center;
  justify-content: space-between; gap: 8px;
}}
.entry-left {{
  display: flex; align-items: center; gap: 8px;
  min-width: 0; flex: 1;
}}
.entry-badge {{
  font-size: 11px; font-weight: 600; border-radius: 5px;
  padding: 2px 7px; white-space: nowrap; flex-shrink: 0;
}}
.entry-name {{
  font-size: 13px; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.entry-right {{
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}}
.entry-meta {{ font-size: 11px; color: {C['text_secondary']}; white-space: nowrap; }}
.entry-meta.muted {{ color: {C['text_tertiary']}; }}
.chevron {{ transition: transform 0.2s; flex-shrink: 0; }}
.entry-card.expanded .chevron {{ transform: rotate(180deg); }}
.entry-detail {{
  display: none; margin-top: 8px; padding-top: 8px;
  border-top: 1px solid {C['divider']};
}}
.entry-card.expanded .entry-detail {{ display: block; }}
.detail-row {{
  font-size: 12px; color: {C['text_secondary']};
  padding: 2px 0; display: flex; gap: 6px;
}}
.detail-label {{
  color: {C['text_tertiary']}; min-width: 60px; flex-shrink: 0;
}}

/* ── Footer ──────────────────────────────────────────────────────── */
.footer {{
  margin-top: 40px; text-align: center;
  font-size: 12px; color: {C['text_tertiary']};
}}
.footer a {{ color: {C['text_link']}; text-decoration: none; }}

/* ── Responsive ──────────────────────────────────────────────────── */
@media (max-width: 520px) {{
  .hero-card {{ flex-direction: column; gap: 20px; align-items: flex-start; }}
  .ring-svg {{ width: 100px; height: 100px; }}
  .page {{ padding: 24px 14px 60px; }}
}}
"""


# ── 主 HTML 生成 ───────────────────────────────────────────────────────────────

def generate_dashboard_html(
    data: dict,
    workspace: str = "",
) -> str:
    """
    生成完整的 Dashboard HTML 字符串。

    Args:
        data      : load_dashboard_data() 的返回值
        workspace : workspace 路径（用于 header 显示）

    Returns:
        完整 HTML 字符串
    """
    longterm  = data.get("longterm_audit")
    health    = data.get("health")
    promotion = data.get("promotion")
    soul      = data.get("soul")
    config    = data.get("config")

    # 综合健康分
    health_score = compute_health_score(longterm, health, soul)
    health_color = _health_color(health_score)

    # Header：取所有 section 中最新的 checked_at
    timestamps = []
    if longterm:
        _, lp = longterm
        if lp.get("memory_md_mtime"):
            timestamps.append(lp["memory_md_mtime"])
    for snap in [health, promotion, soul, config]:
        if snap and snap.get("checked_at"):
            timestamps.append(snap["checked_at"])
    latest_ts = max(timestamps) if timestamps else 0
    updated_ago = _format_ago(latest_ts) if latest_ts > 0 else "从未运行"

    # workspace 显示名
    ws_display = Path(workspace).name if workspace else "未知 workspace"
    scan_time  = (
        time.strftime("%Y-%m-%d %H:%M", time.localtime(latest_ts))
        if latest_ts > 0 else "—"
    )

    # Hero 状态文字
    if health_score is None:
        hero_headline = "暂无数据"
        hero_sub = "请运行任意检查工具以获取健康评分"
    elif health_score >= 80:
        hero_headline = "记忆系统状态良好"
        hero_sub = "各项指标健康，无需立即处理。"
    elif health_score >= 60:
        hero_headline = "记忆系统需要关注"
        hero_sub = "发现部分问题，建议尽快处理。"
    else:
        hero_headline = "记忆系统需要处理"
        hero_sub = "存在较多问题，建议立即运行清理工具。"

    # Hero 数据覆盖说明
    covered = []
    if longterm:  covered.append(("green",  "长期记忆"))
    if health:    covered.append(("green",  "短期记忆"))
    if soul:      covered.append(("green",  "SOUL.md"))
    if not longterm: covered.append(("gray", "长期记忆"))
    if not health:   covered.append(("gray", "短期记忆"))
    if not soul:     covered.append(("gray", "SOUL.md"))

    coverage_html = " ".join(
        f'<span class="coverage-dot" style="background:{COLORS[c]}"></span>{label}'
        for c, label in covered
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenClaw Memory Health</title>
<style>
{_build_css()}
</style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <div class="header">
    <div class="header-top">
      <span class="header-title">OpenClaw Memory Health</span>
      <span class="header-badge">最近更新：{updated_ago}</span>
    </div>
    <div class="header-sub">{ws_display} &nbsp;·&nbsp; {scan_time}</div>
  </div>

  <!-- Hero -->
  <div class="hero-card">
    {_ring_svg(health_score)}
    <div class="hero-right">
      <div class="hero-headline">{hero_headline}</div>
      <div class="hero-sub">{hero_sub}</div>
      <div class="hero-coverage">{coverage_html}</div>
    </div>
  </div>

  <!-- Section 1: 长期记忆 -->
  {_render_longterm(longterm)}

  <!-- Section 2: 短期记忆 -->
  {_render_health(health)}

  <!-- Section 3: 晋升前预检 -->
  {_render_promotion(promotion)}

  <!-- Section 4: SOUL.md -->
  {_render_soul(soul)}

  <!-- Section 5: 配置诊断 -->
  {_render_config(config)}

  <!-- Footer -->
  <div class="footer">
    由 <a href="https://github.com/ladyiceberg/openclaw-memory-quality">openclaw-memhealth</a> 生成
    &nbsp;·&nbsp;
    <a href="https://github.com/ladyiceberg/openclaw-memory-quality/issues/new">报告问题</a>
  </div>

</div>
<script>
// 展开/折叠条目详情
document.querySelectorAll('.entry-card').forEach(card => {{
  card.addEventListener('click', () => card.classList.toggle('expanded'));
}});

// 圆环加载动画
document.addEventListener('DOMContentLoaded', () => {{
  const circle = document.querySelector('circle[stroke-dasharray]');
  if (circle) {{
    const final = circle.getAttribute('stroke-dasharray');
    circle.setAttribute('stroke-dasharray', '0 339.3');
    setTimeout(() => circle.setAttribute('stroke-dasharray', final), 100);
  }}
}});
</script>
</body>
</html>"""


# ── 对外接口 ───────────────────────────────────────────────────────────────────

def open_dashboard(
    workspace: str,
    output_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> Path:
    """
    读取 session_store 数据，生成 Dashboard HTML，用系统浏览器打开。

    Args:
        workspace   : workspace 路径
        output_path : HTML 文件保存路径（默认 ~/.openclaw-memhealth/dashboard.html）
        db_path     : 测试用，覆盖默认 DB 路径

    Returns:
        生成的 HTML 文件路径
    """
    if output_path is None:
        output_dir = Path.home() / ".openclaw-memhealth"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "dashboard.html"

    data = load_dashboard_data(workspace, db_path=db_path)
    html = generate_dashboard_html(data, workspace=workspace)
    output_path.write_text(html, encoding="utf-8")
    webbrowser.open(f"file://{output_path}")

    return output_path

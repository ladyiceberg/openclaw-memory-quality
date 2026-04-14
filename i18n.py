from __future__ import annotations
"""
i18n.py · 多语言文本

所有面向用户的输出文字集中在此，通过 t() 获取。
新增语言只需在 STRINGS 中加一个新的语言 dict。

用法：
    from i18n import t
    t("probe.no_workspace")           # 取当前语言文本
    t("probe.no_workspace", lang="zh") # 强制指定语言
"""

from config import detect_language

# ── 文本库 ────────────────────────────────────────────────────────────────────

STRINGS: dict[str, dict[str, str]] = {

    # ── probe / workspace ─────────────────────────────────────────────────────
    "probe.no_workspace": {
        "en": (
            "❌ No OpenClaw workspace found.\n\n"
            "Tried paths:\n{paths}\n\n"
            "Tips:\n"
            "- Make sure OpenClaw is installed and has been run at least once\n"
            "- Or set the OPENCLAW_WORKSPACE_DIR environment variable"
        ),
        "zh": (
            "❌ 未找到 OpenClaw workspace。\n\n"
            "已尝试路径：\n{paths}\n\n"
            "提示：\n"
            "- 确认 OpenClaw 已安装并运行过至少一次\n"
            "- 或通过环境变量 OPENCLAW_WORKSPACE_DIR 指定路径"
        ),
    },
    "probe.detected": {
        "en": "📌 OpenClaw {version} · {compat}",
        "zh": "📌 OpenClaw {version} · {compat}",
    },
    "probe.compat_ok": {
        "en": "Compatible",
        "zh": "已验证兼容",
    },
    "probe.compat_unknown": {
        "en": "Unverified version",
        "zh": "版本未经验证",
    },
    "probe.shortterm_found": {
        "en": "Short-term memory: {path} ✓",
        "zh": "短期记忆：{path} ✓",
    },
    "probe.shortterm_not_found": {
        "en": (
            "Short-term memory file not found.\n"
            "Tried: {paths}\n\n"
            "This usually means Memory Search is not configured.\n"
            "Please set up an embedding provider (e.g. VOYAGE_API_KEY)."
        ),
        "zh": (
            "未找到短期记忆文件。\n"
            "已尝试：{paths}\n\n"
            "通常原因：Memory Search 尚未配置。\n"
            "请设置 embedding provider（如 VOYAGE_API_KEY）。"
        ),
    },
    "probe.longterm_found": {
        "en": "Long-term memory: MEMORY.md ({fmt}) ✓",
        "zh": "长期记忆：MEMORY.md（{fmt}）✓",
    },
    "probe.longterm_not_found": {
        "en": "MEMORY.md not found — Dreaming has not triggered yet.",
        "zh": "MEMORY.md 不存在，Dreaming 尚未触发过。",
    },
    "probe.longterm_fmt_dreaming": {
        "en": "Dreaming format",
        "zh": "Dreaming 格式",
    },
    "probe.longterm_fmt_manual": {
        "en": "manual format",
        "zh": "手动维护格式",
    },
    "probe.longterm_fmt_unknown": {
        "en": "unknown format",
        "zh": "未知格式",
    },
    "probe.soul_found": {
        "en": "SOUL.md ✓",
        "zh": "SOUL.md ✓",
    },
    "probe.soul_not_found": {
        "en": "SOUL.md not found.",
        "zh": "SOUL.md 不存在。",
    },
    "probe.unknown_format_warning": {
        "en": (
            "⚠️ MEMORY.md format not recognized.\n\n"
            "Available features:\n"
            "  ✅ Short-term memory health check\n"
            "  ✅ Retrieval quality diagnosis\n"
            "  ❌ Long-term memory audit (requires recognizable MEMORY.md format)\n\n"
            "→ Help us support your version: {issue_url}"
        ),
        "zh": (
            "⚠️ MEMORY.md 格式未能识别。\n\n"
            "当前可用功能：\n"
            "  ✅ 短期记忆健康检查\n"
            "  ✅ 检索质量诊断\n"
            "  ❌ 长期记忆审计（需要识别 MEMORY.md 格式）\n\n"
            "→ 帮助我们支持你的版本：{issue_url}"
        ),
    },

    # ── health check ──────────────────────────────────────────────────────────
    "health.header": {
        "en": "📊 OpenClaw Memory Health Check",
        "zh": "📊 OpenClaw 记忆健康检查",
    },
    "health.shortterm_summary": {
        "en": "Short-term memory: {total} entries\n  ├─ Zombie entries: {zombie} ({zombie_pct}%)\n  └─ False-positive suspects: {fp} ({fp_pct}%)",
        "zh": "短期记忆：{total} 条\n  ├─ 僵尸条目：{zombie} 条（{zombie_pct}%）\n  └─ 假阳性嫌疑：{fp} 条（{fp_pct}%）",
    },
    "health.longterm_summary": {
        "en": "Long-term memory: MEMORY.md — {sections} sections, {items} entries",
        "zh": "长期记忆：MEMORY.md 共 {sections} 个 section，{items} 条记忆",
    },
    "health.longterm_na": {
        "en": "Long-term memory: MEMORY.md not found or format unrecognized",
        "zh": "长期记忆：MEMORY.md 不存在或格式未识别",
    },
    "health.scores": {
        "en": "Diagnostic scores:\n  Retrieval Health:  {rh} / 100  {rh_icon}\n  Promotion Risk:    {pr} / 100  {pr_icon}\n  Long-term Rot:     {lr}",
        "zh": "系统诊断分：\n  Retrieval Health：{rh} / 100  {rh_icon}\n  Promotion Risk：  {pr} / 100  {pr_icon}\n  Long-term Rot：   {lr}",
    },
    "health.longterm_rot_na": {
        "en": "-- (run memory_longterm_audit_oc to get this score)",
        "zh": "-- （运行 memory_longterm_audit_oc 获取）",
    },
    "health.fts_warning": {
        "en": "⚠️ Retrieval may be in FTS-fallback or weak-embedding mode",
        "zh": "⚠️ 推断：检索可能处于 FTS 降级或弱 embedding 模式",
    },
    "health.suggest_diagnose": {
        "en": "→ Run memory_retrieval_diagnose_oc() for details",
        "zh": "→ 运行 memory_retrieval_diagnose_oc() 查看详情",
    },
    "health.suggest_audit": {
        "en": "→ Run memory_longterm_audit_oc() to check long-term memory rot",
        "zh": "→ 运行 memory_longterm_audit_oc() 查看长期记忆腐化情况",
    },

    # ── longterm audit ────────────────────────────────────────────────────────
    "audit.header": {
        "en": "📋 Long-term Memory Audit",
        "zh": "📋 长期记忆审计",
    },
    "audit.summary": {
        "en": "MEMORY.md: {sections} sections, {items} entries",
        "zh": "MEMORY.md：{sections} 个 section，{items} 条记忆",
    },
    "audit.results_header": {
        "en": "Audit results:",
        "zh": "审计结果：",
    },
    "audit.keep": {
        "en": "  ✓ Keep:            {n} ({pct}%)",
        "zh": "  ✓ 保留（keep）：           {n} 条（{pct}%）",
    },
    "audit.review": {
        "en": "  ! Review:          {n} ({pct}%)",
        "zh": "  ! 复查（review）：          {n} 条（{pct}%）",
    },
    "audit.delete": {
        "en": "  ✕ Suggested delete: {n} ({pct}%)",
        "zh": "  ✕ 建议删除（delete）：      {n} 条（{pct}%）",
    },
    "audit.delete_reasons_header": {
        "en": "Delete reason breakdown:",
        "zh": "删除原因分布：",
    },
    "audit.reason_deleted": {
        "en": "  Source file deleted:   {n}",
        "zh": "  来源文件已删除：  {n} 条",
    },
    "audit.reason_duplicate": {
        "en": "  Duplicate promotion:   {n}",
        "zh": "  重复晋升：        {n} 条",
    },
    "audit.non_standard_warn": {
        "en": "⚠️  Non-standard sections (hand-written): {n}\n   → Will be preserved in any cleanup operation",
        "zh": "⚠️  非标准段落（用户手写）：{n} 个 section\n   → 这些内容将在任何清理操作中默认保留",
    },
    "audit.llm_hint": {
        "en": "💡 {n} review entries can be further evaluated with LLM\n   Run memory_longterm_audit_oc(use_llm=True) to assess semantic validity",
        "zh": "💡 {n} 条 review 条目可进一步用 LLM 做语义评估\n   运行 memory_longterm_audit_oc(use_llm=True) 判断哪些「改了但结论仍成立」",
    },
    "audit.report_id_line": {
        "en": "Report ID: {report_id}\n→ Run memory_longterm_cleanup_oc(report_id=\"{report_id}\") to apply cleanup",
        "zh": "Report ID：{report_id}\n→ 运行 memory_longterm_cleanup_oc(report_id=\"{report_id}\") 执行清理",
    },
    "audit.no_longterm": {
        "en": "❌ MEMORY.md not found. Dreaming has not triggered yet.",
        "zh": "❌ MEMORY.md 不存在，Dreaming 尚未触发过。",
    },
    "audit.format_unsupported": {
        "en": "❌ MEMORY.md format does not support audit (no structured Dreaming entries).",
        "zh": "❌ 当前 MEMORY.md 格式不支持审计（无结构化 Dreaming 条目）。",
    },
    "audit.parse_error": {
        "en": "❌ MEMORY.md parse failed: {msg}",
        "zh": "❌ MEMORY.md 解析失败：{msg}",
    },
    "audit.llm_disabled": {
        "en": "(use_llm=True not yet implemented in Phase 1)",
        "zh": "（use_llm=True 功能在 Phase 1 暂未实现）",
    },

    # ── tool descriptions（Claude 看到的）─────────────────────────────────────
    "tool.health_check.desc": {
        "en": (
            "Quick health scan of your OpenClaw memory system. "
            "Returns zombie entry count, false-positive rate, and three diagnostic scores. "
            "Read-only, no LLM calls, returns in seconds."
        ),
        "zh": (
            "快速扫描 OpenClaw 记忆系统健康状态。"
            "返回僵尸条目数、假阳性占比和三个诊断分。"
            "纯只读，不调用 LLM，秒级返回。"
        ),
    },
    "tool.retrieval_diagnose.desc": {
        "en": (
            "Detailed retrieval quality diagnosis. "
            "Shows high-frequency low-quality entries and semantic-void entries, "
            "with configuration suggestions to reduce false positives."
        ),
        "zh": (
            "检索质量详细诊断。"
            "展示高频低质条目和语义空洞条目，"
            "并给出减少假阳性的配置建议。"
        ),
    },
    "tool.longterm_audit.desc": {
        "en": (
            "Deep audit of MEMORY.md. Checks source file validity, content consistency, "
            "and duplicate entries. Returns a report_id for use with cleanup. "
            "Pass use_llm=True for semantic evaluation (requires API key)."
        ),
        "zh": (
            "MEMORY.md 深度审计。检查来源文件有效性、内容一致性和重复条目。"
            "返回 report_id 供清理使用。"
            "传入 use_llm=True 可进行语义评估（需要 API key）。"
        ),
    },

    # ── 通用 ──────────────────────────────────────────────────────────────────
    "common.workspace_dir": {
        "en": "Workspace: {path}",
        "zh": "工作目录：{path}",
    },
    "common.unknown_tool": {
        "en": "Unknown tool: {name}",
        "zh": "未知工具：{name}",
    },
}


# ── 获取文本 ──────────────────────────────────────────────────────────────────

def t(key: str, lang: str | None = None, **kwargs) -> str:
    """
    获取指定 key 的文本，自动 format 占位符。

    Args:
        key:    文本 key，格式为 "section.name"
        lang:   语言代码（en / zh）。不传则自动检测。
        **kwargs: 传给 str.format() 的占位符值

    Returns:
        格式化后的文本字符串
    """
    resolved_lang = lang if lang in ("en", "zh") else detect_language()

    entry = STRINGS.get(key, {})
    text = entry.get(resolved_lang) or entry.get("en") or f"[missing: {key}]"

    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass  # 占位符缺失时返回原文，不崩溃

    return text

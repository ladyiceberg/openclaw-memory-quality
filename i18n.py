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
    "audit.llm_header": {
        "en": "🤖 LLM Semantic Evaluation ({n} review entries)",
        "zh": "🤖 LLM 语义评估结果（针对 {n} 条 review 条目）",
    },
    "audit.llm_validity_header": {
        "en": "Semantic Validity Review:",
        "zh": "语义有效性复审：",
    },
    "audit.llm_still_valid": {
        "en": "  Still valid (still_valid): {n}  → upgraded to keep",
        "zh": "  仍然有效（still_valid）：  {n} 条 → 升级为 keep",
    },
    "audit.llm_outdated": {
        "en": "  Semantically outdated (outdated): {n}  → upgraded to delete",
        "zh": "  已语义过时（outdated）：    {n} 条 → 升级为 delete",
    },
    "audit.llm_uncertain": {
        "en": "  Uncertain (uncertain): {n}  → stays review, needs manual judgment",
        "zh": "  上下文不足（uncertain）：   {n} 条 → 维持 review，需人工判断",
    },
    "audit.llm_dedup_header": {
        "en": "🔗 Semantic Dedup Suggestions ({n} potential duplicate pairs):",
        "zh": "🔗 语义去重建议（发现 {n} 对潜在重复）：",
    },
    "audit.llm_dedup_pair": {
        "en": "  Pair {i}: {a} ↔ {b}\n        Merge suggestion: {suggestion}",
        "zh": "  对 {i}：{a} ↔ {b}\n        建议合并为：{suggestion}",
    },
    "audit.llm_no_dedup": {
        "en": "  No semantic duplicates found.",
        "zh": "  未发现语义重复条目。",
    },
    "audit.llm_error": {
        "en": "⚠️  LLM evaluation encountered errors: {msg}",
        "zh": "⚠️  LLM 评估过程中有错误：{msg}",
    },
    "audit.llm_cost_warning": {
        "en": "⚠️  No API key configured. Set OPENAI_API_KEY / KIMI_API_KEY / ANTHROPIC_API_KEY to enable LLM evaluation.",
        "zh": "⚠️  未配置 API Key，无法运行 LLM 评估。请设置 OPENAI_API_KEY / KIMI_API_KEY / ANTHROPIC_API_KEY。",
    },

    # ── retrieval diagnose ────────────────────────────────────────────────────
    "diagnose.header": {
        "en": "🔍 Retrieval Quality Diagnosis",
        "zh": "🔍 检索质量诊断",
    },
    "diagnose.no_shortterm": {
        "en": "❌ Short-term memory file not found. Cannot run retrieval diagnosis.",
        "zh": "❌ 短期记忆文件未找到，无法运行检索质量诊断。",
    },
    "diagnose.read_error": {
        "en": "❌ Failed to read short-term memory: {msg}",
        "zh": "❌ 短期记忆读取失败：{msg}",
    },
    "diagnose.high_freq_section": {
        "en": "High-frequency low-quality entries (avg < 0.35, recalls > 5): {n}",
        "zh": "高频低质条目（avg < 0.35，recalls > 5）：{n} 条",
    },
    "diagnose.semantic_void_section": {
        "en": "Semantic-void high-frequency entries (no tags, recalls > 5): {n}",
        "zh": "语义空洞高频条目（无 tags，recalls > 5）：{n} 条",
    },
    "diagnose.ambiguous_section": {
        "en": "Ambiguous entries (borderline quality, may benefit from LLM review): {n}",
        "zh": "模糊区间条目（质量边界，可选 LLM 复核）：{n} 条",
    },
    "diagnose.entry_line": {
        "en": "  {rank}. {source}:{start}-{end}",
        "zh": "  {rank}. {source}:{start}-{end}",
    },
    "diagnose.entry_stats": {
        "en": "     recalls={recalls}, avg={avg}, max={max_score}, tags=[{tags}]",
        "zh": "     recalls={recalls}, avg={avg}, max={max_score}, tags=[{tags}]",
    },
    "diagnose.reason_never_relevant": {
        "en": "     → No high-quality hit ever — likely FTS literal match",
        "zh": "     → 无一次高质量命中，FTS 字面匹配嫌疑",
    },
    "diagnose.reason_occasional_hit": {
        "en": "     → Occasionally relevant but usually not the target",
        "zh": "     → 偶尔相关但通常不是目标内容",
    },
    "diagnose.reason_semantic_void": {
        "en": "     → High recall with no semantic tags — likely FTS noise",
        "zh": "     → 高频命中但无语义标签，可能是 FTS 噪声",
    },
    "diagnose.reason_ambiguous": {
        "en": "     → Borderline quality, use LLM review to decide",
        "zh": "     → 质量边界，建议 LLM 复核决定去留",
    },
    "diagnose.truncated": {
        "en": "  ... (showing top {shown} of {total})",
        "zh": "  ... （仅展示前 {shown} 条，共 {total} 条）",
    },
    "diagnose.health_score": {
        "en": "⚠️  Retrieval Health: {score}/100\n   Breakdown: high-freq low-quality {hflq_pct}%, semantic-void {sv_pct}%\n   Likely cause: no dedicated embedding or minScore too low (default 0.35)",
        "zh": "⚠️  检索健康分：{score}/100\n   低分原因：高频低质条目占比 {hflq_pct}%，语义空洞高频 {sv_pct}%\n   可能根因：未配置专用 embedding 或 minScore 过低（默认 0.35）",
    },
    "diagnose.health_score_ok": {
        "en": "✅  Retrieval Health: {score}/100",
        "zh": "✅  检索健康分：{score}/100",
    },
    "diagnose.config_advice_header": {
        "en": "💡 Configuration suggestions:",
        "zh": "💡 配置建议：",
    },
    "diagnose.config_minscore": {
        "en": "   - Raise minScore from 0.35 to 0.50 to reduce ~30% false positives entering short-term memory",
        "zh": "   - 将 minScore 从 0.35 提升到 0.50 可减少约 30% 假阳性进入短期记忆",
    },
    "diagnose.config_embedding": {
        "en": "   - Configure voyage-code-3 embedding for better code semantic accuracy",
        "zh": "   - 配置 voyage-code-3 embedding（已内置支持）可提升代码检索语义准确度",
    },
    "diagnose.config_mmr": {
        "en": "   - Enable MMR (disabled by default) to reduce duplicate fragment hits",
        "zh": "   - 开启 MMR（默认关闭）可减少重复片段命中",
    },
    "diagnose.all_healthy": {
        "en": "✅  No high-risk entries found. Retrieval quality looks good.",
        "zh": "✅  未发现高风险条目，检索质量良好。",
    },
    "diagnose.stats_only_hint": {
        "en": "(Pass top_n > 0 to see individual entries)",
        "zh": "（传入 top_n > 0 可查看具体条目）",
    },

    # ── longterm cleanup ──────────────────────────────────────────────────────
    "cleanup.lt.header": {
        "en": "✅ Long-term Memory Cleanup Complete",
        "zh": "✅ 长期记忆清理完成",
    },
    "cleanup.lt.deleted": {
        "en": "Deleted:  {n} entries",
        "zh": "删除：{n} 条",
    },
    "cleanup.lt.kept": {
        "en": "Kept:     {n} entries{manual_note}",
        "zh": "保留：{n} 条{manual_note}",
    },
    "cleanup.lt.manual_note": {
        "en": " (incl. {n} hand-written sections)",
        "zh": "（含 {n} 个用户手写 section）",
    },
    "cleanup.lt.backup": {
        "en": "Backup:   {path}",
        "zh": "备份：{path}",
    },
    "cleanup.lt.sections": {
        "en": "MEMORY.md: {before} sections → {after} sections",
        "zh": "MEMORY.md：{before} 个 section → {after} 个 section",
    },
    "cleanup.lt.no_delete": {
        "en": "ℹ️  No entries marked for deletion. Nothing to do.",
        "zh": "ℹ️  没有需要删除的条目。",
    },
    "cleanup.lt.err_no_report": {
        "en": "❌ Report ID not found: {report_id}\n   Run memory_longterm_audit_oc() first to generate a report.",
        "zh": "❌ 找不到 Report ID：{report_id}\n   请先运行 memory_longterm_audit_oc() 生成审计报告。",
    },
    "cleanup.lt.err_no_longterm": {
        "en": "❌ MEMORY.md not found.",
        "zh": "❌ MEMORY.md 不存在。",
    },
    "cleanup.lt.err_mtime": {
        "en": "❌ MEMORY.md was modified after the audit. Please re-run memory_longterm_audit_oc() before cleanup.",
        "zh": "❌ MEMORY.md 在审计后被修改，请重新运行 memory_longterm_audit_oc() 再执行清理。",
    },
    "cleanup.lt.err_safety_valve": {
        "en": "❌ Safety check failed: parse ratio {ratio:.1%} is below 80%. Aborting to protect data.",
        "zh": "❌ 安全校验失败：解析率 {ratio:.1%} 低于 80%，已中止以保护数据。",
    },
    "cleanup.lt.err_backup": {
        "en": "❌ Backup failed: {msg}. Aborting.",
        "zh": "❌ 备份失败：{msg}，已中止。",
    },
    "cleanup.lt.err_write": {
        "en": "❌ Write failed: {msg}",
        "zh": "❌ 写入失败：{msg}",
    },
    "cleanup.lt.err_lock": {
        "en": "❌ Could not acquire lock (OpenClaw may be running). Try again in a moment.",
        "zh": "❌ 无法获取并发锁（OpenClaw 可能正在运行），请稍后重试。",
    },

    # ── shortterm cleanup ─────────────────────────────────────────────────────
    "cleanup.st.header": {
        "en": "✅ Short-term Memory Cleanup Complete",
        "zh": "✅ 短期记忆清理完成",
    },
    "cleanup.st.dry_run_header": {
        "en": "🔍 Short-term Memory Cleanup Preview (dry_run=True)",
        "zh": "🔍 短期记忆清理预览（dry_run=True）",
    },
    "cleanup.st.would_delete": {
        "en": "Would delete: {n} entries\n  ├─ Zombie:         {zombie} entries\n  └─ False-positive: {fp} entries",
        "zh": "将删除：{n} 条\n  ├─ 僵尸条目：      {zombie} 条\n  └─ 假阳性嫌疑：    {fp} 条",
    },
    "cleanup.st.deleted": {
        "en": "Deleted:  {n} entries  ({zombie} zombie, {fp} false-positive)",
        "zh": "删除：{n} 条（僵尸 {zombie} 条，假阳性 {fp} 条）",
    },
    "cleanup.st.kept": {
        "en": "Kept:     {n} entries",
        "zh": "保留：{n} 条",
    },
    "cleanup.st.backup": {
        "en": "Backup:   {path}",
        "zh": "备份：{path}",
    },
    "cleanup.st.no_delete": {
        "en": "ℹ️  No zombie or false-positive entries found. Nothing to do.",
        "zh": "ℹ️  没有发现僵尸或假阳性条目。",
    },
    "cleanup.st.err_no_shortterm": {
        "en": "❌ Short-term memory file not found.",
        "zh": "❌ 短期记忆文件未找到。",
    },
    "cleanup.st.err_read": {
        "en": "❌ Failed to read short-term memory: {msg}",
        "zh": "❌ 短期记忆读取失败：{msg}",
    },
    "cleanup.st.err_lock": {
        "en": "❌ Could not acquire lock. Try again in a moment.",
        "zh": "❌ 无法获取并发锁，请稍后重试。",
    },
    "cleanup.st.err_backup": {
        "en": "❌ Backup failed: {msg}. Aborting.",
        "zh": "❌ 备份失败：{msg}，已中止。",
    },
    "cleanup.st.dry_run_hint": {
        "en": "→ Run with dry_run=False to apply",
        "zh": "→ 传入 dry_run=False 执行实际删除",
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
    "tool.longterm_cleanup.desc": {
        "en": (
            "Clean up MEMORY.md based on a previous audit result. "
            "Requires report_id from memory_longterm_audit_oc(). "
            "Backs up the file before writing. Atomic write, safe."
        ),
        "zh": (
            "根据审计结果清理 MEMORY.md。"
            "需要提供 memory_longterm_audit_oc() 返回的 report_id。"
            "写入前自动备份，原子写入，安全。"
        ),
    },
    "tool.shortterm_cleanup.desc": {
        "en": (
            "Clean up zombie and/or false-positive entries from short-term memory. "
            "Use dry_run=True (default) to preview, dry_run=False to apply. "
            "cleanup_types defaults to [\"zombie\"]."
        ),
        "zh": (
            "清理短期记忆中的僵尸条目和/或假阳性条目。"
            "dry_run=True（默认）只预览，dry_run=False 实际执行。"
            "cleanup_types 默认为 [\"zombie\"]。"
        ),
    },
    "tool.config_doctor.desc": {
        "en": (
            "Diagnose OpenClaw memory configuration issues from behavioral data. "
            "Detects FTS degradation, low minScore, disabled MMR, and weak embedding. "
            "Read-only. Returns specific configuration suggestions with JSON5 snippets."
        ),
        "zh": (
            "从行为数据推断 OpenClaw 记忆配置问题。"
            "检测 FTS 降级、minScore 过低、MMR 未开启、embedding 质量不足。"
            "纯只读，返回具体配置建议和 JSON5 片段。"
        ),
    },
    "tool.soul_check.desc": {
        "en": (
            "Check SOUL.md health: boundary violations (code, URLs, injections), "
            "identity drift (action verb density, missing sections), "
            "and stability (change tracking across runs). "
            "Read-only. Never auto-modifies SOUL.md."
        ),
        "zh": (
            "检查 SOUL.md 健康状态：边界违规（代码、URL、注入痕迹）、"
            "身份漂移（动词密度、section 缺失）、"
            "稳定性（跨次运行变化追踪）。"
            "纯只读，永不自动修改 SOUL.md。"
        ),
    },
    "tool.promotion_audit.desc": {
        "en": (
            "Pre-promotion quality audit: checks the top-N short-term memory candidates "
            "before Dreaming promotes them. Detects deleted source files, low-value snippets "
            "(imports/comments/debug code), already-promoted duplicates, and false-positive signals. "
            "Optional LLM advisory (use_llm=True) evaluates long-term knowledge value. "
            "Read-only, never modifies memory files."
        ),
        "zh": (
            "晋升前质量预检：在 Dreaming 晋升前对评分最高的 N 条候选执行四道关卡审查——"
            "来源文件存在性、低价值内容（import/注释/调试代码）、"
            "与 MEMORY.md 重复、假阳性信号。"
            "可选 LLM advisory（use_llm=True）评估长期价值。"
            "纯只读，不修改任何文件。"
        ),
    },

    # ── soul check ────────────────────────────────────────────────────────────
    "soul.header": {
        "en": "🔮 SOUL.md Health Check",
        "zh": "🔮 SOUL.md 健康检查",
    },
    "soul.no_soul": {
        "en": "❌ SOUL.md not found. The workspace may not be initialized, or the file was manually deleted.",
        "zh": "❌ SOUL.md 未找到。工作区可能未初始化，或文件已被手动删除。",
    },
    "soul.file_info": {
        "en": "File: {path} ({size} chars)",
        "zh": "文件：{path}（{size} 字符）",
    },
    "soul.last_check_never": {
        "en": "Last check: first run (establishing baseline)",
        "zh": "上次检查：首次运行（建立基准）",
    },
    "soul.last_check_ago": {
        "en": "Last check: {ago} ago{changed}",
        "zh": "上次检查：{ago}前{changed}",
    },
    "soul.changed_flag": {
        "en": "  ⚠️ (changed since last check)",
        "zh": "（距上次有变化 ⚠️）",
    },
    "soul.c1_header": {
        "en": "── C1 Boundary Check ─────────────────────────",
        "zh": "── C1 边界检查 ───────────────────────────────",
    },
    "soul.c2_header": {
        "en": "── C2 Identity Drift Check ───────────────────",
        "zh": "── C2 身份漂移检查 ───────────────────────────",
    },
    "soul.c3_header": {
        "en": "── C3 Stability Check ────────────────────────",
        "zh": "── C3 稳定性检查 ─────────────────────────────",
    },
    "soul.c4_header": {
        "en": "── C4 Conflict Check ─────────────────────────",
        "zh": "── C4 冲突检查 ───────────────────────────────",
    },
    "soul.c4_disabled": {
        "en": "(Disabled — pass use_llm=True to enable semantic conflict detection)",
        "zh": "（未启用，传入 use_llm=True 开启语义冲突检测）",
    },
    "soul.c4_c2_precision_header": {
        "en": "C2 Precision Judgment ({n} suspicious paragraphs):",
        "zh": "C2 精判（{n} 处可疑段落）：",
    },
    "soul.c4_c2_item": {
        "en": "  [{classification}] {hint}  — {reason}",
        "zh": "  [{classification}] {hint}  — {reason}",
    },
    "soul.c4_c2_task_warning": {
        "en": "⚠️  {n} paragraph(s) contain task instructions — SOUL.md should only define persona",
        "zh": "⚠️  {n} 处段落含任务指令，SOUL.md 应只定义人格",
    },
    "soul.c4_no_issues": {
        "en": "✅ No semantic conflicts or identity mismatches found.",
        "zh": "✅ 未发现语义冲突或身份不一致。",
    },
    "soul.c4_conflicts_header": {
        "en": "Internal conflicts found ({n}):",
        "zh": "发现内部冲突（{n} 处）：",
    },
    "soul.c4_conflict_item": {
        "en": "  [{severity}] \"{a}\" ↔ \"{b}\"  — {reason}",
        "zh": "  [{severity}] \"{a}\" ↔ \"{b}\"  — {reason}",
    },
    "soul.c4_mismatches_header": {
        "en": "SOUL.md vs IDENTITY.md mismatches ({n}):",
        "zh": "SOUL.md 与 IDENTITY.md 不一致（{n} 处）：",
    },
    "soul.c4_mismatch_item": {
        "en": "  [{severity}] SOUL: \"{soul}\" / IDENTITY: \"{ident}\"  — {reason}",
        "zh": "  [{severity}] SOUL：\"{soul}\" / IDENTITY：\"{ident}\"  — {reason}",
    },
    "soul.c4_llm_error": {
        "en": "⚠️  LLM evaluation unavailable: {msg}",
        "zh": "⚠️  LLM 评估不可用：{msg}",
    },
    "soul.section_ok": {
        "en": "✅ No issues found.",
        "zh": "✅ 未发现问题。",
    },
    "soul.flag_line": {
        "en": "⚠️  {desc}",
        "zh": "⚠️  {desc}",
    },
    "soul.first_run_note": {
        "en": "ℹ️  First run — baseline established. Stability check will activate on next run.",
        "zh": "ℹ️  首次运行，已建立基准。下次运行时开始稳定性追踪。",
    },
    "soul.summary_header": {
        "en": "── Summary ───────────────────────────────────",
        "zh": "── 总结 ──────────────────────────────────────",
    },
    "soul.risk_ok": {
        "en": "Risk level: ✅ Healthy",
        "zh": "风险等级：✅ 健康",
    },
    "soul.risk_low": {
        "en": "Risk level: 🟡 Low (minor issues, worth reviewing)",
        "zh": "风险等级：🟡 低（有轻微问题，建议 review）",
    },
    "soul.risk_medium": {
        "en": "Risk level: ⚠️  Medium — review recommended",
        "zh": "风险等级：⚠️  中等，建议 review",
    },
    "soul.risk_high": {
        "en": "Risk level: 🔴 High — manual review required",
        "zh": "风险等级：🔴 高风险，需要人工 review",
    },
    "soul.suggest_llm": {
        "en": "→ Run memory_soul_check_oc(use_llm=True) for semantic conflict detection",
        "zh": "→ 运行 memory_soul_check_oc(use_llm=True) 检查语义冲突",
    },

    # ── config doctor ─────────────────────────────────────────────────────────
    "doctor.header": {
        "en": "🩺 Memory Config Diagnosis",
        "zh": "🩺 记忆配置诊断",
    },
    "doctor.no_shortterm": {
        "en": "❌ Short-term memory file not found. Cannot diagnose configuration.",
        "zh": "❌ 短期记忆文件未找到，无法诊断配置。",
    },
    "doctor.all_good": {
        "en": "✅ No configuration issues detected. Memory system looks healthy.",
        "zh": "✅ 未发现配置问题，记忆系统运行正常。",
    },
    "doctor.issues_found": {
        "en": "Found {n} potential configuration issue(s):",
        "zh": "发现 {n} 个潜在配置问题：",
    },
    "doctor.fts_title": {
        "en": "⚠️  [1] Possible FTS fallback mode (no semantic embedding)",
        "zh": "⚠️  [1] 可能处于 FTS 降级模式（未启用语义 embedding）",
    },
    "doctor.fts_signal": {
        "en": "   Signal: avg score {avg:.2f} < 0.45, empty-tag rate {empty_pct:.0f}% > 40%",
        "zh": "   信号：avg score 均值 {avg:.2f} < 0.45，空标签占比 {empty_pct:.0f}% > 40%",
    },
    "doctor.fts_advice": {
        "en": "   Fix: Configure an embedding provider (e.g. VOYAGE_API_KEY + voyage-code-3)",
        "zh": "   建议：配置 embedding provider（如设置 VOYAGE_API_KEY 并使用 voyage-code-3）",
    },
    "doctor.minscore_title": {
        "en": "⚠️  [{n}] minScore may be too low (default 0.35 lets in too much noise)",
        "zh": "⚠️  [{n}] minScore 可能过低（默认 0.35 导致大量噪声进入）",
    },
    "doctor.minscore_signal": {
        "en": "   Signal: {pct:.1f}% of entries are high-frequency low-quality (threshold: 15%)",
        "zh": "   信号：{pct:.1f}% 的条目为高频低质（阈值 15%）",
    },
    "doctor.minscore_advice": {
        "en": "   Fix: Raise minScore from 0.35 to 0.50",
        "zh": "   建议：将 minScore 从 0.35 提升到 0.50",
    },
    "doctor.mmr_title": {
        "en": "⚠️  [{n}] MMR may be disabled (duplicate fragments entering short-term memory)",
        "zh": "⚠️  [{n}] MMR 可能未开启（重复片段进入短期记忆）",
    },
    "doctor.mmr_signal": {
        "en": "   Signal: {pairs} overlapping entry pairs found in same source files",
        "zh": "   信号：在同一来源文件中发现 {pairs} 对行号重叠条目",
    },
    "doctor.mmr_advice": {
        "en": "   Fix: Enable MMR (mmr.enabled: true, lambda: 0.7)",
        "zh": "   建议：启用 MMR（mmr.enabled: true, lambda: 0.7）",
    },
    "doctor.embedding_title": {
        "en": "⚠️  [{n}] Embedding model may have weak semantic quality",
        "zh": "⚠️  [{n}] embedding 模型语义质量可能不足",
    },
    "doctor.embedding_signal": {
        "en": "   Signal: avg score {avg:.2f} in range [0.40, 0.55), few high-score entries ({high_pct:.0f}%)",
        "zh": "   信号：avg score 均值 {avg:.2f} 在 [0.40, 0.55)，高分条目占比 {high_pct:.0f}%",
    },
    "doctor.embedding_advice": {
        "en": "   Fix: Switch to voyage-code-3 (built-in support, better code semantics)",
        "zh": "   建议：切换到 voyage-code-3（已内置支持，代码语义更准确）",
    },
    "doctor.config_snippet_header": {
        "en": "\n💡 Suggested openclaw.json changes (~/.openclaw/openclaw.json, JSON5 format):",
        "zh": "\n💡 建议的 openclaw.json 配置修改（~/.openclaw/openclaw.json，JSON5 格式）：",
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

    # ── dashboard ──────────────────────────────────────────────────────────────
    "dashboard.header": {
        "en": "📊 Memory Health Dashboard",
        "zh": "📊 记忆健康看板",
    },
    "dashboard.opened": {
        "en": "✅ Dashboard opened in your browser.\n   File: {path}",
        "zh": "✅ 看板已在浏览器中打开。\n   文件：{path}",
    },
    "dashboard.tip": {
        "en": "Tip: Run more tools (/memory-check, /soul-check, etc.) to populate all sections.",
        "zh": "提示：运行更多工具（/memory-check、/soul-check 等）以填充全部板块。",
    },
    "dashboard.error": {
        "en": "❌ Failed to generate dashboard: {msg}",
        "zh": "❌ 生成看板失败：{msg}",
    },
    "tool.dashboard.desc": {
        "en": (
            "Generate and open the OpenClaw Memory Health Dashboard in the browser. "
            "Aggregates results from all previously run tools (health check, longterm audit, "
            "promotion audit, soul check, config doctor) into a single visual report. "
            "Use after running any memory tool to see a visual summary."
        ),
        "zh": (
            "生成并在浏览器中打开 OpenClaw 记忆健康看板。"
            "聚合所有已运行工具的结果（health check、longterm audit、"
            "promotion audit、soul check、config doctor）为一份可视化报告。"
            "运行任意记忆工具后使用。"
        ),
    },

    # ── dashboard HTML 内容 ────────────────────────────────────────────────────

    # A. 时间格式化
    "dashboard.time.unknown": {"en": "unknown",    "zh": "未知"},
    "dashboard.time.just_now": {"en": "just now",  "zh": "刚刚"},
    "dashboard.time.minutes_ago": {"en": "{n}m ago",   "zh": "{n} 分钟前"},
    "dashboard.time.hours_ago":   {"en": "{n}h ago",   "zh": "{n} 小时前"},
    "dashboard.time.days_ago":    {"en": "{n}d ago",   "zh": "{n} 天前"},

    # B. 枚举映射 — action
    "dashboard.action.keep":   {"en": "Keep",   "zh": "保留"},
    "dashboard.action.review": {"en": "Review", "zh": "复查"},
    "dashboard.action.delete": {"en": "Delete", "zh": "删除"},

    # B. 枚举映射 — risk level
    "dashboard.risk.ok":     {"en": "Healthy",       "zh": "健康"},
    "dashboard.risk.low":    {"en": "Low Risk",       "zh": "低风险"},
    "dashboard.risk.medium": {"en": "Medium Risk",    "zh": "中等风险"},
    "dashboard.risk.high":   {"en": "High Risk",      "zh": "高风险"},

    # B. 枚举映射 — v1 status
    "dashboard.v1.exists":          {"en": "Source exists",        "zh": "来源存在"},
    "dashboard.v1.deleted":         {"en": "Source deleted",       "zh": "来源已删除"},
    "dashboard.v1.possibly_moved":  {"en": "Possibly moved",       "zh": "可能已移动"},

    # B. 枚举映射 — v3 status
    "dashboard.v3.ok":               {"en": "No duplicate",        "zh": "无重复"},
    "dashboard.v3.duplicate_winner": {"en": "Duplicate (kept)",    "zh": "重复保留"},
    "dashboard.v3.duplicate_loser":  {"en": "Duplicate (removed)", "zh": "重复删除"},

    # B. 枚举映射 — skip reason
    "dashboard.skip.source_deleted":   {"en": "Source file deleted",          "zh": "来源文件已删除"},
    "dashboard.skip.import_only":      {"en": "Import statements only",       "zh": "仅含 import 语句"},
    "dashboard.skip.comments_only":    {"en": "Comments only",                "zh": "仅含注释行"},
    "dashboard.skip.boilerplate":      {"en": "Empty or boilerplate",         "zh": "空内容或样板代码"},
    "dashboard.skip.debug_code":       {"en": "Debug output code",            "zh": "含调试输出代码"},
    "dashboard.skip.already_promoted": {"en": "Already in MEMORY.md",         "zh": "已存在于 MEMORY.md"},

    # B. 枚举映射 — config issue code
    "dashboard.config.fts":       {"en": "FTS degradation mode (no semantic embedding)",  "zh": "FTS 降级模式（未使用语义 embedding）"},
    "dashboard.config.minscore":  {"en": "minScore too low (too much noise)",              "zh": "minScore 过低（噪音条目过多）"},
    "dashboard.config.mmr":       {"en": "MMR not enabled (duplicate entries)",            "zh": "MMR 未开启（重复条目多）"},
    "dashboard.config.embedding": {"en": "Embedding model quality insufficient",           "zh": "Embedding 质量不足"},

    # C. Header / Hero
    "dashboard.html.title":        {"en": "OpenClaw Memory Health",  "zh": "OpenClaw 记忆健康"},
    "dashboard.html.never_run":    {"en": "Never run",               "zh": "从未运行"},
    "dashboard.html.updated_ago":  {"en": "Updated: {ago}",          "zh": "最近更新：{ago}"},
    "dashboard.html.unknown_ws":   {"en": "Unknown workspace",       "zh": "未知 workspace"},

    "dashboard.hero.no_data":        {"en": "No data yet",                                         "zh": "暂无数据"},
    "dashboard.hero.no_data_sub":    {"en": "Run any check tool to get your health score.",        "zh": "请运行任意检查工具以获取健康评分"},
    "dashboard.hero.healthy":        {"en": "Memory system is healthy",                            "zh": "记忆系统状态良好"},
    "dashboard.hero.healthy_sub":    {"en": "All metrics look good. No action needed.",            "zh": "各项指标健康，无需立即处理。"},
    "dashboard.hero.warning":        {"en": "Memory system needs attention",                       "zh": "记忆系统需要关注"},
    "dashboard.hero.warning_sub":    {"en": "Some issues found. Recommended to address soon.",     "zh": "发现部分问题，建议尽快处理。"},
    "dashboard.hero.critical":       {"en": "Memory system needs cleanup",                         "zh": "记忆系统需要处理"},
    "dashboard.hero.critical_sub":   {"en": "Multiple issues found. Run cleanup tools now.",       "zh": "存在较多问题，建议立即运行清理工具。"},

    # C. Hero coverage dots labels
    "dashboard.coverage.longterm":  {"en": "Long-term",   "zh": "长期记忆"},
    "dashboard.coverage.shortterm": {"en": "Short-term",  "zh": "短期记忆"},
    "dashboard.coverage.soul":      {"en": "SOUL.md",     "zh": "SOUL.md"},

    # D. 占位卡片标题 + 提示
    "dashboard.placeholder.longterm.title":  {"en": "Long-term Memory",        "zh": "长期记忆"},
    "dashboard.placeholder.longterm.hint":   {
        "en": "Run <code>/memory-cleanup</code> to get long-term memory analysis",
        "zh": "运行 <code>/memory-cleanup</code> 获取长期记忆分析",
    },
    "dashboard.placeholder.health.title":    {"en": "Short-term Overview",     "zh": "短期记忆概况"},
    "dashboard.placeholder.health.hint":     {
        "en": "Run <code>/memory-check</code> to get short-term memory overview",
        "zh": "运行 <code>/memory-check</code> 获取短期记忆概况",
    },
    "dashboard.placeholder.promotion.title": {"en": "Pre-promotion Audit",     "zh": "晋升前预检"},
    "dashboard.placeholder.promotion.hint":  {
        "en": "Run <code>/memory-promote</code> to get pre-promotion audit report",
        "zh": "运行 <code>/memory-promote</code> 获取晋升前预检报告",
    },
    "dashboard.placeholder.soul.title":      {"en": "SOUL.md Health",          "zh": "SOUL.md 健康"},
    "dashboard.placeholder.soul.hint":       {
        "en": "Run <code>/soul-check</code> to get SOUL.md health report",
        "zh": "运行 <code>/soul-check</code> 获取 SOUL.md 健康报告",
    },
    "dashboard.placeholder.config.title":    {"en": "Config Diagnosis",        "zh": "配置诊断"},
    "dashboard.placeholder.config.hint":     {
        "en": "Run <code>/memory-diagnose</code> to get config diagnosis report",
        "zh": "运行 <code>/memory-diagnose</code> 获取配置诊断报告",
    },

    # E. Section 1：长期记忆
    "dashboard.longterm.title":         {"en": "Long-term Memory",           "zh": "长期记忆"},
    "dashboard.longterm.meta":          {"en": "{sections} sections · {total} entries", "zh": "{sections} 个 section · {total} 条记忆"},
    "dashboard.longterm.keep":          {"en": "Keep",                       "zh": "保留"},
    "dashboard.longterm.review":        {"en": "Review",                     "zh": "复查"},
    "dashboard.longterm.delete":        {"en": "Delete",                     "zh": "删除"},
    "dashboard.longterm.llm_valid":     {"en": "Valid {n}",                  "zh": "有效 {n}"},
    "dashboard.longterm.llm_outdated":  {"en": "Outdated {n}",               "zh": "过时 {n}"},
    "dashboard.longterm.llm_uncertain": {"en": "Uncertain {n}",              "zh": "不确定 {n}"},
    "dashboard.longterm.llm_merge":     {"en": "Merge suggestions {n}",      "zh": "合并建议 {n}"},
    "dashboard.longterm.non_std_warn":  {
        "en": "⚠️ {n} non-standard section(s) (user-written content, preserved during cleanup)",
        "zh": "⚠️ {n} 个非标准段落（用户手写内容，不参与清理）",
    },
    "dashboard.longterm.group_delete":  {"en": "Suggested for deletion",     "zh": "建议删除"},
    "dashboard.longterm.group_review":  {"en": "Suggested for review",       "zh": "建议复查"},
    "dashboard.longterm.group_keep":    {"en": "All good",                   "zh": "状态良好"},
    "dashboard.longterm.detail_source": {"en": "Source",                     "zh": "来源"},
    "dashboard.longterm.detail_file":   {"en": "File status",                "zh": "文件状态"},
    "dashboard.longterm.detail_dup":    {"en": "Duplicate",                  "zh": "重复检测"},
    "dashboard.longterm.detail_score":  {"en": "Score",                      "zh": "晋升分"},

    # E. Section 2：短期记忆
    "dashboard.health.title":      {"en": "Short-term Overview",             "zh": "短期记忆概况"},
    "dashboard.health.total":      {"en": "Total",                           "zh": "总条目"},
    "dashboard.health.zombie":     {"en": "Zombie {pct}%",                   "zh": "僵尸 {pct}%"},
    "dashboard.health.fp":         {"en": "False Pos. {pct}%",               "zh": "假阳性 {pct}%"},
    "dashboard.health.fts_warn":   {
        "en": "⚠️ FTS degradation mode detected — configure an embedding provider",
        "zh": "⚠️ 检测到 FTS 降级模式，建议配置 embedding provider",
    },

    # E. Section 3：晋升前预检
    "dashboard.promotion.title":         {"en": "Pre-promotion Audit",       "zh": "晋升前预检"},
    "dashboard.promotion.meta":          {"en": "{total} candidates · Top {top_n} checked", "zh": "共 {total} 条候选 · 检查 Top {top_n}"},
    "dashboard.promotion.pass":          {"en": "Pass",                      "zh": "通过"},
    "dashboard.promotion.skip":          {"en": "Skip",                      "zh": "建议跳过"},
    "dashboard.promotion.flag":          {"en": "Flag",                      "zh": "需关注"},
    "dashboard.promotion.issues":        {"en": "Needs attention",           "zh": "需处理条目"},
    "dashboard.promotion.llm_longterm":  {"en": "Long-term value {n}",       "zh": "长期价值 {n}"},
    "dashboard.promotion.llm_onetime":   {"en": "One-time context {n}",      "zh": "一次性 {n}"},
    "dashboard.promotion.llm_uncertain": {"en": "Uncertain {n}",             "zh": "不确定 {n}"},

    # E. Section 4：SOUL.md
    "dashboard.soul.title":         {"en": "SOUL.md Health",                 "zh": "SOUL.md 健康"},
    "dashboard.soul.chars":         {"en": "{n} chars",                      "zh": "{n} 字符"},
    "dashboard.soul.directives":    {"en": "{n} directive words",            "zh": "{n} 条强指令词"},
    "dashboard.soul.no_sections":   {"en": "No standard sections",           "zh": "无标准 section"},

    # E. Section 5：配置诊断
    "dashboard.config.title":       {"en": "Config Diagnosis",               "zh": "配置诊断"},
    "dashboard.config.all_good":    {"en": "Config healthy, no issues found","zh": "配置健康，未发现问题"},
    "dashboard.config.issues_found":{"en": "{n} config issue(s) found",      "zh": "发现 {n} 个配置问题"},

    # G. Footer
    "dashboard.footer.generated_by": {"en": "Generated by",    "zh": "由"},
    "dashboard.footer.report_issue": {"en": "Report an issue", "zh": "报告问题"},

    # ── promotion audit ────────────────────────────────────────────────────────
    "promo.header": {
        "en": "🛡️ Pre-Promotion Audit",
        "zh": "🛡️ 晋升前质量预检",
    },
    "promo.no_shortterm": {
        "en": "❌ Short-term memory file not found. Cannot perform promotion audit.",
        "zh": "❌ 短期记忆文件不存在，无法执行晋升前预检。",
    },
    "promo.summary": {
        "en": "Candidates: {total} unpromotted entries, checking Top {top_n}",
        "zh": "候选池：{total} 条未晋升条目，检查 Top {top_n}",
    },
    "promo.results_header": {
        "en": "Results:",
        "zh": "检查结果：",
    },
    "promo.pass": {
        "en": "✓  Pass: {n}",
        "zh": "✓  通过：{n} 条",
    },
    "promo.skip": {
        "en": "✕  Suggested skip: {n}",
        "zh": "✕  建议跳过：{n} 条",
    },
    "promo.flag": {
        "en": "⚠️  Needs attention: {n}",
        "zh": "⚠️  需关注：{n} 条",
    },
    "promo.skip_section_header": {
        "en": "Suggested skip:",
        "zh": "建议跳过：",
    },
    "promo.flag_section_header": {
        "en": "Needs attention (false positive signal):",
        "zh": "需关注（假阳性嫌疑）：",
    },
    "promo.candidate_line": {
        "en": "  {idx}. {path}:{start}-{end}  [score≈{score:.2f}]",
        "zh": "  {idx}. {path}:{start}-{end}  [估算分≈{score:.2f}]",
    },
    "promo.skip_reason_source_deleted": {
        "en": "     Reason: source file no longer exists",
        "zh": "     原因：来源文件已不存在",
    },
    "promo.skip_reason_import_only": {
        "en": "     Reason: snippet contains only import statements",
        "zh": "     原因：片段仅含 import 语句，无语义价值",
    },
    "promo.skip_reason_comments_only": {
        "en": "     Reason: snippet contains only comments",
        "zh": "     原因：片段仅含注释行，无实质内容",
    },
    "promo.skip_reason_boilerplate": {
        "en": "     Reason: snippet is empty or boilerplate only",
        "zh": "     原因：片段为空或仅含样板代码",
    },
    "promo.skip_reason_debug_code": {
        "en": "     Reason: snippet contains debug output statements",
        "zh": "     原因：片段含调试输出代码（console.log/print 等）",
    },
    "promo.skip_reason_already_promoted": {
        "en": "     Reason: already exists in MEMORY.md",
        "zh": "     原因：已存在于 MEMORY.md 中",
    },
    "promo.skip_reason_unknown": {
        "en": "     Reason: {reason}",
        "zh": "     原因：{reason}",
    },
    "promo.flag_reason_fp": {
        "en": "     avg={avg:.2f}, max={max:.2f} — high-frequency but low quality, possible FTS match",
        "zh": "     avg={avg:.2f}, max={max:.2f} — 高频命中但分数低，可能是 FTS 字面匹配",
    },
    "promo.score_note": {
        "en": "⚠️  Note: scores are approximate (consolidation dimension excluded, ±10% variance)",
        "zh": "⚠️  注意：评分为近似值（跳过 consolidation 分量，误差约 ±10%）",
    },
    "promo.all_pass": {
        "en": "✅ All top candidates passed quality checks.",
        "zh": "✅ Top 候选全部通过质量预检。",
    },
    "promo.llm_hint": {
        "en": "→ Run memory_promotion_audit_oc(use_llm=True) for long-term value advisory",
        "zh": "→ 运行 memory_promotion_audit_oc(use_llm=True) 获取长期价值建议",
    },
    "promo.llm_header": {
        "en": "── LLM Long-term Value Advisory ─────────────────",
        "zh": "── LLM 长期价值评估 ──────────────────────────────",
    },
    "promo.llm_long_term": {
        "en": "  Long-term knowledge: {n}",
        "zh": "  适合长期保留：{n} 条",
    },
    "promo.llm_one_time": {
        "en": "  One-time context: {n}",
        "zh": "  一次性上下文：{n} 条",
    },
    "promo.llm_uncertain": {
        "en": "  Uncertain: {n}",
        "zh": "  无法判断：{n} 条",
    },
    "promo.llm_one_time_detail_header": {
        "en": "One-time context (consider skipping):",
        "zh": "一次性上下文（建议跳过）：",
    },
    "promo.llm_advisory_item": {
        "en": "  {idx}. [{verdict}] {hint}  — {reason}",
        "zh": "  {idx}. [{verdict}] {hint}  — {reason}",
    },
    "promo.llm_error": {
        "en": "⚠️  LLM advisory unavailable: {msg}",
        "zh": "⚠️  LLM 评估不可用：{msg}",
    },
    "promo.no_candidates": {
        "en": "ℹ️  No unpromotted candidates found in short-term memory.",
        "zh": "ℹ️  短期记忆中暂无未晋升的候选条目。",
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

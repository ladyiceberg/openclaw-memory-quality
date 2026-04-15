# Changelog

All notable changes to openclaw-memhealth will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Version numbering follows [Semantic Versioning](https://semver.org/).

---

## [0.1.0] — 2026-04-16

First public release. Full MCP tool suite, Skills layer, and visual Dashboard.

### Added

#### 9 MCP Tools (3-layer architecture)

**Layer 1 — Observe (read-only)**
- `memory_health_check_oc()` — quick health scan: zombie count, false-positive rate, retrieval health score, promotion risk score
- `memory_retrieval_diagnose_oc()` — deep retrieval quality diagnosis: high-frequency low-quality entries, minScore and embedding config suggestions
- `memory_longterm_audit_oc()` — full `MEMORY.md` audit: V1 source validity check, V3 duplicate detection, generates `report_id` for safe cleanup

**Layer 2 — Guard**
- `memory_promotion_audit_oc()` — pre-promotion quality gate: 5 structural checks (source validity, content quality, duplicate, false-positive, LLM advisory) before entries enter `MEMORY.md`
- `memory_config_doctor_oc()` — infer `minScore` and embedding configuration issues from retrieval behavior data alone, without requiring raw config file access
- `memory_soul_check_oc()` — audit `SOUL.md` for boundary violations (task instructions leaking into identity), identity drift, and structural stability

**Layer 3 — LLM Semantic Layer**
- `memory_longterm_audit_oc(use_llm=True)` — semantic validity review + merge suggestions for similar entries; degrades gracefully when LLM is unavailable
- `memory_soul_check_oc(use_llm=True)` — persona vs. task-instruction classification, C4 internal contradiction detection
- `memory_longterm_cleanup_oc(report_id)` — safely rewrite `MEMORY.md`: atomic write, automatic backup, faithful port of OpenClaw concurrency lock protocol

#### 5 Skills (slash commands)

- `/memory-check` — run full health check and open visual dashboard
- `/memory-cleanup` — clean up stale long-term memory entries
- `/memory-diagnose` — deep retrieval quality diagnosis
- `/memory-promote` — pre-promotion audit
- `/soul-check` — full `SOUL.md` integrity audit

#### Visual Dashboard (`memory_dashboard_oc`)

- 5-section health dashboard: Long-term Memory · Short-term Overview · Pre-promotion Audit · SOUL.md · Config Diagnosis
- Composite health score (0–100) weighted across long-term, short-term, and SOUL dimensions
- Full bilingual support (Chinese / English) — auto-detects language from system locale
- Apple HIG color system, SVG ring chart, collapsible sections
- Session store persists audit snapshots across tool calls for dashboard aggregation

#### Infrastructure

- `probe_workspace()` — workspace detection layer, runs first, all tools consume `ProbeResult`
- `session_store` — SQLite-backed snapshot storage for all 5 tool types, with workspace isolation
- `llm_client` — unified LLM client supporting OpenAI, Anthropic, Kimi, MiniMax; all LLM features degrade gracefully on API error or missing key
- `backup_manager` — atomic write + timestamped backup before any destructive operation
- `lock_manager` — faithful port of OpenClaw's concurrency lock protocol to prevent write conflicts
- 765 tests across all layers

### Notes

- Requires OpenClaw (any recent version) and Python 3.11+
- LLM API key is optional; all non-LLM features work without it
- Read-only tools (Layer 1) are completely safe to run at any time — no writes, no side effects

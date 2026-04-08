# openclaw-memhealth

**Memory health monitor for OpenClaw — diagnose, guard, and remediate your agent's memory.**

[中文版](README_CN.md) · [Report a Bug](https://github.com/ladyiceberg/openclaw-memory-quality/issues/new?template=bug_report.md) · [Request a Feature](https://github.com/ladyiceberg/openclaw-memory-quality/issues/new?template=feature_request.md)

---

OpenClaw automatically builds a memory system as your agent works — storing short-term recall signals, promoting them into `MEMORY.md`, and loading `SOUL.md` on every session. Over time, this memory accumulates problems that silently degrade your agent's behavior:

- **Stale long-term memories** — code snippets pointing to deleted or heavily refactored files
- **False-positive short-term entries** — low-quality FTS hits that inflate recall counts and get promoted
- **SOUL.md drift** — task instructions and business rules creeping into your agent's identity file
- **No cleanup mechanism** — OpenClaw only adds to memory, never removes

**openclaw-memhealth** is an external MCP-based QA layer that sits alongside your existing memory plugins (MemOS, LosslessClaw, etc.) without occupying a plugin slot. It uses retrieval behavior data — not just content — to diagnose whether your memory system is producing noise.

---

## Three-layer architecture

```
Layer 1: Observe   — diagnose memory health (read-only, zero risk)
Layer 2: Guard     — audit promotion candidates before they enter MEMORY.md
Layer 3: Remediate — safely clean up polluted long-term memory
```

---

## Requirements

- **OpenClaw** (any recent version)
- **Python 3.11+**
- **LLM API Key** (optional — for semantic evaluation in Phase 3 features)
  - OpenAI, Anthropic, Kimi, or MiniMax

---

## Installation

> 🚧 **Work in progress.** The project is under active development. Star/watch the repo to get notified when the first release is ready.

---

## MCP Tools

### Phase 1 — Observe (read-only)

| Tool | Description |
|------|-------------|
| `memory_health_check_oc()` | Quick health scan — zombie count, false-positive rate, three diagnostic scores |
| `memory_retrieval_diagnose_oc()` | Detailed retrieval quality diagnosis — high-freq low-quality entries, config suggestions |
| `memory_longterm_audit_oc()` | Deep audit of `MEMORY.md` — source validity, duplicate detection, generates `report_id` |

### Phase 2 — Remediate

| Tool | Description |
|------|-------------|
| `memory_longterm_cleanup_oc(report_id)` | Safely rewrite `MEMORY.md` — atomic write, backup, concurrency guard |
| `memory_cleanup_shortterm_oc()` | Clean up zombie short-term entries |
| `memory_config_doctor_oc()` | Infer embedding/minScore configuration issues from behavior data |
| `memory_soul_check_oc()` | Audit `SOUL.md` for boundary violations, identity drift, and stability |

### Phase 3 — LLM Semantic Layer

| Tool | Description |
|------|-------------|
| `memory_longterm_audit_oc(use_llm=True)` | Semantic validity review + merge suggestions |
| `memory_soul_check_oc(use_llm=True)` | Persona vs. task-instruction classification, internal contradiction detection |
| `memory_promotion_audit_oc()` | Pre-promotion candidate quality check |

---

## How it works

OpenClaw's memory pipeline has a structural weakness:

```
Retrieval noise (minScore=0.35 default + FTS literal matching)
    ↓ produces
Short-term false positives (high-frequency low-quality entries)
    ↓ via
Promotion miscalculation (frequency component ignores hit quality)
    ↓ pollutes
MEMORY.md (append-only, no cleanup mechanism)
    ↓ causes
Long-term agent behavior drift
```

openclaw-memhealth intercepts this chain at every stage — diagnosing retrieval quality from `queryHashes` and `avgScore` signals, auditing long-term memory against current source files, and checking `SOUL.md` for content that doesn't belong in an identity file.

---

## Relationship to memory-quality-mcp

[memory-quality-mcp](https://github.com/ladyiceberg/memory-quality-mcp) handles **Claude Code** memory quality.
**openclaw-memhealth** handles **OpenClaw** memory quality.

Both tools are part of the **memhealth** product line — same approach, different ecosystems. Power users running both Claude Code and OpenClaw can use both tools side by side.

---

## License

MIT — see [LICENSE](LICENSE)

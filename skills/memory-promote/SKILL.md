---
name: memory-promote
description: Pre-promotion quality audit for OpenClaw short-term memory candidates — checks the top-N entries before Dreaming promotes them to MEMORY.md, detects deleted source files, low-value snippets (imports/comments/debug code), already-promoted duplicates, and false-positive signals. Optional LLM long-term value advisory. Use this skill whenever the user wants to audit memories before Dreaming runs, check promotion candidates, review what's about to be promoted, or uses phrases like "promotion audit", "before dreaming", "check before promote", "memory promotion", "晋升前检查", "晋升审计", "Dreaming 前", "记忆晋升". Use this skill proactively when the user asks about Dreaming or upcoming memory promotions.
---

# Memory Promote

Pre-promotion quality audit. Run before OpenClaw's Dreaming process promotes short-term memories to MEMORY.md.

## Steps

1. Determine parameters:
   - `top_n`: user specified number, or default 10
   - `use_llm`: user said "--llm" or "with LLM" → True, otherwise False
2. Call `memory_promotion_audit_oc(top_n=N, use_llm=...)`
3. Summarize in one sentence, then show the full report

## Summary format

> Top 10 candidates: 7 pass, 2 suggested skip (1 source deleted, 1 import-only), 1 flagged (low avg score).

## What users can do with results

This tool outputs recommendations only — it doesn't block Dreaming. Options for the user:
- Ignore and let Dreaming run normally
- Manually remove unwanted entries from the short-term memory file
- Run `/memory-cleanup` first to remove low-quality entries before Dreaming

## LLM mode adds

Long-term value advisory for each passing/flagged entry:
- `long_term_knowledge` — abstract knowledge or stable design facts, good to keep
- `one_time_context` — one-off context with low long-term value, consider skipping
- `uncertain` — not enough context to judge

Advisory doesn't affect Dreaming — it's informational only.

## Notes

Score shown is approximate (±10%, consolidation dimension excluded).
Read-only — never modifies any files.
LLM mode requires an API key.

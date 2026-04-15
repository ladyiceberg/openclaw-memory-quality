---
name: memory-cleanup
description: Guided two-step cleanup for OpenClaw long-term memory (MEMORY.md) — audit first, confirm with user, then clean. Handles report_id automatically so the user never sees it. Use this skill whenever the user wants to clean, purge, or tidy their OpenClaw memories, mentions stale or old memories, or uses phrases like "clean memory", "cleanup memory", "delete old memories", "remove stale memories", "清理记忆", "删除旧记忆", "记忆清理". Always use this skill for memory cleanup requests — don't attempt cleanup without it.
---

# Memory Cleanup

Two-step guided cleanup. The user must confirm before anything is deleted. Never skip the confirmation step.

## Step 1 — Audit

Call `memory_longterm_audit_oc` and store the returned `report_id` internally (never show it to the user).

Translate the results into plain language, e.g.:

> Found 23 long-term memories to handle:
> - 8 with deleted source files (suggested for removal)
> - 3 exact duplicates (suggested for removal)
> - 12 flagged for review
>
> Estimated reduction: ~17% of MEMORY.md

If the audit shows everything is healthy, tell the user — no cleanup needed.

## Step 2 — Confirm

Ask clearly: **"Proceed with cleanup?"**

- Yes → Step 3
- No / cancel → stop, do nothing
- "Show details" → display the raw audit report, then ask again

## Step 3 — Execute

Call `memory_longterm_cleanup_oc` with the `report_id` from Step 1. Report what was deleted, what was kept, and where the backup lives.

## Error handling

| Error | Plain-language explanation |
|-------|---------------------------|
| MEMORY.md not found | "Long-term memory file doesn't exist yet — Dreaming may not have run." |
| mtime changed | "MEMORY.md was modified after the audit (OpenClaw may have just promoted new memories). Please re-run /memory-cleanup." |
| Lock timeout | "OpenClaw is currently writing to memory. Wait a moment and try again." |

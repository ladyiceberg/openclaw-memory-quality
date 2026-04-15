---
name: memory-check
description: Quickly scan OpenClaw memory system health and summarize findings in plain language. Use this skill whenever the user asks about memory health, memory status, memory stats, wants to know if their OpenClaw memory is working well, or uses phrases like "check memory", "memory health", "how is my memory", "记忆健康", "检查记忆", "记忆状态", "记忆统计". Always use this skill — don't try to answer memory health questions without it.
---

# Memory Check

Run `memory_health_check_oc` and translate the output into a plain-language summary.

## Steps

1. Call `memory_health_check_oc` (pass `workspace_dir` if the user specified one)
2. Read the raw report and identify the most important finding
3. Give a one-sentence verdict first: healthy / minor issues / needs attention
4. Show the full report
5. If there are problems, suggest the next action

## When to suggest follow-up

- Zombie entries > 10% or false-positive signals > 15% → suggest `/memory-cleanup`
- Retrieval quality looks degraded → suggest `/memory-diagnose`
- MEMORY.md has 200+ entries → suggest running a longterm audit
- Everything looks fine → say so, no action needed

## Notes

No API key required. Fast (< 1s). Read-only — never modifies any files.

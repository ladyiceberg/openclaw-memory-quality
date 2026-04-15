---
name: soul-check
description: Audit SOUL.md health for OpenClaw agents — detects boundary violations (injected code, URLs, shell commands, prompt injection), identity drift (action verb density, missing sections), and stability changes across runs. Optional LLM semantic conflict detection available. Use this skill whenever the user wants to check SOUL.md, mentions agent identity issues, soul drift, soul conflicts, or uses phrases like "check soul", "soul health", "SOUL.md", "agent identity", "soul drift", "soul conflict", "检查 SOUL", "SOUL 健康", "身份漂移", "语义冲突". Always use this skill for SOUL.md questions.
---

# Soul Check

Audit SOUL.md health. This file defines the agent's persona and has the highest system priority (priority=20) — it loads every conversation.

## Steps

1. Determine whether to use LLM mode:
   - User says "--llm" or "with LLM" or "semantic check" → `use_llm=True`
   - Otherwise → `use_llm=False`
2. Call `memory_soul_check_oc` with the appropriate `use_llm` value
3. Add a one-line risk verdict before the report:
   - ✅ healthy / 🟡 minor issues / ⚠️ review recommended / 🔴 action required
4. Show the full report
5. If problems found, tell the user what to fix — but note that SOUL.md must be edited manually

## LLM mode adds

- C2 precision: classifies suspicious paragraphs as persona vs task instruction (task instructions don't belong in SOUL.md)
- C4-a: finds semantically contradictory instruction pairs within SOUL.md
- C4-b: compares SOUL.md against IDENTITY.md for inconsistencies

## Important

This tool **never modifies SOUL.md**. Any fixes must be made manually by the user.
LLM mode requires an API key (MINIMAX_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, or KIMI_API_KEY).

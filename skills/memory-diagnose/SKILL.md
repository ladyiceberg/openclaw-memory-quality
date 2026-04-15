---
name: memory-diagnose
description: Deep diagnosis of OpenClaw retrieval quality — identifies false positives, zombie entries, and gives configuration recommendations to fix weak embedding or FTS-only retrieval. Use this skill whenever the user asks about retrieval quality, wonders why memory seems off, wants to understand false positives or zombie entries, asks about embedding or memory configuration, or uses phrases like "memory diagnosis", "bad memories", "why is memory bad", "memory config", "记忆诊断", "检索质量", "假阳性", "记忆配置". Prefer this skill over generic troubleshooting when OpenClaw memory quality is the topic.
---

# Memory Diagnose

Run both retrieval diagnosis and config check, then give a combined verdict.

## Steps

1. Call `memory_retrieval_diagnose_oc` (pass `top_n` if user specified, default 20)
2. Call `memory_config_doctor_oc`
3. Combine both reports into a single diagnostic verdict

## Output structure

Start with a one-sentence diagnosis, then present findings:

> Retrieval quality is degraded. ~18% of entries are high-frequency low-quality false positives, likely FTS literal matches. Recommend: clean up low-quality entries first, then check embedding config.

Then show the two raw reports.

## Suggesting next steps

- High false-positive rate → suggest `/memory-cleanup`
- Config problems found (minScore too low, no embedding provider) → highlight the specific config recommendations from the report
- Ambiguous entries in the "fuzzy zone" → mention that `memory_longterm_audit_oc(use_llm=True)` can do semantic review

## Notes

No API key required. Read-only — never modifies any files.

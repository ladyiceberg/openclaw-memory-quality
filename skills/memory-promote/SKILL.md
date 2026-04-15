---
name: memory-promote
description: >
  Pre-promotion quality audit for OpenClaw short-term memory candidates: checks
  the top-N entries before Dreaming promotes them to MEMORY.md. Detects deleted
  sources, low-value snippets, duplicates, and false positives. Optional LLM
  long-term value advisory. Trigger on: promotion audit, before dreaming,
  check before promote, memory promotion, pre-promote, 晋升前检查, 晋升审计,
  Dreaming 前, 记忆晋升.
allowed-tools: mcp__openclaw-memhealth__memory_promotion_audit_oc
argument-hint: "[workspace_dir] [top_n] [--llm]"
---

# Memory Promote — OpenClaw 晋升前质量预检

在 OpenClaw 的 Dreaming 把短期记忆晋升到 MEMORY.md **之前**，检查候选条目的质量。
帮用户发现不值得晋升的内容（来源已删除、低价值片段、重复条目等）。

## 使用方式

检查评分最高的前 10 条（默认）：
```
/memory-promote
```

检查前 20 条：
```
/memory-promote 20
```

包含 LLM 长期价值评估：
```
/memory-promote --llm
```

## 何时运行

**在 Dreaming 触发前运行**，通常是：
- 感觉短期记忆积累了很多后
- 发现 Dreaming 正在运行或即将运行时
- 定期维护（每周一次）

## 运行步骤

1. 调用 `memory_promotion_audit_oc(top_n=N, use_llm=...)`
2. 翻译结果，重点说明哪些条目**建议跳过**

## 如何翻译结果

直接展示报告，在前面加一句摘要，例如：

> Top 10 候选中，7 条可以正常晋升，2 条建议跳过（1 条来源文件已删除，1 条只有 import 语句），1 条需要关注（平均分偏低）。

## 用户能做什么

此工具只输出建议，**不阻断 Dreaming 流程**。用户可以：
- 忽略建议，让 Dreaming 正常晋升
- 手动在短期记忆文件中删除不想晋升的条目（高级操作）
- 运行 `/memory-cleanup` 先清理低质条目，再让 Dreaming 运行

## 评分说明

报告中的估算分是**近似值**（跳过了 consolidation 分量，误差约 ±10%），
与 OpenClaw 实际晋升评分可能有轻微偏差，仅供参考。

## LLM Advisory 说明

带 `--llm` 时额外提供长期价值评估：
- `long_term_knowledge`：抽象经验/稳定设计事实，适合长期保留
- `one_time_context`：偶发片段/一次性上下文，晋升价值存疑
- `uncertain`：上下文不足，无法判断

Advisory 仅供参考，不影响 Dreaming 的实际晋升决策。

---
name: memory-diagnose
description: >
  Deep diagnosis of OpenClaw retrieval quality: identifies false positives,
  zombie entries, and provides configuration recommendations to fix weak
  embedding or FTS-only retrieval. Trigger on: memory diagnosis, retrieval
  quality, bad memories, why is memory bad, memory config, embedding config,
  记忆诊断, 检索质量, 假阳性, 记忆配置.
allowed-tools: mcp__openclaw-memhealth__memory_retrieval_diagnose_oc, mcp__openclaw-memhealth__memory_config_doctor_oc
argument-hint: "[workspace_dir] [top_n]"
---

# Memory Diagnose — OpenClaw 检索质量深度诊断

当用户感觉"记忆系统不对劲"时使用。诊断检索质量问题，找出低质量条目，给出配置建议。

## 使用方式

```
/memory-diagnose
```

查看更多条目：

```
/memory-diagnose 50
```

## 运行步骤

1. 调用 `memory_retrieval_diagnose_oc`（展示问题条目）
2. 调用 `memory_config_doctor_oc`（检查配置）
3. 综合两份报告，给出诊断结论和行动建议

## 输出结构

先给**一句话诊断结论**，然后分区展示：

### 诊断结论示例

> 检索质量偏低。主要问题：约 18% 的条目是高频低质假阳性，很可能是 FTS 字面匹配噪音。
> 建议：① 先运行 /memory-cleanup 清理低质条目；② 检查 embedding 配置。

### 两类问题区分

| 问题类型 | 描述 | 建议 |
|---------|------|------|
| 假阳性（avgScore 低）| 条目被高频召回但质量低，可能是字面匹配 | `/memory-cleanup` 清理 |
| 配置问题 | minScore 过低、无 embedding provider 等 | 按配置建议修改 |

## 何时推荐 LLM 诊断

如果 `memory_retrieval_diagnose_oc` 结果里有"模糊区间"条目（规则无法确定），
建议用户考虑 `memory_longterm_audit_oc(use_llm=True)` 进行语义复核。

## 注意

不需要 API key。纯只读诊断，不修改任何文件。

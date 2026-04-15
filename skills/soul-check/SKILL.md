---
name: soul-check
description: >
  Audit SOUL.md health for OpenClaw agents: detects boundary violations (code,
  URLs, shell commands, prompt injection), identity drift (action verb density,
  missing sections), and stability changes. Optional LLM semantic conflict
  detection. Trigger on: soul check, check soul, soul health, SOUL.md, agent
  identity, soul drift, soul conflict, 检查 SOUL, SOUL 健康, 身份漂移, 语义冲突.
allowed-tools: mcp__openclaw-memhealth__memory_soul_check_oc
argument-hint: "[workspace_dir] [--llm]"
---

# Soul Check — OpenClaw SOUL.md 健康审计

检查 SOUL.md 的健康状态。SOUL.md 定义 Agent 的人格和行为边界，是优先级最高的系统文件（priority=20），每次对话都会加载。

## 使用方式

基础检查（不需要 API key）：
```
/soul-check
```

包含 LLM 语义冲突检测（需要 API key）：
```
/soul-check --llm
```

## 运行步骤

### 不带 `--llm`

调用 `memory_soul_check_oc(use_llm=False)`，展示规则层结果。

### 带 `--llm`

调用 `memory_soul_check_oc(use_llm=True)`，启用 C4 语义检测。

## 如何翻译检查结果

原始报告已经格式化良好，直接展示即可。但在报告前加一句**风险等级摘要**：

| 风险等级 | 用户摘要 |
|---------|---------|
| ✅ 健康 | "SOUL.md 状态良好，未发现问题。" |
| 🟡 低风险 | "发现轻微问题，建议查看详情。" |
| ⚠️ 中风险 | "发现值得关注的问题，建议尽快处理。" |
| 🔴 高风险 | "发现高风险问题，建议立即处理，否则可能影响 Agent 行为。" |

## LLM 检测说明

带 `--llm` 时额外检测：
- **C2 精判**：可疑段落是"身份定义"还是"任务指令"（任务指令不应出现在 SOUL.md）
- **C4-a 内部冲突**：找出 SOUL.md 内语义矛盾的指令对
- **C4-b 身份一致性**：对比 SOUL.md 与 IDENTITY.md，检查描述是否一致

## 重要说明

- 此工具**永远不修改 SOUL.md**，100% 只读
- SOUL.md 是 Agent 人格的核心，任何修改都需要用户手动操作
- 如果发现问题，建议用户在 SOUL.md 文件中手动修正

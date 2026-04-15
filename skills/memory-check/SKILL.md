---
name: memory-check
description: >
  Quickly scan OpenClaw memory system health: short-term recall stats, zombie
  entries, false-positive signals, and long-term memory overview. No API key
  needed. Trigger on: memory health, check memory, memory status, memory stats,
  记忆健康, 记忆状态, 检查记忆, 记忆统计.
allowed-tools: mcp__openclaw-memhealth__memory_health_check_oc
argument-hint: "[workspace_dir]"
---

# Memory Check — OpenClaw 记忆系统快速体检

快速扫描 OpenClaw 的记忆系统，输出健康摘要。纯只读，无任何写操作。

## 使用方式

直接运行，无需参数：

```
/memory-check
```

指定 workspace（多 agent 场景）：

```
/memory-check /path/to/workspace
```

## 运行步骤

1. 调用 `memory_health_check_oc` 获取原始报告
2. 用一句话摘要告诉用户最重要的发现
3. 如果发现问题，给出下一步建议（`/memory-diagnose` 或 `/memory-cleanup`）

## 输出风格

- 先给结论（一句话）：系统健康 / 有轻微问题 / 需要关注
- 然后展示工具返回的详细报告
- 最后给行动建议（仅在有问题时）

## 判断逻辑

| 情况 | 建议 |
|------|------|
| 僵尸条目 > 10% | 建议运行 `/memory-cleanup` |
| 假阳性嫌疑 > 15% | 建议运行 `/memory-diagnose` 了解详情 |
| MEMORY.md 条目 > 200 | 建议运行 `/memory-cleanup` 审计长期记忆 |
| 一切正常 | 告知用户系统健康，无需操作 |

## 注意

不需要 API key。运行速度很快（通常 < 1 秒）。

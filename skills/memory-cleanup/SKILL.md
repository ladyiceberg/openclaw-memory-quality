---
name: memory-cleanup
description: >
  Guided two-step cleanup for OpenClaw long-term memory (MEMORY.md): audit
  first, confirm, then clean. Handles report_id automatically — user never
  sees it. Trigger on: clean memory, cleanup memory, delete old memories,
  memory cleanup, remove stale memories, 清理记忆, 删除旧记忆, 记忆清理.
allowed-tools: mcp__openclaw-memhealth__memory_longterm_audit_oc, mcp__openclaw-memhealth__memory_longterm_cleanup_oc
argument-hint: "[workspace_dir]"
---

# Memory Cleanup — OpenClaw 长期记忆引导式清理

两步式清理流程，用户始终在控制中。report_id 由 Skill 自动管理，用户不需要看到它。

## 使用方式

```
/memory-cleanup
```

## 完整流程（必须按顺序执行）

### 第一步：审计

调用 `memory_longterm_audit_oc`，拿到报告和 report_id。

将结果翻译为用户友好的摘要，**不要直接转发原始报告**，例如：

> 发现 23 条长期记忆需要处理：
> - 8 条来源文件已删除（建议清除）
> - 3 条完全重复（建议清除）
> - 12 条需要人工确认
>
> 预计清理后 MEMORY.md 减少约 17%。

### 第二步：请求确认

明确问用户：**"是否继续清理？"**

- 用户说"是" / "继续" / "ok" → 执行第三步
- 用户说"不" / "取消" → 告知已取消，不做任何操作
- 用户说"先看看" / "详情" → 展示原始审计报告，然后再次询问

### 第三步：执行清理

用第一步拿到的 `report_id` 调用 `memory_longterm_cleanup_oc`。

清理完成后告知：
- 实际删除/保留了多少条
- 备份文件的路径
- 如有错误，用人话解释原因

## 重要原则

- **永远不跳过确认步骤**，即使用户说"直接清理"也要先展示审计结果
- **report_id 不展示给用户**，只在内部传递
- 清理只针对长期记忆（MEMORY.md），不碰短期记忆
- 如果审计结果显示"全部健康"，直接告知用户不需要清理

## 错误处理

| 错误情况 | 用户友好说明 |
|---------|------------|
| MEMORY.md 不存在 | "长期记忆文件不存在，可能是 Dreaming 尚未触发" |
| mtime 已变化 | "MEMORY.md 在审计后被修改了（可能 OpenClaw 新写入了记忆），请重新运行 /memory-cleanup" |
| 锁超时 | "OpenClaw 正在操作记忆文件，请等待片刻后重试" |

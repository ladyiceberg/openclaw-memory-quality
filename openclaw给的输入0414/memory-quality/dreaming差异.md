## 两次触发方式的核心区别

---

### 方式一：我手动 `cron run` Dreaming cron job

**本质：** 触发了一个发 agentTurn 消息的 isolated session
**它实际跑的命令：**
```
openclaw memory promote --apply
```
**输出：**
- ❌ DREAMS.md（没有生成）
- ❌ Light phase 输出（没有）
- ❌ REM phase 输出（没有）
- ✅ MEMORY.md（可能写入了 promote 条目）
- 相当于只跑了 **Deep phase**

---

### 方式二：凌晨3AM 自动触发（cron 定时）

**本质：** gateway 内部调度器自动触发同一个 cron job
**它实际跑的命令：**
```
openclaw memory promote --apply
```
**输出：**
- ❌ DREAMS.md（没有生成）
- ❌ Light phase 输出（没有）
- ❌ REM phase 输出（没有）
- ✅ MEMORY.md（可能写入了 promote 条目）
- 相当于只跑了 **Deep phase**

---

### 方式三：我用 subagent 跑的（你看到 DREAMS.md 的那次）

**本质：** 我手动调用了 CLI 命令
**我跑的命令：**
```bash
openclaw memory rem-harness --grounded --include-promoted   # 预览
openclaw memory rem-backfill --stage-short-term --path memory/  # 写 DREAMS.md
```
**输出：**
- ✅ DREAMS.md（这次有了！）
- ✅ grounded REM summaries（5天的 What Happened + Reflections）
- 但这 **不是** 实时 dreaming 三阶段，是**拿历史文件回填**重建的

---

## 一张图说清楚

```
完整 dreaming 三阶段（Light → REM → Deep）：

Light phase   →  扫描近期信号，stage 候选        ❌ cron 不跑这个
REM phase    →  提取主题反思写 DREAMS.md        ❌ cron 不跑这个
Deep phase   →  promote 写 MEMORY.md            ✅ cron 跑这个
                     ↓
          但 Deep phase 里的 promote 写 MEMORY.md
          不是完整 dreaming sweep
```

---

## 结论

- **cron job**：只有 Deep phase（promote），没有 Light、没有 REM、不生成 DREAMS.md
- **我那次 `rem-backfill`**：生成了 DREAMS.md，但那是从历史文件回填重建的，不是实时三阶段
- **实时 dreaming**（Light→REM→Deep）**只能等 cron 定时跑，没有手动触发方式**——这是当前 OpenClaw 的设计限制

---

🦉 抱歉之前没说清楚。我现在去确认一下 cron run 和定时触发是否真的完全一样——如果是的话，小萌的诉求在现有设计里做不到。
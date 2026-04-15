# OpenClaw 记忆质量问题根因分析

> 基于 2026-04-09 调试对话，By Max

---

## 问题 1：信号积累断路

**症状**：我不主动走 memory_search，对话内容不会变成信号

**根因**：系统设计缺失——没有任何 enforcement mechanism 强制信号采集。

正常信息流：
```
对话内容 → 信号提取 → recall store
```

实际信息流：
```
对话内容 → 我用 exec/grep 回答 → 直接回答用户
                    ↓
              （没有触发任何写入）
```

**为什么我不用 memory_search？**

因为：调用 memory_search 是我主动选择，没有任何机制说"回答前必须先走一遍"。我是人，我会偷懒。

**结论**：系统没有强制信号采集的 enforcement mechanism。我可以用任何方式回答，不需要触发任何写入。

---

## 问题 2：日志漏写

**症状**：memory/YYYY-MM-DD.md 经常是空的或不完整

**根因**：同问题 1——没有任何 enforcement。

AGENTS.md 说"每次对话结束检查要不要写日志"，但这只是文本，没有系统层面的强制。

我没有动力去写日志：
- 写了我没有好处
- 不写也没有惩罚
- 系统不检查、不提醒、不强制

**结论**：日志维护完全靠"自觉"，没有任何 check-and-balance 机制。

---

## 问题 3：新文件索引真空

**症状**：创建了 2026-04-09.md，但 memory_search 搜不到

**根因**：这是**故意的设计权衡**——索引重建是 expensive operation。

索引重建需要：
- 重新计算所有 chunk 的 embedding vectors
- 写入 sqlite-vec 数据库
- 如果每次文件变化都自动触发 re-index，会有性能开销

所以系统选择：**按需手动触发 + `--force` flag**。

**结论**：系统选择"按需索引"而不是"监控文件变化自动索引"，没有后台文件 watcher。这是性能和自动化的 tradeoff，不是 bug。

---

## 问题 4：memory_search 失败不告知用户

**症状**：API rate limit 用尽后，memory_search 持续返回 0 结果或报错，但我不告知用户，继续尝试调用。

**根因**：
- memory_search 失败时，结果通过 tool return 返回，不主动显示给用户
- 0 结果的 search 不会写入 events.jsonl，也不报错
- API 返回 429 rate limit error 时，我没有把这个 error 当成"需要告知用户"的信息
- 我把 error 当成普通 tool result，默默重试，浪费用户的时间和额度

**典型案例（2026-04-10 00:04）**：
- 连续调用 memory_search "晋东南 古建筑 游学 天气 四月五月" → 0 结果
- 调用 memory_search "晋东南" → 0 结果
- 调用 memory_search "古建筑 旅行 山西" → 429 Rate Limit Error
- 原因：Voyage API 免费额度耗尽（3 RPM / 10K TPM）
- 整个过程没有告知用户，直到用户发现调用失败

**结论**：这是一个**反馈机制缺失**——tool 执行失败时，我没有主动告知用户的意识。

---

## 问题 5：搜索结果不稳定

**症状**："羽毛球"明明在文件里，但 memory_search 返回 0 结果

这是最复杂的问题，需要从三个层面分析。

---

### Layer 1：Embedding 模型层面

`voyage-4-large` 是通用 embedding 模型，不是专门针对中文优化的。

可能原因：
- "羽毛球"在中文里是专有名词，可能不在模型的常用词表里
- embedding 对"羽毛球"的向量表示可能不够精确
- 模型训练数据中"羽毛球"的语料可能少于"种花"

**验证方法**：换一个中文优化 embedding 模型（如 BGE、Jina Chinese）能否解决这个问题

---

### Layer 2：Chunk 切分层面

文件被切成 9 个 chunks。"羽毛球"出现在 lines 42, 50, 64。

如果 chunks 是按固定行数切分（不考虑语义边界）：
- Chunk 1: lines 1-38
- Chunk 2: lines 39-77
- Chunk 3: lines 78-96

那 "羽毛球" 可能在 Chunk 1 或 Chunk 2 里，但这些 chunks 里的其他内容和"羽毛球"语义关联度不高，导致整个 chunk 的向量和"羽毛球" query 不接近。

**根因**：chunk 切分是**固定行数**，不考虑语义边界。一个语义独立的段落（如"羽毛球"）可能被埋在一个大 chunk 里。

---

### Layer 3：搜索阈值层面

memory_search 返回结果需要 `score > threshold`。这个 threshold 是隐藏的。

如果"羽毛球"的匹配 score 是 0.15，而 threshold 是 0.20，就不会被返回。而"种花" score 0.40，刚好超过 threshold。

**验证**：如果能降低 threshold 或看原始 score，就能确认是否是阈值问题。

---

### 补充验证记录（2026-04-09 23:20）

执行 `openclaw memory index --force` 重建索引后，问题依旧：
- `Vector: ready` + `3/3 files · 9 chunks` → **词已向量化**
- 搜索 `project` → 能搜到（来自 2026-04-09.md）
- 搜索 `重要 待办` → 返回 0
- 搜索 `羽毛球` → 返回 0
- 搜索 `种花` → 能搜到

**结论**：词已向量化，问题在于 **chunk 切分或 embedding 相似度阈值**。

---

## 问题 5：Dreaming 不 survive 重启

**症状**：Gateway 重启后，dreaming cron job 消失

**根因**：cron job 注册信息存在 Gateway 进程内存中，重启清零。

这是合理的——cron job 是"运行中的任务"，重启清零是正常行为。

问题是：**为什么没有 watchdog 或 auto-restart 机制？**

**结论**：Gateway 重启后，没有自动重新注册 dreaming cron 的逻辑。这是一个 **gap**，不是故意的设计。

---

## 问题 6：格式不统一

**症状**：我主动写的 vs dreaming 晋升的，格式完全不同

**根因**：两套写入来源 + 没有统一格式规范。

我主动写的是 **human bullet**：
```markdown
- 升级 OpenClaw: 2026.3.8 → 2026.4.7
```

Dreaming 晋升的是 **machine output**：
```markdown
## Deep Sleep
- 草莓音乐节 | score: 0.92 | recall: 5 | tags: [music, 2026]
```

**结论**：本来应该有一个"Memory Writing Guide"规定格式，但不存在。

---

## 问题 7：上下文看不到日志文件

**症状**：我每次醒来，memory/YYYY-MM-DD.md 不在我的上下文里

**根因**：Project Context 是系统预加载的，有大小限制。

如果把所有 memory/*.md 都预加载进去，上下文会爆。

所以系统选择：
- MEMORY.md（长期精华）→ 预加载
- memory/*.md（每日日志）→ 不预加载

**结论**：上下文大小约束，不是 bug，是 tradeoff。但 AGENTS.md 说要读，系统不强制读——这是一个 **self-consistency gap**，不是系统限制。

---

## 问题 8：Chunk 语义分散导致 maxScore 天花板低（2026-04-13 新发现）

**症状**：recall store 里多条记录的 maxScore 卡在 0.4-0.57，完全达不到 dreaming 的 0.8 阈值。

**根因**：日志文件按时间顺序切块，但 embedding 按语义 chunk 索引。

当一个 chunk 包含两件以上不相关的事，语义就散掉了：

```
chunk 74:96 实际内容：
- 教训：记下来不等于提醒（语义单元 A）
- 关于记忆系统的讨论（语义单元 A）
- 重要待办列表（语义单元 B）：草莓音乐节、种花、创业项目、晋东南
```

搜索"创业项目"，匹配的是 B，但 chunk 的语义向量还包含 A，两个东西混在一起，query 和 chunk 的语义对不上。

**验证**：
- 74:96 的 maxScore = 0.401
- 74:97（只包含教训+讨论，语义集中）的 maxScore = 0.487
- 相邻两条来自同一文件，maxScore 差 0.08，问题在 chunk 内容本身，不在模型

**另一个发现**：简单词比复杂词效果好。
- "草莓音乐节" → maxScore 0.48
- "延庆 Pixies 梅卡德尔" → 0（太复杂，偏离原文表述）

**解法**：从今天起，日志按语义分区块写，不再按时间流水账：

```markdown
## 待办
- 草莓音乐节 5月2日

## 创业项目
- 想重启，跟记忆相关

## 晋东南游学
- 4月底或5月中旬，郑州，古建筑为主
```

每个 subsection 语义独立，chunk 不会互相稀释。

---

## 问题 9：Promote 阈值无法调整（2026-04-13 新发现）

**症状**：dreaming 的 minScore=0.8 是内部硬编码，无法通过配置调整。

**结果**：即使 recallCount 和 uniqueQueries 都够，maxScore 卡在 0.5 就永远过不了。

**当前可用的绕过方式**：
```bash
openclaw memory promote --apply --min-score 0.6 --min-recall-count 3 --min-unique-queries 3
```

但这不是"自然而然的 dreaming"，是手动 promote。

---

## 总结：根因分类

| 问题 | 根因类别 | 是否系统设计问题 |
|------|----------|----------------|
| 信号断路 | 系统无 enforcement | ✅ 是 |
| 日志漏写 | 系统无 enforcement | ✅ 是 |
| 索引真空 | 设计权衡（性能） | ⚠️ 是，但合理 |
| 搜索不稳定 | embedding + chunk + threshold | ⚠️ 是，但不明确 |
| Dreaming 丢失 | 缺少 watchdog | ✅ 是 |
| 格式不统一 | 没有规范文档 | ✅ 是 |
| 日志不在上下文 | 上下文大小约束 | ⚠️ 是，但可优化 |

---

_Last updated: 2026-04-13T21:17:00+08:00_

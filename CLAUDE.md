# CLAUDE.md — 项目工作规范

> 本文件是 Claude Code 的项目级指令，对当前项目的所有操作均适用。

---

## 一、仓库同步原则（最重要）

### 不同步到 GitHub 的内容（私有过程文档）

以下文件和目录属于内部过程文档，**绝对不同步到 GitHub 仓库**：

```
研究与调研：
  research/                  ← 所有调研文档
  背景分析.md
  产品方案V1.md

产品与开发设计：
  产品规格文档.md
  开发计划.md

测试数据（含隐私）：
  workspace/                 ← 真实 OpenClaw workspace 数据
  tests/fixtures/real/       ← 真实用户数据 fixture
```

### 同步到 GitHub 的内容（公开）

```
代码：
  server.py
  src/
  tests/（fixtures/real/ 除外）

项目配置：
  pyproject.toml
  requirements.txt
  .gitignore
  CLAUDE.md（本文件）

公开文档：
  README.md（待写）
  CHANGELOG.md（待写）
  LICENSE（待写）
```

### .gitignore 必须包含

```
# 过程文档（不公开）
research/
背景分析.md
产品方案V1.md
产品规格文档.md
开发计划.md

# 真实用户数据（隐私保护）
workspace/
tests/fixtures/real/

# 运行时产物
*.pyc
__pycache__/
.env
*.db
*.sqlite
```

---

## 二、项目基本信息

```
仓库名：openclaw-memory-quality
产品名：openclaw-memhealth
定位：OpenClaw 记忆系统的外部 QA 层（MCP Server 形态）
语言：Python 3.11+
```

### 与 memory-quality-mcp 的关系

```
memory-quality-mcp        → Claude Code 版记忆质量管理（已发布）
openclaw-memhealth        → OpenClaw 版记忆质量管理（本项目）
两者同属 memhealth 产品线，共享部分底层模块（llm_client、session_store、config）
```

---

## 三、开发工作规范

### 文件操作红线

```
1. 绝对不修改 workspace/ 目录下的任何文件（真实用户数据，只读）
2. 写操作测试只能在 tempfile.mkdtemp() 创建的临时目录进行
3. 不向 tests/fixtures/real/ 以外的路径写入任何真实用户数据
```

### 代码规范

```
1. 每个模块都要有对应的测试文件
2. 测试必须通过才能进入下一个 Step（参考开发计划.md）
3. 从 memory-quality-mcp 复用的模块只复制不修改
4. 所有阈值常量集中定义，不在业务逻辑中硬编码数字
```

### OpenClaw 兼容性

```
当前适配版本：OpenClaw v2026.4.4
关键路径（硬编码，源码核实）：
  短期记忆：{workspaceDir}/memory/.dreams/short-term-recall.json
  并发锁：  {workspaceDir}/memory/.dreams/short-term-promotion.lock
  长期记忆：{workspaceDir}/MEMORY.md
  SOUL：    {workspaceDir}/SOUL.md

如 OpenClaw 版本升级导致路径或格式变化，必须重新核实源码后再修改
```

---

## 四、参考文档（本地，不公开）

开发过程中如有疑问，参考以下本地文档：

```
产品规格文档.md   ← 技术细节、数据结构、业务规则、MCP 工具接口
开发计划.md       ← 分步开发计划、每步完成标准、注意事项
```

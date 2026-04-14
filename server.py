from __future__ import annotations
"""
server.py · openclaw-memhealth MCP Server

工具列表：
  Phase 1（只读）：
    memory_health_check_oc       - 快速健康扫描
    memory_retrieval_diagnose_oc - 检索质量详细诊断
    memory_longterm_audit_oc     - MEMORY.md 深度审计

  Phase 2（含写操作）：
    memory_longterm_cleanup_oc   - MEMORY.md 安全清理
    memory_cleanup_shortterm_oc  - 短期记忆僵尸清理
    memory_config_doctor_oc      - 配置建议（推断式）
    memory_soul_check_oc         - SOUL.md 健康检查

  Phase 3（LLM 语义层）：
    memory_promotion_audit_oc    - 晋升前候选质量预检
"""

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from i18n import t
from src.probe import format_probe_summary, probe_workspace

# ── Server 实例 ────────────────────────────────────────────────────────────────

app = Server("openclaw-memhealth")

# ── 工具注册 ───────────────────────────────────────────────────────────────────


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="memory_health_check_oc",
            description=t("tool.health_check.desc"),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_dir": {
                        "type": "string",
                        "description": "OpenClaw workspace 路径（可选，不传则自动检测）",
                    },
                },
            },
        ),
        Tool(
            name="memory_retrieval_diagnose_oc",
            description=t("tool.retrieval_diagnose.desc"),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_dir": {
                        "type": "string",
                        "description": "OpenClaw workspace 路径（可选）",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "展示风险最高的前 N 条（默认 20）",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="memory_longterm_audit_oc",
            description=t("tool.longterm_audit.desc"),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_dir": {
                        "type": "string",
                        "description": "OpenClaw workspace 路径（可选）",
                    },
                    "use_llm": {
                        "type": "boolean",
                        "description": "是否启用 LLM 语义评估（默认 false，需要 API key）",
                        "default": False,
                    },
                },
            },
        ),
    ]


# ── 工具实现（Phase 1 占位符，后续 Step 替换）─────────────────────────────────


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    workspace_dir = arguments.get("workspace_dir")

    # 所有工具第一步：probe workspace
    probe = probe_workspace(workspace_dir)
    summary = format_probe_summary(probe)

    if name == "memory_health_check_oc":
        return await _health_check(probe, summary)

    if name == "memory_retrieval_diagnose_oc":
        top_n = int(arguments.get("top_n", 20))
        return await _retrieval_diagnose(probe, summary, top_n)

    if name == "memory_longterm_audit_oc":
        use_llm = bool(arguments.get("use_llm", False))
        return await _longterm_audit(probe, summary, use_llm)

    return [TextContent(type="text", text=t("common.unknown_tool", name=name))]


# ── Phase 1 工具实现（Step 4/7/6 会替换这里的占位符）─────────────────────────


async def _health_check(probe, summary: str) -> list[TextContent]:
    """memory_health_check_oc 实现占位符（Step 4 替换）。"""
    lines = [summary, ""]

    if probe.warnings:
        for w in probe.warnings:
            lines.append(f"⚠️ {w}")
        lines.append("")

    if not probe.has_shortterm:
        lines.append("短期记忆文件不存在，无法运行健康检查。")
        lines.append("请先配置 Memory Search embedding provider。")
        return [TextContent(type="text", text="\n".join(lines))]

    # TODO: Step 4 实现完整逻辑
    lines.append("🚧 健康检查功能开发中（Step 4）")
    return [TextContent(type="text", text="\n".join(lines))]


async def _retrieval_diagnose(probe, summary: str, top_n: int) -> list[TextContent]:
    """memory_retrieval_diagnose_oc 实现占位符（Step 7 替换）。"""
    lines = [summary, ""]

    if not probe.has_shortterm:
        lines.append("短期记忆文件不存在，无法运行检索质量诊断。")
        return [TextContent(type="text", text="\n".join(lines))]

    # TODO: Step 7 实现完整逻辑
    lines.append("🚧 检索质量诊断开发中（Step 7）")
    return [TextContent(type="text", text="\n".join(lines))]


async def _longterm_audit(probe, summary: str, use_llm: bool) -> list[TextContent]:
    """memory_longterm_audit_oc 实现占位符（Step 6 替换）。"""
    lines = [summary, ""]

    if not probe.has_longterm:
        lines.append("MEMORY.md 不存在，Dreaming 尚未触发过。")
        return [TextContent(type="text", text="\n".join(lines))]

    if not probe.supports_longterm_audit:
        lines.append(
            "当前 MEMORY.md 格式不支持长期记忆审计（无结构化 Dreaming 条目）。"
        )
        return [TextContent(type="text", text="\n".join(lines))]

    # TODO: Step 6 实现完整逻辑
    lines.append("🚧 长期记忆审计开发中（Step 6）")
    return [TextContent(type="text", text="\n".join(lines))]


# ── 入口 ───────────────────────────────────────────────────────────────────────


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()

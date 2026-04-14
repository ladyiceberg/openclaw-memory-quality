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
from src.tools.health_check import run_health_check
from src.tools.longterm_audit import run_longterm_audit
from src.tools.retrieval_diagnose import run_retrieval_diagnose
from src.tools.longterm_cleanup import run_longterm_cleanup
from src.tools.shortterm_cleanup import run_shortterm_cleanup
from src.tools.config_doctor import run_config_doctor

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
        Tool(
            name="memory_longterm_cleanup_oc",
            description=t("tool.longterm_cleanup.desc"),
            inputSchema={
                "type": "object",
                "properties": {
                    "report_id": {
                        "type": "string",
                        "description": "memory_longterm_audit_oc() 返回的 report_id（必填）",
                    },
                    "workspace_dir": {
                        "type": "string",
                        "description": "OpenClaw workspace 路径（可选）",
                    },
                },
                "required": ["report_id"],
            },
        ),
        Tool(
            name="memory_cleanup_shortterm_oc",
            description=t("tool.shortterm_cleanup.desc"),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_dir": {
                        "type": "string",
                        "description": "OpenClaw workspace 路径（可选）",
                    },
                    "cleanup_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "清理类型，默认 [\"zombie\"]，可选 [\"zombie\",\"false_positive\"]",
                        "default": ["zombie"],
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "true=只预览不修改（默认），false=实际执行",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="memory_config_doctor_oc",
            description=t("tool.config_doctor.desc"),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_dir": {
                        "type": "string",
                        "description": "OpenClaw workspace 路径（可选）",
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

    if name == "memory_longterm_cleanup_oc":
        report_id = arguments.get("report_id", "")
        return await _longterm_cleanup(probe, report_id)

    if name == "memory_cleanup_shortterm_oc":
        cleanup_types = arguments.get("cleanup_types", ["zombie"])
        dry_run = bool(arguments.get("dry_run", True))
        return await _shortterm_cleanup(probe, cleanup_types, dry_run)

    if name == "memory_config_doctor_oc":
        return await _config_doctor(probe)

    return [TextContent(type="text", text=t("common.unknown_tool", name=name))]


# ── Phase 1 工具实现（Step 4/7/6 会替换这里的占位符）─────────────────────────


async def _health_check(probe, summary: str) -> list[TextContent]:
    """memory_health_check_oc 实现。"""
    report = run_health_check(probe)
    return [TextContent(type="text", text=report)]


async def _retrieval_diagnose(probe, summary: str, top_n: int) -> list[TextContent]:
    """memory_retrieval_diagnose_oc 实现。"""
    report = run_retrieval_diagnose(probe, top_n=top_n)
    return [TextContent(type="text", text=report)]


async def _longterm_audit(probe, summary: str, use_llm: bool) -> list[TextContent]:
    """memory_longterm_audit_oc 实现。"""
    _report_id, text = run_longterm_audit(probe, use_llm=use_llm)
    return [TextContent(type="text", text=text)]


async def _longterm_cleanup(probe, report_id: str) -> list[TextContent]:
    """memory_longterm_cleanup_oc 实现。"""
    text = run_longterm_cleanup(probe, report_id=report_id)
    return [TextContent(type="text", text=text)]


async def _shortterm_cleanup(probe, cleanup_types: list, dry_run: bool) -> list[TextContent]:
    """memory_cleanup_shortterm_oc 实现。"""
    text = run_shortterm_cleanup(probe, cleanup_types=cleanup_types, dry_run=dry_run)
    return [TextContent(type="text", text=text)]


async def _config_doctor(probe) -> list[TextContent]:
    """memory_config_doctor_oc 实现。"""
    text = run_config_doctor(probe)
    return [TextContent(type="text", text=text)]


# ── 入口 ───────────────────────────────────────────────────────────────────────


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()

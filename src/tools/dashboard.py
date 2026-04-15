from __future__ import annotations
"""
dashboard.py (tools) · memory_dashboard_oc 工具的核心逻辑

与 MCP 层解耦：只接收 ProbeResult，返回格式化文本（文件路径提示）。
实际的 HTML 生成和浏览器打开由 src/dashboard.py 负责。

执行流程：
  1. 从 session_store 读取所有已存储的快照数据
  2. 生成 Dashboard HTML
  3. 写入 ~/.openclaw-memhealth/dashboard.html
  4. 用系统浏览器打开
  5. 返回文件路径提示
"""

from pathlib import Path
from typing import Optional

from src.probe import ProbeResult
from src.dashboard import open_dashboard
from i18n import t


def run_dashboard(
    probe: ProbeResult,
    db_path: Optional[Path] = None,
) -> str:
    """
    生成并打开 Dashboard。

    Args:
        probe   : probe_workspace() 的返回值
        db_path : 测试用，覆盖默认 SQLite 路径

    Returns:
        格式化的结果提示文本
    """
    lines: list[str] = []
    lines.append(t("dashboard.header"))
    lines.append("━" * 30)
    lines.append("")

    try:
        output_path = open_dashboard(
            workspace=probe.workspace_dir,
            db_path=db_path,
        )
        lines.append(t("dashboard.opened", path=str(output_path)))
        lines.append("")
        lines.append(t("dashboard.tip"))
    except Exception as e:
        lines.append(t("dashboard.error", msg=str(e)))

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)

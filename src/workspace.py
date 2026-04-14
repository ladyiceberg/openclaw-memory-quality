from __future__ import annotations
"""
workspace.py · OpenClaw workspaceDir 自动检测

workspaceDir 是 OpenClaw 管理的状态目录，不是用户的项目目录。

默认位置（源码 src/agents/workspace.ts 确认）：
  单 agent：     ~/.openclaw/workspace/
  多 profile：   ~/.openclaw/workspace-{profile}/
  多 agent：     ~/.openclaw/workspace-{agentId}/
"""

import os
from pathlib import Path


# ── 标志文件：用于判断一个目录是否是 workspace ────────────────────────────────

# 任一文件存在即认为是有效 workspace
_WORKSPACE_MARKERS = [
    "MEMORY.md",
    "SOUL.md",
    "AGENTS.md",
    Path("memory") / "short-time-recall.json",        # v2026.4.x 实测
    Path("memory") / ".dreams" / "short-term-recall.json",  # 源码版本
]


def _is_workspace(path: Path) -> bool:
    """判断给定路径是否是 OpenClaw workspace。"""
    if not path.is_dir():
        return False
    return any((path / marker).exists() for marker in _WORKSPACE_MARKERS)


# ── 核心检测函数 ───────────────────────────────────────────────────────────────

def detect_workspace_dirs() -> list[str]:
    """
    自动检测所有 OpenClaw workspaceDir，返回绝对路径列表。

    优先级：
      1. 环境变量 OPENCLAW_WORKSPACE_DIR（用户显式指定，直接返回）
      2. ~/.openclaw/workspace/（默认单 agent，最常见）
      3. ~/.openclaw/workspace-*/（多 agent/profile，glob 匹配）
      4. ~/.openclaw/workspace/（如不存在也包含，供 probe 层给出友好提示）

    注意：workspaceDir 不在用户项目目录里，不向上遍历 cwd。
    """
    # 1. 环境变量显式指定
    env_dir = os.environ.get("OPENCLAW_WORKSPACE_DIR", "").strip()
    if env_dir:
        return [str(Path(env_dir).expanduser().resolve())]

    home = Path.home()
    openclaw_dir = home / ".openclaw"
    found: list[str] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        resolved = str(p.resolve())
        if resolved not in seen:
            seen.add(resolved)
            found.append(resolved)

    # 2. 默认 workspace
    default = openclaw_dir / "workspace"
    if default.exists():
        _add(default)

    # 3. 多 agent/profile：workspace-* glob
    if openclaw_dir.is_dir():
        for candidate in sorted(openclaw_dir.glob("workspace-*")):
            if candidate.is_dir():
                _add(candidate)

    # 如果都不存在，返回默认路径（供 probe 层给出友好提示）
    if not found:
        _add(default)

    return found


def find_workspace_dir(workspace_dir: str | None = None) -> str | None:
    """
    解析单个 workspaceDir。

    Args:
        workspace_dir: 用户显式传入的路径（可选）。
                       不传则调用 detect_workspace_dirs() 取第一个结果。

    Returns:
        workspaceDir 绝对路径字符串，或 None（找不到时）。
    """
    if workspace_dir:
        p = Path(workspace_dir).expanduser().resolve()
        return str(p) if p.exists() else None

    dirs = detect_workspace_dirs()
    # 返回第一个实际存在的
    for d in dirs:
        if Path(d).exists():
            return d
    return None

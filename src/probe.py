from __future__ import annotations
"""
probe.py · workspace 探测模块

每次工具运行的第一步。探测 workspace 结构、识别文件路径和格式版本。
所有后续 reader 接收 ProbeResult，不自己猜路径。

原则：不假设，要探测（probe first, don't assert）。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.formats import (
    SHORT_TERM_CANDIDATES,
    FormatAdapter,
    UnknownFormatAdapter,
    detect_longterm_format,
    ISSUE_URL,
)
from src.workspace import detect_workspace_dirs, find_workspace_dir


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    """
    workspace 探测结果。所有后续模块基于此工作，不自己猜路径。
    """
    workspace_dir: str                  # workspaceDir 绝对路径
    openclaw_version: str | None        # 检测到的版本，如 "2026.4.7"，None 表示未知

    shortterm_path: Path | None         # 实际找到的短期记忆文件
    shortterm_format: str               # "v2026_4_x" / "source_code" / "unknown"

    longterm_path: Path | None          # MEMORY.md 路径（None = 不存在）
    longterm_format: str                # "dreaming" / "manual" / "mixed" / "unknown"
    longterm_adapter: FormatAdapter     # 对应的 format adapter

    soul_path: Path | None              # SOUL.md 路径
    identity_path: Path | None          # IDENTITY.md 路径

    compatible: bool                    # 是否在已验证兼容版本列表内
    warnings: list[str] = field(default_factory=list)

    @property
    def has_shortterm(self) -> bool:
        return self.shortterm_path is not None and self.shortterm_path.exists()

    @property
    def has_longterm(self) -> bool:
        return self.longterm_path is not None and self.longterm_path.exists()

    @property
    def has_soul(self) -> bool:
        return self.soul_path is not None and self.soul_path.exists()

    @property
    def supports_longterm_audit(self) -> bool:
        return self.has_longterm and self.longterm_adapter.supports_longterm_audit


# ── 已验证兼容版本（主版本号匹配即可）────────────────────────────────────────

_COMPATIBLE_VERSION_PREFIXES = (
    "2026.4.",
    "2026.3.",
)


def _is_compatible_version(version: str | None) -> bool:
    if version is None:
        return False
    return any(version.startswith(p) for p in _COMPATIBLE_VERSION_PREFIXES)


# ── 版本检测 ───────────────────────────────────────────────────────────────────

def _detect_version(workspace_dir: Path) -> str | None:
    """
    尝试从 ~/.openclaw/openclaw.json 读取 OpenClaw 版本号。
    读取失败时返回 None（不抛异常）。
    """
    config_candidates = [
        Path.home() / ".openclaw" / "openclaw.json",
        Path.home() / ".clawdbot" / "openclaw.json",
        Path.home() / ".clawdbot" / "clawdbot.json",
    ]
    for config_path in config_candidates:
        try:
            raw = config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            version = data.get("version") or data.get("appVersion")
            if isinstance(version, str) and version:
                return version.strip()
        except Exception:
            continue
    return None


# ── 短期记忆路径探测 ───────────────────────────────────────────────────────────

def _probe_shortterm(workspace_dir: Path) -> tuple[Path | None, str]:
    """
    按优先级探测短期记忆文件，返回 (实际路径或 None, 格式名)。
    """
    for candidate in SHORT_TERM_CANDIDATES:
        p = workspace_dir / candidate
        if p.exists():
            # 根据路径推断格式名
            if ".dreams" in candidate:
                fmt = "source_code"
            else:
                fmt = "unknown"
            return p, fmt
    return None, "unknown"


# ── 长期记忆格式探测 ───────────────────────────────────────────────────────────

def _probe_longterm(workspace_dir: Path) -> tuple[Path | None, str, FormatAdapter]:
    """
    探测 MEMORY.md，识别格式，返回 (路径或 None, 格式名, adapter)。
    """
    longterm_path = workspace_dir / "MEMORY.md"
    if not longterm_path.exists():
        return None, "not_found", UnknownFormatAdapter()

    try:
        content = longterm_path.read_text(encoding="utf-8")
        fmt, adapter = detect_longterm_format(content)
        return longterm_path, fmt, adapter
    except Exception:
        return longterm_path, "unknown", UnknownFormatAdapter()


# ── 主探测函数 ────────────────────────────────────────────────────────────────

def probe_workspace(workspace_dir: str | None = None) -> ProbeResult:
    """
    探测 OpenClaw workspace，返回 ProbeResult。

    Args:
        workspace_dir: 用户显式传入的路径（可选）。
                       不传则自动检测。

    Returns:
        ProbeResult（即使 workspace 不存在也返回，不抛异常）。
        调用方通过 result.warnings 和 result.compatible 判断状态。
    """
    warnings: list[str] = []

    # 解析 workspace_dir
    resolved = find_workspace_dir(workspace_dir)
    if resolved is None:
        # workspace 不存在，返回最小可用的结果
        candidates_tried = detect_workspace_dirs()
        warnings.append(
            f"未找到 OpenClaw workspace。已尝试路径：\n"
            + "\n".join(f"  ✗ {p}" for p in candidates_tried)
        )
        fallback = str(Path.home() / ".openclaw" / "workspace")
        return ProbeResult(
            workspace_dir=fallback,
            openclaw_version=None,
            shortterm_path=None,
            shortterm_format="unknown",
            longterm_path=None,
            longterm_format="not_found",
            longterm_adapter=UnknownFormatAdapter(),
            soul_path=None,
            identity_path=None,
            compatible=False,
            warnings=warnings,
        )

    ws = Path(resolved)

    # 版本检测
    version = _detect_version(ws)
    compatible = _is_compatible_version(version)
    if not compatible and version is not None:
        warnings.append(
            f"OpenClaw v{version} 尚未经过验证，部分功能可能不可用。"
        )

    # 短期记忆探测
    shortterm_path, shortterm_fmt = _probe_shortterm(ws)
    if shortterm_path is None:
        warnings.append(
            "未找到短期记忆文件。Memory Search 可能未配置 embedding provider。\n"
            "已尝试：" + ", ".join(SHORT_TERM_CANDIDATES)
        )

    # 长期记忆探测
    longterm_path, longterm_fmt, longterm_adapter = _probe_longterm(ws)
    if longterm_path is None:
        warnings.append("MEMORY.md 不存在，Dreaming 尚未触发过。")
    elif longterm_fmt == "unknown":
        warnings.append(
            f"MEMORY.md 格式未能识别，长期记忆审计功能不可用。\n"
            f"帮助我们支持你的版本：{ISSUE_URL}"
        )

    # SOUL.md / IDENTITY.md
    soul_path = ws / "SOUL.md"
    identity_path = ws / "IDENTITY.md"

    return ProbeResult(
        workspace_dir=resolved,
        openclaw_version=version,
        shortterm_path=shortterm_path,
        shortterm_format=shortterm_fmt,
        longterm_path=longterm_path,
        longterm_format=longterm_fmt,
        longterm_adapter=longterm_adapter,
        soul_path=soul_path if soul_path.exists() else None,
        identity_path=identity_path if identity_path.exists() else None,
        compatible=compatible,
        warnings=warnings,
    )


def format_probe_summary(result: ProbeResult) -> str:
    """生成 probe 结果的单行摘要，用于工具输出的头部。"""
    version_str = f"v{result.openclaw_version}" if result.openclaw_version else "版本未知"
    compat_str = "已验证兼容" if result.compatible else "版本未经验证"

    lines = [f"📌 OpenClaw {version_str} · {compat_str}"]

    if result.has_shortterm:
        rel = Path(result.shortterm_path).relative_to(result.workspace_dir)
        lines.append(f"   短期记忆：{rel} ✓")
    else:
        lines.append("   短期记忆：未找到 ✗")

    if result.has_longterm:
        fmt_display = {
            "source_code": "Dreaming 格式",
            "mixed": "手动 + Dreaming 混合",
            "manual": "手动维护格式（不支持审计）",
            "unknown": "未知格式",
        }.get(result.longterm_format, result.longterm_format)
        lines.append(f"   长期记忆：MEMORY.md（{fmt_display}）✓")
    else:
        lines.append("   长期记忆：MEMORY.md 不存在")

    if result.has_soul:
        lines.append("   SOUL.md：✓")

    return "\n".join(lines)

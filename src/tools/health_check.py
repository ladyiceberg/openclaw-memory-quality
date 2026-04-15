from __future__ import annotations
"""
health_check.py · memory_health_check_oc 工具的核心逻辑

与 MCP 层解耦：只接收 ProbeResult，返回格式化文本字符串。
测试可直接调用，不需要启动 MCP server。

执行流程：
  1. 读取并解析 short-term-recall.json
  2. B1 僵尸统计 + B2 假阳性统计
  3. 读取 MEMORY.md，轻量计数（section 数 + item 数，不做 V1/V2/V3）
  4. 拼装三个诊断分 + 格式化输出
"""

import time
from datetime import datetime, timezone
from typing import Optional

from src.probe import ProbeResult
from src.readers.shortterm_reader import (
    ShortTermReadError,
    ShortTermStore,
    read_shortterm,
)
from src.readers.longterm_reader import (
    LongTermReadError,
    LongTermStore,
    read_longterm,
)
from src.analyzers.zombie_detector import compute_zombie_stats
from src.analyzers.false_positive import compute_false_positive_stats
from src.session_store import save_health_snapshot
from i18n import t


def run_health_check(
    probe: ProbeResult,
    now_ms: Optional[int] = None,
    db_path=None,
) -> str:
    """
    执行健康检查，返回格式化文本。

    Args:
        probe   : probe_workspace() 的返回值
        now_ms  : 当前时间毫秒戳（测试用，不传则取系统时间）
        db_path : 测试用，覆盖默认 SQLite 路径

    Returns:
        格式化的健康检查报告（多行文本）
    """
    if now_ms is None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    lines: list[str] = []

    # ── 标题 ───────────────────────────────────────────────────────────────────
    lines.append(t("health.header"))
    lines.append("━" * 32)
    lines.append("")

    # ── 短期记忆不存在：早退 ───────────────────────────────────────────────────
    if not probe.has_shortterm:
        lines.append("❌ 短期记忆文件未找到。")
        lines.append("   Memory Search 可能未配置 embedding provider。")
        lines.append("")
        lines.append("   提示：设置 VOYAGE_API_KEY 或其他 embedding provider 后重试。")
        return "\n".join(lines)

    # ── 读取短期记忆 ───────────────────────────────────────────────────────────
    st_result = read_shortterm(probe)

    if isinstance(st_result, ShortTermReadError):
        lines.append(f"❌ 短期记忆读取失败：{st_result.message}")
        return "\n".join(lines)

    store: ShortTermStore = st_result

    # ── B1 + B2 统计 ───────────────────────────────────────────────────────────
    zombie_stats = compute_zombie_stats(store, now_ms)
    fp_stats = compute_false_positive_stats(store)

    zombie_pct = f"{zombie_stats.zombie_ratio * 100:.1f}"
    fp_pct = f"{fp_stats.suspect_ratio * 100:.1f}"

    lines.append(
        t(
            "health.shortterm_summary",
            total=f"{zombie_stats.total:,}",
            zombie=f"{zombie_stats.zombie_count:,}",
            zombie_pct=zombie_pct,
            fp=f"{fp_stats.suspect_count:,}",
            fp_pct=fp_pct,
        )
    )
    lines.append("")

    # ── 长期记忆轻量计数 ───────────────────────────────────────────────────────
    lt_result = read_longterm(probe)

    if isinstance(lt_result, LongTermStore) and lt_result.total_items >= 0:
        lt_store: LongTermStore = lt_result
        if lt_store.total_items > 0 or len(lt_store.sections) > 0:
            lines.append(
                t(
                    "health.longterm_summary",
                    sections=len(lt_store.sections),
                    items=lt_store.total_items,
                )
            )
        else:
            lines.append(t("health.longterm_na"))
    else:
        lines.append(t("health.longterm_na"))

    lines.append("")

    # ── 三个诊断分 ─────────────────────────────────────────────────────────────
    rh = fp_stats.retrieval_health_score
    pr = fp_stats.promotion_risk_score

    rh_icon = _score_icon(rh, higher_is_better=True)
    pr_icon = _score_icon(pr, higher_is_better=False)  # 晋升风险：越高越危险

    lines.append(
        t(
            "health.scores",
            rh=rh,
            rh_icon=rh_icon,
            pr=pr,
            pr_icon=pr_icon,
            lr=t("health.longterm_rot_na"),
        )
    )
    lines.append("")

    # ── FTS 降级警告 ───────────────────────────────────────────────────────────
    if fp_stats.fts_degradation_suspected:
        lines.append(t("health.fts_warning"))
        lines.append(t("health.suggest_diagnose"))
        lines.append("")

    # ── 建议（诊断分偏低时给出）────────────────────────────────────────────────
    if rh < 70:
        lines.append(t("health.suggest_diagnose"))
    if probe.has_longterm:
        lines.append(t("health.suggest_audit"))

    # ── 存入 session_store（供 Dashboard 读取）──────────────────────────────────
    lt_sections = 0
    lt_items = 0
    if isinstance(lt_result, LongTermStore):
        lt_sections = len(lt_result.sections)
        lt_items = lt_result.total_items

    try:
        save_health_snapshot(
            workspace=probe.workspace_dir,
            payload={
                "shortterm_total":   zombie_stats.total,
                "zombie_count":      zombie_stats.zombie_count,
                "zombie_ratio":      round(zombie_stats.zombie_ratio, 4),
                "fp_count":          fp_stats.suspect_count,
                "fp_ratio":          round(fp_stats.suspect_ratio, 4),
                "retrieval_health":  rh,
                "promotion_risk":    pr,
                "fts_degradation":   fp_stats.fts_degradation_suspected,
                "longterm_sections": lt_sections,
                "longterm_items":    lt_items,
            },
            db_path=db_path,
        )
    except Exception:
        pass  # 存储失败不影响主流程

    # 去掉末尾多余空行
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def _score_icon(score: int, higher_is_better: bool) -> str:
    """
    根据分数返回状态图标。
    higher_is_better=True：高分好（Retrieval Health）
    higher_is_better=False：低分好（Promotion Risk）
    """
    if higher_is_better:
        if score >= 80:
            return "✅"
        elif score >= 60:
            return "⚠️"
        else:
            return "🔴"
    else:
        if score <= 20:
            return "✅"
        elif score <= 50:
            return "⚠️"
        else:
            return "🔴"

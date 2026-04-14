from __future__ import annotations
"""
lock_manager.py · OpenClaw 并发锁协议复现

完整复现 openclaw-main 3 的锁协议（short-term-promotion.ts withShortTermLock）。
我们的写操作工具必须遵守同一把锁，才能与 OpenClaw 的 Dreaming 进程安全共存。

锁协议要点（源码逐行核实）：
  锁文件：{workspaceDir}/memory/.dreams/short-term-promotion.lock
  格式：  {PID}:{timestamp_ms}\n
  创建：  open(path, "x") — 独占创建，文件已存在则 FileExistsError
  超时：  10 秒（SHORT_TERM_LOCK_WAIT_TIMEOUT_MS）
  Stale：  mtime 超过 60 秒（SHORT_TERM_LOCK_STALE_MS）
  重试：  40 毫秒（SHORT_TERM_LOCK_RETRY_DELAY_MS）
  抢占：  读 PID → kill(pid, 0) 检查进程是否存活
          ESRCH → 进程不存在 → 可抢占
          EPERM / 其他错误 → 视为存活，不抢占（保守策略）

Python 实现说明：
  - 使用上下文管理器（with 语句），确保锁在任何情况下都会被释放
  - 不依赖 threading.Lock，锁状态由文件系统保证（跨进程安全）
  - 测试时可传入 workspace_dir 为临时目录，完全隔离
"""

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional


# ── 源码对照常量 ───────────────────────────────────────────────────────────────

LOCK_RELATIVE_PATH   = "memory/.dreams/short-term-promotion.lock"
LOCK_WAIT_TIMEOUT_S  = 10.0          # 10 秒（源码 10_000ms）
LOCK_STALE_S         = 60.0          # 60 秒（源码 60_000ms）
LOCK_RETRY_DELAY_S   = 0.040         # 40 毫秒（源码 40ms）


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def _lock_path(workspace_dir: Path) -> Path:
    return workspace_dir / LOCK_RELATIVE_PATH


def _parse_lock_owner_pid(raw: str) -> Optional[int]:
    """
    从锁文件内容中解析 PID。
    格式：{PID}:{timestamp_ms}\n
    解析失败返回 None（视为可抢占）。
    """
    import re
    m = re.match(r"^(\d+):", raw.strip())
    if not m:
        return None
    try:
        pid = int(m.group(1))
        return pid if pid > 0 else None
    except ValueError:
        return None


def _is_process_likely_alive(pid: int) -> bool:
    """
    用 kill(pid, 0) 检查进程是否存活（不发送实际信号）。
    - ESRCH → 进程不存在 → False
    - EPERM → 进程存在但无权发信号 → True（保守策略，与源码一致）
    - 其他错误 → True（保守策略）
    """
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        import errno
        if e.errno == errno.ESRCH:
            return False
        # EPERM 和其他错误视为存活
        return True


def _can_steal_stale_lock(lock_path: Path) -> bool:
    """
    判断是否可以抢占 stale 锁。
    读取锁文件 → 解析 PID → 检查进程是否存活。
    读取失败（文件消失等）→ 返回 True（可抢占）。
    """
    try:
        raw = lock_path.read_text(encoding="utf-8")
    except OSError:
        return True

    pid = _parse_lock_owner_pid(raw)
    if pid is None:
        return True

    return not _is_process_likely_alive(pid)


# ── 自定义异常 ────────────────────────────────────────────────────────────────

class LockTimeoutError(Exception):
    """超时未能获取锁。"""
    pass


class LockAcquireError(Exception):
    """获取锁时发生非预期错误。"""
    pass


# ── 上下文管理器 ───────────────────────────────────────────────────────────────

@contextmanager
def acquire_lock(workspace_dir: Path) -> Generator[None, None, None]:
    """
    获取 OpenClaw 并发锁，作为上下文管理器使用。

    使用方式：
        with acquire_lock(workspace_dir):
            # 在锁保护下执行写操作
            ...

    锁会在 with 块退出时（无论正常或异常）自动释放。

    Raises:
        LockTimeoutError  : 10 秒内未能获取锁
        LockAcquireError  : 获取锁时发生非预期错误
    """
    lock_path = _lock_path(workspace_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    started_at = time.monotonic()
    lock_content = f"{os.getpid()}:{int(time.time() * 1000)}\n"

    while True:
        try:
            # 独占创建：文件已存在则抛 FileExistsError（等价于 O_EXCL）
            with open(lock_path, "x", encoding="utf-8") as f:
                f.write(lock_content)
            # 成功写入，持有锁，执行任务
            break

        except FileExistsError:
            # 锁被其他进程持有，检查是否 stale
            try:
                age_s = time.time() - lock_path.stat().st_mtime
            except OSError:
                age_s = 0.0

            if age_s > LOCK_STALE_S:
                if _can_steal_stale_lock(lock_path):
                    try:
                        lock_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue   # 重试获取

            # 检查超时
            if time.monotonic() - started_at >= LOCK_WAIT_TIMEOUT_S:
                raise LockTimeoutError(
                    f"超时 {LOCK_WAIT_TIMEOUT_S}s 未能获取锁：{lock_path}"
                )

            time.sleep(LOCK_RETRY_DELAY_S)

        except OSError as e:
            raise LockAcquireError(f"获取锁时发生错误：{e}") from e

    try:
        yield
    finally:
        # 无论如何都释放锁
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def is_locked(workspace_dir: Path) -> bool:
    """
    检查 workspace 当前是否持有锁（不包含 stale 判断）。
    供只读诊断工具使用，写操作不应依赖此函数。
    """
    return _lock_path(workspace_dir).exists()

"""
test_lock_manager.py · 并发锁管理器测试

所有测试均在临时目录进行，不接触任何真实 workspace。

覆盖场景：
  - 基本获取 / 释放
  - 锁内容格式（PID:timestamp）
  - 异常退出时自动释放
  - 锁已存在时等待（超时）
  - Stale 锁检测与抢占
  - 辅助函数单元测试
"""
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from src.safety.lock_manager import (
    LOCK_RELATIVE_PATH,
    LOCK_STALE_S,
    LOCK_WAIT_TIMEOUT_S,
    LockAcquireError,
    LockTimeoutError,
    acquire_lock,
    is_locked,
    _can_steal_stale_lock,
    _is_process_likely_alive,
    _lock_path,
    _parse_lock_owner_pid,
)


# ── 测试辅助 ───────────────────────────────────────────────────────────────────

class TempWorkspace:
    """临时 workspace，测试结束自动清理。"""
    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name)

    def lock_path(self) -> Path:
        return _lock_path(self.path)

    def write_lock(self, content: str) -> None:
        """直接写入锁文件（模拟其他进程持有锁）。"""
        lp = self.lock_path()
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(content, encoding="utf-8")

    def cleanup(self):
        self._td.cleanup()


# ── _parse_lock_owner_pid ─────────────────────────────────────────────────────

class TestParseLockOwnerPid:
    def test_valid_format(self):
        """标准格式：{PID}:{timestamp}\n"""
        assert _parse_lock_owner_pid("12345:1744617600000\n") == 12345

    def test_valid_no_newline(self):
        """无末尾换行也能解析。"""
        assert _parse_lock_owner_pid("12345:1744617600000") == 12345

    def test_empty_string(self):
        assert _parse_lock_owner_pid("") is None

    def test_no_colon(self):
        assert _parse_lock_owner_pid("badcontent") is None

    def test_non_numeric_pid(self):
        assert _parse_lock_owner_pid("abc:1744617600000") is None

    def test_zero_pid(self):
        """PID=0 无效（Linux PID 从 1 开始）。"""
        assert _parse_lock_owner_pid("0:1744617600000") is None

    def test_large_valid_pid(self):
        """大 PID 也能正确解析。"""
        assert _parse_lock_owner_pid("999999:1744617600000") == 999999


# ── _is_process_likely_alive ──────────────────────────────────────────────────

class TestIsProcessLikelyAlive:
    def test_current_process_alive(self):
        """当前进程自身应该是存活的。"""
        assert _is_process_likely_alive(os.getpid()) is True

    def test_nonexistent_pid_dead(self):
        """不存在的 PID 应该返回 False。"""
        assert _is_process_likely_alive(999_999_999) is False

    def test_returns_bool(self):
        result = _is_process_likely_alive(os.getpid())
        assert isinstance(result, bool)


# ── 基本获取和释放 ─────────────────────────────────────────────────────────────

class TestAcquireRelease:
    def test_acquire_creates_lock_file(self):
        """acquire_lock 进入后锁文件存在。"""
        ws = TempWorkspace()
        try:
            with acquire_lock(ws.path):
                assert ws.lock_path().exists()
        finally:
            ws.cleanup()

    def test_release_removes_lock_file(self):
        """with 块退出后锁文件消失。"""
        ws = TempWorkspace()
        try:
            with acquire_lock(ws.path):
                pass
            assert not ws.lock_path().exists()
        finally:
            ws.cleanup()

    def test_lock_content_format(self):
        """锁文件内容格式：{PID}:{timestamp_ms}。"""
        ws = TempWorkspace()
        try:
            before_ms = int(time.time() * 1000)
            with acquire_lock(ws.path):
                content = ws.lock_path().read_text(encoding="utf-8")
                after_ms = int(time.time() * 1000)

            parts = content.strip().split(":")
            assert len(parts) == 2
            pid = int(parts[0])
            ts  = int(parts[1])

            assert pid == os.getpid()
            assert before_ms <= ts <= after_ms + 100
        finally:
            ws.cleanup()

    def test_lock_released_on_exception(self):
        """with 块内抛出异常时，锁也要被释放。"""
        ws = TempWorkspace()
        try:
            with pytest.raises(ValueError):
                with acquire_lock(ws.path):
                    raise ValueError("test exception")

            assert not ws.lock_path().exists()
        finally:
            ws.cleanup()

    def test_is_locked_reflects_state(self):
        """is_locked() 准确反映当前锁状态。"""
        ws = TempWorkspace()
        try:
            assert not is_locked(ws.path)
            with acquire_lock(ws.path):
                assert is_locked(ws.path)
            assert not is_locked(ws.path)
        finally:
            ws.cleanup()

    def test_creates_parent_dirs(self):
        """锁文件的父目录（memory/.dreams/）不存在时自动创建。"""
        ws = TempWorkspace()
        try:
            # 确认目录初始不存在
            dreams_dir = ws.path / "memory" / ".dreams"
            assert not dreams_dir.exists()

            with acquire_lock(ws.path):
                assert dreams_dir.exists()
        finally:
            ws.cleanup()

    def test_lock_path_correct(self):
        """锁文件路径符合 OpenClaw 规范。"""
        ws = TempWorkspace()
        try:
            with acquire_lock(ws.path):
                expected = ws.path / LOCK_RELATIVE_PATH
                assert ws.lock_path() == expected
                assert ws.lock_path().exists()
        finally:
            ws.cleanup()


# ── 超时 ──────────────────────────────────────────────────────────────────────

class TestLockTimeout:
    def test_timeout_when_lock_held_by_live_process(self):
        """
        锁被当前进程持有（模拟另一个进程）时，再次尝试获取会超时。

        注意：用极短超时（0.1s）以免拖慢测试。
        通过 monkeypatch 临时缩短超时常量。
        """
        ws = TempWorkspace()
        try:
            # 写入一个当前进程 PID 的锁（视为活跃锁）
            ws.write_lock(f"{os.getpid()}:{int(time.time() * 1000)}\n")

            # 用极短超时测试
            import src.safety.lock_manager as lm
            original = lm.LOCK_WAIT_TIMEOUT_S
            lm.LOCK_WAIT_TIMEOUT_S = 0.1
            try:
                with pytest.raises(LockTimeoutError):
                    with acquire_lock(ws.path):
                        pass
            finally:
                lm.LOCK_WAIT_TIMEOUT_S = original
        finally:
            ws.cleanup()

    def test_timeout_error_message_contains_path(self):
        """超时错误信息包含锁文件路径。"""
        ws = TempWorkspace()
        try:
            ws.write_lock(f"{os.getpid()}:{int(time.time() * 1000)}\n")

            import src.safety.lock_manager as lm
            original = lm.LOCK_WAIT_TIMEOUT_S
            lm.LOCK_WAIT_TIMEOUT_S = 0.1
            try:
                with pytest.raises(LockTimeoutError) as exc_info:
                    with acquire_lock(ws.path):
                        pass
                assert "lock" in str(exc_info.value).lower() or str(ws.path) in str(exc_info.value)
            finally:
                lm.LOCK_WAIT_TIMEOUT_S = original
        finally:
            ws.cleanup()


# ── Stale 锁抢占 ──────────────────────────────────────────────────────────────

class TestStaleLock:
    def test_stale_lock_by_dead_process_is_stolen(self):
        """
        Stale 锁（mtime 超过 60s）且进程不存活 → 被抢占，不超时。
        """
        ws = TempWorkspace()
        try:
            # 写入一个不存在进程的 PID 的锁
            dead_pid = 999_999_999
            ws.write_lock(f"{dead_pid}:{int(time.time() * 1000)}\n")

            # 手动把锁文件 mtime 设为 70 秒前（超过 LOCK_STALE_S=60）
            stale_time = time.time() - (LOCK_STALE_S + 10)
            os.utime(ws.lock_path(), (stale_time, stale_time))

            # 应该能成功获取锁（不抛 LockTimeoutError）
            with acquire_lock(ws.path):
                assert ws.lock_path().exists()

            assert not ws.lock_path().exists()
        finally:
            ws.cleanup()

    def test_stale_lock_by_live_process_not_stolen(self):
        """
        Stale 锁（mtime 超过 60s）但进程仍存活 → 不抢占，最终超时。
        """
        ws = TempWorkspace()
        try:
            # 当前进程 PID → 视为存活
            ws.write_lock(f"{os.getpid()}:{int(time.time() * 1000)}\n")

            # mtime 设为 70 秒前
            stale_time = time.time() - (LOCK_STALE_S + 10)
            os.utime(ws.lock_path(), (stale_time, stale_time))

            import src.safety.lock_manager as lm
            original = lm.LOCK_WAIT_TIMEOUT_S
            lm.LOCK_WAIT_TIMEOUT_S = 0.1
            try:
                with pytest.raises(LockTimeoutError):
                    with acquire_lock(ws.path):
                        pass
            finally:
                lm.LOCK_WAIT_TIMEOUT_S = original
        finally:
            ws.cleanup()

    def test_can_steal_stale_lock_dead_process(self):
        """_can_steal_stale_lock：不存在的 PID → True。"""
        ws = TempWorkspace()
        try:
            ws.write_lock("999999999:1744617600000\n")
            assert _can_steal_stale_lock(ws.lock_path()) is True
        finally:
            ws.cleanup()

    def test_can_steal_stale_lock_live_process(self):
        """_can_steal_stale_lock：当前进程 PID → False（进程存活不可抢占）。"""
        ws = TempWorkspace()
        try:
            ws.write_lock(f"{os.getpid()}:1744617600000\n")
            assert _can_steal_stale_lock(ws.lock_path()) is False
        finally:
            ws.cleanup()

    def test_can_steal_stale_lock_unreadable(self):
        """_can_steal_stale_lock：锁文件不存在（已被删除）→ True（可抢占）。"""
        ws = TempWorkspace()
        try:
            fake_path = ws.path / "nonexistent.lock"
            assert _can_steal_stale_lock(fake_path) is True
        finally:
            ws.cleanup()

    def test_can_steal_stale_lock_invalid_content(self):
        """_can_steal_stale_lock：锁文件内容无法解析 PID → True。"""
        ws = TempWorkspace()
        try:
            ws.write_lock("invalid content no pid\n")
            assert _can_steal_stale_lock(ws.lock_path()) is True
        finally:
            ws.cleanup()

    def test_fresh_lock_not_stolen(self):
        """
        锁文件 mtime 是新鲜的（< 60s），即使 PID 不存在，也不应被抢占。
        （新鲜锁可能是刚创建的，PID 可能还未写完）
        """
        ws = TempWorkspace()
        try:
            # 不存在的 PID，但 mtime 是当前时间（新鲜）
            dead_pid = 999_999_999
            ws.write_lock(f"{dead_pid}:{int(time.time() * 1000)}\n")
            # 不修改 mtime，保持新鲜

            import src.safety.lock_manager as lm
            original = lm.LOCK_WAIT_TIMEOUT_S
            lm.LOCK_WAIT_TIMEOUT_S = 0.1
            try:
                with pytest.raises(LockTimeoutError):
                    with acquire_lock(ws.path):
                        pass
            finally:
                lm.LOCK_WAIT_TIMEOUT_S = original
        finally:
            ws.cleanup()


# ── 重入与串行 ─────────────────────────────────────────────────────────────────

class TestLockSerial:
    def test_sequential_acquires_succeed(self):
        """连续两次获取（不重叠）都能成功。"""
        ws = TempWorkspace()
        try:
            with acquire_lock(ws.path):
                pass
            # 第一次释放后第二次应成功
            with acquire_lock(ws.path):
                assert is_locked(ws.path)
        finally:
            ws.cleanup()

    def test_thread_waits_for_lock(self):
        """
        线程 A 持有锁，线程 B 等待；A 释放后 B 能获取锁。
        验证等待-重试机制正常工作。
        """
        ws = TempWorkspace()
        results = []

        def thread_a():
            with acquire_lock(ws.path):
                results.append("A_acquired")
                time.sleep(0.05)   # 持有 50ms
                results.append("A_releasing")

        def thread_b():
            time.sleep(0.01)   # 等 A 先进入
            with acquire_lock(ws.path):
                results.append("B_acquired")

        try:
            ta = threading.Thread(target=thread_a)
            tb = threading.Thread(target=thread_b)
            ta.start(); tb.start()
            ta.join(timeout=5); tb.join(timeout=5)

            assert "A_acquired"  in results
            assert "A_releasing" in results
            assert "B_acquired"  in results
            # B 一定在 A 释放之后才获取
            assert results.index("B_acquired") > results.index("A_releasing")
        finally:
            ws.cleanup()

"""
test_workspace.py · workspace 自动检测测试
"""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.workspace import detect_workspace_dirs, find_workspace_dir


class TestDetectWorkspaceDirs:
    def test_env_var_takes_priority(self, tmp_path):
        """OPENCLAW_WORKSPACE_DIR 环境变量优先级最高。"""
        with patch.dict(os.environ, {"OPENCLAW_WORKSPACE_DIR": str(tmp_path)}):
            result = detect_workspace_dirs()
        assert result == [str(tmp_path.resolve())]

    def test_default_workspace_found(self, tmp_path, monkeypatch):
        """~/.openclaw/workspace/ 存在时返回它。"""
        fake_home = tmp_path
        fake_workspace = fake_home / ".openclaw" / "workspace"
        fake_workspace.mkdir(parents=True)

        monkeypatch.setenv("OPENCLAW_WORKSPACE_DIR", "")
        with patch("src.workspace.Path.home", return_value=fake_home):
            result = detect_workspace_dirs()

        assert str(fake_workspace.resolve()) in result

    def test_multiple_workspaces_found(self, tmp_path, monkeypatch):
        """多个 workspace-* 目录时全部返回。"""
        fake_home = tmp_path
        openclaw_dir = fake_home / ".openclaw"
        (openclaw_dir / "workspace").mkdir(parents=True)
        (openclaw_dir / "workspace-work").mkdir(parents=True)
        (openclaw_dir / "workspace-personal").mkdir(parents=True)

        monkeypatch.setenv("OPENCLAW_WORKSPACE_DIR", "")
        with patch("src.workspace.Path.home", return_value=fake_home):
            result = detect_workspace_dirs()

        assert len(result) >= 3

    def test_no_workspace_returns_default_path(self, tmp_path, monkeypatch):
        """都不存在时，返回默认路径（供 probe 给出友好提示）。"""
        fake_home = tmp_path  # 空目录，无 .openclaw
        monkeypatch.setenv("OPENCLAW_WORKSPACE_DIR", "")
        with patch("src.workspace.Path.home", return_value=fake_home):
            result = detect_workspace_dirs()

        # 返回非空列表（包含默认路径）
        assert len(result) >= 1
        assert ".openclaw" in result[0]


class TestFindWorkspaceDir:
    def test_explicit_path_exists(self, tmp_path):
        """显式传入存在的路径直接返回。"""
        result = find_workspace_dir(str(tmp_path))
        assert result == str(tmp_path.resolve())

    def test_explicit_path_not_exists(self, tmp_path):
        """显式传入不存在的路径返回 None。"""
        non_exist = str(tmp_path / "not_exist")
        result = find_workspace_dir(non_exist)
        assert result is None

    def test_auto_detect_real_workspace(self):
        """自动检测：如果真实 workspace 存在就应该找到。"""
        real = Path.home() / ".openclaw" / "workspace"
        result = find_workspace_dir()
        if real.exists():
            assert result is not None
        # 如果不存在，result 可能是 None，不报错

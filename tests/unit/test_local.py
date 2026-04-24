"""Unit tests for _local.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tmux_manager._local import (
    attach_session,
    command_available,
    kill_session,
    list_sessions,
    new_session,
)


class TestCommandAvailable:
    def test_found(self):
        with patch("tmux_manager._local.shutil.which", return_value="/usr/bin/tmux"):
            assert command_available("tmux") is True

    def test_not_found(self):
        with patch("tmux_manager._local.shutil.which", return_value=None):
            assert command_available("tmux") is False


class TestListSessions:
    def _result(self, returncode: int, stdout: str) -> MagicMock:
        r = MagicMock()
        r.returncode = returncode
        r.stdout = stdout
        return r

    def test_returns_session_names(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, "main\nwork\n"),
        ):
            assert list_sessions() == ["main", "work"]

    def test_nonzero_exit_returns_empty(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(1, ""),
        ):
            assert list_sessions() == []

    def test_empty_output_returns_empty(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, ""),
        ):
            assert list_sessions() == []


class TestNewSession:
    def test_success_returns_true(self):
        r = MagicMock()
        r.returncode = 0
        with patch("tmux_manager._local.subprocess.run", return_value=r):
            assert new_session("work") is True

    def test_failure_returns_false(self):
        r = MagicMock()
        r.returncode = 1
        with patch("tmux_manager._local.subprocess.run", return_value=r):
            assert new_session("work") is False


class TestKillSession:
    def test_success_returns_true(self):
        r = MagicMock()
        r.returncode = 0
        with patch("tmux_manager._local.subprocess.run", return_value=r):
            assert kill_session("work") is True

    def test_failure_returns_false(self):
        r = MagicMock()
        r.returncode = 1
        with patch("tmux_manager._local.subprocess.run", return_value=r):
            assert kill_session("work") is False


class TestAttachSession:
    def test_calls_tmux_attach(self):
        with patch("tmux_manager._local.subprocess.run") as mock_run:
            attach_session("main")
        args = mock_run.call_args[0][0]
        assert "tmux" in args
        assert "attach-session" in args
        assert "main" in args

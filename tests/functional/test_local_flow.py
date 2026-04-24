"""Functional tests for local TmuxManager flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tmux_manager import TmuxManager


def _run_result(returncode: int, stdout: str = "") -> MagicMock:
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    return r


class TestLocalFlow:
    def test_full_lifecycle(self):
        """Create, list, check, kill a local session end-to-end (mocked)."""
        mgr = TmuxManager()

        with patch("tmux_manager._local.subprocess.run", return_value=_run_result(0)):
            assert mgr.new_session("work") is True

        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=_run_result(0, "work\n"),
        ):
            assert mgr.has_session("work") is True
            assert mgr.list_sessions() == ["work"]

        with patch("tmux_manager._local.subprocess.run", return_value=_run_result(0)):
            assert mgr.kill_session("work") is True

        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=_run_result(1, ""),
        ):
            assert mgr.has_session("work") is False

    def test_is_available_uses_which(self):
        with patch("tmux_manager._local.shutil.which", return_value="/usr/bin/tmux"):
            assert TmuxManager().is_available() is True

    def test_command_available_false_when_missing(self):
        with patch("tmux_manager._local.shutil.which", return_value=None):
            assert TmuxManager().command_available("fzf") is False

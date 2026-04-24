"""Functional tests for remote TmuxManager flow."""

from __future__ import annotations

from unittest.mock import patch

from tmux_manager import TmuxManager


class TestRemoteFlow:
    def test_full_lifecycle(self):
        """Create, list, kill a remote session end-to-end (mocked _ssh_exec)."""
        mgr = TmuxManager("devbox", "alice")

        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")):
            assert mgr.new_session("work") is True

        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "work\n")):
            assert mgr.has_session("work") is True
            assert mgr.list_sessions() == ["work"]

        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")):
            assert mgr.kill_session("work") is True

        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")):
            assert mgr.has_session("work") is False

    def test_unreachable_host_safe(self):
        """All methods return safe defaults when SSH fails."""
        mgr = TmuxManager("unreachable", None)

        with patch("tmux_manager._remote._ssh_exec", return_value=(-1, "")):
            assert mgr.is_available() is False
            assert mgr.list_sessions() == []
            assert mgr.has_session("x") is False
            assert mgr.new_session("x") is False
            assert mgr.kill_session("x") is False

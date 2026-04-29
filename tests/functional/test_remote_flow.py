"""Functional tests for remote TmuxManager flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tmux_manager import TmuxManager


class TestRemoteFlow:
    def test_full_lifecycle(self):
        """Create, list, kill a remote session end-to-end."""
        with patch("tmux_manager._remote._ssh_exec") as mock_exec:
            mgr = TmuxManager("devbox", "alice")

            mock_exec.return_value = (0, "")
            assert mgr.new_session("work") is True

            mock_exec.return_value = (0, "work\n")
            assert mgr.has_session("work") is True
            assert mgr.list_sessions() == ["work"]

            mock_exec.return_value = (0, "")
            assert mgr.kill_session("work") is True

            mock_exec.return_value = (0, "")
            assert mgr.has_session("work") is False

    def test_all_operations_use_ssh(self):
        """Verify all operations call _ssh_exec with correct host/user."""
        with patch("tmux_manager._remote._ssh_exec") as mock_exec:
            mgr = TmuxManager("devbox", "alice")

            mock_exec.return_value = (0, "/usr/bin/tmux\n")
            mgr.is_available()

            mock_exec.return_value = (0, "")
            mgr.new_session("s1")

            mock_exec.return_value = (0, "s1\n")
            mgr.list_sessions()

            mock_exec.return_value = (0, "")
            mgr.kill_session("s1")

            assert mock_exec.call_count == 4
            for call in mock_exec.call_args_list:
                assert call[0][0] == "devbox"
                assert call[0][1] == "alice"

    def test_ssh_failure_returns_empty(self):
        """When ssh fails, list_sessions returns [] gracefully."""
        with patch("tmux_manager._remote._ssh_exec", return_value=(-1, "")):
            mgr = TmuxManager("unreachable", None)
            assert mgr.list_sessions() == []

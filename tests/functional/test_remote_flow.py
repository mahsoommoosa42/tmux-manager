"""Functional tests for remote TmuxManager flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import paramiko
import pytest

from tmux_manager import TmuxManager


class TestRemoteFlow:
    def test_full_lifecycle(self):
        """Create, list, kill a remote session end-to-end via persistent conn."""
        conn = MagicMock()
        with patch("tmux_manager.manager._remote._SSHConnection", return_value=conn):
            mgr = TmuxManager("devbox", "alice")

        conn.exec.return_value = (0, "")
        assert mgr.new_session("work") is True

        conn.exec.return_value = (0, "work\n")
        assert mgr.has_session("work") is True
        assert mgr.list_sessions() == ["work"]

        conn.exec.return_value = (0, "")
        assert mgr.kill_session("work") is True

        conn.exec.return_value = (0, "")
        assert mgr.has_session("work") is False

    def test_all_operations_use_single_connection(self):
        """Verify a sequence of operations all go through a single mock exec."""
        conn = MagicMock()
        with patch("tmux_manager.manager._remote._SSHConnection", return_value=conn):
            mgr = TmuxManager("devbox", "alice")

        conn.exec.return_value = (0, "/usr/bin/tmux\n")
        mgr.is_available()

        conn.exec.return_value = (0, "")
        mgr.new_session("s1")

        conn.exec.return_value = (0, "s1\n")
        mgr.list_sessions()

        conn.exec.return_value = (0, "")
        mgr.kill_session("s1")

        assert conn.exec.call_count == 4

    def test_unreachable_host_raises(self):
        """Constructing TmuxManager with unreachable host now raises."""
        with (
            patch(
                "tmux_manager._remote._load_ssh_config",
                return_value={},
            ),
            patch(
                "tmux_manager._remote.paramiko.SSHClient",
            ) as mock_cls,
            pytest.raises(paramiko.SSHException, match="connection failed"),
        ):
            mock_cls.return_value.connect.side_effect = paramiko.SSHException(
                "connection failed"
            )
            TmuxManager("unreachable", None)

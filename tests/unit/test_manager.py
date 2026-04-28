"""Unit tests for manager.py (TmuxManager)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tmux_manager import TmuxManager


class TestTmuxManagerLocal:
    """TmuxManager with no host dispatches to _local."""

    def test_is_available_true(self):
        with patch("tmux_manager.manager._local.command_available", return_value=True):
            assert TmuxManager().is_available() is True

    def test_is_available_false(self):
        with patch("tmux_manager.manager._local.command_available", return_value=False):
            assert TmuxManager().is_available() is False

    def test_command_available(self):
        with patch("tmux_manager.manager._local.command_available", return_value=True) as m:
            result = TmuxManager().command_available("fzf")
        m.assert_called_once_with("fzf")
        assert result is True

    def test_list_sessions(self):
        with patch("tmux_manager.manager._local.list_sessions", return_value=["main"]):
            assert TmuxManager().list_sessions() == ["main"]

    def test_has_session_true(self):
        with patch("tmux_manager.manager._local.list_sessions", return_value=["main", "work"]):
            assert TmuxManager().has_session("main") is True

    def test_has_session_false(self):
        with patch("tmux_manager.manager._local.list_sessions", return_value=["main"]):
            assert TmuxManager().has_session("nope") is False

    def test_new_session(self):
        with patch("tmux_manager.manager._local.new_session", return_value=True) as m:
            result = TmuxManager().new_session("work")
        m.assert_called_once_with("work")
        assert result is True

    def test_kill_session(self):
        with patch("tmux_manager.manager._local.kill_session", return_value=True) as m:
            result = TmuxManager().kill_session("work")
        m.assert_called_once_with("work")
        assert result is True

    def test_attach_session(self):
        with patch("tmux_manager.manager._local.attach_session") as m:
            TmuxManager().attach_session("main")
        m.assert_called_once_with("main")

    def test_init_no_connection_for_local(self):
        mgr = TmuxManager()
        assert mgr._conn is None

    def test_close_noop_for_local(self):
        mgr = TmuxManager()
        mgr._close()

    def test_context_manager_local(self):
        with TmuxManager() as mgr:
            assert mgr._conn is None

    def test_del_noop_for_local(self):
        mgr = TmuxManager()
        mgr.__del__()


class TestTmuxManagerRemote:
    """TmuxManager with host dispatches to _remote via persistent connection."""

    @staticmethod
    def _mock_conn():
        return patch("tmux_manager.manager._remote._SSHConnection", return_value=MagicMock())

    def test_init_creates_connection(self):
        with patch("tmux_manager.manager._remote._SSHConnection") as mock_cls:
            mgr = TmuxManager("devbox", "alice")
        mock_cls.assert_called_once_with("devbox", "alice")
        assert mgr._conn is mock_cls.return_value

    def test_init_no_connection_for_local(self):
        mgr = TmuxManager()
        assert mgr._conn is None

    def test_context_manager_closes(self):
        conn = MagicMock()
        with patch("tmux_manager.manager._remote._SSHConnection", return_value=conn):
            with TmuxManager("devbox") as mgr:
                pass
        conn.close.assert_called()

    def test_del_closes(self):
        conn = MagicMock()
        with patch("tmux_manager.manager._remote._SSHConnection", return_value=conn):
            mgr = TmuxManager("devbox")
        mgr.__del__()
        conn.close.assert_called()

    def test_use_after_close_raises(self):
        conn = MagicMock()
        with patch("tmux_manager.manager._remote._SSHConnection", return_value=conn):
            mgr = TmuxManager("devbox")
        mgr._close()
        with pytest.raises(RuntimeError, match="connection is closed"):
            mgr.list_sessions()

    def test_is_available_true(self):
        conn = MagicMock()
        with (
            patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
            patch("tmux_manager.manager._remote._command_available_conn", return_value=True),
        ):
            assert TmuxManager("devbox").is_available() is True

    def test_is_available_false(self):
        conn = MagicMock()
        with (
            patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
            patch("tmux_manager.manager._remote._command_available_conn", return_value=False),
        ):
            assert TmuxManager("devbox").is_available() is False

    def test_command_available_delegates(self):
        conn = MagicMock()
        with (
            patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
            patch("tmux_manager.manager._remote._command_available_conn", return_value=True) as m,
        ):
            result = TmuxManager("devbox", "alice").command_available("fzf")
        m.assert_called_once_with(conn, "fzf")
        assert result is True

    def test_list_sessions_delegates(self):
        conn = MagicMock()
        with (
            patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
            patch("tmux_manager.manager._remote._list_sessions_conn", return_value=["s1"]) as m,
        ):
            result = TmuxManager("devbox", "alice").list_sessions()
        m.assert_called_once_with(conn)
        assert result == ["s1"]

    def test_has_session_delegates(self):
        conn = MagicMock()
        with (
            patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
            patch("tmux_manager.manager._remote._list_sessions_conn", return_value=["s1"]),
        ):
            assert TmuxManager("devbox").has_session("s1") is True

    def test_new_session_delegates(self):
        conn = MagicMock()
        with (
            patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
            patch("tmux_manager.manager._remote._new_session_conn", return_value=True) as m,
        ):
            result = TmuxManager("devbox", "alice").new_session("work")
        m.assert_called_once_with(conn, "work")
        assert result is True

    def test_kill_session_delegates(self):
        conn = MagicMock()
        with (
            patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
            patch("tmux_manager.manager._remote._kill_session_conn", return_value=False) as m,
        ):
            result = TmuxManager("devbox").kill_session("work")
        m.assert_called_once_with(conn, "work")
        assert result is False

    def test_attach_uses_system_ssh(self):
        conn = MagicMock()
        with (
            patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
            patch("tmux_manager.manager._remote.attach_session") as m,
        ):
            TmuxManager("devbox", "alice").attach_session("main")
        m.assert_called_once_with("devbox", "alice", "main")

    def test_no_user_passes_none(self):
        conn = MagicMock()
        with (
            patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
            patch("tmux_manager.manager._remote._list_sessions_conn", return_value=[]) as m,
        ):
            TmuxManager("devbox").list_sessions()
        m.assert_called_once_with(conn)

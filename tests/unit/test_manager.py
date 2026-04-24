"""Unit tests for manager.py (TmuxManager)."""

from __future__ import annotations

from unittest.mock import patch

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


class TestTmuxManagerRemote:
    """TmuxManager with host dispatches to _remote."""

    def test_is_available_true(self):
        with patch("tmux_manager.manager._remote.command_available", return_value=True):
            assert TmuxManager("devbox").is_available() is True

    def test_is_available_false(self):
        with patch("tmux_manager.manager._remote.command_available", return_value=False):
            assert TmuxManager("devbox").is_available() is False

    def test_command_available_passes_host_and_user(self):
        with patch("tmux_manager.manager._remote.command_available", return_value=True) as m:
            TmuxManager("devbox", "alice").command_available("fzf")
        m.assert_called_once_with("devbox", "alice", "fzf")

    def test_list_sessions_passes_host_and_user(self):
        with patch("tmux_manager.manager._remote.list_sessions", return_value=["s1"]) as m:
            result = TmuxManager("devbox", "alice").list_sessions()
        m.assert_called_once_with("devbox", "alice")
        assert result == ["s1"]

    def test_new_session_passes_args(self):
        with patch("tmux_manager.manager._remote.new_session", return_value=True) as m:
            TmuxManager("devbox", "alice").new_session("work")
        m.assert_called_once_with("devbox", "alice", "work")

    def test_kill_session_passes_args(self):
        with patch("tmux_manager.manager._remote.kill_session", return_value=False) as m:
            result = TmuxManager("devbox").kill_session("work")
        m.assert_called_once_with("devbox", None, "work")
        assert result is False

    def test_attach_session_passes_args(self):
        with patch("tmux_manager.manager._remote.attach_session") as m:
            TmuxManager("devbox", "alice").attach_session("main")
        m.assert_called_once_with("devbox", "alice", "main")

    def test_no_user_passes_none(self):
        with patch("tmux_manager.manager._remote.list_sessions", return_value=[]) as m:
            TmuxManager("devbox").list_sessions()
        m.assert_called_once_with("devbox", None)

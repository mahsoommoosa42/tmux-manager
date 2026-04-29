"""Unit tests for manager.py (TmuxManager)."""

from __future__ import annotations

import os
from unittest.mock import patch

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

    def test_init_stores_none_host(self):
        mgr = TmuxManager()
        assert mgr._host is None
        assert mgr._control_dir is None
        assert mgr._control_path is None

    def test_context_manager_local(self):
        with TmuxManager() as mgr:
            assert mgr._host is None

    def test_connect_local_noop(self):
        mgr = TmuxManager()
        assert mgr.connect() is mgr

    def test_close_local_is_noop(self):
        mgr = TmuxManager()
        mgr.close()  # should not raise

    def test_del_local_is_noop(self):
        mgr = TmuxManager()
        mgr.__del__()  # should not raise


class TestTmuxManagerRemote:
    """TmuxManager with host dispatches to _remote with control_path."""

    def test_init_creates_control_dir(self):
        mgr = TmuxManager("devbox", "alice")
        assert mgr._host == "devbox"
        assert mgr._user == "alice"
        assert mgr._control_dir is not None
        assert os.path.isdir(mgr._control_dir)
        assert mgr._control_path is not None
        mgr.close()

    def test_context_manager_cleans_up(self):
        with TmuxManager("devbox") as mgr:
            d = mgr._control_dir
            assert os.path.isdir(d)
        assert not os.path.exists(d)

    def test_close_idempotent(self):
        mgr = TmuxManager("devbox")
        mgr.close()
        mgr.close()  # second call should not raise

    def test_del_cleans_up(self):
        mgr = TmuxManager("devbox")
        d = mgr._control_dir
        assert os.path.isdir(d)
        mgr.__del__()
        assert not os.path.exists(d)

    def test_close_calls_close_mux(self):
        mgr = TmuxManager("devbox", "alice")
        cp = mgr._control_path
        with patch("tmux_manager.manager._remote._close_mux") as m:
            mgr.close()
        m.assert_called_once_with("devbox", "alice", cp)

    def test_connect_remote_success(self):
        with patch("tmux_manager.manager._remote._validate", return_value=True) as m:
            mgr = TmuxManager("devbox", "alice")
            assert mgr.connect() is mgr
        m.assert_called_once_with(
            "devbox", "alice", control_path=mgr._control_path,
        )

    def test_connect_remote_failure(self):
        with patch("tmux_manager.manager._remote._validate", return_value=False):
            mgr = TmuxManager("unreachable")
            with pytest.raises(ConnectionError, match="unreachable"):
                mgr.connect()

    def test_connect_chaining(self):
        with patch("tmux_manager.manager._remote._validate", return_value=True):
            with patch("tmux_manager.manager._remote._list_sessions", return_value=["s1"]):
                mgr = TmuxManager("devbox").connect()
                assert mgr.list_sessions() == ["s1"]

    def test_is_available_true(self):
        with patch("tmux_manager.manager._remote._command_available", return_value=True):
            assert TmuxManager("devbox").is_available() is True

    def test_is_available_false(self):
        with patch("tmux_manager.manager._remote._command_available", return_value=False):
            assert TmuxManager("devbox").is_available() is False

    def test_command_available_delegates(self):
        with patch("tmux_manager.manager._remote._command_available", return_value=True) as m:
            mgr = TmuxManager("devbox", "alice")
            result = mgr.command_available("fzf")
        m.assert_called_once_with(
            "devbox", "alice", "fzf", control_path=mgr._control_path,
        )
        assert result is True

    def test_list_sessions_delegates(self):
        with patch("tmux_manager.manager._remote._list_sessions", return_value=["s1"]) as m:
            mgr = TmuxManager("devbox", "alice")
            result = mgr.list_sessions()
        m.assert_called_once_with(
            "devbox", "alice", control_path=mgr._control_path,
        )
        assert result == ["s1"]

    def test_has_session_delegates(self):
        with patch("tmux_manager.manager._remote._list_sessions", return_value=["s1"]):
            assert TmuxManager("devbox").has_session("s1") is True

    def test_new_session_delegates(self):
        with patch("tmux_manager.manager._remote._new_session", return_value=True) as m:
            mgr = TmuxManager("devbox", "alice")
            result = mgr.new_session("work")
        m.assert_called_once_with(
            "devbox", "alice", "work", control_path=mgr._control_path,
        )
        assert result is True

    def test_kill_session_delegates(self):
        with patch("tmux_manager.manager._remote._kill_session", return_value=False) as m:
            mgr = TmuxManager("devbox")
            result = mgr.kill_session("work")
        m.assert_called_once_with(
            "devbox", None, "work", control_path=mgr._control_path,
        )
        assert result is False

    def test_attach_session_delegates(self):
        with patch("tmux_manager.manager._remote._attach_session") as m:
            mgr = TmuxManager("devbox", "alice")
            mgr.attach_session("main")
        m.assert_called_once_with(
            "devbox", "alice", "main", control_path=mgr._control_path,
        )

    def test_no_user_passes_none(self):
        with patch("tmux_manager.manager._remote._list_sessions", return_value=[]) as m:
            mgr = TmuxManager("devbox")
            mgr.list_sessions()
        m.assert_called_once_with(
            "devbox", None, control_path=mgr._control_path,
        )

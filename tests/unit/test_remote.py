"""Unit tests for _remote.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tmux_manager._remote import (
    _attach_session,
    _command_available,
    _kill_session,
    _list_sessions,
    _new_session,
    _ssh_exec,
    _ssh_target,
)


# ── _ssh_target ──────────────────────────────────────────────────────────────


class TestSshTarget:
    def test_with_user(self):
        assert _ssh_target("devbox", "alice") == "alice@devbox"

    def test_without_user(self):
        assert _ssh_target("devbox", None) == "devbox"


# ── _ssh_exec ────────────────────────────────────────────────────────────────


class TestSshExec:
    def test_returns_status_and_stdout(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "hello\n"
        with patch("tmux_manager._remote.subprocess.run", return_value=mock_result) as m:
            status, output = _ssh_exec("devbox", "alice", "echo hello")
        assert status == 0
        assert output == "hello\n"
        m.assert_called_once_with(
            ["ssh", "alice@devbox", "echo hello"],
            capture_output=True,
            text=True,
        )

    def test_returns_nonzero_status(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("tmux_manager._remote.subprocess.run", return_value=mock_result):
            status, output = _ssh_exec("devbox", None, "false")
        assert status == 1
        assert output == ""

    def test_oserror_returns_minus_one(self):
        with patch("tmux_manager._remote.subprocess.run", side_effect=OSError("no ssh")):
            status, output = _ssh_exec("devbox", None, "cmd")
        assert status == -1
        assert output == ""


# ── helper functions ─────────────────────────────────────────────────────────


class TestListSessions:
    def test_returns_names(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "main\nwork\n")):
            assert _list_sessions("devbox", "alice") == ["main", "work"]

    def test_empty_on_failure(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(-1, "")):
            assert _list_sessions("devbox", None) == []

    def test_empty_on_empty_output(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")):
            assert _list_sessions("devbox", None) == []

    def test_filters_blank_lines(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "main\n\nwork\n")):
            assert _list_sessions("devbox", None) == ["main", "work"]


class TestNewSession:
    def test_success(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            assert _new_session("devbox", "alice", "work") is True
        cmd = m.call_args[0][2]
        assert "tmux new-session -d -s work" in cmd

    def test_failure(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert _new_session("devbox", None, "work") is False


class TestKillSession:
    def test_success(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            assert _kill_session("devbox", "alice", "work") is True
        cmd = m.call_args[0][2]
        assert "tmux kill-session -t work" in cmd

    def test_failure(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert _kill_session("devbox", None, "work") is False


class TestCommandAvailable:
    def test_found(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "/usr/bin/tmux\n")):
            assert _command_available("devbox", "alice", "tmux") is True

    def test_not_found(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert _command_available("devbox", None, "tmux") is False


class TestAttachSession:
    def test_calls_ssh_with_tty(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session("devbox", "alice", "work")
        mock_run.assert_called_once_with(
            ["ssh", "-t", "alice@devbox", "tmux attach-session -t work"]
        )

    def test_no_user(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session("devbox", None, "work")
        mock_run.assert_called_once_with(
            ["ssh", "-t", "devbox", "tmux attach-session -t work"]
        )

    def test_shell_quotes_name(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session("devbox", None, "bad'; rm -rf /")
        cmd = mock_run.call_args[0][0][3]
        assert cmd == "tmux attach-session -t 'bad'\"'\"'; rm -rf /'"

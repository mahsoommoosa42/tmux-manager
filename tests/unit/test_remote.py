"""Unit tests for _remote.py."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import paramiko
import pytest

from tmux_manager._remote import (
    _ssh_exec,
    attach_session,
    command_available,
    kill_session,
    list_sessions,
    new_session,
)


def _make_client(exit_status: int = 0, output: bytes = b"") -> MagicMock:
    mock_channel = MagicMock()
    mock_channel.recv_exit_status.return_value = exit_status
    mock_stdout = MagicMock()
    mock_stdout.channel = mock_channel
    mock_stdout.read.return_value = output
    client = MagicMock()
    client.exec_command.return_value = (None, mock_stdout, None)
    return client


class TestSshExec:
    def test_returns_exit_status_and_output(self):
        client = _make_client(0, b"hello\n")
        with patch("tmux_manager._remote.paramiko.SSHClient", return_value=client):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == 0
        assert output == "hello\n"

    def test_ssh_exception_returns_minus_one(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException("err")
        with patch("tmux_manager._remote.paramiko.SSHClient", return_value=client):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_socket_timeout_returns_minus_one(self):
        client = MagicMock()
        client.connect.side_effect = socket.timeout()
        with patch("tmux_manager._remote.paramiko.SSHClient", return_value=client):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_oserror_returns_minus_one(self):
        client = MagicMock()
        client.connect.side_effect = OSError("unreachable")
        with patch("tmux_manager._remote.paramiko.SSHClient", return_value=client):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_client_always_closed(self):
        client = _make_client()
        with patch("tmux_manager._remote.paramiko.SSHClient", return_value=client):
            _ssh_exec("host", None, "cmd")
        client.close.assert_called_once()

    def test_client_closed_on_exception(self):
        client = MagicMock()
        client.connect.side_effect = OSError()
        with patch("tmux_manager._remote.paramiko.SSHClient", return_value=client):
            _ssh_exec("host", None, "cmd")
        client.close.assert_called_once()

    def test_passes_user_and_host_to_connect(self):
        client = _make_client()
        with patch("tmux_manager._remote.paramiko.SSHClient", return_value=client):
            _ssh_exec("myhost", "alice", "cmd")
        kw = client.connect.call_args.kwargs
        assert kw["hostname"] == "myhost"
        assert kw["username"] == "alice"


class TestCommandAvailable:
    def test_found(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")):
            assert command_available("host", None, "tmux") is True

    def test_not_found(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert command_available("host", None, "tmux") is False

    def test_failure_returns_false(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(-1, "")):
            assert command_available("host", None, "tmux") is False

    def test_passes_command_check(self):
        captured = {}

        def capture(host, user, cmd):
            captured["cmd"] = cmd
            return 0, ""

        with patch("tmux_manager._remote._ssh_exec", side_effect=capture):
            command_available("host", None, "fzf")

        assert "fzf" in captured["cmd"]


class TestListSessions:
    def test_returns_session_names(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "main\nwork\n")):
            assert list_sessions("host", None) == ["main", "work"]

    def test_empty_output_returns_empty(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")):
            assert list_sessions("host", None) == []

    def test_nonzero_exit_returns_empty(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert list_sessions("host", None) == []

    def test_failure_returns_empty(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(-1, "")):
            assert list_sessions("host", None) == []

    def test_with_user(self):
        captured = {}

        def capture(host, user, cmd):
            captured["user"] = user
            return 0, "main\n"

        with patch("tmux_manager._remote._ssh_exec", side_effect=capture):
            list_sessions("host", "bob")

        assert captured["user"] == "bob"


class TestNewSession:
    def test_success_returns_true(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")):
            assert new_session("host", None, "work") is True

    def test_failure_returns_false(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert new_session("host", None, "work") is False

    def test_passes_session_name(self):
        captured = {}

        def capture(host, user, cmd):
            captured["cmd"] = cmd
            return 0, ""

        with patch("tmux_manager._remote._ssh_exec", side_effect=capture):
            new_session("host", None, "mysession")

        assert "mysession" in captured["cmd"]


class TestKillSession:
    def test_success_returns_true(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")):
            assert kill_session("host", None, "work") is True

    def test_failure_returns_false(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert kill_session("host", None, "work") is False

    def test_passes_session_name(self):
        captured = {}

        def capture(host, user, cmd):
            captured["cmd"] = cmd
            return 0, ""

        with patch("tmux_manager._remote._ssh_exec", side_effect=capture):
            kill_session("host", None, "mysession")

        assert "mysession" in captured["cmd"]


class TestAttachSession:
    def test_calls_ssh_t(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            attach_session("devbox", None, "main")
        args = mock_run.call_args[0][0]
        assert "ssh" in args
        assert "-t" in args
        assert "devbox" in args

    def test_includes_user(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            attach_session("devbox", "alice", "main")
        args = mock_run.call_args[0][0]
        assert "alice@devbox" in args

    def test_includes_session_name(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            attach_session("devbox", None, "mysession")
        full = " ".join(mock_run.call_args[0][0])
        assert "mysession" in full

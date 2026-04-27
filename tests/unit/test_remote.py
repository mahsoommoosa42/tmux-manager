"""Unit tests for _remote.py."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import paramiko
import pytest

from tmux_manager._remote import (
    _load_ssh_config,
    _password_cache,
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


class TestLoadSshConfig:
    def test_returns_empty_when_no_config_file(self, tmp_path):
        with patch("tmux_manager._remote.Path.home", return_value=tmp_path):
            result = _load_ssh_config("devbox", None)
        assert result == {}

    def test_resolves_hostname_alias(self, tmp_path):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "config").write_text(
            "Host devbox\n    HostName 192.168.1.10\n", encoding="utf-8"
        )
        with patch("tmux_manager._remote.Path.home", return_value=tmp_path):
            result = _load_ssh_config("devbox", None)
        assert result["hostname"] == "192.168.1.10"

    def test_resolves_user_from_config(self, tmp_path):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "config").write_text(
            "Host devbox\n    User alice\n", encoding="utf-8"
        )
        with patch("tmux_manager._remote.Path.home", return_value=tmp_path):
            result = _load_ssh_config("devbox", None)
        assert result["username"] == "alice"

    def test_explicit_user_overrides_config(self, tmp_path):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "config").write_text(
            "Host devbox\n    User config-user\n", encoding="utf-8"
        )
        with patch("tmux_manager._remote.Path.home", return_value=tmp_path):
            result = _load_ssh_config("devbox", "explicit-user")
        assert result["username"] == "explicit-user"

    def test_resolves_port(self, tmp_path):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "config").write_text(
            "Host devbox\n    Port 2222\n", encoding="utf-8"
        )
        with patch("tmux_manager._remote.Path.home", return_value=tmp_path):
            result = _load_ssh_config("devbox", None)
        assert result["port"] == 2222

    def test_resolves_identity_file(self, tmp_path):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "config").write_text(
            "Host devbox\n    IdentityFile ~/.ssh/id_ed25519\n", encoding="utf-8"
        )
        with patch("tmux_manager._remote.Path.home", return_value=tmp_path):
            result = _load_ssh_config("devbox", None)
        assert "key_filename" in result


NO_CONFIG = {}  # empty SSH config for tests that don't need alias resolution


class TestSshExec:
    def setup_method(self):
        _password_cache.clear()

    def teardown_method(self):
        _password_cache.clear()

    def test_returns_exit_status_and_output(self):
        client = _make_client(0, b"hello\n")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == 0
        assert output == "hello\n"

    def test_ssh_exception_returns_minus_one(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException("err")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_socket_timeout_returns_minus_one(self):
        client = MagicMock()
        client.connect.side_effect = socket.timeout()
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_oserror_returns_minus_one(self):
        client = MagicMock()
        client.connect.side_effect = OSError("unreachable")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_client_always_closed(self):
        client = _make_client()
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            _ssh_exec("host", None, "cmd")
        client.close.assert_called_once()

    def test_client_closed_on_exception(self):
        client = MagicMock()
        client.connect.side_effect = OSError()
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            _ssh_exec("host", None, "cmd")
        client.close.assert_called_once()

    def test_passes_host_and_user_to_connect(self):
        client = _make_client()
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            _ssh_exec("myhost", "alice", "cmd")
        kw = client.connect.call_args.kwargs
        assert kw["hostname"] == "myhost"
        assert kw["username"] == "alice"

    def test_ssh_config_alias_resolves_hostname(self):
        client = _make_client()
        resolved = {"hostname": "192.168.1.10", "username": "alice", "port": 22}
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=resolved),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            _ssh_exec("devbox", None, "cmd")
        kw = client.connect.call_args.kwargs
        assert kw["hostname"] == "192.168.1.10"
        assert kw["username"] == "alice"


class TestPasswordAuth:
    def setup_method(self):
        _password_cache.clear()

    def teardown_method(self):
        _password_cache.clear()

    def test_password_fallback_on_auth_failure(self):
        client = _make_client(0, b"ok\n")
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="secret"),
        ):
            status, output = _ssh_exec("host", "alice", "cmd")
        assert status == 0
        assert output == "ok\n"
        assert client.connect.call_count == 2
        assert client.connect.call_args.kwargs["password"] == "secret"

    def test_password_cached_after_success(self):
        client = _make_client(0, b"ok\n")
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="secret"),
        ):
            _ssh_exec("host", "alice", "cmd")
        assert ("host", "alice") in _password_cache
        assert _password_cache[("host", "alice")] == "secret"

    def test_cached_password_used_on_second_call(self):
        _password_cache[("host", "alice")] = "cached-pw"
        client = _make_client(0, b"ok\n")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            status, output = _ssh_exec("host", "alice", "cmd")
        assert status == 0
        kw = client.connect.call_args.kwargs
        assert kw["password"] == "cached-pw"
        assert client.connect.call_count == 1

    def test_password_prompt_shows_host_and_user(self):
        client = _make_client(0, b"ok\n")
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="pw") as mock_gp,
        ):
            _ssh_exec("myhost", "bob", "cmd")
        mock_gp.assert_called_once_with("Password for bob@myhost: ")

    def test_password_prompt_with_no_user(self):
        client = _make_client(0, b"ok\n")
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="pw") as mock_gp,
        ):
            _ssh_exec("myhost", None, "cmd")
        mock_gp.assert_called_once_with("Password for myhost: ")

    def test_password_auth_also_fails_returns_minus_one(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.AuthenticationException("denied")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="wrong"),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_cached_password_auth_fails_evicts_cache(self):
        _password_cache[("host", None)] = "stale-pw"
        client = MagicMock()
        client.connect.side_effect = paramiko.AuthenticationException("denied")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""
        assert ("host", None) not in _password_cache


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

    def test_passes_correct_command_string(self):
        captured = {}

        def capture(host, user, cmd):
            captured["cmd"] = cmd
            return 0, ""

        with patch("tmux_manager._remote._ssh_exec", side_effect=capture):
            command_available("host", None, "fzf")

        assert "fzf" in captured["cmd"]

    def test_shell_quotes_command_name(self):
        captured = {}

        def capture(host, user, cmd):
            captured["cmd"] = cmd
            return 0, ""

        with patch("tmux_manager._remote._ssh_exec", side_effect=capture):
            command_available("host", None, "bad;rm -rf /")

        assert captured["cmd"] == "command -v 'bad;rm -rf /'"


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

    def test_shell_quotes_session_name(self):
        captured = {}

        def capture(host, user, cmd):
            captured["cmd"] = cmd
            return 0, ""

        with patch("tmux_manager._remote._ssh_exec", side_effect=capture):
            new_session("host", None, "bad'; rm -rf /")

        assert captured["cmd"] == "tmux new-session -d -s 'bad'\"'\"'; rm -rf /'"


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

    def test_shell_quotes_session_name(self):
        captured = {}

        def capture(host, user, cmd):
            captured["cmd"] = cmd
            return 0, ""

        with patch("tmux_manager._remote._ssh_exec", side_effect=capture):
            kill_session("host", None, "bad'; rm -rf /")

        assert captured["cmd"] == "tmux kill-session -t 'bad'\"'\"'; rm -rf /'"


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

    def test_shell_quotes_session_name(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            attach_session("devbox", None, "bad'; rm -rf /")
        tmux_cmd = mock_run.call_args[0][0][-1]
        assert tmux_cmd == "tmux attach-session -t 'bad'\"'\"'; rm -rf /'"

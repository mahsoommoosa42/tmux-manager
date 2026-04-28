"""Unit tests for _remote.py."""

from __future__ import annotations

import contextlib
import socket
from unittest.mock import MagicMock, patch

import paramiko
import pytest

from tmux_manager._remote import (
    _SSHConnection,
    _attach_session_conn,
    _command_available_conn,
    _kill_session_conn,
    _list_sessions_conn,
    _load_ssh_config,
    _new_session_conn,
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

    def test_uses_reject_policy(self):
        client = _make_client()
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            _ssh_exec("host", None, "cmd")
        client.set_missing_host_key_policy.assert_called_once()
        policy = client.set_missing_host_key_policy.call_args[0][0]
        assert isinstance(policy, paramiko.RejectPolicy)

    def test_unknown_host_prints_known_hosts_hint(self, capsys):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException(
            "Server 'myhost' not found in known_hosts"
        )
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            status, output = _ssh_exec("myhost", None, "cmd")
        assert status == -1
        err = capsys.readouterr().err
        assert "myhost" in err
        assert "known_hosts" in err

    def test_other_ssh_exception_no_hint(self, capsys):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException("auth failed")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            _ssh_exec("host", None, "cmd")
        err = capsys.readouterr().err
        assert err == ""

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
    def test_password_fallback_on_auth_failure(self):
        client = _make_client(0, b"ok\n")
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="secret"),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            status, output = _ssh_exec("host", "alice", "cmd")
        assert status == 0
        assert output == "ok\n"
        assert client.connect.call_count == 2
        retry_kw = client.connect.call_args.kwargs
        assert retry_kw["password"] == "secret"
        assert retry_kw["look_for_keys"] is False
        assert retry_kw["allow_agent"] is False

    def test_password_prompt_shows_host_and_user(self):
        client = _make_client(0, b"ok\n")
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="pw") as mock_gp,
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
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
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="pw") as mock_gp,
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            _ssh_exec("myhost", None, "cmd")
        mock_gp.assert_called_once_with("Password for myhost: ")

    def test_password_auth_also_fails_returns_minus_one(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.AuthenticationException("denied")
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="wrong"),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_no_prompt_when_not_tty(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.AuthenticationException("denied")
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_no_prompt_when_stdin_is_none(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.AuthenticationException("denied")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.sys.stdin", None),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_no_auth_methods_prompts_for_password(self):
        client = _make_client(0, b"ok\n")
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.SSHException("No authentication methods available")

        client.connect.side_effect = connect_side_effect
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="pw"),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            status, output = _ssh_exec("host", "user", "cmd")
        assert status == 0
        assert output == "ok\n"

    def test_no_auth_methods_no_prompt_when_not_tty(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException(
            "No authentication methods available"
        )
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

    def test_non_auth_ssh_exception_not_caught(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException("Incompatible protocol")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            status, output = _ssh_exec("host", None, "cmd")
        assert status == -1
        assert output == ""

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


# ── _SSHConnection tests ─────────────────────────────────────────────────────

NO_SSH_CONFIG = {}


@contextlib.contextmanager
def _patch_conn_open(client):
    """Context manager that lets _SSHConnection.__init__ succeed with *client*."""
    with (
        patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
        patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
    ):
        yield


class TestSSHConnectionInternal:
    def test_connect_creates_client_and_connects(self):
        client = _make_client()
        with _patch_conn_open(client):
            conn = _SSHConnection("myhost", "alice")
        client.connect.assert_called_once()
        kw = client.connect.call_args.kwargs
        assert kw["hostname"] == "myhost"
        assert kw["username"] == "alice"
        assert kw["port"] == 22
        assert kw["timeout"] == 5
        assert kw["look_for_keys"] is True
        assert kw["allow_agent"] is True
        conn.close()

    def test_connect_uses_reject_policy(self):
        client = _make_client()
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        args = client.set_missing_host_key_policy.call_args[0]
        assert isinstance(args[0], paramiko.RejectPolicy)
        conn.close()

    def test_connect_loads_ssh_config(self):
        client = _make_client()
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG) as m_cfg,
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
        ):
            conn = _SSHConnection("devbox", "alice")
        m_cfg.assert_called_once_with("devbox", "alice")
        conn.close()

    def test_close_calls_client_close(self):
        client = _make_client()
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        conn.close()
        client.close.assert_called_once()

    def test_close_idempotent(self):
        client = _make_client()
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        conn.close()
        conn.close()
        client.close.assert_called_once()

    def test_close_when_no_client(self):
        client = _make_client()
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        conn._client = None
        conn.close()

    def test_is_connected_true(self):
        client = _make_client()
        transport = MagicMock()
        transport.is_active.return_value = True
        client.get_transport.return_value = transport
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        assert conn.is_connected is True
        conn.close()

    def test_is_connected_false_no_client(self):
        client = _make_client()
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        conn._client = None
        assert conn.is_connected is False

    def test_is_connected_false_no_transport(self):
        client = _make_client()
        client.get_transport.return_value = None
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        assert conn.is_connected is False
        conn.close()

    def test_is_connected_false_inactive_transport(self):
        client = _make_client()
        transport = MagicMock()
        transport.is_active.return_value = False
        client.get_transport.return_value = transport
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        assert conn.is_connected is False
        conn.close()

    def test_exec_returns_status_and_output(self):
        client = _make_client(0, b"hello\n")
        transport = MagicMock()
        transport.is_active.return_value = True
        client.get_transport.return_value = transport
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        status, output = conn.exec("echo hello")
        assert status == 0
        assert output == "hello\n"
        conn.close()

    def test_exec_returns_minus_one_when_not_connected(self):
        client = _make_client()
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        conn._client = None
        status, output = conn.exec("cmd")
        assert status == -1
        assert output == ""

    def test_exec_catches_ssh_exception(self):
        client = _make_client()
        transport = MagicMock()
        transport.is_active.return_value = True
        client.get_transport.return_value = transport
        client.exec_command.side_effect = paramiko.SSHException("err")
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        status, output = conn.exec("cmd")
        assert status == -1
        assert output == ""
        conn.close()

    def test_exec_catches_socket_timeout(self):
        client = _make_client()
        transport = MagicMock()
        transport.is_active.return_value = True
        client.get_transport.return_value = transport
        client.exec_command.side_effect = socket.timeout()
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        status, output = conn.exec("cmd")
        assert status == -1
        assert output == ""
        conn.close()

    def test_exec_catches_oserror(self):
        client = _make_client()
        transport = MagicMock()
        transport.is_active.return_value = True
        client.get_transport.return_value = transport
        client.exec_command.side_effect = OSError("broken")
        with _patch_conn_open(client):
            conn = _SSHConnection("host", None)
        status, output = conn.exec("cmd")
        assert status == -1
        assert output == ""
        conn.close()

    def test_connect_failure_propagates(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException("Incompatible protocol")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            pytest.raises(paramiko.SSHException, match="Incompatible protocol"),
        ):
            _SSHConnection("host", None)

    def test_connect_failure_closes_client(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException("Incompatible protocol")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            pytest.raises(paramiko.SSHException),
        ):
            _SSHConnection("host", None)
        client.close.assert_called_once()

    def test_connect_known_hosts_hint(self, capsys):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException(
            "Server 'mybox' not found in known_hosts"
        )
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            pytest.raises(paramiko.SSHException),
        ):
            _SSHConnection("mybox", None)
        captured = capsys.readouterr()
        assert "not in ~/.ssh/known_hosts" in captured.err
        assert "Connect once via 'ssh' CLI" in captured.err

    def test_password_retry_failure_closes_client(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.AuthenticationException("denied")
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="wrong"),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
            pytest.raises(paramiko.AuthenticationException),
        ):
            _SSHConnection("host", None)
        client.close.assert_called_once()

    def test_password_fallback_on_auth_failure(self):
        client = _make_client()
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="secret"),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            conn = _SSHConnection("host", "alice")
        assert client.connect.call_count == 2
        retry_kw = client.connect.call_args.kwargs
        assert retry_kw["password"] == "secret"
        assert retry_kw["look_for_keys"] is False
        assert retry_kw["allow_agent"] is False
        conn.close()

    def test_password_prompt_shows_host_and_user(self):
        client = _make_client()
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="pw") as mock_gp,
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            conn = _SSHConnection("myhost", "bob")
        mock_gp.assert_called_once_with("Password for bob@myhost: ")
        conn.close()

    def test_password_prompt_with_no_user(self):
        client = _make_client()
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="pw") as mock_gp,
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            conn = _SSHConnection("myhost", None)
        mock_gp.assert_called_once_with("Password for myhost: ")
        conn.close()

    def test_password_auth_also_fails_propagates(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.AuthenticationException("denied")
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="wrong"),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
            pytest.raises(paramiko.AuthenticationException),
        ):
            _SSHConnection("host", None)

    def test_no_prompt_when_not_tty(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.AuthenticationException("denied")
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
            pytest.raises(paramiko.AuthenticationException),
        ):
            _SSHConnection("host", None)

    def test_no_prompt_when_stdin_is_none(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.AuthenticationException("denied")
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.sys.stdin", None),
            pytest.raises(paramiko.AuthenticationException),
        ):
            _SSHConnection("host", None)

    def test_no_auth_methods_prompts_for_password(self):
        client = _make_client()
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.SSHException("No authentication methods available")

        client.connect.side_effect = connect_side_effect
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="pw"),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            conn = _SSHConnection("host", "user")
        assert client.connect.call_count == 2
        conn.close()

    def test_no_auth_methods_no_prompt_when_not_tty(self):
        client = MagicMock()
        client.connect.side_effect = paramiko.SSHException(
            "No authentication methods available"
        )
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
            pytest.raises(paramiko.SSHException),
        ):
            _SSHConnection("host", None)

    def test_password_retry_disables_key_auth(self):
        client = _make_client()
        call_count = 0

        def connect_side_effect(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and "password" not in kw:
                raise paramiko.AuthenticationException("key auth failed")

        client.connect.side_effect = connect_side_effect
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            patch("tmux_manager._remote._load_ssh_config", return_value=NO_SSH_CONFIG),
            patch("tmux_manager._remote.paramiko.SSHClient", return_value=client),
            patch("tmux_manager._remote.getpass.getpass", return_value="pw"),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            conn = _SSHConnection("host", "user")
        retry_kw = client.connect.call_args.kwargs
        assert retry_kw["look_for_keys"] is False
        assert retry_kw["allow_agent"] is False
        conn.close()


# ── _*_conn helper tests ─────────────────────────────────────────────────────


class TestConnHelpers:
    def test_list_sessions_conn_returns_names(self):
        conn = MagicMock()
        conn.exec.return_value = (0, "main\nwork\n")
        assert _list_sessions_conn(conn) == ["main", "work"]

    def test_list_sessions_conn_empty_on_failure(self):
        conn = MagicMock()
        conn.exec.return_value = (-1, "")
        assert _list_sessions_conn(conn) == []

    def test_list_sessions_conn_empty_on_empty_output(self):
        conn = MagicMock()
        conn.exec.return_value = (0, "")
        assert _list_sessions_conn(conn) == []

    def test_new_session_conn_success(self):
        conn = MagicMock()
        conn.exec.return_value = (0, "")
        assert _new_session_conn(conn, "work") is True

    def test_new_session_conn_failure(self):
        conn = MagicMock()
        conn.exec.return_value = (1, "")
        assert _new_session_conn(conn, "work") is False

    def test_kill_session_conn_success(self):
        conn = MagicMock()
        conn.exec.return_value = (0, "")
        assert _kill_session_conn(conn, "work") is True

    def test_kill_session_conn_failure(self):
        conn = MagicMock()
        conn.exec.return_value = (1, "")
        assert _kill_session_conn(conn, "work") is False

    def test_command_available_conn_found(self):
        conn = MagicMock()
        conn.exec.return_value = (0, "/usr/bin/tmux\n")
        assert _command_available_conn(conn, "tmux") is True

    def test_command_available_conn_not_found(self):
        conn = MagicMock()
        conn.exec.return_value = (1, "")
        assert _command_available_conn(conn, "tmux") is False

    def test_attach_session_conn_not_connected(self):
        conn = MagicMock()
        conn.is_connected = False
        _attach_session_conn(conn, "work")
        conn._client.get_transport.assert_not_called()

    def test_attach_session_conn_no_transport(self):
        conn = MagicMock()
        conn.is_connected = True
        conn._client.get_transport.return_value = None
        _attach_session_conn(conn, "work")

    def test_attach_session_conn_opens_pty_and_forwards(self):
        channel = MagicMock()
        channel.recv.side_effect = [b"hello", b""]
        transport = MagicMock()
        transport.open_session.return_value = channel
        conn = MagicMock()
        conn.is_connected = True
        conn._client.get_transport.return_value = transport
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        with (
            patch("tmux_manager._remote.os.get_terminal_size", return_value=(40, 120)),
            patch("tmux_manager._remote.termios.tcgetattr", return_value=[]),
            patch("tmux_manager._remote.tty.setraw"),
            patch("tmux_manager._remote.termios.tcsetattr"),
            patch(
                "tmux_manager._remote.select.select",
                side_effect=[([channel], [], []), ([channel], [], [])],
            ),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
            patch("tmux_manager._remote.sys.stdout", mock_stdout),
        ):
            _attach_session_conn(conn, "work")
        channel.get_pty.assert_called_once_with(width=120, height=40)
        channel.exec_command.assert_called_once_with("tmux attach-session -t work")
        mock_stdout.buffer.write.assert_called_once_with(b"hello")
        mock_stdout.buffer.flush.assert_called_once()
        channel.close.assert_called_once()

    def test_attach_session_conn_fallback_terminal_size(self):
        channel = MagicMock()
        channel.recv.return_value = b""
        transport = MagicMock()
        transport.open_session.return_value = channel
        conn = MagicMock()
        conn.is_connected = True
        conn._client.get_transport.return_value = transport
        mock_stdin = MagicMock()
        with (
            patch("tmux_manager._remote.os.get_terminal_size", side_effect=OSError),
            patch("tmux_manager._remote.termios.tcgetattr", return_value=[]),
            patch("tmux_manager._remote.tty.setraw"),
            patch("tmux_manager._remote.termios.tcsetattr"),
            patch("tmux_manager._remote.select.select", return_value=([channel], [], [])),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            _attach_session_conn(conn, "work")
        channel.get_pty.assert_called_once_with(width=80, height=24)

    def test_attach_session_conn_stdin_forwarding(self):
        channel = MagicMock()
        transport = MagicMock()
        transport.open_session.return_value = channel
        conn = MagicMock()
        conn.is_connected = True
        conn._client.get_transport.return_value = transport
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        with (
            patch("tmux_manager._remote.os.get_terminal_size", return_value=(25, 80)),
            patch("tmux_manager._remote.termios.tcgetattr", return_value=[]),
            patch("tmux_manager._remote.tty.setraw"),
            patch("tmux_manager._remote.termios.tcsetattr"),
            patch(
                "tmux_manager._remote.select.select",
                side_effect=[([mock_stdin], [], []), ([mock_stdin], [], [])],
            ),
            patch("tmux_manager._remote.os.read", side_effect=[b"q", b""]),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
            patch("tmux_manager._remote.sys.stdout", mock_stdout),
        ):
            _attach_session_conn(conn, "work")
        channel.send.assert_called_once_with(b"q")
        channel.close.assert_called_once()

    def test_attach_session_conn_restores_tty_on_error(self):
        channel = MagicMock()
        transport = MagicMock()
        transport.open_session.return_value = channel
        conn = MagicMock()
        conn.is_connected = True
        conn._client.get_transport.return_value = transport
        mock_stdin = MagicMock()
        saved_attrs = [1, 2, 3]
        with (
            patch("tmux_manager._remote.os.get_terminal_size", return_value=(25, 80)),
            patch("tmux_manager._remote.termios.tcgetattr", return_value=saved_attrs),
            patch("tmux_manager._remote.tty.setraw", side_effect=OSError("bad")),
            patch("tmux_manager._remote.termios.tcsetattr") as mock_restore,
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
            pytest.raises(OSError, match="bad"),
        ):
            _attach_session_conn(conn, "work")
        mock_restore.assert_called_once()
        channel.close.assert_called_once()

    def test_attach_session_conn_shell_quotes_name(self):
        channel = MagicMock()
        channel.recv.return_value = b""
        transport = MagicMock()
        transport.open_session.return_value = channel
        conn = MagicMock()
        conn.is_connected = True
        conn._client.get_transport.return_value = transport
        mock_stdin = MagicMock()
        with (
            patch("tmux_manager._remote.os.get_terminal_size", return_value=(25, 80)),
            patch("tmux_manager._remote.termios.tcgetattr", return_value=[]),
            patch("tmux_manager._remote.tty.setraw"),
            patch("tmux_manager._remote.termios.tcsetattr"),
            patch("tmux_manager._remote.select.select", return_value=([channel], [], [])),
            patch("tmux_manager._remote.sys.stdin", mock_stdin),
        ):
            _attach_session_conn(conn, "bad'; rm -rf /")
        cmd = channel.exec_command.call_args[0][0]
        assert cmd == "tmux attach-session -t 'bad'\"'\"'; rm -rf /'"

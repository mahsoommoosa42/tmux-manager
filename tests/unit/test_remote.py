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
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session_conn(conn, "work")
        mock_run.assert_not_called()

    def test_attach_session_conn_with_user(self):
        conn = MagicMock()
        conn.is_connected = True
        conn._host = "devbox"
        conn._user = "alice"
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session_conn(conn, "work")
        mock_run.assert_called_once_with(
            ["ssh", "-t", "alice@devbox", "tmux attach-session -t work"]
        )

    def test_attach_session_conn_no_user(self):
        conn = MagicMock()
        conn.is_connected = True
        conn._host = "devbox"
        conn._user = None
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session_conn(conn, "work")
        mock_run.assert_called_once_with(
            ["ssh", "-t", "devbox", "tmux attach-session -t work"]
        )

    def test_attach_session_conn_shell_quotes_name(self):
        conn = MagicMock()
        conn.is_connected = True
        conn._host = "devbox"
        conn._user = None
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session_conn(conn, "bad'; rm -rf /")
        cmd = mock_run.call_args[0][0][3]
        assert cmd == "tmux attach-session -t 'bad'\"'\"'; rm -rf /'"

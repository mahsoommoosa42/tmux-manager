"""Remote tmux operations via paramiko SSH."""

from __future__ import annotations

import getpass
import os
import shlex
import socket
import subprocess
import sys
from pathlib import Path

import paramiko

def _load_ssh_config(host: str, user: str | None) -> dict:
    """Read ~/.ssh/config and resolve connect kwargs for *host*.

    Returns a dict with keys that may include: hostname, username,
    key_filename, port. Unset values are omitted so paramiko uses
    its own defaults.
    """
    config_path = Path.home() / ".ssh" / "config"
    if not config_path.exists():
        return {}

    cfg = paramiko.SSHConfig()
    with config_path.open(encoding="utf-8") as fh:
        cfg.parse(fh)
    host_cfg = cfg.lookup(host)

    kwargs: dict = {"hostname": host_cfg.get("hostname", host)}
    # Explicit user arg overrides SSH config
    if user is not None:
        kwargs["username"] = user
    elif "user" in host_cfg:
        kwargs["username"] = host_cfg["user"]
    if "identityfile" in host_cfg:
        kwargs["key_filename"] = host_cfg["identityfile"]
    if "port" in host_cfg:
        kwargs["port"] = int(host_cfg["port"])
    return kwargs



# ── Persistent connection (internal) ─────────────────────────────────────────


class _SSHConnection:
    """Persistent SSH connection to a remote host.

    Internal — not part of the public API.
    """

    def __init__(self, host: str, user: str | None) -> None:
        self._host = host
        self._user = user
        self._client: paramiko.SSHClient | None = None
        self._open()

    @property
    def is_connected(self) -> bool:
        if self._client is None:
            return False
        transport = self._client.get_transport()
        return transport is not None and transport.is_active()

    def _open(self) -> None:
        """Open the SSH connection. Called once from __init__.

        Mirrors the auth logic of ``_ssh_exec``: tries key-based auth first,
        then falls back to password prompt when stdin is a TTY.
        """
        ssh_cfg = _load_ssh_config(self._host, self._user)
        connect_kw = {
            "hostname": ssh_cfg.get("hostname", self._host),
            "username": ssh_cfg.get("username", self._user),
            "port": ssh_cfg.get("port", 22),
            "key_filename": ssh_cfg.get("key_filename") or None,
            "timeout": 5,
        }
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            try:
                client.connect(
                    **connect_kw,
                    look_for_keys=True,
                    allow_agent=True,
                )
            except paramiko.SSHException as exc:
                is_auth_failure = isinstance(
                    exc, paramiko.AuthenticationException
                ) or "no authentication methods" in str(exc).lower()
                if not is_auth_failure or not (sys.stdin is not None and sys.stdin.isatty()):
                    raise
                display_host = connect_kw["hostname"]
                display_user = connect_kw["username"]
                display_target = f"{display_user}@{display_host}" if display_user else display_host
                prompt = f"Password for {display_target}: "
                password = getpass.getpass(prompt)
                client.connect(**connect_kw, password=password, look_for_keys=False, allow_agent=False)
        except BaseException as exc:
            client.close()
            if "not found in known_hosts" in str(exc):
                print(
                    f"Host '{self._host}' is not in ~/.ssh/known_hosts. "
                    "Connect once via 'ssh' CLI to add it.",
                    file=sys.stderr,
                )
            raise
        self._client = client

    def close(self) -> None:
        """Close the SSH connection if open. Safe to call multiple times."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def exec(self, command: str) -> tuple[int, str]:
        """Execute command over the persistent connection.
        Returns (exit_status, stdout_text). Returns (-1, "") on failure.
        """
        if not self.is_connected:
            return -1, ""
        try:
            _, stdout, _ = self._client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode()
            return exit_status, output
        except (paramiko.SSHException, socket.timeout, OSError):
            return -1, ""


def _list_sessions_conn(conn: _SSHConnection) -> list[str]:
    exit_status, output = conn.exec(
        "tmux list-sessions -F '#{session_name}' 2>/dev/null"
    )
    if exit_status != 0 or not output.strip():
        return []
    return [s for s in output.strip().splitlines() if s]


def _new_session_conn(conn: _SSHConnection, name: str) -> bool:
    exit_status, _ = conn.exec(f"tmux new-session -d -s {shlex.quote(name)}")
    return exit_status == 0


def _kill_session_conn(conn: _SSHConnection, name: str) -> bool:
    exit_status, _ = conn.exec(f"tmux kill-session -t {shlex.quote(name)}")
    return exit_status == 0


def _command_available_conn(conn: _SSHConnection, cmd: str) -> bool:
    exit_status, _ = conn.exec(f"command -v {shlex.quote(cmd)}")
    return exit_status == 0


def _attach_session_conn(conn: _SSHConnection, name: str) -> None:
    """Attach to a tmux session over the persistent SSH connection with PTY."""
    if not conn.is_connected:
        return
    transport = conn._client.get_transport()
    if transport is None:
        return

    if sys.platform == "win32":
        _attach_session_subprocess(conn, name)
    else:
        _attach_session_pty(transport, name)


def _attach_session_subprocess(conn: _SSHConnection, name: str) -> None:
    """Attach via system ssh on Windows (termios/tty unavailable)."""
    target = f"{conn._user}@{conn._host}" if conn._user else conn._host
    subprocess.run(
        ["ssh", "-t", target, f"tmux attach-session -t {shlex.quote(name)}"]
    )


def _attach_session_pty(transport, name: str) -> None:
    """Attach via paramiko PTY with raw terminal I/O (Unix)."""
    import select
    import termios
    import tty

    channel = transport.open_session()
    oldtty = None
    try:
        try:
            cols, rows = os.get_terminal_size()
        except OSError:
            cols, rows = 80, 24
        channel.get_pty(width=cols, height=rows)
        channel.exec_command(f"tmux attach-session -t {shlex.quote(name)}")
        oldtty = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())
        channel.setblocking(0)
        while True:
            r, _, _ = select.select([channel, sys.stdin], [], [])
            if channel in r:
                data = channel.recv(1024)
                if len(data) == 0:
                    break
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            if sys.stdin in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if len(data) == 0:
                    break
                channel.send(data)
    finally:
        if oldtty is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)
        channel.close()

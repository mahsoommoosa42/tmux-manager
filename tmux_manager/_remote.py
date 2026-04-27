"""Remote tmux operations via paramiko SSH."""

from __future__ import annotations

import os
import select
import shlex
import socket
import sys
import threading
from pathlib import Path

import paramiko

try:
    import termios
    import tty
except ImportError:  # pragma: no cover
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]


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
    if "proxycommand" in host_cfg:
        kwargs["sock"] = paramiko.ProxyCommand(host_cfg["proxycommand"])
    return kwargs


def _ssh_exec(host: str, user: str | None, command: str) -> tuple[int, str]:
    """Execute *command* on *host* via paramiko; return (exit_status, stdout).

    Reads ~/.ssh/config so SSH aliases, custom ports, and identity files
    are respected automatically.
    Returns (-1, "") on any connection, auth, or network failure.
    """
    ssh_cfg = _load_ssh_config(host, user)

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_kwargs: dict = {
            "hostname": ssh_cfg.get("hostname", host),
            "username": ssh_cfg.get("username", user),
            "port": ssh_cfg.get("port", 22),
            "key_filename": ssh_cfg.get("key_filename") or None,
            "timeout": 5,
            "look_for_keys": True,
            "allow_agent": True,
        }
        if "sock" in ssh_cfg:
            connect_kwargs["sock"] = ssh_cfg["sock"]
        client.connect(**connect_kwargs)
        _, stdout, _ = client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode()
        return exit_status, output
    except (paramiko.SSHException, socket.timeout, OSError):
        return -1, ""
    finally:
        client.close()


def command_available(host: str, user: str | None, cmd: str) -> bool:
    """Return True if *cmd* is on PATH on *host*."""
    exit_status, _ = _ssh_exec(host, user, f"command -v {shlex.quote(cmd)}")
    return exit_status == 0


def list_sessions(host: str, user: str | None) -> list[str]:
    """Return tmux session names on *host*, or [] if none/unreachable."""
    exit_status, output = _ssh_exec(
        host, user, "tmux list-sessions -F '#{session_name}' 2>/dev/null"
    )
    if exit_status != 0 or not output.strip():
        return []
    return [s for s in output.strip().splitlines() if s]


def new_session(host: str, user: str | None, name: str) -> bool:
    """Create a new detached tmux session on *host*. True on success."""
    exit_status, _ = _ssh_exec(host, user, f"tmux new-session -d -s {shlex.quote(name)}")
    return exit_status == 0


def kill_session(host: str, user: str | None, name: str) -> bool:
    """Kill the named tmux session on *host*. True on success."""
    exit_status, _ = _ssh_exec(host, user, f"tmux kill-session -t {shlex.quote(name)}")
    return exit_status == 0


def _ssh_interactive(host: str, user: str | None, command: str | None = None) -> None:
    """Open an interactive paramiko session to *host* with PTY forwarding.

    If *command* is given it is executed in the remote PTY; otherwise an
    interactive login shell is opened.
    """
    ssh_cfg = _load_ssh_config(host, user)
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_kwargs: dict = {
            "hostname": ssh_cfg.get("hostname", host),
            "username": ssh_cfg.get("username", user),
            "port": ssh_cfg.get("port", 22),
            "key_filename": ssh_cfg.get("key_filename") or None,
            "timeout": 5,
            "look_for_keys": True,
            "allow_agent": True,
        }
        if "sock" in ssh_cfg:
            connect_kwargs["sock"] = ssh_cfg["sock"]
        client.connect(**connect_kwargs)
        channel = client.get_transport().open_session()
        channel.get_pty()
        if command:
            channel.exec_command(command)
        else:
            channel.invoke_shell()
        _forward_io(channel)
    except (paramiko.SSHException, socket.timeout, OSError):
        return
    finally:
        client.close()


def _forward_io(channel: paramiko.Channel) -> None:
    """Forward stdin/stdout between the local terminal and *channel*."""
    if os.name == "posix":
        _forward_posix(channel)
    else:
        _forward_windows(channel)


def _forward_posix(channel: paramiko.Channel) -> None:  # pragma: no cover
    """POSIX I/O forwarding using termios raw mode and select."""
    oldtty = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
        channel.settimeout(0.0)

        while True:
            r, _, _ = select.select([channel, sys.stdin], [], [])
            if channel in r:
                data = channel.recv(1024)
                if not data:
                    break
                sys.stdout.buffer.write(data)
                sys.stdout.flush()
            if sys.stdin in r:
                data = sys.stdin.buffer.read(1)
                if not data:
                    break
                channel.send(data)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)


def _forward_windows(channel: paramiko.Channel) -> None:
    """Windows I/O forwarding using threads."""
    done = threading.Event()

    def _reader() -> None:
        try:
            while True:
                data = channel.recv(1024)
                if not data:
                    break
                sys.stdout.buffer.write(data)
                sys.stdout.flush()
        except (socket.timeout, OSError, EOFError):
            pass
        finally:
            done.set()

    def _writer() -> None:
        try:
            while not done.is_set():
                data = sys.stdin.buffer.read(1)
                if not data:
                    break
                channel.send(data)
        except (OSError, EOFError):
            pass
        finally:
            done.set()

    reader = threading.Thread(target=_reader, daemon=True)
    writer = threading.Thread(target=_writer, daemon=True)
    reader.start()
    writer.start()
    done.wait()
    reader.join(timeout=2)
    writer.join(timeout=2)


def attach_session(host: str, user: str | None, name: str) -> None:
    """Attach to *name* on *host* via paramiko interactive PTY."""
    _ssh_interactive(host, user, f"tmux attach-session -t {shlex.quote(name)}")


def open_shell(host: str, user: str | None) -> None:
    """Open an interactive SSH shell on *host* via paramiko."""
    _ssh_interactive(host, user)

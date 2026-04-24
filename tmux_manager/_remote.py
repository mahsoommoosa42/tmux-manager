"""Remote tmux operations via paramiko SSH."""

from __future__ import annotations

import socket
import subprocess

import paramiko


def _ssh_exec(host: str, user: str | None, command: str) -> tuple[int, str]:
    """Execute *command* on *host* via paramiko; return (exit_status, stdout).

    Returns (-1, "") on any connection, auth, or network failure.
    """
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            username=user,
            timeout=5,
            look_for_keys=True,
            allow_agent=True,
        )
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
    exit_status, _ = _ssh_exec(host, user, f"command -v {cmd}")
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
    exit_status, _ = _ssh_exec(host, user, f"tmux new-session -d -s '{name}'")
    return exit_status == 0


def kill_session(host: str, user: str | None, name: str) -> bool:
    """Kill the named tmux session on *host*. True on success."""
    exit_status, _ = _ssh_exec(host, user, f"tmux kill-session -t '{name}'")
    return exit_status == 0


def attach_session(host: str, user: str | None, name: str) -> None:
    """Attach to *name* on *host* via ssh -t (requires a live PTY)."""
    target = f"{user}@{host}" if user else host
    subprocess.run(["ssh", "-t", target, f"tmux attach-session -t '{name}'"])

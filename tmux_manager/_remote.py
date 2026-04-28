"""Remote tmux operations via paramiko SSH."""

from __future__ import annotations

import getpass
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


def _ssh_exec(host: str, user: str | None, command: str) -> tuple[int, str]:
    """Execute *command* on *host* via paramiko; return (exit_status, stdout).

    Reads ~/.ssh/config so SSH aliases, custom ports, and identity files
    are respected automatically.  If key-based auth fails and stdin is a
    TTY, falls back to password authentication (prompted every time).
    Returns (-1, "") on any connection, auth, or network failure.
    """
    ssh_cfg = _load_ssh_config(host, user)
    connect_kw = {
        "hostname": ssh_cfg.get("hostname", host),
        "username": ssh_cfg.get("username", user),
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
        _, stdout, _ = client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode()
        return exit_status, output
    except (paramiko.SSHException, socket.timeout, OSError) as exc:
        if "not found in known_hosts" in str(exc):
            print(
                f"Host '{host}' is not in ~/.ssh/known_hosts. "
                "Connect once via 'ssh' CLI to add it.",
                file=sys.stderr,
            )
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


def attach_session(host: str, user: str | None, name: str) -> None:
    """Attach to *name* on *host* via ssh -t (requires a live PTY)."""
    target = f"{user}@{host}" if user else host
    subprocess.run(["ssh", "-t", target, f"tmux attach-session -t {shlex.quote(name)}"])

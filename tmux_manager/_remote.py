"""Remote tmux operations via system SSH."""

from __future__ import annotations

import shlex
import subprocess


def _ssh_target(host: str, user: str | None) -> str:
    """Build the ssh target string."""
    return f"{user}@{host}" if user else host


def _ssh_exec(host: str, user: str | None, command: str) -> tuple[int, str]:
    """Run a command on a remote host via system ssh.

    Returns ``(returncode, stdout_text)``.  Returns ``(-1, "")`` when
    the ssh binary is missing or the OS refuses to spawn the process.
    """
    try:
        result = subprocess.run(
            ["ssh", _ssh_target(host, user), command],
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout
    except OSError:
        return -1, ""


def _list_sessions(host: str, user: str | None) -> list[str]:
    exit_status, output = _ssh_exec(
        host, user, "tmux list-sessions -F '#{session_name}' 2>/dev/null"
    )
    if exit_status != 0 or not output.strip():
        return []
    return [s for s in output.strip().splitlines() if s]


def _new_session(host: str, user: str | None, name: str) -> bool:
    exit_status, _ = _ssh_exec(
        host, user, f"tmux new-session -d -s {shlex.quote(name)}"
    )
    return exit_status == 0


def _kill_session(host: str, user: str | None, name: str) -> bool:
    exit_status, _ = _ssh_exec(
        host, user, f"tmux kill-session -t {shlex.quote(name)}"
    )
    return exit_status == 0


def _command_available(host: str, user: str | None, cmd: str) -> bool:
    exit_status, _ = _ssh_exec(
        host, user, f"command -v {shlex.quote(cmd)}"
    )
    return exit_status == 0


def _attach_session(host: str, user: str | None, name: str) -> None:
    """Attach to a tmux session via system ssh (interactive)."""
    subprocess.run(
        ["ssh", "-t", _ssh_target(host, user),
         f"tmux attach-session -t {shlex.quote(name)}"]
    )

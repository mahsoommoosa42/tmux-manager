"""Remote tmux operations via system SSH."""

from __future__ import annotations

import shlex
import subprocess
import sys


def _ssh_target(host: str, user: str | None) -> str:
    """Build the ssh target string."""
    return f"{user}@{host}" if user else host


def _mux_args(control_path: str | None) -> list[str]:
    """Return SSH ControlMaster arguments for connection reuse.

    Returns an empty list on Windows (ControlMaster is not supported
    by the Win32-OpenSSH port) or when *control_path* is ``None``.
    """
    if control_path is None or sys.platform == "win32":
        return []
    return [
        "-o", f"ControlPath={control_path}",
        "-o", "ControlMaster=auto",
        "-o", "ControlPersist=120",
    ]


def _ssh_exec(
    host: str,
    user: str | None,
    command: str,
    *,
    control_path: str | None = None,
) -> tuple[int, str]:
    """Run a command on a remote host via system ssh.

    Returns ``(returncode, stdout_text)``.  Returns ``(-1, "")`` when
    the ssh binary is missing or the OS refuses to spawn the process.
    """
    try:
        result = subprocess.run(
            ["ssh"]
            + _mux_args(control_path)
            + [_ssh_target(host, user), command],
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout
    except OSError:
        return -1, ""


def _validate(
    host: str, user: str | None, *, control_path: str | None = None,
) -> bool:
    """Return True if the remote host is reachable via SSH."""
    exit_status, _ = _ssh_exec(host, user, "true", control_path=control_path)
    return exit_status == 0


def _list_sessions(
    host: str, user: str | None, *, control_path: str | None = None,
) -> list[str]:
    exit_status, output = _ssh_exec(
        host, user, "tmux list-sessions -F '#{session_name}' 2>/dev/null",
        control_path=control_path,
    )
    if exit_status != 0 or not output.strip():
        return []
    return [s for s in output.strip().splitlines() if s]


def _new_session(
    host: str, user: str | None, name: str, *, control_path: str | None = None,
) -> bool:
    exit_status, _ = _ssh_exec(
        host, user, f"tmux new-session -d -s {shlex.quote(name)}",
        control_path=control_path,
    )
    return exit_status == 0


def _kill_session(
    host: str, user: str | None, name: str, *, control_path: str | None = None,
) -> bool:
    exit_status, _ = _ssh_exec(
        host, user, f"tmux kill-session -t {shlex.quote(name)}",
        control_path=control_path,
    )
    return exit_status == 0


def _command_available(
    host: str, user: str | None, cmd: str, *, control_path: str | None = None,
) -> bool:
    exit_status, _ = _ssh_exec(
        host, user, f"command -v {shlex.quote(cmd)}",
        control_path=control_path,
    )
    return exit_status == 0


def _attach_session(
    host: str, user: str | None, name: str, *, control_path: str | None = None,
) -> None:
    """Attach to a tmux session via system ssh (interactive)."""
    subprocess.run(
        ["ssh", "-t"]
        + _mux_args(control_path)
        + [_ssh_target(host, user),
           f"tmux attach-session -t {shlex.quote(name)}"]
    )


def _capture_pane(
    host: str, user: str | None, name: str, *, control_path: str | None = None,
) -> str:
    """Return the visible contents of the active pane of session *name*.

    Returns an empty string if the session does not exist or the SSH
    command fails.
    """
    exit_status, output = _ssh_exec(
        host, user,
        f"tmux capture-pane -p -J -t {shlex.quote(name)} 2>/dev/null",
        control_path=control_path,
    )
    if exit_status != 0:
        return ""
    return output


def _close_mux(host: str, user: str | None, control_path: str) -> None:
    """Ask the ControlMaster process to exit."""
    if sys.platform == "win32":
        return
    try:
        subprocess.run(
            ["ssh", "-O", "exit",
             "-o", f"ControlPath={control_path}",
             _ssh_target(host, user)],
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass

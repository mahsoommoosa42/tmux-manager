"""Local tmux operations via shutil and subprocess."""

from __future__ import annotations

import shutil
import subprocess


def command_available(cmd: str) -> bool:
    """Return True if *cmd* is on the local PATH."""
    return shutil.which(cmd) is not None


def list_sessions() -> list[str]:
    """Return local tmux session names, or [] if tmux is not running."""
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [s for s in result.stdout.strip().splitlines() if s]


def new_session(name: str) -> bool:
    """Create a new detached local tmux session. True on success."""
    result = subprocess.run(
        ["tmux", "new-session", "-d", "-s", name],
        capture_output=True,
    )
    return result.returncode == 0


def kill_session(name: str) -> bool:
    """Kill the named local tmux session. True on success."""
    result = subprocess.run(
        ["tmux", "kill-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0


def attach_session(name: str) -> None:
    """Attach to the named local tmux session (requires a live PTY)."""
    subprocess.run(["tmux", "attach-session", "-t", name])


def capture_pane(name: str) -> str:
    """Return the visible contents of the active pane of session *name*.

    Returns an empty string if the session does not exist or tmux fails.
    """
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-J", "-t", name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout

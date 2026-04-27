"""Local tmux operations via shutil and subprocess."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone


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


def session_info(name: str) -> dict | None:
    """Return metadata for the named session, or None if it doesn't exist."""
    fmt = "#{session_windows}\t#{session_created}\t#{session_attached}"
    result = subprocess.run(
        ["tmux", "display-message", "-t", name, "-p", fmt],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    parts = result.stdout.strip().split("\t")
    return {
        "name": name,
        "windows": int(parts[0]),
        "created": datetime.fromtimestamp(int(parts[1]), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        ),
        "attached": parts[2] != "0",
    }


def capture_pane(name: str, lines: int = 50) -> str:
    """Capture visible pane content from the named session."""
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", name, "-p"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    content = result.stdout.rstrip("\n")
    output_lines = content.splitlines()
    if len(output_lines) > lines:
        output_lines = output_lines[-lines:]
    return "\n".join(output_lines)


def attach_session(name: str) -> None:
    """Attach to the named local tmux session (requires a live PTY)."""
    subprocess.run(["tmux", "attach-session", "-t", name])

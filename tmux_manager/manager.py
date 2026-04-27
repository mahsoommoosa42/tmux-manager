"""TmuxManager — unified local and remote tmux session management."""

from __future__ import annotations

from . import _local, _remote


class TmuxManager:
    """Manage tmux sessions on a local or remote machine.

    Pass *host* to operate over SSH; omit it (or pass None) for local operations.
    """

    def __init__(self, host: str | None = None, user: str | None = None) -> None:
        self._host = host
        self._user = user

    # ── tool availability ────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """True if tmux is installed on the target machine."""
        return self.command_available("tmux")

    def command_available(self, command: str) -> bool:
        """True if *command* is on PATH on the target machine."""
        if self._host is None:
            return _local.command_available(command)
        return _remote.command_available(self._host, self._user, command)

    # ── session management ───────────────────────────────────────────────────

    def list_sessions(self) -> list[str]:
        """Return session names; [] if none exist or the host is unreachable."""
        if self._host is None:
            return _local.list_sessions()
        return _remote.list_sessions(self._host, self._user)

    def has_session(self, name: str) -> bool:
        """True if a session named *name* exists."""
        return name in self.list_sessions()

    def new_session(self, name: str) -> bool:
        """Create a new detached session named *name*. True on success."""
        if self._host is None:
            return _local.new_session(name)
        return _remote.new_session(self._host, self._user, name)

    def kill_session(self, name: str) -> bool:
        """Kill the session named *name*. True on success."""
        if self._host is None:
            return _local.kill_session(name)
        return _remote.kill_session(self._host, self._user, name)

    def attach_session(self, name: str) -> None:
        """Attach to *name* (requires a live PTY)."""
        if self._host is None:
            _local.attach_session(name)
        else:
            _remote.attach_session(self._host, self._user, name)

    def open_shell(self) -> None:
        """Open an interactive SSH shell (remote only)."""
        if self._host is None:
            return
        _remote.open_shell(self._host, self._user)

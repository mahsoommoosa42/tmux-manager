"""TmuxManager — unified local and remote tmux session management."""

from __future__ import annotations

from . import _local, _remote


class TmuxManager:
    """Manage tmux sessions on a local or remote machine.

    Pass *host* to operate over SSH; omit it (or pass None) for local operations.
    Remote connections authenticate at construction time and persist for the
    lifetime of the object. Use as a context manager to ensure cleanup:

        with TmuxManager("devbox") as mgr:
            mgr.list_sessions()
    """

    def __init__(self, host: str | None = None, user: str | None = None) -> None:
        self._host = host
        self._user = user
        self._conn: _remote._SSHConnection | None = None
        if host is not None:
            self._conn = _remote._SSHConnection(host, user)

    # ── context manager & cleanup ─────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._close()

    def __del__(self) -> None:
        self._close()

    def _close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _require_conn(self) -> _remote._SSHConnection:
        if self._conn is None:
            raise RuntimeError("TmuxManager connection is closed")
        return self._conn

    # ── tool availability ─────────────────────────────────────────────

    def is_available(self) -> bool:
        """True if tmux is installed on the target machine."""
        return self.command_available("tmux")

    def command_available(self, command: str) -> bool:
        """True if *command* is on PATH on the target machine."""
        if self._host is None:
            return _local.command_available(command)
        return _remote._command_available_conn(self._require_conn(), command)

    # ── session management ────────────────────────────────────────────

    def list_sessions(self) -> list[str]:
        """Return session names; [] if none exist or the host is unreachable."""
        if self._host is None:
            return _local.list_sessions()
        return _remote._list_sessions_conn(self._require_conn())

    def has_session(self, name: str) -> bool:
        """True if a session named *name* exists."""
        return name in self.list_sessions()

    def new_session(self, name: str) -> bool:
        """Create a new detached session named *name*. True on success."""
        if self._host is None:
            return _local.new_session(name)
        return _remote._new_session_conn(self._require_conn(), name)

    def kill_session(self, name: str) -> bool:
        """Kill the session named *name*. True on success."""
        if self._host is None:
            return _local.kill_session(name)
        return _remote._kill_session_conn(self._require_conn(), name)

    def attach_session(self, name: str) -> None:
        """Attach to *name* (requires a live PTY)."""
        if self._host is None:
            _local.attach_session(name)
        else:
            _remote.attach_session(self._host, self._user, name)

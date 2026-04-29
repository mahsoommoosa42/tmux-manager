"""TmuxManager — unified local and remote tmux session management."""

from __future__ import annotations

import os
import shutil
import tempfile

from . import _local, _remote


class TmuxManager:
    """Manage tmux sessions on a local or remote machine.

    Pass *host* to operate over SSH; omit it (or pass None) for local
    operations.  Remote operations delegate to the system ``ssh`` command
    with ControlMaster multiplexing so only the first call authenticates.

        with TmuxManager("devbox") as mgr:
            mgr.list_sessions()
    """

    def __init__(self, host: str | None = None, user: str | None = None) -> None:
        self._host = host
        self._user = user
        self._control_dir: str | None = None
        self._control_path: str | None = None
        if host is not None:
            self._control_dir = tempfile.mkdtemp(prefix="tmux-mgr-")
            self._control_path = os.path.join(self._control_dir, "ctrl")

    # ── context manager & cleanup ─────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        """Tear down SSH multiplexing and clean up. Safe to call repeatedly."""
        cp = self._control_path
        cd = self._control_dir
        self._control_path = None
        self._control_dir = None
        if cp is not None and self._host is not None:
            _remote._close_mux(self._host, self._user, cp)
        if cd is not None:
            shutil.rmtree(cd, ignore_errors=True)

    # ── connectivity ───────────────────────────────────────────────────

    def connect(self) -> "TmuxManager":
        """Validate SSH connectivity and warm up ControlMaster.

        Raises ``ConnectionError`` if the remote host is unreachable.
        No-op for local mode.  Returns *self* so callers can chain::

            mgr = TmuxManager("devbox", "alice").connect()
        """
        if self._host is not None:
            if not _remote._validate(
                self._host, self._user,
                control_path=self._control_path,
            ):
                raise ConnectionError(
                    f"SSH connection to {self._host} failed"
                )
        return self

    # ── tool availability ─────────────────────────────────────────────

    def is_available(self) -> bool:
        """True if tmux is installed on the target machine."""
        return self.command_available("tmux")

    def command_available(self, command: str) -> bool:
        """True if *command* is on PATH on the target machine."""
        if self._host is None:
            return _local.command_available(command)
        return _remote._command_available(
            self._host, self._user, command,
            control_path=self._control_path,
        )

    # ── session management ────────────────────────────────────────────

    def list_sessions(self) -> list[str]:
        """Return session names; [] if none exist or the host is unreachable."""
        if self._host is None:
            return _local.list_sessions()
        return _remote._list_sessions(
            self._host, self._user, control_path=self._control_path,
        )

    def has_session(self, name: str) -> bool:
        """True if a session named *name* exists."""
        return name in self.list_sessions()

    def new_session(self, name: str) -> bool:
        """Create a new detached session named *name*. True on success."""
        if self._host is None:
            return _local.new_session(name)
        return _remote._new_session(
            self._host, self._user, name,
            control_path=self._control_path,
        )

    def kill_session(self, name: str) -> bool:
        """Kill the session named *name*. True on success."""
        if self._host is None:
            return _local.kill_session(name)
        return _remote._kill_session(
            self._host, self._user, name,
            control_path=self._control_path,
        )

    def attach_session(self, name: str) -> None:
        """Attach to *name* (requires a live PTY)."""
        if self._host is None:
            _local.attach_session(name)
        else:
            _remote._attach_session(
                self._host, self._user, name,
                control_path=self._control_path,
            )

"""Shared test configuration."""

import sys
from unittest.mock import MagicMock

# Stub Unix-only modules on Windows so that tests can patch and import them.
# These modules are only used inside _attach_session_conn() which is never
# called for real on Windows (tmux doesn't run there), but tests still need
# to mock them.
if sys.platform == "win32":
    for _mod in ("termios", "tty"):
        if _mod not in sys.modules:
            sys.modules[_mod] = MagicMock()

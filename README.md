# tmux-manager

Manage tmux sessions on local and remote machines from Python.

```python
from tmux_manager import TmuxManager

# Local
mgr = TmuxManager()
mgr.new_session("work")
print(mgr.list_sessions())   # ["work"]
mgr.attach_session("work")

# Remote (via SSH)
mgr = TmuxManager(host="devbox", user="alice")
print(mgr.list_sessions())
mgr.attach_session("main")
```

## Install

```
uv add tmux-manager @ git+https://github.com/mahsoommoosa42/tmux-manager
```

## API

```python
TmuxManager(host=None, user=None)
```

| Method | Description |
|---|---|
| `is_available()` | True if tmux is installed on the target |
| `command_available(cmd)` | True if *cmd* is on PATH on the target |
| `list_sessions()` | Return list of session names |
| `has_session(name)` | True if session *name* exists |
| `new_session(name)` | Create a new detached session |
| `kill_session(name)` | Kill the named session |
| `attach_session(name)` | Attach (requires a live PTY) |

Remote operations use `paramiko` (SSH key auth, no passwords).
Attach always uses the system `ssh` binary for PTY support.

## License

GNU General Public License v3.

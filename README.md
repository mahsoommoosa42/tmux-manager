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
uv add tmux-manager
```

or with pip:

```
pip install tmux-manager
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

## SSH aliases

Remote operations read `~/.ssh/config` automatically, so any alias
you have defined works without extra configuration:

```
# ~/.ssh/config
Host devbox
    HostName 192.168.1.10
    User alice
    IdentityFile ~/.ssh/id_ed25519
    Port 2222
```

```python
# Just use the alias name — hostname, user, port and key are resolved automatically
mgr = TmuxManager("devbox")
print(mgr.list_sessions())
```

`attach_session` always delegates to the system `ssh` binary so the full
SSH config (ProxyJump, etc.) is respected there too.

## Notes

- Remote queries use `paramiko` (SSH key auth, no passwords needed)
- `attach_session` uses the system `ssh` binary for PTY support

## License

GNU General Public License v3.

# tmux-manager

Manage tmux sessions on local and remote machines from Python.

```python
from tmux_manager import TmuxManager

# Local
mgr = TmuxManager()
mgr.new_session("work")
print(mgr.list_sessions())   # ["work"]
mgr.attach_session("work")

# Remote — validates connectivity, warms up ControlMaster
with TmuxManager(host="devbox", user="alice") as mgr:
    mgr.connect()  # raises ConnectionError if unreachable
    mgr.new_session("work")
    print(mgr.list_sessions())
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
| `connect()` | Validate SSH connectivity; warms up ControlMaster (Linux/macOS). Raises `ConnectionError` on failure. Returns `self` for chaining |
| `close()` | Tear down SSH multiplexing and clean up temp dir. Called automatically by `__exit__` and `__del__` |
| `is_available()` | True if tmux is installed on the target |
| `command_available(cmd)` | True if *cmd* is on PATH on the target |
| `list_sessions()` | Return list of session names |
| `has_session(name)` | True if session *name* exists |
| `new_session(name)` | Create a new detached session |
| `kill_session(name)` | Kill the named session |
| `attach_session(name)` | Attach (requires a live PTY) |
| `capture_pane(name)` | Return visible contents of session's active pane (for previews) |

## SSH aliases

Remote operations use the system `ssh` command, which reads `~/.ssh/config`
automatically. Any alias you have defined works without extra configuration:

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

## Connection multiplexing

On **Linux/macOS**, SSH ControlMaster multiplexing is used automatically.
The first SSH call authenticates (e.g. password prompt), and subsequent
calls reuse the connection — no extra password prompts. Call `connect()`
to warm up the master connection upfront:

```python
mgr = TmuxManager("devbox", "alice").connect()
mgr.list_sessions()    # reuses connection — no password prompt
mgr.is_available()     # reuses connection — no password prompt
```

On **Windows**, ControlMaster is not supported by Win32-OpenSSH.
Each operation spawns an independent `ssh` process, so password auth
will prompt once per call. **Use SSH key-based authentication to avoid
repeated prompts:**

```
# ~/.ssh/config
Host devbox
    IdentityFile ~/.ssh/id_ed25519
```

## Notes

- All remote operations delegate to the system `ssh` command (zero runtime dependencies)
- Use as a context manager (`with`) to clean up ControlMaster sockets
- `connect()` validates SSH connectivity upfront and raises `ConnectionError` on failure
- `attach_session` uses `ssh -t` for interactive PTY attachment

## Development

### Local Setup

Clone the repo and install in editable mode:

```bash
git clone https://github.com/mahsoommoosa42/tmux-manager.git
cd tmux-manager
uv sync --extra dev
```

Run tests:

```bash
uv run pytest --cov=tmux_manager --cov-report=term-missing
```

All tests must pass at 100% branch coverage before submitting a PR.

### Project Structure

See [CLAUDE.md](CLAUDE.md) for detailed architecture, module documentation, testing patterns, and design decisions.

## Contributing

### Opening a Pull Request

1. **Fork and clone:** Fork the repo, then clone your fork locally
2. **Create a branch:** `git checkout -b fix/issue-name` or `feat/feature-name`
3. **Make changes:** Write code, add tests, update docs as needed
4. **Run tests:** Ensure `uv run pytest --cov-fail-under=100` passes
5. **Commit:** Write clear, concise commit messages
6. **Push:** `git push origin your-branch`
7. **Open PR:** Open a pull request on GitHub with a description of your changes

### Guidelines

- All new code must have 100% branch test coverage
- Follow existing code style (see CLAUDE.md for patterns)
- Update README.md if adding new features
- No external runtime dependencies (zero-dep library)

## License

GNU General Public License v3.

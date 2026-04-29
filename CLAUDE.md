# tmux-manager Development Guide

## Project Overview

`tmux-manager` is a Python library that provides a unified interface for managing tmux sessions on both local and remote machines via SSH. It abstracts away the complexity of SSH configuration and paramiko while providing a simple, synchronous API.

**Key Features:**
- Local and remote tmux session management via single `TmuxManager` class
- Automatic SSH config file parsing (handles aliases, ports, identity files, ProxyJump)
- Paramiko-based SSH queries (key auth preferred, password fallback via getpass)
- 100% branch test coverage

**Target Users:** Python developers building terminal UIs, deployment tools, or CI/CD integrations that need tmux session management.

## Architecture

### Core Design Pattern: Local/Remote Dispatch

The `TmuxManager` class uses a dispatch pattern:
- **No host parameter** → delegate to `_local.py` (subprocess-based)
- **Host parameter** → delegate to `_remote.py` (paramiko-based SSH)

This keeps concerns separated and makes testing straightforward (mock the backend module).

### Module Structure

```
tmux_manager/
├── __init__.py           # Public API exports (TmuxManager)
├── manager.py            # TmuxManager class - dispatcher
├── _local.py             # Local operations via subprocess
├── _remote.py            # Remote operations via paramiko
tests/
├── unit/
│   ├── test_manager.py    # Tests local/remote dispatch
│   ├── test_local.py      # Tests subprocess operations
│   ├── test_remote.py     # Tests SSH operations and config parsing
│   └── __init__.py
├── functional/
│   ├── test_local_flow.py  # End-to-end local tests
│   ├── test_remote_flow.py # End-to-end remote tests
│   └── __init__.py
pyproject.toml
README.md
LICENSE
```

## Key Files and Their Roles

### `tmux_manager/manager.py`
- **Class:** `TmuxManager(host=None, user=None)`
- **Responsibility:** Dispatch layer — determines local vs remote and delegates
- **Key Methods:**
  - `is_available()` → `command_available("tmux")`
  - `command_available(cmd)` → check if cmd is on PATH
  - `list_sessions()` → return session names
  - `has_session(name)` → check if session exists
  - `new_session(name)` → create detached session
  - `kill_session(name)` → kill session
  - `attach_session(name)` → attach (requires PTY)
- **Testing:** Mock `_local` or `_remote` modules; verify dispatch logic

### `tmux_manager/_local.py`
- **Functions:** All take simple args, no host/user
- **Implementation:** `shutil.which()` + `subprocess.run()`
- **Key Details:**
  - `list_sessions()` returns `[]` if tmux not running (returncode != 0)
  - `attach_session()` replaces Python process with `tmux`
  - No error handling beyond return codes
- **Testing:** Mock `subprocess.run()` and `shutil.which()`

### `tmux_manager/_remote.py`
- **SSH Config Loading:** `_load_ssh_config(host, user) → dict with hostname/port/user/key`
- **Persistent Connection:** `_SSHConnection` class (intentionally private, underscore-prefixed)
  - Opened once in `__init__`, reused for all operations on a `TmuxManager` instance
  - Uses `paramiko.RejectPolicy()` — will not auto-add unknown host keys
  - Exposes `exec(command) → (exit_status, stdout_text)`, `close()`, and `is_connected`
  - Must NOT be exported in `__init__.py` or appear in any public type hint
- **Connection-aware helpers:** `_list_sessions_conn`, `_new_session_conn`, `_kill_session_conn`, `_command_available_conn`, `_attach_session_conn` — all take a `_SSHConnection` as first arg
- **Operations:** Similar to `_local` but via SSH
- **Key Details:**
  - Uses `paramiko` for command execution (key auth first, password fallback via `getpass`)
  - `_load_ssh_config()` uses `paramiko.SSHConfig` to parse `~/.ssh/config`
  - Handles hostname aliases, custom ports, identity files
  - `_attach_session_conn()` uses a paramiko channel with PTY for interactive attach over the persistent connection
- **Testing:** Mock `paramiko.SSHClient` and `_load_ssh_config`. For `_SSHConnection`, mock at `tmux_manager._remote.paramiko.SSHClient` and `tmux_manager._remote._load_ssh_config`.

## Testing Strategy

### Test Organization

**Unit Tests (mock all external calls):**
- Test individual functions in isolation
- Mock subprocess, paramiko, file I/O
- Fast, deterministic, no side effects

**Functional Tests (integration-level, optional paramiko):**
- Test realistic workflows
- May mock SSH if no real host available
- Verify end-to-end behavior

### Coverage Requirements

**100% branch coverage required** (enforced by pytest `--cov-fail-under=100`)

To check coverage:
```bash
pytest --cov=tmux_manager --cov-report=term-missing
```

Missing branches appear in the report. Common sources:
- Error handling paths not exercised
- Conditional logic (if/else) where both paths must be tested
- Exception handling blocks

### Test Patterns

**Pattern 1: Mock subprocess operations**
```python
def test_list_sessions_success(self):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "main\nwork\n"
    with patch("tmux_manager._local.subprocess.run", return_value=mock_result):
        assert list_sessions() == ["main", "work"]
```

**Pattern 2: Verify mock was called with correct args**
```python
def test_new_session_args(self):
    with patch("tmux_manager._local.subprocess.run") as mock:
        new_session("my-session")
    mock.assert_called_once_with(["tmux", "new-session", "-d", "-s", "my-session"], ...)
```

**Pattern 3: Test dispatch to backend (remote with persistent connection)**
```python
def test_list_sessions_delegates(self):
    conn = MagicMock()
    with (
        patch("tmux_manager.manager._remote._SSHConnection", return_value=conn),
        patch("tmux_manager.manager._remote._list_sessions_conn", return_value=["s1"]) as m,
    ):
        result = TmuxManager("devbox", "alice").list_sessions()
    m.assert_called_once_with(conn)
    assert result == ["s1"]
```

**Pattern 4: Mock _SSHConnection for manager tests**
```python
# Always mock _SSHConnection when constructing a remote TmuxManager in tests:
conn = MagicMock()
with patch("tmux_manager.manager._remote._SSHConnection", return_value=conn):
    mgr = TmuxManager("devbox")
# Then mock the private _*_conn helpers for individual operations
```

## SSH Config Integration

`_load_ssh_config(host, user)` reads `~/.ssh/config` and returns a dict with:
- `hostname` — resolved from `HostName` field (defaults to host if not found)
- `port` — from `Port` field (defaults to 22)
- `username` — from `User` field or function parameter
- `key_filename` — list from `IdentityFile` fields

This allows users to define hosts once in SSH config and use the alias in code:
```python
# ~/.ssh/config has: Host devbox, HostName 192.168.1.10, User alice, Port 2222
mgr = TmuxManager("devbox")  # Automatically resolved
```

## Common Development Tasks

### Running Tests
```bash
# All tests with coverage
pytest --cov=tmux_manager --cov-report=term-missing

# Specific test file
pytest tests/unit/test_manager.py

# Specific test class
pytest tests/unit/test_manager.py::TestTmuxManagerLocal

# Specific test method
pytest tests/unit/test_manager.py::TestTmuxManagerLocal::test_is_available_true
```

### Adding a New Method to TmuxManager
1. Add method to `manager.py` with dispatch logic
2. Add implementation to `_local.py` and `_remote.py`
3. Add unit tests in `test_manager.py` (verify dispatch)
4. Add unit tests in `test_local.py` and `test_remote.py` (verify implementation)
5. Run `pytest --cov-fail-under=100` to ensure 100% coverage

### Modifying SSH Config Parsing
1. Update `_load_ssh_config()` in `_remote.py`
2. Add test cases in `test_remote.py::TestLoadSshConfig`
3. Consider edge cases: missing fields, duplicate hosts, syntax errors
4. Verify coverage with `pytest --cov`

### Debugging SSH Connection Issues
- Check `~/.ssh/config` syntax (use `ssh -G hostname` to debug)
- Verify identity file permissions: `ls -l ~/.ssh/id_*`

## Dependencies and Constraints

**Runtime Dependencies:**
- `paramiko` — SSH operations (v2.7+)

**Dev Dependencies:**
- `pytest`, `pytest-cov` — testing and coverage

**Python Version:** 3.12 only

**File Encoding:** UTF-8 (explicitly specified in code)

## Design Decisions

### Why paramiko for everything?
- Single persistent SSH connection for all operations (queries and attach)
- `attach_session` uses a paramiko channel with PTY allocation and raw terminal I/O forwarding
- Avoids re-authentication for interactive sessions on password-auth hosts

### Why synchronous API?
- Simplicity: no event loops or asyncio complexity
- Typical use case is short-lived operations (list, create, kill)
- If async needed later, can be added without breaking sync API

### Why dispatch pattern instead of subclasses?
- TmuxManager API is small and stable
- Dispatch is explicit and testable
- Avoids inheritance complexity

### Why a persistent SSH connection?
- Avoids opening a new SSH connection for every remote operation
- `_SSHConnection` is intentionally private (underscore prefix) and never exposed in the public API
- `TmuxManager` supports context manager (`with`) for deterministic cleanup
- Construction with an unreachable host raises immediately — no silent failures
- All operations including `attach_session` use the persistent connection — no separate `ssh` subprocess needed

## Known Limitations and Future Work

**Current Limitations:**
- Password prompted every time via getpass (never cached or stored)
- No session information beyond names (id, creation time, etc.)
- No support for reading tmux config files
- Remote hosts must be in ~/.ssh/known_hosts (AutoAddPolicy is not used for security reasons)

**Future Opportunities:**
- Async API (TmuxManagerAsync) if needed
- Rich session info (subprocess with `-F` and more fields)
- Session event streaming (watch for new/deleted sessions)
- Tmux configuration helpers (read/validate tmux config)

## References

- [Tmux Manual](https://man7.org/linux/man-pages/man1/tmux.1.html)
- [Paramiko Docs](https://www.paramiko.org/)
- [SSH Config Format](https://man7.org/linux/man-pages/man5/ssh_config.5.html)
- [Pytest Best Practices](https://docs.pytest.org/en/stable/how-to.html)

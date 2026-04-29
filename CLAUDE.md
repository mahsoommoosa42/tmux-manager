# tmux-manager Development Guide

## Project Overview

`tmux-manager` is a Python library that provides a unified interface for managing tmux sessions on both local and remote machines via SSH. It delegates to the system `ssh` command for remote operations, keeping the codebase cross-platform with zero runtime dependencies.

**Key Features:**
- Local and remote tmux session management via single `TmuxManager` class
- System `ssh` for all remote operations (reads `~/.ssh/config` natively)
- Zero runtime dependencies
- 100% branch test coverage

**Target Users:** Python developers building terminal UIs, deployment tools, or CI/CD integrations that need tmux session management.

## Architecture

### Core Design Pattern: Local/Remote Dispatch

The `TmuxManager` class uses a dispatch pattern:
- **No host parameter** → delegate to `_local.py` (subprocess-based)
- **Host parameter** → delegate to `_remote.py` (subprocess `ssh`)

This keeps concerns separated and makes testing straightforward (mock the backend module).

### Module Structure

```
tmux_manager/
├── __init__.py           # Public API exports (TmuxManager)
├── manager.py            # TmuxManager class - dispatcher
├── _local.py             # Local operations via subprocess
├── _remote.py            # Remote operations via system ssh
tests/
├── __init__.py
├── conftest.py            # Shared test configuration
├── unit/
│   ├── __init__.py
│   ├── test_manager.py    # Tests local/remote dispatch
│   ├── test_local.py      # Tests subprocess operations
│   └── test_remote.py     # Tests SSH operations
├── functional/
│   ├── __init__.py
│   ├── test_local_flow.py  # End-to-end local tests
│   └── test_remote_flow.py # End-to-end remote tests
pyproject.toml
README.md
LICENSE
```

## Key Files and Their Roles

### `tmux_manager/manager.py`
- **Class:** `TmuxManager(host=None, user=None)`
- **Responsibility:** Dispatch layer — determines local vs remote and delegates
- **Key Methods:**
  - `connect()` → validate SSH connectivity and warm up ControlMaster; raises `ConnectionError` on failure; returns `self` for chaining
  - `is_available()` → `command_available("tmux")`
  - `command_available(cmd)` → check if cmd is on PATH
  - `list_sessions()` → return session names
  - `has_session(name)` → check if session exists
  - `new_session(name)` → create detached session
  - `kill_session(name)` → kill session
  - `attach_session(name)` → attach (requires PTY)
- **`close()`** — tears down SSH ControlMaster and removes temp dir. Called by `__exit__` and `__del__`
- **Context Manager:** Supported (`with TmuxManager(...) as mgr:`). Calls `close()` on exit to clean up SSH multiplexing
- **Testing:** Mock `_local` or `_remote` functions; verify dispatch logic

### `tmux_manager/_local.py`
- **Functions:** All take simple args, no host/user
- **Implementation:** `shutil.which()` + `subprocess.run()`
- **Key Details:**
  - `list_sessions()` returns `[]` if tmux not running (returncode != 0)
  - `attach_session()` runs `tmux attach-session` as a child process via `subprocess.run()`
  - No error handling beyond return codes
- **Testing:** Mock `subprocess.run()` and `shutil.which()`

### `tmux_manager/_remote.py`
- **`_ssh_target(host, user)`** — builds `user@host` or `host` string
- **`_mux_args(control_path)`** — returns ControlMaster SSH options (empty on Windows)
- **`_ssh_exec(host, user, command, *, control_path=None)`** — runs `ssh target command` via subprocess, returns `(exit_status, stdout)`. Returns `(-1, "")` on `OSError`
- **`_validate(host, user, *, control_path=None)`** — runs `ssh host true` to check reachability; returns `bool`
- **Helper functions:** `_list_sessions`, `_new_session`, `_kill_session`, `_command_available` — all take `host`, `user`, and `control_path` kwarg, delegate to `_ssh_exec`
- **`_attach_session(host, user, name, *, control_path=None)`** — uses `ssh -t` for interactive PTY attach
- **`_close_mux(host, user, control_path)`** — sends `ssh -O exit` to tear down ControlMaster (no-op on Windows)
- **Key Details:**
  - System `ssh` handles config resolution, host key verification, and authentication natively
  - SSH ControlMaster multiplexing reuses connections on Linux/macOS (skipped on Windows)
  - No Python-level SSH config parsing needed
  - Cross-platform (works on Windows, macOS, Linux)
- **Testing:** Mock `subprocess.run` or `_ssh_exec`

## Testing Strategy

### Test Organization

**Unit Tests (mock all external calls):**
- Test individual functions in isolation
- Mock subprocess
- Fast, deterministic, no side effects

**Functional Tests (integration-level):**
- Test realistic workflows
- Mock `_ssh_exec` for remote tests
- Verify end-to-end behavior

### Coverage Requirements

**100% branch coverage required** (enforced by pytest `--cov-fail-under=100`)

To check coverage:
```bash
pytest --cov=tmux_manager --cov-report=term-missing
```

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

**Pattern 2: Mock _ssh_exec for remote helpers**
```python
def test_list_sessions_returns_names(self):
    with patch("tmux_manager._remote._ssh_exec", return_value=(0, "main\nwork\n")):
        assert _list_sessions("devbox", "alice") == ["main", "work"]
```

**Pattern 3: Test dispatch to remote backend (with control_path)**
```python
def test_list_sessions_delegates(self):
    with patch("tmux_manager.manager._remote._list_sessions", return_value=["s1"]) as m:
        mgr = TmuxManager("devbox", "alice")
        result = mgr.list_sessions()
    m.assert_called_once_with(
        "devbox", "alice", control_path=mgr._control_path,
    )
    assert result == ["s1"]
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

## Dependencies and Constraints

**Runtime Dependencies:** None

**Dev Dependencies:**
- `pytest`, `pytest-cov` — testing and coverage

**Python Version:** 3.12 only

**File Encoding:** UTF-8 (Python 3 default)

## Design Decisions

### Why system ssh for everything?
- Zero runtime dependencies (no paramiko)
- System `ssh` handles config resolution, host keys, and authentication natively
- Cross-platform: works on Windows (OpenSSH), macOS, and Linux
- `attach_session` uses `ssh -t` for interactive PTY, delegating terminal I/O to the native client

### Why synchronous API?
- Simplicity: no event loops or asyncio complexity
- Typical use case is short-lived operations (list, create, kill)
- If async needed later, can be added without breaking sync API

### Why dispatch pattern instead of subclasses?
- TmuxManager API is small and stable
- Dispatch is explicit and testable
- Avoids inheritance complexity

## Known Limitations and Future Work

**Current Limitations:**
- SSH ControlMaster multiplexing only works on Linux/macOS; Windows users get a fresh ssh process per operation
- No session information beyond names (id, creation time, etc.)
- No support for reading tmux config files
- SSH must be installed and configured on the system

**Future Opportunities:**
- Async API (TmuxManagerAsync) if needed
- Rich session info (subprocess with `-F` and more fields)
- Session event streaming (watch for new/deleted sessions)
- Tmux configuration helpers (read/validate tmux config)

## References

- [Tmux Manual](https://man7.org/linux/man-pages/man1/tmux.1.html)
- [SSH Config Format](https://man7.org/linux/man-pages/man5/ssh_config.5.html)
- [Pytest Best Practices](https://docs.pytest.org/en/stable/how-to.html)

"""Unit tests for _remote.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tmux_manager._remote import (
    _attach_session,
    _capture_pane,
    _close_mux,
    _command_available,
    _kill_session,
    _list_sessions,
    _mux_args,
    _new_session,
    _ssh_exec,
    _ssh_target,
    _validate,
)


# ── _ssh_target ──────────────────────────────────────────────────────────────


class TestSshTarget:
    def test_with_user(self):
        assert _ssh_target("devbox", "alice") == "alice@devbox"

    def test_without_user(self):
        assert _ssh_target("devbox", None) == "devbox"


# ── _mux_args ────────────────────────────────────────────────────────────────


class TestMuxArgs:
    def test_returns_options_with_control_path(self):
        args = _mux_args("/tmp/ctrl")
        assert "-o" in args
        assert "ControlPath=/tmp/ctrl" in args
        assert "ControlMaster=auto" in args
        assert "ControlPersist=120" in args

    def test_returns_empty_when_none(self):
        assert _mux_args(None) == []

    def test_returns_empty_on_win32(self):
        with patch("tmux_manager._remote.sys.platform", "win32"):
            assert _mux_args("/tmp/ctrl") == []


# ── _ssh_exec ────────────────────────────────────────────────────────────────


class TestSshExec:
    def test_returns_status_and_stdout(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "hello\n"
        with patch("tmux_manager._remote.subprocess.run", return_value=mock_result) as m:
            status, output = _ssh_exec("devbox", "alice", "echo hello")
        assert status == 0
        assert output == "hello\n"
        m.assert_called_once_with(
            ["ssh", "alice@devbox", "echo hello"],
            capture_output=True,
            text=True,
        )

    def test_returns_nonzero_status(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("tmux_manager._remote.subprocess.run", return_value=mock_result):
            status, output = _ssh_exec("devbox", None, "false")
        assert status == 1
        assert output == ""

    def test_oserror_returns_minus_one(self):
        with patch("tmux_manager._remote.subprocess.run", side_effect=OSError("no ssh")):
            status, output = _ssh_exec("devbox", None, "cmd")
        assert status == -1
        assert output == ""

    def test_passes_mux_args(self):
        mock_result = MagicMock(returncode=0, stdout="")
        with patch("tmux_manager._remote.subprocess.run", return_value=mock_result) as m:
            _ssh_exec("devbox", None, "cmd", control_path="/tmp/ctrl")
        cmd = m.call_args[0][0]
        assert "-o" in cmd
        assert "ControlPath=/tmp/ctrl" in cmd


# ── _validate ────────────────────────────────────────────────────────────────


class TestValidate:
    def test_success(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            assert _validate("devbox", "alice") is True
        assert m.call_args[0][2] == "true"

    def test_failure(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(255, "")):
            assert _validate("devbox", None) is False

    def test_passes_control_path(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            _validate("h", None, control_path="/tmp/c")
        assert m.call_args[1]["control_path"] == "/tmp/c"


# ── helper functions ─────────────────────────────────────────────────────────


class TestListSessions:
    def test_returns_names(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "main\nwork\n")):
            assert _list_sessions("devbox", "alice") == ["main", "work"]

    def test_empty_on_failure(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(-1, "")):
            assert _list_sessions("devbox", None) == []

    def test_empty_on_empty_output(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")):
            assert _list_sessions("devbox", None) == []

    def test_filters_blank_lines(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "main\n\nwork\n")):
            assert _list_sessions("devbox", None) == ["main", "work"]

    def test_passes_control_path(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            _list_sessions("h", None, control_path="/tmp/c")
        assert m.call_args[1]["control_path"] == "/tmp/c"


class TestNewSession:
    def test_success(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            assert _new_session("devbox", "alice", "work") is True
        cmd = m.call_args[0][2]
        assert "tmux new-session -d -s work" in cmd

    def test_failure(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert _new_session("devbox", None, "work") is False

    def test_passes_control_path(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            _new_session("h", None, "s", control_path="/tmp/c")
        assert m.call_args[1]["control_path"] == "/tmp/c"


class TestKillSession:
    def test_success(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            assert _kill_session("devbox", "alice", "work") is True
        cmd = m.call_args[0][2]
        assert "tmux kill-session -t work" in cmd

    def test_failure(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert _kill_session("devbox", None, "work") is False

    def test_passes_control_path(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            _kill_session("h", None, "s", control_path="/tmp/c")
        assert m.call_args[1]["control_path"] == "/tmp/c"


class TestCommandAvailable:
    def test_found(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "/usr/bin/tmux\n")):
            assert _command_available("devbox", "alice", "tmux") is True

    def test_not_found(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert _command_available("devbox", None, "tmux") is False

    def test_passes_control_path(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            _command_available("h", None, "c", control_path="/tmp/c")
        assert m.call_args[1]["control_path"] == "/tmp/c"


class TestAttachSession:
    def test_calls_ssh_with_tty(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session("devbox", "alice", "work")
        mock_run.assert_called_once_with(
            ["ssh", "-t", "alice@devbox", "tmux attach-session -t work"]
        )

    def test_no_user(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session("devbox", None, "work")
        mock_run.assert_called_once_with(
            ["ssh", "-t", "devbox", "tmux attach-session -t work"]
        )

    def test_shell_quotes_name(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session("devbox", None, "bad'; rm -rf /")
        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "tmux attach-session -t 'bad'\"'\"'; rm -rf /'"

    def test_passes_mux_args(self):
        with patch("tmux_manager._remote.subprocess.run") as mock_run:
            _attach_session("devbox", None, "s", control_path="/tmp/c")
        cmd = mock_run.call_args[0][0]
        assert "ControlPath=/tmp/c" in cmd


class TestCapturePane:
    def test_returns_output_on_success(self):
        with patch(
            "tmux_manager._remote._ssh_exec",
            return_value=(0, "hello\nworld\n"),
        ) as m:
            assert _capture_pane("devbox", "alice", "main") == "hello\nworld\n"
        cmd = m.call_args[0][2]
        assert "tmux capture-pane -p -J -t main" in cmd

    def test_empty_on_failure(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(1, "")):
            assert _capture_pane("devbox", None, "main") == ""

    def test_shell_quotes_name(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            _capture_pane("devbox", None, "bad'; rm -rf /")
        cmd = m.call_args[0][2]
        assert "'bad'\"'\"'; rm -rf /'" in cmd

    def test_passes_control_path(self):
        with patch("tmux_manager._remote._ssh_exec", return_value=(0, "")) as m:
            _capture_pane("h", None, "s", control_path="/tmp/c")
        assert m.call_args[1]["control_path"] == "/tmp/c"


# ── _close_mux ───────────────────────────────────────────────────────────────


class TestCloseMux:
    def test_sends_exit(self):
        with patch("tmux_manager._remote.subprocess.run") as m:
            _close_mux("devbox", "alice", "/tmp/ctrl")
        cmd = m.call_args[0][0]
        assert cmd[:2] == ["ssh", "-O"]
        assert "exit" in cmd
        assert "ControlPath=/tmp/ctrl" in cmd

    def test_noop_on_win32(self):
        with (
            patch("tmux_manager._remote.sys.platform", "win32"),
            patch("tmux_manager._remote.subprocess.run") as m,
        ):
            _close_mux("devbox", None, "/tmp/ctrl")
        m.assert_not_called()

    def test_ignores_oserror(self):
        with patch("tmux_manager._remote.subprocess.run", side_effect=OSError):
            _close_mux("devbox", None, "/tmp/ctrl")

    def test_ignores_timeout(self):
        import subprocess

        with patch(
            "tmux_manager._remote.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ssh", 5),
        ):
            _close_mux("devbox", None, "/tmp/ctrl")

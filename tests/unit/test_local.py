"""Unit tests for _local.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tmux_manager._local import (
    attach_session,
    capture_pane,
    command_available,
    kill_session,
    list_sessions,
    new_session,
    session_info,
)


class TestCommandAvailable:
    def test_found(self):
        with patch("tmux_manager._local.shutil.which", return_value="/usr/bin/tmux"):
            assert command_available("tmux") is True

    def test_not_found(self):
        with patch("tmux_manager._local.shutil.which", return_value=None):
            assert command_available("tmux") is False


class TestListSessions:
    def _result(self, returncode: int, stdout: str) -> MagicMock:
        r = MagicMock()
        r.returncode = returncode
        r.stdout = stdout
        return r

    def test_returns_session_names(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, "main\nwork\n"),
        ):
            assert list_sessions() == ["main", "work"]

    def test_nonzero_exit_returns_empty(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(1, ""),
        ):
            assert list_sessions() == []

    def test_empty_output_returns_empty(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, ""),
        ):
            assert list_sessions() == []


class TestNewSession:
    def test_success_returns_true(self):
        r = MagicMock()
        r.returncode = 0
        with patch("tmux_manager._local.subprocess.run", return_value=r):
            assert new_session("work") is True

    def test_failure_returns_false(self):
        r = MagicMock()
        r.returncode = 1
        with patch("tmux_manager._local.subprocess.run", return_value=r):
            assert new_session("work") is False


class TestKillSession:
    def test_success_returns_true(self):
        r = MagicMock()
        r.returncode = 0
        with patch("tmux_manager._local.subprocess.run", return_value=r):
            assert kill_session("work") is True

    def test_failure_returns_false(self):
        r = MagicMock()
        r.returncode = 1
        with patch("tmux_manager._local.subprocess.run", return_value=r):
            assert kill_session("work") is False


class TestSessionInfo:
    def _result(self, returncode: int, stdout: str) -> MagicMock:
        r = MagicMock()
        r.returncode = returncode
        r.stdout = stdout
        return r

    def test_returns_metadata(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, "3\t1700000000\t1\n"),
        ):
            info = session_info("main")
        assert info is not None
        assert info["name"] == "main"
        assert info["windows"] == 3
        assert info["attached"] is True
        assert "2023" in info["created"]

    def test_returns_none_on_failure(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(1, ""),
        ):
            assert session_info("missing") is None

    def test_returns_none_on_empty_output(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, ""),
        ):
            assert session_info("missing") is None

    def test_not_attached(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, "1\t1700000000\t0\n"),
        ):
            info = session_info("work")
        assert info is not None
        assert info["attached"] is False


class TestCapturePane:
    def _result(self, returncode: int, stdout: str) -> MagicMock:
        r = MagicMock()
        r.returncode = returncode
        r.stdout = stdout
        return r

    def test_returns_pane_content(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, "$ ls\nfile1\nfile2\n"),
        ):
            content = capture_pane("main")
        assert "$ ls" in content
        assert "file1" in content

    def test_returns_empty_on_failure(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(1, ""),
        ):
            assert capture_pane("missing") == ""

    def test_truncates_to_lines(self):
        long_output = "\n".join(f"line{i}" for i in range(100)) + "\n"
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, long_output),
        ):
            content = capture_pane("main", lines=10)
        assert len(content.splitlines()) == 10
        assert "line99" in content

    def test_no_truncation_when_short(self):
        with patch(
            "tmux_manager._local.subprocess.run",
            return_value=self._result(0, "short\n"),
        ):
            content = capture_pane("main", lines=50)
        assert content == "short"


class TestAttachSession:
    def test_calls_tmux_attach(self):
        with patch("tmux_manager._local.subprocess.run") as mock_run:
            attach_session("main")
        args = mock_run.call_args[0][0]
        assert "tmux" in args
        assert "attach-session" in args
        assert "main" in args

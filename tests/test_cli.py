import os
import pytest
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, AsyncMock

from web.cli import cli, _acquire_lock, _release_lock, LOCK_PATH


def test_cli_help():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for sub in ("fetch", "email-digest", "regenerate-history", "migrate-state-db"):
        assert sub in result.output


def test_fetch_help():
    result = CliRunner().invoke(cli, ["fetch", "--help"])
    assert result.exit_code == 0


def test_email_digest_help():
    result = CliRunner().invoke(cli, ["email-digest", "--help"])
    assert result.exit_code == 0
    for opt in ("--due", "--user-email", "--test"):
        assert opt in result.output


def test_lock_acquire_release_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("web.cli.LOCK_PATH", tmp_path / ".fetch.lock")
    assert _acquire_lock() is True
    assert (tmp_path / ".fetch.lock").exists()
    _release_lock()
    assert not (tmp_path / ".fetch.lock").exists()


def test_lock_blocks_when_held_by_alive_process(tmp_path, monkeypatch):
    lock = tmp_path / ".fetch.lock"
    monkeypatch.setattr("web.cli.LOCK_PATH", lock)
    # PID 1 (init) is always alive on macOS/Linux
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("1")
    assert _acquire_lock() is False
    # cleanup: remove the synthetic lock
    lock.unlink()


def test_lock_reclaims_stale_lock(tmp_path, monkeypatch):
    lock = tmp_path / ".fetch.lock"
    monkeypatch.setattr("web.cli.LOCK_PATH", lock)
    lock.parent.mkdir(parents=True, exist_ok=True)
    # Use a definitely-dead PID (very high number is almost certainly not in use)
    lock.write_text("99999999")
    assert _acquire_lock() is True
    _release_lock()


def test_fetch_command_runs_run_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr("web.cli.LOCK_PATH", tmp_path / ".fetch.lock")
    from web.services.fetch_runner import FetchResult
    fake_result = FetchResult(stored_count=3, fetch_history_id=1, errors=[])
    with patch("web.services.fetch_runner.run_fetch",
               new=AsyncMock(return_value=fake_result)):
        result = CliRunner().invoke(cli, ["fetch"])
    assert result.exit_code == 0
    assert "stored=3" in result.output


def test_fetch_command_nonzero_exit_on_errors(tmp_path, monkeypatch):
    monkeypatch.setattr("web.cli.LOCK_PATH", tmp_path / ".fetch.lock")
    from web.services.fetch_runner import FetchResult
    fake_result = FetchResult(stored_count=0, fetch_history_id=1, errors=["nih: timeout"])
    with patch("web.services.fetch_runner.run_fetch",
               new=AsyncMock(return_value=fake_result)):
        result = CliRunner().invoke(cli, ["fetch"])
    assert result.exit_code != 0


def test_email_digest_due_calls_dispatch_due_users(tmp_path, monkeypatch):
    from web.services.email_dispatcher import DispatchResult
    fake_results = [DispatchResult(user_id="x", sent=2, success=True)]
    with patch("web.services.email_dispatcher.dispatch_due_users",
               new=AsyncMock(return_value=fake_results)) as mock:
        result = CliRunner().invoke(cli, ["email-digest", "--due"])
    assert result.exit_code == 0
    mock.assert_awaited_once()


def test_email_digest_user_email_calls_dispatch_one_user(tmp_path):
    from web.services.email_dispatcher import DispatchResult
    fake_results = [DispatchResult(user_id="x", sent=1, success=True)]
    with patch("web.services.email_dispatcher.dispatch_one_user",
               new=AsyncMock(return_value=fake_results)) as mock:
        result = CliRunner().invoke(cli, ["email-digest", "--user-email", "x@y.com"])
    assert result.exit_code == 0
    mock.assert_awaited_once_with("x@y.com", test_mode=False)

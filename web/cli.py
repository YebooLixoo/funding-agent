"""Funding Agent administrative CLI (Task 13).

Single Click entry point with subcommands ``fetch``, ``email-digest``,
``regenerate-history``, and ``migrate-state-db``. Designed to be invoked
by ``launchd`` (or a human operator).

The ``fetch`` subcommand acquires an advisory file lock at
``data/.fetch.lock`` so concurrent invocations don't race. The lock stores
the holder's PID; if the holder is no longer alive the lock is reclaimed.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

LOCK_PATH = Path("data/.fetch.lock")


@click.group()
def cli() -> None:
    """Funding Agent administrative CLI."""
    load_dotenv()


@cli.command()
def fetch() -> None:
    """Run the fetch pipeline once. Acquires data/.fetch.lock; refuses if held."""
    if not _acquire_lock():
        click.echo("Another fetch is already running. Exiting.", err=True)
        sys.exit(1)
    try:
        from web.services.fetch_runner import run_fetch

        result = asyncio.run(run_fetch())
        click.echo(f"stored={result.stored_count} errors={len(result.errors)}")
        sys.exit(0 if not result.errors else 1)
    finally:
        _release_lock()


@cli.command("email-digest")
@click.option(
    "--due",
    "mode",
    flag_value="due",
    default=True,
    help="Dispatch to all due users (default).",
)
@click.option(
    "--user-email",
    "user_email",
    default=None,
    help="Dispatch to a single user identified by email.",
)
@click.option(
    "--test",
    "test_mode",
    is_flag=True,
    default=False,
    help="Test mode: skip broadcast list, do not write deliveries.",
)
def email_digest(mode: str, user_email: str | None, test_mode: bool) -> None:
    """Send digest emails to due users (or a specific user via --user-email)."""
    from web.services.email_dispatcher import (
        dispatch_due_users,
        dispatch_one_user,
    )

    if user_email:
        results = asyncio.run(
            dispatch_one_user(user_email, test_mode=test_mode)
        )
    else:
        results = asyncio.run(dispatch_due_users())
    click.echo(f"dispatched={len(results)}")


@cli.command("regenerate-history")
def regenerate_history() -> None:
    """Regenerate the static docs/index.html history page from platform DB."""
    from src.history_generator import HistoryGenerator
    from web.config import get_settings
    from web.database import async_session
    from web.services.history_data_source import (
        PlatformDBSource,
        fetch_admin_emailed_opportunities,
    )

    settings = get_settings()

    async def _run() -> None:
        async with async_session() as s:
            rows = await fetch_admin_emailed_opportunities(
                s, settings.admin_email
            )
        HistoryGenerator(output_dir="docs").generate(PlatformDBSource(rows))

    asyncio.run(_run())
    click.echo(f"history regenerated for {settings.admin_email}")


@cli.command("migrate-state-db")
def migrate_state_db() -> None:
    """One-time import of legacy data/state.db into platform DB."""
    from scripts.migrate_state_db import main as run_migration

    run_migration()


def _acquire_lock() -> bool:
    """Acquire the fetch lock.

    Returns ``False`` if held by an alive process. Reclaims stale locks
    (PID no longer running).
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip())
        except ValueError:
            LOCK_PATH.unlink(missing_ok=True)  # garbage contents; treat as stale
        else:
            try:
                os.kill(pid, 0)  # signal 0 = liveness probe
                return False  # alive process holds the lock
            except ProcessLookupError:
                LOCK_PATH.unlink(missing_ok=True)  # stale; clear it
            except PermissionError:
                # EPERM: process exists but we can't signal it. Still alive.
                return False
    LOCK_PATH.write_text(str(os.getpid()))
    return True


def _release_lock() -> None:
    LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    cli()

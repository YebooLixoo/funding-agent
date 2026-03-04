"""Shared utilities: logging, retry, date helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from rich.logging import RichHandler


def setup_logging(name: str = "funding_agent", log_dir: str = "outputs/logs") -> logging.Logger:
    """Configure logging with Rich handler and file output.

    Configures the 'src' parent logger so all src.* module loggers
    (e.g. src.daily_fetch, src.fetcher.nsf) inherit the handlers.

    Args:
        name: Base name for the log file (e.g. 'daily_fetch').
        log_dir: Directory for log files.

    Returns:
        The 'src' logger with handlers attached.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Configure the 'src' parent logger so all src.* module loggers inherit handlers
    src_logger = logging.getLogger("src")
    src_logger.setLevel(logging.DEBUG)

    if not src_logger.handlers:
        # Console handler with Rich
        console = RichHandler(rich_tracebacks=True, markup=True)
        console.setLevel(logging.INFO)
        src_logger.addHandler(console)

        # File handler
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(log_path / f"{name}_{timestamp}.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        )
        src_logger.addHandler(file_handler)

    return src_logger


MOUNTAIN_TZ = ZoneInfo("America/Denver")


def now_mt() -> datetime:
    """Current Mountain Time as timezone-aware datetime."""
    return datetime.now(MOUNTAIN_TZ)


def yesterday_noon_mt() -> datetime:
    """Yesterday at 12:00 PM Mountain Time."""
    now = now_mt()
    yesterday = now - timedelta(days=1)
    return yesterday.replace(hour=12, minute=0, second=0, microsecond=0)


def last_thursday_noon_mt() -> datetime:
    """Last Thursday at 12:00 PM Mountain Time.

    If today is Thursday, returns the previous Thursday (7 days ago).
    """
    now = now_mt()
    days_since_thursday = (now.weekday() - 3) % 7
    if days_since_thursday == 0:
        days_since_thursday = 7
    last_thu = now - timedelta(days=days_since_thursday)
    return last_thu.replace(hour=12, minute=0, second=0, microsecond=0)


def today_noon_mt() -> datetime:
    """Today at 12:00 PM Mountain Time."""
    now = now_mt()
    return now.replace(hour=12, minute=0, second=0, microsecond=0)


def format_date(dt: datetime | None) -> str:
    """Format a datetime for display."""
    if dt is None:
        return "N/A"
    return dt.strftime("%B %d, %Y")


def format_date_iso(dt: datetime | None) -> str:
    """Format a datetime as ISO date string."""
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d")


def parse_date(date_str: str) -> datetime | None:
    """Parse various date string formats."""
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None

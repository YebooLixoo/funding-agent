"""Shared utilities: logging, retry, date helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.logging import RichHandler


def setup_logging(name: str = "funding_agent", log_dir: str = "outputs/logs") -> logging.Logger:
    """Configure logging with Rich handler and file output."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # Console handler with Rich
        console = RichHandler(rich_tracebacks=True, markup=True)
        console.setLevel(logging.INFO)
        logger.addHandler(console)

        # File handler
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(log_path / f"{name}_{timestamp}.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        )
        logger.addHandler(file_handler)

    return logger


def utc_now() -> datetime:
    """Current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def yesterday_noon_utc() -> datetime:
    """Yesterday at 12:00 PM UTC."""
    now = utc_now()
    yesterday = now - timedelta(days=1)
    return yesterday.replace(hour=12, minute=0, second=0, microsecond=0)


def today_noon_utc() -> datetime:
    """Today at 12:00 PM UTC."""
    now = utc_now()
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

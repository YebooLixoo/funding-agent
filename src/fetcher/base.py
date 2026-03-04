"""Base fetcher abstract class."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import ssl

import certifi
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import Opportunity

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class BaseFetcher(ABC):
    """Abstract base for all data fetchers."""

    source_name: str = ""
    source_type: str = "government"

    def __init__(self, timeout: float = 30.0) -> None:
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=_DEFAULT_HEADERS,
            verify=ssl.create_default_context(cafile=certifi.where()),
        )

    async def close(self) -> None:
        await self.client.aclose()

    @abstractmethod
    async def fetch(
        self,
        window_start: datetime,
        window_end: datetime,
        keywords: Optional[list[str]] = None,
    ) -> list[Opportunity]:
        """Fetch opportunities within a time window.

        Args:
            window_start: Start of the fetch window.
            window_end: End of the fetch window.
            keywords: Search keywords to use.

        Returns:
            List of Opportunity objects found.
        """
        ...

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    async def _get(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> httpx.Response:
        """HTTP GET with retry."""
        logger.debug(f"GET {url} params={params}")
        resp = await self.client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    async def _post(self, url: str, json: Optional[dict] = None, headers: Optional[dict] = None) -> httpx.Response:
        """HTTP POST with retry."""
        logger.debug(f"POST {url}")
        resp = await self.client.post(url, json=json, headers=headers)
        resp.raise_for_status()
        return resp

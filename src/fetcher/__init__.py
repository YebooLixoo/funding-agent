"""Fetcher factory and registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Type

if TYPE_CHECKING:
    from src.fetcher.base import BaseFetcher

FETCHER_REGISTRY: Dict[str, Type[BaseFetcher]] = {}


def register_fetcher(name: str):
    """Decorator to register a fetcher class."""
    def decorator(cls):
        FETCHER_REGISTRY[name] = cls
        return cls
    return decorator


def get_fetcher(name: str, **kwargs) -> BaseFetcher:
    """Create a fetcher instance by name."""
    cls = FETCHER_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown fetcher: {name}. Available: {list(FETCHER_REGISTRY.keys())}")
    return cls(**kwargs)


# Register all fetchers on import
from src.fetcher.grants_gov import GrantsGovFetcher  # noqa: E402, F401
from src.fetcher.nsf import NSFFetcher  # noqa: E402, F401
from src.fetcher.web_scraper import WebScraperFetcher  # noqa: E402, F401

from src.fetcher.opportunity_validator import OpportunityValidator  # noqa: E402, F401

__all__ = [
    "FETCHER_REGISTRY",
    "register_fetcher",
    "get_fetcher",
    "NSFFetcher",
    "GrantsGovFetcher",
    "WebScraperFetcher",
    "OpportunityValidator",
]

"""Per-user university funding fetcher.

Discovers and scrapes a user's institution's internal funding pages
based on their profile. Uses a known mapping of university URLs with
a fallback heuristic search for unmapped institutions.
"""

from __future__ import annotations

import logging
from pathlib import Path

from omegaconf import OmegaConf

logger = logging.getLogger(__name__)

# Load institution URL mapping from config
_UNI_CONFIG_PATH = Path("conf/sources/university.yaml")
_INSTITUTION_URLS: dict[str, list[dict]] = {}

if _UNI_CONFIG_PATH.exists():
    _cfg = OmegaConf.load(str(_UNI_CONFIG_PATH))
    _raw = OmegaConf.to_container(_cfg, resolve=True)
    _INSTITUTION_URLS = _raw.get("university", {}).get("institution_urls", {})

# Common patterns for university research funding pages
_FUNDING_PATH_PATTERNS = [
    "/research/funding",
    "/research/funding-opportunities",
    "/funding/",
    "/grants/",
    "/research/grants",
    "/vpresearch/funding",
    "/doresearch/find-funding",
]


def get_university_sources(institution: str | None) -> list[dict]:
    """Get funding source URLs for a user's institution.

    Args:
        institution: The user's institution name (e.g., "University of Utah").

    Returns:
        List of {"name": ..., "label": ..., "url": ...} dicts suitable
        for passing to WebScraperFetcher.fetch_source().
    """
    if not institution:
        return []

    # Normalize for lookup
    inst_lower = institution.strip().lower()

    # Try exact match first
    for known_inst, urls in _INSTITUTION_URLS.items():
        if known_inst.lower() == inst_lower:
            return [
                {
                    "name": f"uni_{known_inst.lower().replace(' ', '_')}_{i}",
                    "label": f"{known_inst} - {entry['label']}",
                    "url": entry["url"],
                }
                for i, entry in enumerate(urls)
            ]

    # Try partial match (e.g., "Utah" matches "University of Utah")
    for known_inst, urls in _INSTITUTION_URLS.items():
        if inst_lower in known_inst.lower() or known_inst.lower() in inst_lower:
            return [
                {
                    "name": f"uni_{known_inst.lower().replace(' ', '_')}_{i}",
                    "label": f"{known_inst} - {entry['label']}",
                    "url": entry["url"],
                }
                for i, entry in enumerate(urls)
            ]

    logger.info(f"No pre-configured funding URLs for institution: {institution}")
    return []


def list_supported_institutions() -> list[str]:
    """Return list of institutions with pre-configured funding URLs."""
    return sorted(_INSTITUTION_URLS.keys())

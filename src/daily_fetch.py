"""Stage 1: Daily fetch pipeline.

Runs daily at 12:00 PM noon Mountain Time. Fetches from all sources, deduplicates,
filters by relevance, summarizes, and stores in SQLite.

Usage:
    uv run python -m src.daily_fetch
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import DictConfig, OmegaConf

from src.fetcher import get_fetcher
from src.fetcher.web_scraper import WebScraperFetcher
from src.filter.keyword_filter import FilterConfig, KeywordFilter
from src.filter.llm_filter import LLMFilter
from src.models import Opportunity
from src.state import StateDB
from src.summarizer import Summarizer
from src.utils import now_mt, setup_logging, yesterday_noon_mt

logger = logging.getLogger(__name__)


def load_config() -> DictConfig:
    """Load Hydra config from conf/ directory."""
    cfg = OmegaConf.load("conf/config.yaml")
    for extra in ["conf/sources/government.yaml", "conf/sources/industry.yaml",
                   "conf/filter.yaml", "conf/email.yaml"]:
        if Path(extra).exists():
            cfg = OmegaConf.merge(cfg, OmegaConf.load(extra))
    return cfg


async def fetch_government(cfg: DictConfig, window_start: datetime, window_end: datetime) -> list[Opportunity]:
    """Fetch from all government API sources in parallel."""
    tasks = []

    gov_cfg = cfg.get("government", {})

    # NSF
    if gov_cfg.get("nsf", {}).get("enabled", False):
        fetcher = get_fetcher("nsf")
        tasks.append(fetcher.fetch(window_start, window_end, list(gov_cfg.nsf.search_keywords)))

    # Grants.gov
    if gov_cfg.get("grants_gov", {}).get("enabled", False):
        fetcher = get_fetcher("grants_gov")
        tasks.append(fetcher.fetch(window_start, window_end, list(gov_cfg.grants_gov.search_keywords)))

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)

    opportunities = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Government fetch error: {result}")
        else:
            opportunities.extend(result)

    return opportunities


async def fetch_industry(cfg: DictConfig, window_start: datetime, window_end: datetime) -> list[Opportunity]:
    """Fetch from all industry web sources in parallel."""
    industry_cfg = cfg.get("industry", {})
    sources = industry_cfg.get("sources", [])

    if not sources:
        return []

    scraper = WebScraperFetcher()
    tasks = [
        scraper.fetch_source(
            name=src["name"],
            label=src["label"],
            url=src["url"],
            window_start=window_start,
            window_end=window_end,
        )
        for src in sources
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    await scraper.close()

    opportunities = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Industry fetch error: {result}")
        else:
            opportunities.extend(result)

    return opportunities


async def run_pipeline(cfg: DictConfig) -> None:
    """Execute the full daily fetch pipeline."""
    db = StateDB(cfg.project.db_path)

    # Step 1: Determine fetch window (Mountain Time)
    last_end = db.get_last_successful_fetch_end()
    if last_end is not None:
        window_start = last_end
    else:
        window_start = yesterday_noon_mt()
    window_end = now_mt()

    logger.info(f"Fetch window: {window_start.isoformat()} → {window_end.isoformat()}")

    # Step 2: Fetch from all sources in parallel
    gov_opps, ind_opps = await asyncio.gather(
        fetch_government(cfg, window_start, window_end),
        fetch_industry(cfg, window_start, window_end),
    )

    all_opps = gov_opps + ind_opps
    logger.info(f"Total fetched: {len(all_opps)} ({len(gov_opps)} gov, {len(ind_opps)} industry)")

    # Step 3: Deduplicate against SQLite
    new_opps = [opp for opp in all_opps if not db.is_seen(opp.composite_id)]
    logger.info(f"After dedup: {len(new_opps)} new opportunities")

    if not new_opps:
        logger.info("No new opportunities found")
        db.record_fetch("all", window_start, window_end, success=True, count=0)
        db.close()
        return

    # Step 4: Filter by relevance
    filter_cfg = cfg.get("filter", {})
    kw_filter = KeywordFilter(FilterConfig(
        primary_keywords=list(filter_cfg.get("primary_keywords", [])),
        domain_keywords=list(filter_cfg.get("domain_keywords", [])),
        exclusions=list(filter_cfg.get("exclusions", [])),
        keyword_threshold=filter_cfg.get("keyword_threshold", 0.3),
    ))

    accepted, borderline = kw_filter.filter(new_opps)

    # LLM filter for borderline cases
    if borderline:
        llm_filter = LLMFilter(model=cfg.get("llm", {}).get("model", "gpt-5.2"))
        llm_accepted = await llm_filter.filter_borderline(
            borderline, threshold=filter_cfg.get("llm_threshold", 0.5)
        )
        accepted.extend(llm_accepted)

    logger.info(f"After filtering: {len(accepted)} relevant opportunities")

    if not accepted:
        logger.info("No relevant opportunities after filtering")
        db.record_fetch("all", window_start, window_end, success=True, count=0)
        db.close()
        return

    # Step 5: Summarize
    summarizer = Summarizer(model=cfg.get("llm", {}).get("model", "gpt-5.2"))
    summarized = await summarizer.summarize_batch(accepted)

    # Step 6: Store in SQLite
    stored_count = 0
    for opp in summarized:
        if db.store_opportunity(opp):
            stored_count += 1

    logger.info(f"Stored {stored_count} new opportunities")

    # Step 7: Record successful fetch
    db.record_fetch("all", window_start, window_end, success=True, count=stored_count)

    # Cleanup old entries
    cleaned = db.cleanup_old(days=cfg.project.get("cleanup_days", 90))
    if cleaned:
        logger.info(f"Cleaned up {cleaned} old entries")

    db.close()


def main() -> None:
    load_dotenv()
    setup_logging("daily_fetch")
    cfg = load_config()
    logger.info("Starting daily fetch pipeline")

    try:
        asyncio.run(run_pipeline(cfg))
        logger.info("Daily fetch completed successfully")
    except Exception:
        logger.exception("Daily fetch failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

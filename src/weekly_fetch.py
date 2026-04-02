"""Stage 1: Weekly fetch pipeline.

Runs every Thursday at 12:00 PM noon Mountain Time. Fetches from all sources
using a 7-day window (last Thursday noon -> this Thursday noon), deduplicates,
filters by relevance, summarizes, and stores in SQLite.

Usage:
    uv run python -m src.weekly_fetch
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import DictConfig, OmegaConf

from src.emailer import Emailer
from src.fetcher import get_fetcher
from src.fetcher.grants_gov import GrantsGovFetcher
from src.fetcher.web_scraper import WebScraperFetcher
from src.filter.keyword_filter import FilterConfig, KeywordFilter
from src.filter.llm_filter import LLMFilter
from src.models import Opportunity
from src.history_generator import HistoryGenerator
from src.state import StateDB
from src.summarizer import Summarizer
from src.utils import last_thursday_noon_mt, now_mt, setup_logging

logger = logging.getLogger(__name__)


def load_config() -> DictConfig:
    """Load Hydra config from conf/ directory."""
    cfg = OmegaConf.load("conf/config.yaml")
    for extra in ["conf/sources/government.yaml", "conf/sources/industry.yaml",
                   "conf/sources/university.yaml", "conf/sources/compute.yaml",
                   "conf/filter.yaml", "conf/email.yaml"]:
        if Path(extra).exists():
            cfg = OmegaConf.merge(cfg, OmegaConf.load(extra))
    return cfg


async def fetch_government(
    cfg: DictConfig, window_start: datetime, window_end: datetime, model: str
) -> list[Opportunity]:
    """Fetch from all government API sources and web pages in parallel."""
    tasks = []
    api_fetchers = []

    gov_cfg = cfg.get("government", {})

    # NSF
    if gov_cfg.get("nsf", {}).get("enabled", False):
        fetcher = get_fetcher("nsf", model=model)
        api_fetchers.append(fetcher)
        tasks.append(fetcher.fetch(window_start, window_end, list(gov_cfg.nsf.search_keywords)))

    # NIH
    if gov_cfg.get("nih", {}).get("enabled", False):
        fetcher = get_fetcher("nih", model=model)
        api_fetchers.append(fetcher)
        tasks.append(fetcher.fetch(window_start, window_end, list(gov_cfg.nih.search_keywords)))

    # Grants.gov
    if gov_cfg.get("grants_gov", {}).get("enabled", False):
        fetcher = get_fetcher("grants_gov")
        api_fetchers.append(fetcher)
        tasks.append(fetcher.fetch(window_start, window_end, list(gov_cfg.grants_gov.search_keywords)))

    # Government web sources (DOE, USDOT, etc.)
    web_sources = gov_cfg.get("web_sources", [])
    if web_sources:
        scraper = WebScraperFetcher(model=model, source_type="government")
        for src in web_sources:
            tasks.append(scraper.fetch_source(
                name=src["name"],
                label=src["label"],
                url=src["url"],
                window_start=window_start,
                window_end=window_end,
            ))

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)

    opportunities = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Government fetch error: {result}")
        else:
            opportunities.extend(result)

    # Close all fetcher clients
    for f in api_fetchers:
        await f.close()
    if web_sources:
        await scraper.close()

    return opportunities


async def fetch_industry(
    cfg: DictConfig, window_start: datetime, window_end: datetime, model: str
) -> list[Opportunity]:
    """Fetch from all industry web sources in parallel."""
    industry_cfg = cfg.get("industry", {})
    sources = industry_cfg.get("sources", [])

    if not sources:
        return []

    scraper = WebScraperFetcher(model=model)
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


async def fetch_university(
    cfg: DictConfig, window_start: datetime, window_end: datetime, model: str
) -> list[Opportunity]:
    """Fetch from all university internal funding sources in parallel."""
    uni_cfg = cfg.get("university", {})
    sources = uni_cfg.get("sources", [])

    if not sources:
        return []

    scraper = WebScraperFetcher(model=model, source_type="university")
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
            logger.error(f"University fetch error: {result}")
        else:
            opportunities.extend(result)

    return opportunities


async def fetch_compute(
    cfg: DictConfig, window_start: datetime, window_end: datetime, model: str
) -> list[Opportunity]:
    """Fetch from all compute resource sources in parallel."""
    compute_cfg = cfg.get("compute", {})
    sources = []
    for category in ["government", "industry", "university"]:
        sources.extend(compute_cfg.get(category, []))

    if not sources:
        return []

    scraper = WebScraperFetcher(model=model, source_type="compute")
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
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Compute fetch error ({sources[i]['name']}): {result}")
        else:
            src = sources[i]
            for opp in result:
                enriched = Opportunity(
                    source=opp.source,
                    source_id=opp.source_id,
                    title=opp.title,
                    description=opp.description,
                    url=opp.url,
                    source_type="compute",
                    deadline=opp.deadline,
                    posted_date=opp.posted_date,
                    funding_amount=opp.funding_amount,
                    keywords=opp.keywords,
                    relevance_score=opp.relevance_score,
                    summary=opp.summary,
                    opportunity_status=opp.opportunity_status,
                    deadline_type=src.get("deadline_type", opp.deadline_type),
                    resource_type=src.get("resource_type"),
                    resource_provider=src.get("resource_provider"),
                    resource_scale=src.get("resource_scale"),
                    allocation_details=src.get("allocation_details"),
                    eligibility=src.get("eligibility"),
                    access_url=src.get("access_url"),
                )
                opportunities.append(enriched)

    return opportunities


async def fetch_approaching_deadlines(cfg: DictConfig) -> list[Opportunity]:
    """Fetch opportunities with approaching deadlines from Grants.gov.

    Complements the normal post_date-based fetch by finding older opportunities
    whose deadlines are approaching within the configured lookahead window.
    """
    gov_cfg = cfg.get("government", {})
    grants_cfg = gov_cfg.get("grants_gov", {})

    if not grants_cfg.get("enabled", False):
        return []

    lookahead_days = grants_cfg.get("deadline_lookahead_days", 30)
    keywords = list(grants_cfg.get("search_keywords", []))

    fetcher = GrantsGovFetcher()
    try:
        return await fetcher.fetch_approaching_deadlines(
            keywords=keywords,
            lookahead_days=lookahead_days,
        )
    except Exception:
        logger.exception("Approaching-deadline fetch failed")
        return []
    finally:
        await fetcher.close()


async def run_pipeline(cfg: DictConfig) -> None:
    """Execute the weekly fetch pipeline."""
    db = StateDB(cfg.project.db_path)
    model = cfg.get("llm", {}).get("model", "gpt-5.2")

    # Step 1: Determine fetch window (7-day window, Mountain Time)
    last_end = db.get_last_successful_fetch_end()
    if last_end is not None:
        window_start = last_end
    else:
        window_start = last_thursday_noon_mt()
    window_end = now_mt()

    logger.info(f"Fetch window: {window_start.isoformat()} -> {window_end.isoformat()}")

    # Step 2: Fetch from all sources in parallel
    gov_opps, ind_opps, uni_opps, compute_opps = await asyncio.gather(
        fetch_government(cfg, window_start, window_end, model),
        fetch_industry(cfg, window_start, window_end, model),
        fetch_university(cfg, window_start, window_end, model),
        fetch_compute(cfg, window_start, window_end, model),
    )

    all_opps = gov_opps + ind_opps + uni_opps + compute_opps
    logger.info(
        f"Total fetched: {len(all_opps)} "
        f"({len(gov_opps)} gov, {len(ind_opps)} industry, "
        f"{len(uni_opps)} university, {len(compute_opps)} compute)"
    )

    # Step 2b: Fetch approaching-deadline opportunities from Grants.gov
    deadline_opps = await fetch_approaching_deadlines(cfg)
    if deadline_opps:
        logger.info(f"Approaching deadlines: {len(deadline_opps)} opportunities")
        all_opps.extend(deadline_opps)

    # Step 2c: Deduplicate within current batch (cross-source)
    seen_titles = []
    deduped_opps = []
    for opp in all_opps:
        from difflib import SequenceMatcher
        import re as _re
        norm = _re.sub(r'\s+', ' ', _re.sub(r'[^\w\s]', '', opp.title.lower().strip()))
        is_dup = False
        for seen in seen_titles:
            if SequenceMatcher(None, norm, seen).ratio() >= 0.80:
                logger.debug(f"Batch dedup: skipping '{opp.title[:60]}' (similar to existing)")
                is_dup = True
                break
        if not is_dup:
            seen_titles.append(norm)
            deduped_opps.append(opp)
    all_opps = deduped_opps
    logger.info(f"After batch dedup: {len(all_opps)} unique opportunities")

    # Step 3: Deduplicate against SQLite (by composite_id, URL, and title similarity)
    new_opps = [
        opp for opp in all_opps
        if not db.is_seen(opp.composite_id)
        and not db.is_url_seen(opp.url)
        and not db.is_title_similar(opp.title)
    ]
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
        career_keywords=list(filter_cfg.get("career_keywords", [])),
        faculty_keywords=list(filter_cfg.get("faculty_keywords", [])),
        compute_keywords=list(filter_cfg.get("compute_keywords", [])),
        keyword_threshold=filter_cfg.get("keyword_threshold", 0.3),
    ))

    accepted, borderline = kw_filter.filter(new_opps)

    # LLM filter for borderline cases
    if borderline:
        llm_filter = LLMFilter(model=model)
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
    summarizer = Summarizer(model=model)
    summarized = await summarizer.summarize_batch(accepted)

    # Step 6: Store in SQLite
    stored_count = 0
    for opp in summarized:
        if db.store_opportunity(opp):
            stored_count += 1

    logger.info(f"Stored {stored_count} new opportunities")

    # Step 7: Record successful fetch
    db.record_fetch("all", window_start, window_end, success=True, count=stored_count)

    # Step 8: Generate digest HTML for evening email
    _generate_digest(cfg, db)

    # Step 9: Regenerate history page so it's current when digest links to it
    try:
        history_output_dir = cfg.get("email", {}).get("history_output_dir", "outputs/history")
        history_gen = HistoryGenerator(output_dir=history_output_dir)
        history_gen.generate(db)
    except Exception:
        logger.exception("History page generation failed (non-fatal)")

    # Cleanup old entries
    cleaned = db.cleanup_old(days=cfg.project.get("cleanup_days", 90))
    if cleaned:
        logger.info(f"Cleaned up {cleaned} old entries")

    db.close()


def _generate_digest(cfg: DictConfig, db: StateDB) -> None:
    """Generate and archive digest HTML for the evening email pipeline."""
    email_cfg = cfg.get("email", {})

    # Refresh quarterly opps: if their deadline has passed, update to next
    # quarter and reset to pending so they reappear as reminders
    db.refresh_quarterly_deadlines()

    pending = db.get_pending_opportunities()
    lookahead = email_cfg.get("deadline_lookahead_days", 30)
    upcoming = db.get_upcoming_deadlines(days=lookahead)
    coming_soon = db.get_coming_soon_opportunities()

    if not pending and not upcoming and not coming_soon:
        logger.info("No opportunities for digest, skipping generation")
        return

    # Exclude coming_soon from main sections — they get their own dedicated section
    # Rolling/quarterly stay in their normal source-type sections with inline badges
    open_pending = [o for o in pending if o.get("opportunity_status") != "coming_soon"]
    gov_opps = [o for o in open_pending if o.get("source_type") == "government"]
    ind_opps = [o for o in open_pending if o.get("source_type") == "industry"]
    uni_opps = [o for o in open_pending if o.get("source_type") == "university"]
    compute_opps_list = [o for o in open_pending if o.get("source_type") == "compute"]

    emailer = Emailer(
        smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
        smtp_port=email_cfg.get("smtp_port", 587),
        use_tls=email_cfg.get("use_tls", True),
        archive_dir=email_cfg.get("digest_archive_dir", "outputs/digests"),
    )

    date_str = datetime.now().strftime("%B %d, %Y")
    history_url = email_cfg.get("history_url", "")
    html = emailer.compose(
        government_opps=gov_opps,
        industry_opps=ind_opps,
        upcoming_deadlines=upcoming,
        date_str=date_str,
        history_url=history_url or None,
        coming_soon_opps=coming_soon,
        university_opps=uni_opps,
        compute_opps=compute_opps_list,
    )

    # Archive with date-only filename so weekly_email can find it
    date_tag = datetime.now().strftime("%Y%m%d")
    emailer.archive_digest(html, date_str=date_tag)
    logger.info(
        f"Digest pre-generated: {len(pending)} opps, {len(upcoming)} deadlines, "
        f"{len(coming_soon)} coming soon, {len(uni_opps)} university, "
        f"{len(compute_opps_list)} compute"
    )


def main() -> None:
    load_dotenv()
    setup_logging("weekly_fetch")
    cfg = load_config()
    logger.info("Starting weekly fetch pipeline")

    try:
        asyncio.run(run_pipeline(cfg))
        logger.info("Weekly fetch completed successfully")
    except Exception:
        logger.exception("Weekly fetch failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

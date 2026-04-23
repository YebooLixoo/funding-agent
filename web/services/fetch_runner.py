"""End-to-end fetch orchestration against the platform DB (Task 11).

Replaces ``src/weekly_fetch.py::run_pipeline``. Reads search terms + filter
keywords from the DB (populated by Task 6 ``keyword_sync``), invokes the
existing ``src/`` library fetchers, filters & summarizes, writes through
``opportunity_writer.upsert_opportunity``, auto-scores via
``auto_scorer.score_new_opportunities``, and records ``fetch_history``.

Multi-session boundary contract (Codex review concern D7):
    Phase 1 — config snapshot (short async session, NO remote I/O).
    Phase 2 — remote fetch + LLM (NO session held).
    Phase 3 — write batch (short async session).
    Phase 4 — auto-score + history + bootstrap (short async session).

The Phase-2 helpers (``_collect_opportunities``, ``_filter_opps``,
``_summarize_batch``) are top-level coroutines specifically so tests can
patch them without monkeying with method bindings.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from omegaconf import OmegaConf
from sqlalchemy import select

from src.fetcher import get_fetcher
from src.fetcher.grants_gov import GrantsGovFetcher
from src.fetcher.web_scraper import WebScraperFetcher
from src.filter.keyword_filter import FilterConfig, KeywordFilter
from src.filter.llm_filter import LLMFilter
from src.summarizer import Summarizer
from src.utils import last_thursday_noon_mt, now_mt
from web.config import get_settings
from web.database import async_session
from web.models.fetch_history import FetchHistory
from web.models.source_bootstrap import SourceBootstrap
from web.models.system_keywords import SystemFilterKeyword, SystemSearchTerm
from web.models.user import User
from web.services.auto_scorer import score_new_opportunities
from web.services.keyword_sync import resync_system_tables
from web.services.opportunity_writer import upsert_opportunity

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    stored_count: int
    fetch_history_id: int | None
    errors: list[str] = field(default_factory=list)


# --- Public entry point ----------------------------------------------------


async def run_fetch(now: datetime | None = None) -> FetchResult:
    """Run a single fetch end-to-end. See module docstring for phase layout."""
    settings = get_settings()
    now_dt = now or now_mt()

    # Phase 1 — config snapshot (short session, no remote I/O)
    admin_id, by_source, filter_kws = await _load_config(settings)

    # Phase 2 — remote fetch + LLM (NO session held)
    window_start = last_thursday_noon_mt()
    window_end = now_dt

    raw_opps, errors = await _collect_opportunities(
        by_source, window_start, window_end, settings
    )
    raw_opps = _batch_dedup(raw_opps)
    accepted = await _filter_opps(raw_opps, filter_kws=filter_kws, settings=settings)
    summarized = await _summarize_batch(accepted, settings.llm_model)

    # Phase 3 — write
    stored_ids = await _write_opps(summarized)

    # Phase 4 — auto-score, bootstrap-mark, history
    fh_id = await _record_run(
        stored_ids, window_start, window_end, errors, by_source
    )

    return FetchResult(
        stored_count=len(stored_ids), fetch_history_id=fh_id, errors=errors
    )


# --- Phase 1: load DB-side config ------------------------------------------


async def _load_config(settings):
    """Fetch admin, resync system tables, snapshot search terms + filter kws."""
    async with async_session() as s:
        admin = (
            await s.execute(
                select(User).where(
                    User.email == settings.admin_email, User.is_admin.is_(True)
                )
            )
        ).scalar_one()

        # Idempotent backstop: ensures system_* tables match admin's keywords.
        await resync_system_tables(s, admin.id)

        st_rows = (
            await s.execute(
                select(SystemSearchTerm.term, SystemSearchTerm.target_source).where(
                    SystemSearchTerm.is_active.is_(True),
                    SystemSearchTerm.source_user_id == admin.id,
                )
            )
        ).all()
        kw_rows = (
            await s.execute(
                select(SystemFilterKeyword.keyword, SystemFilterKeyword.category).where(
                    SystemFilterKeyword.is_active.is_(True),
                    SystemFilterKeyword.source_user_id == admin.id,
                )
            )
        ).all()
        await s.commit()

    by_source: dict[str, list[str]] = {}
    for term, src in st_rows:
        by_source.setdefault(src, []).append(term)
    return admin.id, by_source, list(kw_rows)


# --- Phase 2: remote fetch (NO session) ------------------------------------


async def _collect_opportunities(by_source, window_start, window_end, settings):
    """Fan out per-source fetchers in parallel; isolate per-source errors.

    Returns ``(opportunities, error_messages)``. Ports the structure of
    ``src/weekly_fetch.py``'s ``fetch_government`` + ``fetch_industry`` +
    ``fetch_university`` + ``fetch_compute`` + ``fetch_approaching_deadlines``,
    but consumes ``by_source`` (per-source term lists from the DB) instead of
    YAML-defined ``search_keywords``.

    Source URL lists still come from ``conf/sources/*.yaml``.
    """
    cfg = _load_yaml_sources()
    bootstrap_sources = await _get_unbootstrapped_sources(cfg)
    if bootstrap_sources:
        logger.info(
            "Bootstrap: %d sources need first-time fetch: %s",
            len(bootstrap_sources),
            sorted(bootstrap_sources),
        )

    tasks: list = []
    api_fetchers: list = []
    scrapers: list = []
    compute_sources: list = []

    gov_cfg = cfg.get("government", {}) or {}

    # NSF / NIH / Grants.gov
    for api_name in ("nsf", "nih", "grants_gov"):
        if not gov_cfg.get(api_name, {}).get("enabled", False):
            continue
        terms = by_source.get(api_name, [])
        if not terms:
            continue
        if api_name in ("nsf", "nih"):
            fetcher = get_fetcher(api_name, model=settings.llm_model)
        else:
            fetcher = get_fetcher(api_name)
        api_fetchers.append(fetcher)
        ws = None if api_name in bootstrap_sources else window_start
        tasks.append(_safe_fetch(api_name, fetcher.fetch(ws, window_end, terms)))

    # Government web sources (DOE, USDOT, etc.)
    gov_scraper = None
    for src in (gov_cfg.get("web_sources") or []):
        if gov_scraper is None:
            gov_scraper = WebScraperFetcher(
                model=settings.llm_model, source_type="government"
            )
            scrapers.append(gov_scraper)
        ws = None if src["name"] in bootstrap_sources else window_start
        tasks.append(
            _safe_fetch(
                src["name"],
                gov_scraper.fetch_source(
                    name=src["name"],
                    label=src["label"],
                    url=src["url"],
                    window_start=ws,
                    window_end=window_end,
                ),
            )
        )

    # Industry web sources
    ind_scraper = None
    for src in (cfg.get("industry", {}).get("sources") or []):
        if ind_scraper is None:
            ind_scraper = WebScraperFetcher(model=settings.llm_model)
            scrapers.append(ind_scraper)
        ws = None if src["name"] in bootstrap_sources else window_start
        tasks.append(
            _safe_fetch(
                src["name"],
                ind_scraper.fetch_source(
                    name=src["name"],
                    label=src["label"],
                    url=src["url"],
                    window_start=ws,
                    window_end=window_end,
                ),
            )
        )

    # University internal sources
    uni_scraper = None
    for src in (cfg.get("university", {}).get("sources") or []):
        if uni_scraper is None:
            uni_scraper = WebScraperFetcher(
                model=settings.llm_model, source_type="university"
            )
            scrapers.append(uni_scraper)
        ws = None if src["name"] in bootstrap_sources else window_start
        tasks.append(
            _safe_fetch(
                src["name"],
                uni_scraper.fetch_source(
                    name=src["name"],
                    label=src["label"],
                    url=src["url"],
                    window_start=ws,
                    window_end=window_end,
                ),
            )
        )

    # Compute sources (curated metadata enriched after fetch)
    compute_scraper = None
    for cat in ("government", "industry", "university"):
        for src in (cfg.get("compute", {}).get(cat) or []):
            compute_sources.append(src)
            if compute_scraper is None:
                compute_scraper = WebScraperFetcher(
                    model=settings.llm_model, source_type="compute"
                )
                scrapers.append(compute_scraper)
            ws = None if src["name"] in bootstrap_sources else window_start
            tasks.append(
                _safe_fetch(
                    src["name"],
                    compute_scraper.fetch_source(
                        name=src["name"],
                        label=src["label"],
                        url=src["url"],
                        window_start=ws,
                        window_end=window_end,
                    ),
                )
            )

    # Grants.gov approaching-deadlines pass (was missing from v1)
    grants_terms = by_source.get("grants_gov", [])
    if grants_terms and gov_cfg.get("grants_gov", {}).get("enabled", False):
        gg = GrantsGovFetcher()
        api_fetchers.append(gg)
        lookahead = gov_cfg.get("grants_gov", {}).get("deadline_lookahead_days", 30)
        tasks.append(
            _safe_fetch(
                "grants_gov_deadlines",
                gg.fetch_approaching_deadlines(
                    keywords=grants_terms, lookahead_days=lookahead
                ),
            )
        )

    if not tasks:
        return [], []

    # Per-source error isolation: ``_safe_fetch`` always returns ``(name, val)``
    # so ``return_exceptions=False`` is fine here.
    raw_results = await asyncio.gather(*tasks)

    opps: list = []
    errors: list[str] = []
    compute_index = {s["name"]: s for s in compute_sources}
    for name, batch_or_err in raw_results:
        if isinstance(batch_or_err, Exception):
            errors.append(f"{name}: {batch_or_err}")
            logger.error("Fetch error for %s: %s", name, batch_or_err)
        else:
            for opp in batch_or_err:
                opps.append(_enrich_compute(opp, compute_index))

    # Cleanup async clients
    for f in api_fetchers:
        try:
            await f.close()
        except Exception:
            logger.debug("close() failed for %s", f, exc_info=True)
    for sc in scrapers:
        try:
            await sc.close()
        except Exception:
            logger.debug("close() failed for scraper", exc_info=True)

    return opps, errors


async def _safe_fetch(name: str, coro):
    """Wrap a fetch coroutine; return ``(name, result_or_exception)``."""
    try:
        return name, await coro
    except Exception as exc:  # noqa: BLE001 — surfaced as error message
        return name, exc


_RELEVANCE_SCORE = {"very_high": 0.9, "high": 0.8, "medium": 0.7}


def _enrich_compute(opp, compute_index: dict):
    """Copy curated YAML metadata onto compute opportunities."""
    if opp.source_type != "compute":
        return opp
    src = compute_index.get(opp.source)
    if not src:
        return opp
    return replace(
        opp,
        relevance_score=_RELEVANCE_SCORE.get(src.get("relevance", "medium"), 0.7),
        deadline_type=src.get("deadline_type", opp.deadline_type),
        resource_type=src.get("resource_type"),
        resource_provider=src.get("resource_provider"),
        resource_scale=src.get("resource_scale"),
        allocation_details=src.get("allocation_details"),
        eligibility=src.get("eligibility"),
        access_url=src.get("access_url"),
    )


def _batch_dedup(opps: list) -> list:
    """Cross-source title-similarity dedup within a single batch.

    Ports ``src/weekly_fetch.py:361-376``. Threshold 0.80 matches
    ``opportunity_writer._TITLE_THRESHOLD``.
    """
    seen: list[str] = []
    out: list = []
    for opp in opps:
        norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", opp.title.lower().strip()))
        if any(SequenceMatcher(None, norm, s).ratio() >= 0.80 for s in seen):
            continue
        seen.append(norm)
        out.append(opp)
    return out


async def _filter_opps(opps, *, filter_kws, settings):
    """Run KeywordFilter (+ LLMFilter for borderline) on non-compute opps.

    Compute opportunities bypass the keyword filter — they are pre-curated via
    YAML and validated by ``OpportunityValidator``. See ``src/weekly_fetch.py:395``.
    """
    non_compute = [o for o in opps if o.source_type != "compute"]
    compute = [o for o in opps if o.source_type == "compute"]

    cfg = FilterConfig(
        primary_keywords=[kw for kw, cat in filter_kws if cat == "primary"],
        domain_keywords=[kw for kw, cat in filter_kws if cat == "domain"],
        career_keywords=[kw for kw, cat in filter_kws if cat == "career"],
        faculty_keywords=[kw for kw, cat in filter_kws if cat == "faculty"],
        compute_keywords=[],
        exclusions=[kw for kw, cat in filter_kws if cat == "exclusion"],
        keyword_threshold=settings.keyword_threshold,
    )
    accepted, borderline = KeywordFilter(cfg).filter(non_compute)
    if borderline:
        llm_accepted = await LLMFilter(model=settings.llm_model).filter_borderline(
            borderline, threshold=settings.llm_threshold
        )
        accepted = list(accepted) + list(llm_accepted)
    return list(accepted) + compute


async def _summarize_batch(opps, model: str):
    """LLM-summarize a batch of opportunities."""
    if not opps:
        return []
    return await Summarizer(model=model).summarize_batch(opps)


# --- Phase 3: write to DB --------------------------------------------------


async def _write_opps(opps: list) -> list:
    """Upsert opportunities; return list of newly-inserted row IDs."""
    stored: list = []
    if not opps:
        return stored
    async with async_session() as s:
        for opp in opps:
            row, was_new = await upsert_opportunity(s, opp)
            if was_new:
                stored.append(row.id)
        await s.commit()
    return stored


# --- Phase 4: score, bootstrap-mark, history ------------------------------


async def _record_run(
    stored_ids: list,
    window_start: datetime,
    window_end: datetime,
    errors: list[str],
    by_source: dict[str, list[str]],
) -> int | None:
    """Score new opps, mark successful sources as bootstrapped, write history."""
    fh_id: int | None = None
    async with async_session() as s:
        if stored_ids:
            await score_new_opportunities(s, stored_ids)

        # Bootstrap marking: any known source NOT present in errors counts as
        # successfully fetched and gets a SourceBootstrap row (presence == done).
        # Ports ``src/state.py::mark_source_bootstrapped`` +
        # ``src/weekly_fetch.py::_mark_bootstrapped``.
        await _mark_bootstraps(s, errors)

        fh = FetchHistory(
            source="all",
            fetch_window_start=window_start,
            fetch_window_end=window_end,
            success=not errors,
            count=len(stored_ids),
            error_msg="; ".join(errors) if errors else None,
        )
        s.add(fh)
        await s.flush()
        fh_id = fh.id
        await s.commit()
    return fh_id


async def _mark_bootstraps(s, errors: list[str]) -> None:
    """Insert ``SourceBootstrap`` rows for sources that just fetched cleanly.

    The model treats row presence as "bootstrap complete" (no per-row state
    flag). We therefore only insert for sources that:
      1) appear in the YAML known-source list,
      2) do NOT have a bootstrap row already, and
      3) do NOT appear in this run's per-source error list.
    """
    cfg = _load_yaml_sources()
    known = _collect_known_sources(cfg)
    if not known:
        return

    failed_sources = {err.split(":", 1)[0].strip() for err in errors}

    existing = (
        await s.execute(select(SourceBootstrap.source_name))
    ).scalars().all()
    already = set(existing)

    now_dt = datetime.now(timezone.utc)
    for name, stype in known:
        if name in already or name in failed_sources:
            continue
        s.add(
            SourceBootstrap(
                source_name=name, source_type=stype, bootstrapped_at=now_dt
            )
        )
        logger.info("Source '%s' (%s) marked as bootstrapped", name, stype)


# --- Source/config helpers -------------------------------------------------


def _load_yaml_sources() -> dict:
    """Load + merge the source YAMLs into a plain dict."""
    cfg = OmegaConf.load("conf/config.yaml")
    for extra in (
        "conf/sources/government.yaml",
        "conf/sources/industry.yaml",
        "conf/sources/university.yaml",
        "conf/sources/compute.yaml",
    ):
        if Path(extra).exists():
            cfg = OmegaConf.merge(cfg, OmegaConf.load(extra))
    return OmegaConf.to_container(cfg, resolve=True)


def _collect_known_sources(cfg: dict) -> list[tuple[str, str]]:
    """Mirror ``src/weekly_fetch.py::_collect_known_sources``."""
    known: list[tuple[str, str]] = []
    gov_cfg = cfg.get("government", {}) or {}
    for api in ("nsf", "nih", "grants_gov"):
        if gov_cfg.get(api, {}).get("enabled", False):
            known.append((api, "government"))
    for src in (gov_cfg.get("web_sources") or []):
        known.append((src["name"], "government"))
    for src in (cfg.get("industry", {}).get("sources") or []):
        known.append((src["name"], "industry"))
    for src in (cfg.get("university", {}).get("sources") or []):
        known.append((src["name"], "university"))
    for cat in ("government", "industry", "university"):
        for src in (cfg.get("compute", {}).get(cat) or []):
            known.append((src["name"], "compute"))
    return known


async def _get_unbootstrapped_sources(cfg: dict) -> set[str]:
    """Return YAML-known source names that have no ``SourceBootstrap`` row."""
    known = {name for name, _ in _collect_known_sources(cfg)}
    async with async_session() as s:
        rows = (await s.execute(select(SourceBootstrap.source_name))).scalars().all()
    return known - set(rows)

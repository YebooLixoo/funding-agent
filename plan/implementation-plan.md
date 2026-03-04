# Funding Opportunity Search Agent System

## Overview

Automated Python system that searches funding/grant opportunities from government APIs and industry websites weekly, filters for AI + transportation relevance, and emails a digest every Thursday at 8:00 PM to bo.yu@utah.edu.

---

## Architecture (Two-Stage Pipeline)

```
STAGE 1: Daily Fetch (every day at 12:00 PM noon)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Fetchers   │───▶│  Deduplicate │───▶│   Filter     │───▶│  Summarize   │
│  (parallel)  │    │  (SQLite)    │    │ (keyword+LLM)│    │  & Store DB  │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘

STAGE 2: Weekly Email (every Thursday at 8:00 PM)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Query DB    │───▶│  Compose     │───▶│  Send Email  │
│ (last 7 days)│    │  HTML Digest │    │  (Gmail SMTP)│
└──────────────┘    └──────────────┘    └──────────────┘
```

**Daily fetch window**: Yesterday 12:00 PM → Today 12:00 PM (exact 24h, no gaps)
- If a run fails, next run extends window back to `last_successful_fetch_end` → never misses updates

**Why two stages?**
- **Rate limits**: Grants.gov allows 60 req/min — daily fetching spreads the load
- **Punctual email**: Thursday 8 PM email compiles pre-stored data instantly (no delay)
- **Resilience**: If one day's fetch fails, next day auto-recovers the missed window
- **Freshness**: Opportunities are captured within 24 hours of posting

---

## Implementation Plan

### Step 1: Project Setup
- Create project with `uv init funding-agent`
- Add dependencies to `pyproject.toml`
- Set up Hydra config structure
- Create `.env.example` with required API keys

**Key dependencies**: `httpx`, `feedparser`, `beautifulsoup4`, `jinja2`, `hydra-core`, `omegaconf`, `python-dotenv`, `openai`, `rich`, `tenacity`, `certifi`

### Step 2: Core Data Model
- `src/models.py`: `Opportunity` frozen dataclass with fields: id, source, source_type, title, description, url, deadline, posted_date, funding_amount, keywords

### Step 3: State Management
- `src/state.py`: SQLite database with 3 tables:
  - **`seen_opportunities`**: All fetched opportunities (id, source, title, url, summary, deadline, posted_date, relevance_score, status [`pending_email`|`emailed`|`expired`], fetched_at)
  - **`fetch_history`**: Track each fetch run (source, fetch_window_start, fetch_window_end, success, count, error_msg)
    - Key field: `last_successful_fetch_end` — used by next run to determine where to start, ensuring **no gaps if a run fails or is delayed**
  - **`email_history`**: Track each email sent (sent_at, count, success)
- Dedup by composite ID (`{source}_{source_id}`)
- Query for upcoming deadlines: `SELECT * FROM seen_opportunities WHERE deadline BETWEEN now AND now+30days`
- Auto-cleanup entries older than 90 days

### Step 4: Government API Fetchers
- `src/fetcher/nsf.py`: Dual approach — Awards API for keyword search + RSS feed for new funding announcements
- `src/fetcher/grants_gov.py`: POST with `query` (AND operator), `post_date` range, pagination

### Step 5: Industry Web Scraper
- `src/fetcher/web_scraper.py`: Generic scraper using `httpx` + `BeautifulSoup`
  - Fetch page HTML, extract text content
  - Hash content for change detection
  - Parse for funding-related keywords, deadlines, amounts
- Config-driven: each industry source defined in `conf/sources/industry.yaml`

### Step 6: Relevance Filter (Keyword + LLM Hybrid)
- `src/filter/keyword_filter.py`: Fast first-pass keyword matching
  - **Primary topics** (must match ≥1): AI, machine learning, deep learning, neural network, computer vision, NLP, autonomous
  - **Domain topics** (boost score): transportation, vehicle, traffic, mobility, energy, grid, electricity, disaster, emergency, resilience, network, infrastructure, smart city
  - **Exclusions** (skip): K-12, undergraduate only, postdoc only
  - Score = weighted sum, threshold at 0.3
- `src/filter/llm_filter.py`: GPT-5.2 for borderline cases (score 0.3-0.6)

### Step 7: Summarizer (LLM-powered)
- `src/summarizer.py`: Use GPT-5.2 to generate concise summaries for each opportunity

### Step 8: Email System (Gmail SMTP)
- `src/emailer.py`: Gmail SMTP sender via App Password
  - **Section 1**: New Government Opportunities (grouped by NSF/Grants.gov)
  - **Section 2**: New Industry Opportunities (grouped by company)
  - **Section 3**: Upcoming Deadlines (known deadlines within 30 days)
  - Professional styling with University of Utah red (#CC0000)

### Step 9: Daily Fetch Pipeline
- `src/daily_fetch.py`: Entry point for Stage 1

### Step 10: Weekly Email Pipeline
- `src/weekly_email.py`: Entry point for Stage 2

### Step 11: Scheduling (Two LaunchAgents)
- `launchd/com.boyu.funding-agent.daily.plist`: Daily fetch at 12:00 PM noon
- `launchd/com.boyu.funding-agent.weekly.plist`: Weekly email Thu 8:00 PM

### Step 12: Testing & Verification
- Unit tests for fetchers, filters, emailer, and state management

---

## Design Decisions

- **Email**: Gmail SMTP with App Password, multiple recipients supported
- **AI Filtering**: Keyword-first + GPT-5.2 for borderline cases and summaries
- **SAM.gov**: Removed due to legal risk concerns around scraping sensitivity
- **Deadline reminders**: Include "Upcoming Deadlines" section for known deadlines within 30 days

## Implementation Status

- [x] Step 1: Project setup
- [x] Step 2: Core data model
- [x] Step 3: State management (SQLite)
- [x] Step 4: Government API fetchers (NSF, Grants.gov)
- [x] Step 5: Industry web scraper (16 sources)
- [x] Step 6: Relevance filter (keyword + LLM)
- [x] Step 7: Summarizer (GPT-5.2)
- [x] Step 8: Email system (multi-recipient Gmail SMTP)
- [x] Step 9: Daily fetch pipeline
- [x] Step 10: Weekly email pipeline
- [x] Step 11: Scheduling (LaunchAgents installed)
- [x] Step 12: Testing (21/21 tests passing)

## Changes from Original Plan

| Item | Original | Actual |
|------|----------|--------|
| SAM.gov | Included | Removed (legal risk) |
| LLM provider | Anthropic Claude Haiku | OpenAI GPT-5.2 |
| Email recipients | Single (bo.yu@utah.edu) | Multiple (4 recipients) |
| OpenAI API param | `max_tokens` | `max_completion_tokens` (GPT-5.2 requirement) |
| Grants.gov API body | Flat pagination | Nested `sort_order` array format |

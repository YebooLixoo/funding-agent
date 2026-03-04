# Funding Opportunity Search Agent

Automated system that discovers funding and grant opportunities relevant to **AI + Transportation** research from government APIs and industry websites, then delivers a curated HTML digest via email every Thursday.

Built for the [University of Utah](https://www.utah.edu/) research group.

## How It Works

The system runs as a **two-stage pipeline** scheduled via macOS LaunchAgents:

```
STAGE 1: Daily Fetch (every day at 12:00 PM MT)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Fetchers   │───>│  Deduplicate │───>│   Filter     │───>│  Summarize   │
│  (parallel)  │    │  (SQLite)    │    │ (keyword+LLM)│    │  & Store DB  │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘

STAGE 2: Weekly Email (every Thursday at 8:00 PM MT)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Query DB    │───>│  Compose     │───>│  Send Email  │
│ (last 7 days)│    │  HTML Digest │    │  (Gmail SMTP)│
└──────────────┘    └──────────────┘    └──────────────┘
```

**Why two stages?**

- **Rate limits** — Grants.gov and NSF have rate limits; daily fetching spreads the load.
- **Punctual email** — Thursday 8 PM email compiles pre-stored data instantly.
- **Resilience** — If one day's fetch fails, the next day auto-recovers the missed window.
- **Freshness** — Opportunities are captured within 24 hours of posting.

## Funding Sources

### Government APIs

| Source | Method | Notes |
|--------|--------|-------|
| **NSF** | REST API + RSS feed | Awards API for keyword search; RSS for new funding announcements |
| **Grants.gov** | REST API (Simpler API v1) | Federal grant opportunities aggregator; API key required |

### Industry (Web Scraping)

| Company | Program | Relevance |
|---------|---------|-----------|
| Amazon | Research Awards | High |
| Google | Research Scholar Program | High |
| NVIDIA | Academic Hardware Grant | Very High |
| Microsoft | Azure Research Credits | Medium |
| Meta | Llama Impact Grants | Medium |
| Apple | Scholars in AI/ML | Medium |
| Qualcomm | Innovation Fellowship | High |
| Samsung | Global Research Outreach | Medium |
| Toyota | Research Institute | Very High |
| Ford | University Research | Very High |
| Bosch | University Partnerships | High |
| Cisco | Research Funding | Medium |
| IBM | Faculty Awards | Medium |
| Adobe | Data Science Awards | Low |
| DOE | Funding Opportunities | High |
| USDOT | Grant Programs | Very High |

See [`docs/funding_sources.md`](docs/funding_sources.md) for full URLs and API details.

## Relevance Filtering

A two-pass hybrid approach ensures high-quality results:

1. **Keyword Filter (fast)** — Matches against primary AI keywords (machine learning, deep learning, autonomous, etc.) and domain keywords (transportation, vehicle, traffic, infrastructure, etc.). Exclusions like "K-12" and "undergraduate only" are auto-rejected.
2. **LLM Filter (borderline cases)** — Opportunities scoring between 0.3-0.6 are sent to GPT-5.2 for contextual evaluation against the professor's research profile. Only used when ambiguous (~$0.01/call).

Each accepted opportunity is then summarized by GPT-5.2 into 2-3 sentences highlighting relevance to AI + transportation.

## Project Structure

```
funding-agent/
├── conf/                          # Hydra configuration
│   ├── config.yaml                # Main config (LLM model, DB path)
│   ├── sources/                   # Data source configs
│   │   ├── government.yaml        # NSF, Grants.gov API settings
│   │   └── industry.yaml          # 16 industry source URLs
│   ├── filter.yaml                # Keywords & relevance thresholds
│   └── email.yaml                 # SMTP settings & recipient list
├── src/
│   ├── daily_fetch.py             # Stage 1: Daily fetch pipeline
│   ├── weekly_email.py            # Stage 2: Weekly email pipeline
│   ├── models.py                  # Opportunity dataclass
│   ├── state.py                   # SQLite state management
│   ├── fetcher/                   # Data retrieval modules
│   │   ├── base.py                # BaseFetcher ABC with retry
│   │   ├── nsf.py                 # NSF API + RSS fetcher
│   │   ├── grants_gov.py          # Grants.gov API fetcher
│   │   └── web_scraper.py         # Generic industry page scraper
│   ├── filter/                    # Relevance filtering
│   │   ├── keyword_filter.py      # Fast keyword matching
│   │   └── llm_filter.py          # GPT-5.2 for borderline cases
│   ├── summarizer.py              # GPT-5.2 opportunity summaries
│   ├── emailer.py                 # Gmail SMTP sender
│   └── utils.py                   # Logging, date helpers
├── templates/
│   └── digest.html                # Jinja2 email template
├── data/
│   └── state.db                   # SQLite database (gitignored)
├── launchd/                       # macOS LaunchAgent plists
├── scripts/                       # Install/uninstall & manual triggers
├── tests/                         # Unit tests
└── outputs/
    ├── logs/                      # Execution logs
    └── digests/                   # Archived HTML digests
```

## Setup

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- macOS (for LaunchAgent scheduling)

### 1. Install Dependencies

```bash
cd ~/funding-agent
uv sync
```

### 2. Configure API Keys

Copy the example and fill in your credentials:

```bash
cp .env.example .env
```

Required keys in `.env`:

| Variable | Where to Get It |
|----------|----------------|
| `GRANTS_GOV_API_KEY` | [Simpler Grants.gov Developer Portal](https://simpler.grants.gov/developer) |
| `OPENAI_API_KEY` | [OpenAI API Keys](https://platform.openai.com/api-keys) |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | [Google App Passwords](https://myaccount.google.com/apppasswords) (requires 2FA) |

### 3. Configure Recipients

Edit `conf/email.yaml` to add or remove email recipients:

```yaml
email:
  recipients:
    - "bo.yu@utah.edu"
    - "chenxi.liu@utah.edu"
    - "fred.yang@utah.edu"
    - "xuewen.luo@utah.edu"
```

### 4. Install Scheduling

```bash
./scripts/install.sh
```

This installs two macOS LaunchAgents:
- **Daily fetch** at 12:00 PM noon Mountain Time (`com.boyu.funding-agent.daily`)
- **Weekly email** every Thursday at 8:00 PM Mountain Time (`com.boyu.funding-agent.weekly`)

Verify they are loaded:

```bash
launchctl list | grep funding-agent
```

To uninstall:

```bash
./scripts/uninstall.sh
```

## Usage

### Manual Triggers

Run the daily fetch immediately:

```bash
./scripts/fetch_now.sh
```

Send the weekly email immediately:

```bash
./scripts/email_now.sh
```

### Check Database Status

```bash
uv run python -c "
from src.state import StateDB
db = StateDB('data/state.db')
pending = db.get_pending_opportunities()
print(f'Pending opportunities: {len(pending)}')
for p in pending:
    print(f'  [{p[\"source\"]}] {p[\"title\"][:80]}')
db.close()
"
```

### View Logs

```bash
ls outputs/logs/
tail -50 outputs/logs/daily_fetch_*.log
```

### View Archived Digests

```bash
open outputs/digests/        # Open in Finder
```

## Configuration

All configuration is managed through YAML files in `conf/`:

- **`config.yaml`** — LLM model, database path, log directory
- **`sources/government.yaml`** — API endpoints and search keywords for NSF, Grants.gov
- **`sources/industry.yaml`** — Industry source URLs and relevance ratings
- **`filter.yaml`** — Primary/domain keywords, exclusions, score thresholds
- **`email.yaml`** — SMTP settings, recipient list, digest options

## Testing

```bash
uv run python -m pytest tests/ -v
```

## Database

SQLite database at `data/state.db` with three tables:

| Table | Purpose |
|-------|---------|
| `seen_opportunities` | All fetched opportunities with dedup, relevance scores, email status |
| `fetch_history` | Tracks each fetch run's time window for gap-free recovery |
| `email_history` | Records each email send with success/failure |

Old entries are automatically cleaned up after 90 days.

## Manual Review Required

The following funding sources **cannot be monitored automatically** due to scraping restrictions or legal concerns. Researchers should check these sites manually on a regular basis (recommended: weekly or biweekly).

### Government — Legal Restrictions

| Source | URL | Reason |
|--------|-----|--------|
| **SAM.gov** | https://sam.gov/ | Strict Terms of Service prohibit automated data collection; potential legal risk. Use the web portal to search for federal contract and grant opportunities manually. |

### Industry — Blocked by Anti-Scraping Protections

These sites actively block automated access via 403 Forbidden responses, SSL restrictions, or bot detection:

| Source | URL | Block Type | What to Look For |
|--------|-----|-----------|------------------|
| **USDOT** | https://www.transportation.gov/grants | 403 Forbidden | Federal transportation grants — **very high relevance** to AI + transportation research |
| **DOE** | https://www.energy.gov/funding-financing | 403 Forbidden | Energy and infrastructure funding — relevant to smart grid and energy AI research |
| **Adobe** | https://research.adobe.com/data-science-research-awards/ | SSL certificate block | Data Science Research Awards for faculty |
| **Meta** | https://www.llama.com/llama-ai-innovation/ | 400 Bad Request | Llama Impact Grants for AI research |
| **Ford** | https://research.ford.com/ | Connection reset | University research partnerships — **very high relevance** to autonomous vehicle research |

### Aggregator Sites

These are useful search engines for discovering additional opportunities but require authenticated access or manual browsing:

| Source | URL | Notes |
|--------|-----|-------|
| **GrantForward** | https://www.grantforward.com/ | University grant search engine; may be available through institutional login |
| **GrantedAI** | https://grantedai.com/ | AI-specific grant aggregator |

> **Tip**: Consider setting a calendar reminder every Monday to check the high-relevance sources above (SAM.gov, USDOT, DOE, Ford) for new opportunities.

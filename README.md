# Funding Opportunity Search Agent

Automated system that discovers funding and grant opportunities relevant to **AI + Transportation** research from government APIs and industry websites, then delivers a curated HTML digest via email every Thursday.

Built for the [University of Utah](https://www.utah.edu/) research group.

## How It Works

The system runs as a **two-stage pipeline** scheduled via macOS LaunchAgents:

```
STAGE 1: Weekly Fetch (every Thursday at 12:00 PM MT)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Fetchers   │───>│  LLM Validate│───>│   Filter     │───>│  Summarize   │
│  (parallel)  │    │  (GPT-5.2)   │    │ (keyword+LLM)│    │  & Store DB  │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘

STAGE 2: Weekly Email (every Thursday at 8:00 PM MT)
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Query DB    │───>│  Compose     │───>│  Send Email  │
│ (last 7 days)│    │  HTML Digest │    │  (Gmail SMTP)│
└──────────────┘    └──────────────┘    └──────────────┘
```

**Why two stages?**

- **Rate limits** — Grants.gov and NSF have rate limits; separating fetch from email avoids timeouts.
- **Punctual email** — Thursday 8 PM email compiles pre-stored data instantly.
- **Resilience** — If a fetch fails, the next week auto-recovers the missed window.
- **Quality gate** — GPT-5.2 validates every opportunity before storage, ensuring only real, currently-open calls are included.

## Funding Sources

### Government APIs

| Source | Method | Notes |
|--------|--------|-------|
| **NSF** | RSS feed | New funding announcements from `nsf.gov/rss/rss_www_funding.xml`; LLM-validated |
| **Grants.gov** | REST API (Simpler API v1) | Federal grant aggregator; keyword search with client-side date filtering; API key required |
| **DOE** | Web scraping | `energy.gov/funding-financing` (currently blocked by 403; see Manual Review) |
| **USDOT** | Web scraping | `transportation.gov/grants` (currently blocked by 403; see Manual Review) |

### Industry (Web Scraping + LLM Validation)

| Company | Program | Relevance |
|---------|---------|-----------|
| NVIDIA | Academic Hardware Grant | Very High |
| Google | Research Scholar Program | High |
| Qualcomm | Innovation Fellowship | High |
| Amazon | Research Awards | High |
| Microsoft | Research Academic Programs | Medium |
| Cisco | Research Funding | Medium |
| IBM | Faculty Awards | Medium |
| Samsung | Global Research Outreach | Medium |
| Adobe | Data Science Awards | Low |

All industry pages are scraped and validated by GPT-5.2 via the `OpportunityValidator`. Only opportunities that are **currently accepting applications** with an explicit deadline or rolling status are included.

See [`docs/funding_sources.md`](docs/funding_sources.md) for full URLs and API details.

## LLM Validation Gate

Every opportunity passes through a GPT-5.2 validation gate (`OpportunityValidator`) before being accepted:

**For industry web pages:**
- Page content is sent to GPT-5.2 which identifies only real, currently-open funding opportunities
- Each extracted opportunity must have `confidence >= 0.6`
- Must have an explicit future deadline (`deadline_status: "explicit_date"`) or be explicitly rolling (`deadline_status: "rolling"`)
- Past deadlines and generic program descriptions are automatically rejected

**For government API results:**
- NSF RSS items are individually validated by GPT-5.2
- Grants.gov results are filtered by keyword search, date window, and deadline

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
│   │   ├── government.yaml        # NSF, Grants.gov API + DOE/USDOT web sources
│   │   └── industry.yaml          # 9 industry source URLs
│   ├── filter.yaml                # Keywords & relevance thresholds
│   └── email.yaml                 # SMTP settings & recipient list
├── src/
│   ├── weekly_fetch.py             # Stage 1: Weekly fetch pipeline (7-day window)
│   ├── weekly_email.py            # Stage 2: Weekly email pipeline
│   ├── models.py                  # Opportunity dataclass (frozen)
│   ├── state.py                   # SQLite state management
│   ├── fetcher/                   # Data retrieval modules
│   │   ├── base.py                # BaseFetcher ABC with retry
│   │   ├── nsf.py                 # NSF RSS fetcher + LLM validation
│   │   ├── grants_gov.py          # Grants.gov Simpler API fetcher
│   │   ├── web_scraper.py         # Industry/government page scraper
│   │   └── opportunity_validator.py  # GPT-5.2 LLM validation gate
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
├── tests/                         # Unit tests (42 tests)
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

Copy the example and fill in your recipients:

```bash
cp conf/email.yaml.example conf/email.yaml
```

Then edit `conf/email.yaml` to add your email recipients:

```yaml
email:
  recipients:
    - "user1@example.com"
    - "user2@example.com"
```

### 4. Install Scheduling

```bash
./scripts/install.sh
```

This installs two macOS LaunchAgents:
- **Weekly fetch** every Thursday at 12:00 PM noon Mountain Time (`com.boyu.funding-agent.daily`)
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

Run the weekly fetch immediately:

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
tail -50 outputs/logs/weekly_fetch_*.log
```

### View Archived Digests

```bash
open outputs/digests/        # Open in Finder
```

## Configuration

All configuration is managed through YAML files in `conf/`:

- **`config.yaml`** — LLM model, database path, log directory
- **`sources/government.yaml`** — NSF RSS, Grants.gov API settings, DOE/USDOT web sources
- **`sources/industry.yaml`** — 9 industry source URLs and relevance ratings
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

### Industry/Government — Blocked by Anti-Scraping Protections

These sites actively block automated access via 403 Forbidden responses, SSL restrictions, or bot detection. DOE and USDOT are configured as government web sources but currently fail with 403:

| Source | URL | Block Type | What to Look For |
|--------|-----|-----------|------------------|
| **USDOT** | https://www.transportation.gov/grants | 403 Forbidden | Federal transportation grants — **very high relevance** to AI + transportation research |
| **DOE** | https://www.energy.gov/funding-financing | 403 Forbidden | Energy and infrastructure funding — relevant to smart grid and energy AI research |
| **Adobe** | https://research.adobe.com/data-science-research-awards/ | SSL certificate block | Data Science Research Awards for faculty |
| **Sloan Fellowships** | https://sloan.org/fellowships | 403 Forbidden | Prestigious early-career fellowships for outstanding researchers |
| **AFOSR YIP** | https://www.afrl.af.mil/About/Fact-Sheets/Fact-Sheet-Display/Article/2282031/young-investigator-research-program/ | 403 Forbidden | Air Force Young Investigator Program for early-career faculty |

### Aggregator Sites

These are useful search engines for discovering additional opportunities but require authenticated access or manual browsing:

| Source | URL | Notes |
|--------|-----|-------|
| **GrantForward** | https://www.grantforward.com/ | University grant search engine; may be available through institutional login |
| **GrantedAI** | https://grantedai.com/ | AI-specific grant aggregator |

> **Tip**: Consider setting a calendar reminder every Thursday to check the high-relevance sources above (SAM.gov, USDOT, DOE, Sloan, AFOSR) for new opportunities.

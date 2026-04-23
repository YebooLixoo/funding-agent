# Funding Agent

> **Stop scrolling NSF, NIH, and Grants.gov for hours every week.** Funding Agent is your AI research-funding scout — it reads your CV, learns what you work on, and emails you a curated digest of every relevant grant, fellowship, and compute allocation as it drops.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688.svg)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![SQLite WAL](https://img.shields.io/badge/SQLite-WAL-003B57.svg)](https://www.sqlite.org/)

---

## The problem

Faculty, postdocs, and PIs lose **hours every week** hunting for grants across:

- 🇺🇸 Federal sources — NSF, NIH, Grants.gov, DOE, EPA, USDOT, NASA …
- 🏢 Industry programs — NVIDIA, Google, Amazon, Microsoft, Meta, OpenAI …
- 🎓 University internal funds — seed grants, equipment matches, travel awards
- ⚡ Compute allocations — NSF ACCESS, DOE INCITE, AWS/Azure/GCP credits

Every site has a different layout, a different RSS quirk, a different deadline format. By the time you've checked them all, you've burned a Tuesday morning — and missed the one that actually mattered.

## What Funding Agent does

**Upload your CV. Forget the grind. Open your inbox to relevant opportunities.**

1. **You upload a CV or paper** → GPT extracts your research keywords (primary, domain, career stage) into a personalized profile.
2. **The system fetches** every Thursday from 25+ sources — federal APIs, scraped industry pages, curated GPU/HPC programs.
3. **It scores every opportunity** against *your* profile using a four-signal algorithm (keyword match + profile similarity + bookmark/dismiss behavior + deadline urgency).
4. **You get a digest** in your inbox at the cadence you choose — daily, weekly, or biweekly.
5. **You refine via chat** — *"focus more on RL for robotics, less on NLP"* — and the system updates your filter on the fly.

Every researcher gets their own keywords, their own scoring threshold, their own digest schedule, and their own broadcast list to forward digests to colleagues without forcing them to sign up.

## Highlights

| | |
|---|---|
| 🧠 **Smart keyword extraction** | Drop a CV PDF; GPT categorizes your interests into primary, domain, career, and faculty buckets |
| 📡 **25+ sources, one digest** | Federal, industry, university, and compute programs aggregated and deduplicated |
| 🎯 **Multi-signal scoring** | Keyword match (40%) + profile similarity (30%) + behavioral signals (20%) + deadline urgency (10%) |
| 💬 **Conversational tuning** | Chat with the AI to refine your filter; suggested keyword updates apply with one click |
| 📨 **Per-user broadcast lists** | Add up to 25 colleagues to receive your digest — no logins required, one-click unsubscribe |
| 📅 **Deadline tracking** | Calendar view of approaching deadlines, sorted by relevance to you |
| 🔄 **Adaptive bootstrap** | New sources automatically pull historical opportunities on first run, then settle into the weekly cadence |
| 🌍 **GitHub-Pages history** | A static, public archive of every opportunity ever emailed — searchable, browsable, no login |

## Live history page

Browse the curated archive at **[https://yeboolixoo.github.io/funding-agent/](https://yeboolixoo.github.io/funding-agent/)** — every opportunity that's ever made it into a digest, grouped by month and source.

---

## Quick start

### Prerequisites

- Python 3.10+ and [uv](https://docs.astral.sh/uv/)
- Node.js 18+ *(only if running the React frontend locally)*
- An OpenAI API key
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) *(for sending digests)*

### Install

```bash
git clone https://github.com/YebooLixoo/funding-agent.git
cd funding-agent

uv sync                                   # backend (creates .venv from uv.lock)
cd frontend && npm install && cd ..       # frontend (optional)

cp .env.example .env                      # then fill in OPENAI_API_KEY, GMAIL_*, JWT_SECRET_KEY, ADMIN_EMAIL
uv run alembic upgrade head               # creates data/platform.db with full schema
```

### Run

```bash
./scripts/start_platform.sh               # FastAPI on :8000, Vite on :5173
```

Open **http://localhost:5173**, register, upload your CV, and you're set.

### Schedule the recurring jobs (macOS)

```bash
./scripts/install.sh                      # installs launchd plists for fetch, email, backup
```

That installs three jobs:

- `com.boyu.funding-agent.fetch` — Thursday 12:00 MT, runs `web.cli fetch`
- `com.boyu.funding-agent.email` — hourly, runs `web.cli email-digest --due` (each user's frequency/day_of_week pref governs whether they actually get a send)
- `com.boyu.funding-agent.backup` — daily 02:00, snapshots `data/platform.db` to `data/backups/`

To uninstall: `./scripts/uninstall.sh`. To trigger manually:

```bash
uv run python -m web.cli fetch                                            # one-shot fetch
uv run python -m web.cli email-digest --user-email me@x --test            # dry-run email
uv run python -m web.cli regenerate-history                               # rebuild docs/index.html
```

### Run with Docker

```bash
docker compose up -d
```

Single SQLite volume, no Postgres, no scheduler container — pair with host cron / launchd for the recurring jobs.

---

## How it works

```
┌──────────────────────────────────────────────────────────┐
│  React + Tailwind  ──────  FastAPI (request-handling     │
│  ┌──────────────┐          only; no background work)     │
│  │ Dashboard    │                  │                     │
│  │ Opportunities│                  ▼                     │
│  │ Documents    │      ┌────────────────────────┐        │
│  │ Chat         │      │  data/platform.db      │        │
│  │ Profile      │      │  (SQLite WAL,          │        │
│  └──────────────┘      │   Alembic-managed)     │        │
│                        └───────────┬────────────┘        │
│                                    ▲                     │
│                                    │                     │
│         launchd  ───►  python -m web.cli                 │
│           │              ├─ fetch (orchestrates src/)    │
│           │              ├─ email-digest --due           │
│           │              └─ regenerate-history           │
│           │                                              │
│           └──►  src/  (fetch/filter/summarize library)   │
│                  ├─ fetcher/  (NSF, NIH, Grants.gov,     │
│                  │             industry/uni/compute      │
│                  │             web scrapers)             │
│                  ├─ filter/   (keyword + LLM borderline) │
│                  └─ summarizer.py (GPT 2-3 sentence      │
│                                    summaries)            │
└──────────────────────────────────────────────────────────┘
```

**Key design choices**:

- **One database, one truth.** `data/platform.db` (SQLite WAL) is the only DB — the FastAPI request path and the launchd CLI both write to it.
- **No in-process scheduler.** Background work runs as separate `python -m web.cli` processes under launchd. FastAPI stays responsive; multi-worker uvicorn is safe.
- **Alembic is authoritative.** Migrations live in `alembic/versions/` and are the only path to schema changes — no `create_all` on startup.
- **Outbox pattern for emails.** Delivery state commits *before* SMTP send to prevent dupe-on-retry after a commit failure.
- **Per-source error isolation.** A single failing scraper (energy.gov 404, OpenAI rate limit) doesn't kill the run — the rest of the pipeline continues and the failure is recorded in `fetch_history`.

### Tech stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI (async) |
| Frontend | React 19 + Vite + Tailwind CSS + TypeScript |
| Database | SQLite (WAL mode) via SQLAlchemy 2.x async + Alembic |
| Scheduler | macOS launchd → `web/cli.py` (Click) |
| Auth | JWT (python-jose + passlib + bcrypt 4.0) |
| PDF parsing | PyMuPDF |
| LLM | OpenAI Python SDK (keyword extraction, chat, scoring, summarization) |
| Email | Gmail SMTP |
| Tests | pytest + pytest-asyncio (177 tests) |

---

## Project structure

```
funding-agent/
├── web/                     FastAPI app + admin CLI
│   ├── main.py              app entry (request handling only)
│   ├── cli.py               Click CLI (what launchd schedules)
│   ├── models/              ORM models
│   ├── routers/             REST endpoints
│   └── services/            fetch_runner, email_dispatcher, scoring, …
├── frontend/                React + Vite + Tailwind
├── src/                     Fetch / filter / summarize library (no DB coupling)
│   ├── fetcher/             NSF, NIH, Grants.gov, web scrapers
│   ├── filter/              keyword + LLM borderline filter
│   └── summarizer.py        GPT-driven 2-3 sentence summaries
├── alembic/versions/        authoritative schema migrations
├── launchd/                 macOS launchd plists (fetch / email / backup)
├── conf/                    YAML source configs (NSF/NIH/Grants.gov endpoints, etc.)
├── docs/                    static GitHub-Pages history archive
├── tests/                   177 pytest tests
└── scripts/                 install / uninstall / start / fetch_now / email_now
```

---

## API surface

All endpoints prefixed `/api/v1/` and require JWT Bearer auth (except `/auth/register`, `/auth/login`, and the public `/unsubscribe/{token}`).

| Group | Notable endpoints |
|-------|------------------|
| **Auth** | `POST /auth/{register,login,refresh}` |
| **Users** | `GET/PUT/DELETE /users/me` |
| **Opportunities** | `GET /opportunities` (paginated, scored), bookmark, dismiss |
| **Keywords** | `GET /keywords`, bulk add, update, delete (admin edits auto-sync to system fetch) |
| **Documents** | `POST /documents/upload` (multipart PDF), list, reprocess |
| **Scoring** | `POST /scoring/rescore` |
| **Chat** | `POST /chat` (AI keyword refinement), apply suggested actions |
| **Email** | `GET/PUT /email/preferences`, history, send test |
| **Broadcast** | `GET/POST/DELETE /broadcast/recipients` (≤25/user); public `/unsubscribe/{token}` |
| **Fetch** | `GET/PUT /fetch/config`, trigger, status |

Interactive API docs at `http://localhost:8000/docs`.

---

## How scoring works

Each user's opportunities are ranked by a **four-signal weighted score** in `web/services/scoring.py`:

| Signal | Weight | What it measures |
|--------|--------|------------------|
| Keyword match | **40%** | Multi-track overlap with your `UserKeyword` rows, weighted per-keyword |
| Profile similarity | **30%** | Term overlap between your `research_summary` / department / position and the opportunity text |
| Behavioral | **20%** | Boost for opportunities similar to your bookmarks; penalty for those similar to dismissed ones |
| Urgency | **10%** | Deadline proximity + recency boost |

Borderline keyword matches (0.2–0.6) are sent to the LLM for contextual review. Curated compute resources (NSF ACCESS, DOE INCITE, etc.) bypass the keyword filter — they're pre-vetted via the YAML curation in `conf/sources/compute.yaml`.

---

## Configuration

`.env` keys:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENAI_API_KEY` | yes | — | LLM operations |
| `JWT_SECRET_KEY` | yes | — | Auth token signing |
| `GMAIL_ADDRESS` | yes | — | Digest sender |
| `GMAIL_APP_PASSWORD` | yes | — | Gmail [App Password](https://myaccount.google.com/apppasswords) |
| `ADMIN_EMAIL` | yes (CLI) | — | Identifies the user whose keywords drive the system fetch |
| `DATABASE_URL` | no | `sqlite+aiosqlite:///data/platform.db` | Override only if you need a non-default location |
| `GRANTS_GOV_API_KEY` | no | — | [Register here](https://simpler.grants.gov/developer); higher rate limits |

YAML configs in `conf/`:

- `conf/sources/{government,industry,university,compute}.yaml` — source endpoints (URLs, RSS feeds, search-keyword lists for API sources)
- `conf/email.yaml` (gitignored; copy from `.example`) — Gmail SMTP settings, broadcast recipient list, history page URL

---

## Tests

```bash
uv run pytest tests/ -v
```

**177 tests passing**, covering: auth, CRUD, opportunity dedup, keyword sync, auto-scoring, due-time logic (with timezone correctness), email dispatcher (outbox pattern), broadcast list + unsubscribe, fetch orchestration, migration script, CLI surface, SQLite WAL pragmas.

---

## Roadmap

The system was originally built single-user; it now consolidates the standalone CLI pipeline and the multi-user web platform into one. **Next on the roadmap**:

- **World-scale fetch:** when active users grow, the `system_search_terms` table will auto-expand from union-of-all-active-users keywords (no re-architecture; one query change).
- **Embedding-based semantic matching** beyond the current term-overlap scoring.
- **Native Linux/cron support** for environments without launchd.
- **Public source-suggestion UX** so non-admin users can request new sources.

See `docs/superpowers/specs/2026-04-16-consolidate-pipeline-and-platform-design.md` for the architectural reasoning.

---

## Contributing

Contributions welcome — especially:

- **New funding sources** (drop a YAML entry under `conf/sources/`)
- **Improved scoring signals** (semantic embeddings, behavioral models, …)
- **Frontend polish** (the React app is functional but plain)
- **Linux launchd-equivalent** scripts (systemd timers, cron wrappers)

Open an issue or PR. The implementation plan format under `docs/superpowers/plans/` is a useful template for proposing larger changes.

---

## License

MIT — use it, fork it, ship your own.

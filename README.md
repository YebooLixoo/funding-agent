# Funding Agent

An open-source AI-powered platform that helps researchers discover, filter, and track funding opportunities personalized to their research profile. Upload your CV or papers, and the system automatically extracts your research keywords, scores opportunities by relevance, and delivers curated digests to your inbox.

## Why Funding Agent?

Finding the right grants is tedious. Researchers waste hours scrolling through generic listings from NSF, NIH, Grants.gov, DOE, and industry programs. Funding Agent solves this by:

- **Auto-extracting your research profile** from uploaded documents (CV, papers)
- **Scoring every opportunity** against your unique keyword profile using a proven multi-track algorithm
- **Delivering personalized email digests** on your schedule (daily, weekly, or biweekly)
- **AI chat assistant** to refine your keywords and filter rules conversationally

Every researcher gets their own fully customized experience — their own keywords, sources, scoring thresholds, and email preferences.

## Features

- **Smart Keyword Extraction** — Upload your resume or papers; GPT extracts categorized keywords (primary, domain, career, faculty) specific to your research area
- **Multi-Source Aggregation** — Pulls from 25+ funding sources: NSF, NIH, Grants.gov, DOE, EPA, USDOT, and major industry programs (NVIDIA, Google, Amazon, Microsoft, etc.)
- **Relevance Scoring** — Multi-track keyword scoring algorithm with optional LLM filtering for borderline cases
- **Deadline Tracking** — Calendar view of upcoming deadlines filtered by your relevance
- **Bookmarks & Dismissals** — Save interesting opportunities, hide irrelevant ones
- **Per-User Email Digests** — Configurable frequency, minimum score threshold, and deadline lookahead
- **AI Chat** — Conversational interface to refine your keyword profile ("focus more on reinforcement learning for robotics, less on NLP")
- **Source Control** — Toggle which funding sources to search, set custom search terms

## Architecture

```
┌────────────────────────────────────────────────────────┐
│  Single consolidated system                            │
│                                                        │
│  React + Tailwind ──── FastAPI (async, request-only)   │
│       │                    │                           │
│  User Dashboard        SQLAlchemy (SQLite, WAL)        │
│  Opportunity Browser   JWT Auth                        │
│  Document Upload       LLM Integration                 │
│  AI Chat                                               │
│                            │                           │
│                            ▼                           │
│         data/platform.db (single source of truth)      │
│                            ▲                           │
│                            │                           │
│  web/cli.py ─────── launchd plists                     │
│   - fetch (Thu 12:00)                                  │
│   - email-digest --due (hourly)                        │
│   - sqlite .backup (daily 02:00)                       │
└────────────────────────────────────────────────────────┘
```

FastAPI hosts no background work. Scheduled jobs run as `python -m web.cli ...`
under launchd; both the API and the CLI share the same SQLite database
managed by Alembic migrations.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python, async) |
| Frontend | React 19 + Vite + Tailwind CSS + TypeScript |
| Database | SQLite (WAL mode) via SQLAlchemy async + Alembic |
| Scheduler | macOS launchd → `web/cli.py` (Click) |
| Auth | JWT (python-jose + passlib) |
| PDF Processing | PyMuPDF |
| LLM | OpenAI API (keyword extraction, chat, scoring) |
| Deployment | Docker Compose (single backend + frontend, SQLite volume) |

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+ (only needed if you want to run the React frontend locally)

### 1. Clone and Install

```bash
git clone https://github.com/boyuan12/funding-agent.git
cd funding-agent

# Backend dependencies (creates .venv + installs from uv.lock)
uv sync

# Frontend dependencies (optional)
cd frontend && npm install && cd ..
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Required variables in `.env`:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Defaults to `sqlite+aiosqlite:///data/platform.db`; override only for non-local setups |
| `OPENAI_API_KEY` | For keyword extraction, chat, and LLM filtering |
| `JWT_SECRET_KEY` | Secret for signing auth tokens |
| `GMAIL_ADDRESS` | For sending email digests |
| `GMAIL_APP_PASSWORD` | [Google App Password](https://myaccount.google.com/apppasswords) |

### 3. Run (Development)

```bash
# Apply migrations (idempotent; auto-creates data/platform.db on first run)
uv run alembic upgrade head

# Start both backend and frontend
./scripts/start_platform.sh
```

Visit **http://localhost:5173** to register and start exploring.

### 4. Scheduled jobs (optional, macOS)

Background work (fetch, email digests, SQLite backup) is driven by the
`web/cli.py` Click app — never by FastAPI itself. To register the launchd jobs
shipped under `launchd/`, run `./scripts/install.sh`. Manual triggers:

```bash
./scripts/fetch_now.sh                         # web.cli fetch
./scripts/email_now.sh                         # test mode (requires ADMIN_EMAIL)
./scripts/email_now.sh --prod                  # email-digest --due (all due users)
```

### 5. Run (Production with Docker)

```bash
docker compose up -d
```

This starts the FastAPI backend (SQLite at `./data/platform.db`) and the
nginx-served React frontend. No external database server is needed.

## Project Structure

```
funding-agent/
├── web/                        # FastAPI backend + admin CLI
│   ├── main.py                 # App entry point (request handling only)
│   ├── cli.py                  # Click CLI: fetch, email-digest, regenerate-history
│   ├── config.py               # Settings (env-based)
│   ├── database.py             # SQLAlchemy async engine (SQLite, WAL)
│   ├── models/                 # ORM models (user, document, keyword, opportunity, etc.)
│   ├── schemas/                # Pydantic request/response schemas
│   ├── routers/                # API endpoints (auth, users, opportunities, keywords, etc.)
│   └── services/               # Business logic (scoring, fetch_runner, email dispatch, chat)
├── frontend/                   # React + Vite + Tailwind
│   └── src/
│       ├── pages/              # Dashboard, Opportunities, Profile, Documents, Chat, etc.
│       ├── components/         # Layout, shared UI
│       ├── api/                # API client modules
│       └── hooks/              # Auth context, custom hooks
├── src/                        # Fetch / filter / summarize library (no DB coupling)
│   ├── filter/                 # Keyword + LLM filtering engine
│   ├── fetcher/                # Source-specific data fetchers
│   └── models.py               # Opportunity data model
├── tests/                      # Backend test suite
├── alembic/                    # Database migrations (authoritative schema)
├── launchd/                    # macOS launchd plists (fetch / email / backup)
├── docker-compose.yml          # Production deployment (SQLite volume)
└── scripts/                    # Dev/ops scripts
```

## API Endpoints

All endpoints are prefixed with `/api/v1/` and require JWT Bearer auth (except register/login).

| Group | Endpoints |
|-------|-----------|
| **Auth** | `POST /auth/register`, `/auth/login`, `/auth/refresh` |
| **Users** | `GET/PUT/DELETE /users/me` |
| **Opportunities** | `GET /opportunities` (paginated, filterable), `GET /opportunities/{id}`, bookmark, dismiss |
| **Keywords** | `GET /keywords` (grouped by category), `POST /keywords`, bulk add, update, delete |
| **Documents** | `POST /documents/upload` (multipart), list, reprocess |
| **Scoring** | `POST /scoring/rescore` (re-score all opportunities for user) |
| **Chat** | `POST /chat` (AI keyword refinement), apply suggested actions |
| **Email** | `GET/PUT /email/preferences`, send test, history |
| **Fetch** | `GET/PUT /fetch/config`, trigger manual fetch, status |

## How Scoring Works

The platform uses a **multi-track keyword scoring algorithm**:

1. **Track 1 (AI + Domain)**: Matches your primary research keywords and domain-specific terms
2. **Track 2 (Career + Faculty)**: Matches career-stage keywords (early career, junior faculty, etc.)
3. **Cross-bonuses**: Opportunities matching both tracks get boosted scores
4. **Exclusion filter**: Auto-rejects opportunities matching your exclusion keywords
5. **LLM borderline filter** (optional): Sends ambiguous scores (0.2-0.6) to GPT for contextual review

Each user's keywords are extracted from their uploaded documents and can be refined via the AI chat interface or manual editing.

## Testing

```bash
uv run python -m pytest tests/ -v
```

68 tests covering auth, CRUD, scoring, document processing, chat, email preferences, fetch config, and deadline sorting.

## Contributing

Contributions are welcome! Whether it's adding new funding sources, improving the scoring algorithm, or enhancing the UI — feel free to open an issue or submit a PR.

## License

MIT

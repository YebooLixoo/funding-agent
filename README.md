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
┌─────────────────────────────────────────────────┐
│  Web Platform                                   │
│                                                 │
│  React + Tailwind ──── FastAPI (async)           │
│       │                    │                    │
│  User Dashboard        SQLAlchemy (PostgreSQL)  │
│  Opportunity Browser   JWT Auth                 │
│  Document Upload       Background Tasks         │
│  AI Chat               LLM Integration          │
│  Email/Source Config    Per-user Scheduling      │
└─────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python, async) |
| Frontend | React 19 + Vite + Tailwind CSS + TypeScript |
| Database | PostgreSQL (SQLAlchemy + Alembic) — SQLite for dev |
| Auth | JWT (python-jose + passlib) |
| PDF Processing | PyMuPDF |
| LLM | OpenAI API (keyword extraction, chat, scoring) |
| Deployment | Docker Compose |

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+
- PostgreSQL (or SQLite for development)

### 1. Clone and Install

```bash
git clone https://github.com/boyuan12/funding-agent.git
cd funding-agent

# Backend dependencies
uv sync

# Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Required variables in `.env`:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (or `sqlite+aiosqlite:///data/platform.db` for dev) |
| `OPENAI_API_KEY` | For keyword extraction, chat, and LLM filtering |
| `JWT_SECRET_KEY` | Secret for signing auth tokens |
| `GMAIL_ADDRESS` | For sending email digests |
| `GMAIL_APP_PASSWORD` | [Google App Password](https://myaccount.google.com/apppasswords) |

### 3. Run (Development)

```bash
# Start both backend and frontend
./scripts/start_platform.sh

# Or run separately:
# Backend
DATABASE_URL="sqlite+aiosqlite:///data/platform.db" uv run uvicorn web.main:app --reload --port 8000

# Frontend
cd frontend && npx vite --port 5173
```

Visit **http://localhost:5173** to register and start exploring.

### 4. Run (Production with Docker)

```bash
docker compose up -d
```

This starts PostgreSQL, the FastAPI backend, and an nginx-served React frontend.

## Project Structure

```
funding-agent/
├── web/                        # FastAPI backend
│   ├── main.py                 # App entry point
│   ├── config.py               # Settings (env-based)
│   ├── database.py             # SQLAlchemy async engine
│   ├── models/                 # ORM models (user, document, keyword, opportunity, etc.)
│   ├── schemas/                # Pydantic request/response schemas
│   ├── routers/                # API endpoints (auth, users, opportunities, keywords, etc.)
│   └── services/               # Business logic (scoring, document processing, chat, email)
├── frontend/                   # React + Vite + Tailwind
│   └── src/
│       ├── pages/              # Dashboard, Opportunities, Profile, Documents, Chat, etc.
│       ├── components/         # Layout, shared UI
│       ├── api/                # API client modules
│       └── hooks/              # Auth context, custom hooks
├── src/                        # Core pipeline (fetchers, filters, scoring algorithms)
│   ├── filter/                 # Keyword + LLM filtering engine
│   ├── fetcher/                # Source-specific data fetchers
│   └── models.py               # Opportunity data model
├── tests/                      # Backend test suite (68 tests)
├── alembic/                    # Database migrations
├── docker-compose.yml          # Production deployment
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

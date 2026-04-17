# Consolidate Internal Pipeline and Web Platform — Design

**Date:** 2026-04-16
**Status:** Draft, awaiting review
**Author:** Boyu Yu (with Claude)

## 1. Context

The repository currently runs **two coexisting systems** that share opportunity data via a one-way bridge:

- **Internal pipeline (`src/`)** — a single-user Python CLI driven by `conf/*.yaml`. Runs on launchd every Thursday: noon (fetch) and 8 PM (email). Writes to `data/state.db` (SQLite). Generates a static history page at `docs/index.html`. Owns all fetchers, the keyword filter, the LLM borderline filter, the summarizer, and the SMTP digest.
- **Web platform (`web/` + `frontend/`)** — a multi-user FastAPI + React app. Has its own DB (`data/platform.db` SQLite or `funding_platform` Postgres), per-user keyword profiles, scoring, bookmarks, dismissals, AI chat, document uploads, and per-user email preferences. **Does not fetch its own opportunities** — it copies them from `data/state.db` on startup via `web/services/seed_opportunities.py`.

This split is historical baggage. It causes:

- **Two databases** to keep in sync (with `seed_opportunities.py` as a leaky bridge).
- **Two scoring layers** that drift (`src/filter/keyword_filter.py` config in YAML; `web/services/scoring.py` config in DB).
- **Confused ownership**: changes to the opportunity schema or filter logic must be made in both places.
- **Stale `seed_opportunities.py` bootstrap**: opportunities seeded on startup; updates after that require restarts or manual seeds.
- **The platform's `email_scheduler.py` is built but unwired** — no scheduler triggers it, so per-user digests don't actually go out.

This design consolidates everything into the platform (`web/`), with `src/` retained as a fetch/filter/summarize **library** called by the platform. The internal CLI becomes a thin command-line wrapper around the same in-process code paths.

## 2. Goals and non-goals

### 2.1 Goals (Project A — this spec)

- **One database** (SQLite) as the single source of truth.
- **One scheduler** (APScheduler in-process) running fetch + per-user digest jobs.
- **Admin user account** (`user_id=1`, the existing Boyu account) drives the system fetch via `system_search_terms` and `system_filter_keywords` tables that auto-sync from the admin's `UserKeyword` rows.
- **Behavior parity with today**: same Thursday-noon fetch, same Thursday-8pm digest content, same static history page at `docs/index.html`, same OpenAI cost.
- **Per-user broadcast lists**: any user can CC colleagues on their digest with no logins required; tokenized unsubscribe.
- **In-app per-user history view** in addition to the global static page.
- **D3-shaped data model**: when Project B arrives, the only change is swapping the auto-sync source from "admin user" to "union of all users" — no re-architecture.

### 2.2 Non-goals (deferred to Project B)

- Per-user fetch agents.
- Union-of-users `system_search_terms` (the table exists; it just stays seeded from one user in v1).
- Embedding-based semantic matching beyond what `web/services/scoring.py` already does.
- Public registration of arbitrary users (registration already works; this spec doesn't expand the audience).
- Postgres support (drop for now; can return when scale demands it).

## 3. Decisions

Captured from the brainstorming session (2026-04-16):

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Broadcast list per user (CC colleagues, no login required) | Lowest-friction colleague onboarding; preserves today's broadcast UX |
| D2 | Admin user account drives the system fetch | Matches "internal system is just my account" framing |
| D3 | `system_search_terms` + `system_filter_keywords` tables, seeded from admin's `UserKeyword`; D3-ready (Project B swaps source to union-of-users) | Sub-linear scaling; no re-architecture later |
| D4 | APScheduler in-process for v1; HTTP endpoint (cron-hits-`POST /admin/fetch`) as upgrade path | Simplest infra; identical job code in either case |
| D5 | One-time migration of `data/state.db` → `data/platform.db`; archive `state.db`; delete `seed_opportunities.py` | Clean cut-over, preserves history |
| D6 | Both global static `docs/index.html` and in-app per-user history view | Public archive + logged-in personalization |
| D7 | Keep fetch-time relevance filter, but source it from `system_filter_keywords` (DB), not `conf/filter.yaml` | Cost-flat, behavior parity, world-scale upgrade path is one query change |
| D8 | SQLite-only (drop Postgres); use WAL mode | Scale doesn't justify Postgres; eliminates dev pain; simplifies Docker |
| D9 | `conf/sources/*.yaml` stays in YAML | Source endpoint list is admin-curated, version-controlled, changes rarely |
| D10 | Repurpose `fetch_now.sh` and `email_now.sh` as `python -m web.cli fetch` / `email-digest` wrappers | Same UX; same DB |
| D11 | Tokenized unsubscribe link in every broadcast email | Standard practice; legal/anti-spam |
| D12 | Admin UX = auto-sync from admin's `UserKeyword`; no separate admin UI in v1 | Minimal surface area; admin already has a Profile keyword editor |
| D13 | Port `source_bootstrap` table directly into platform DB | Same logic, same behavior |

## 4. Architecture

### 4.1 Component layout (post-consolidation)

```
┌─────────────────────────────────────────────────────────────┐
│  FastAPI app (web/main.py)                                  │
│                                                             │
│  ┌──────────────┐ ┌────────────────┐ ┌──────────────────┐   │
│  │ HTTP routers │ │ APScheduler     │ │ web/cli.py       │   │
│  │ (existing)   │ │  (new)          │ │ (new — manual    │   │
│  │              │ │                 │ │   triggers)      │   │
│  └──────┬───────┘ └────────┬────────┘ └────────┬─────────┘   │
│         │                  │                   │             │
│         └──────────┬───────┴───────────────────┘             │
│                    │                                         │
│         ┌──────────▼──────────┐                              │
│         │ web/services/        │                             │
│         │   fetch_runner.py    │  ← new: orchestrates a fetch│
│         │   email_dispatcher   │  ← new: dispatches digests  │
│         │   scoring.py         │  (existing)                 │
│         └──────────┬──────────┘                              │
│                    │ uses                                    │
│         ┌──────────▼──────────┐                              │
│         │ src/  (library)      │ — fetchers, filter,         │
│         │                      │   summarizer, history       │
│         │                      │   generator, emailer        │
│         └──────────┬──────────┘                              │
│                    │                                         │
│         ┌──────────▼──────────┐                              │
│         │ data/platform.db     │  ← single SQLite, WAL mode  │
│         └─────────────────────┘                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 What changes vs. today

| Area | Before | After |
|------|--------|-------|
| Databases | `data/state.db` (SQLite) + `data/platform.db` (SQLite) or Postgres | `data/platform.db` (SQLite, WAL) only |
| Scheduling | launchd → `python -m src.weekly_fetch` / `weekly_email` | APScheduler inside FastAPI; launchd just starts FastAPI |
| Fetch trigger | CLI script + cron | APScheduler job (with manual override via `web/cli.py`) |
| Filter source | `conf/filter.yaml` | `system_filter_keywords` table, auto-synced from admin's `UserKeyword` |
| Search-term source (NSF/NIH/Grants.gov queries) | `conf/sources/government.yaml::*.search_keywords` | `system_search_terms` table, auto-synced from admin's `UserKeyword` |
| Sources list (URLs) | `conf/sources/*.yaml` | unchanged — stays in YAML |
| Per-user digest sender | None (built but unwired) | APScheduler nightly job iterating `email_scheduler.get_users_due_for_email` |
| Static history page | Generated from `state.db` after Thursday email | Generated from `platform.db` after fetch + after each per-user digest |
| Bridge code | `web/services/seed_opportunities.py` | Deleted |
| Postgres support | Yes | Removed (asyncpg dep dropped, `docker-compose.yml` simplified) |

### 4.3 Data flow — Thursday noon fetch (consolidated)

1. APScheduler trigger (`weekly_fetch_job`, Thursday 12:00 MT) calls `web/services/fetch_runner.run_fetch(db_session)`.
2. `fetch_runner` reads `system_search_terms` and `system_filter_keywords` from DB. Seeds them from admin's active `UserKeyword` rows on every run (idempotent — see §5.3).
3. `fetch_runner` invokes the existing `src/` fetchers in parallel (NSF, NIH, Grants.gov, government web sources, industry, university, compute) using terms from `system_search_terms` for the API queries. Web scrapers are unchanged (they don't take search terms).
4. Returned `Opportunity` dataclasses go through `KeywordFilter` (using `system_filter_keywords`) → `LLMFilter` borderline pass → curated compute bypass (unchanged) → `Summarizer`.
5. Survivors are written to `platform.db` via SQLAlchemy ORM (new helper: `web/services/opportunity_writer.upsert_opportunity`). Dedup by `composite_id`, URL, and title-similarity (logic ported from `src/state.py`).
6. After successful fetch, the global digest HTML for that week is generated and archived (same as today, used by Thursday-8pm admin digest).
7. The static `docs/index.html` is regenerated.
8. Bootstrap state is updated (newly-bootstrapped sources marked).
9. `fetch_history` row recorded.

### 4.4 Data flow — per-user digest

1. APScheduler trigger (`per_user_digest_job`, hourly check) calls `email_dispatcher.dispatch_due_users(db_session)`.
2. For each user returned by `email_scheduler.get_users_due_for_email`:
   1. Build the user's digest HTML using `email_scheduler.get_opportunities_for_user` + the existing `Emailer.compose` template.
   2. Recipients = `[user.email] + active_broadcast_recipients(user_id)`.
   3. Each recipient gets a personalized email with their unsubscribe token in the footer (admin user gets none; broadcast recipients get one each).
   4. Send via `Emailer.send`.
   5. `mark_emailed` for the opportunities included.
   6. Record `UserEmailHistory` row.
   7. Update `last_sent_at` on `UserEmailPref`.
3. Regenerate the static `docs/index.html` to include any newly-emailed opportunities.

The admin's Thursday-8pm digest is a special case: it's the first user processed (since admin's frequency is weekly with `last_sent_at` set such that 8pm Thursday triggers).

## 5. Data model changes

All migrations expressed as Alembic revisions in `alembic/versions/`. SQLite-compatible (no Postgres-only types).

### 5.1 New tables

```sql
-- Search terms used for API queries (NSF/NIH/Grants.gov)
CREATE TABLE system_search_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL UNIQUE,
    source_user_id INTEGER NOT NULL,    -- which user contributed it (always admin in v1)
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_user_id) REFERENCES users(id)
);

-- Keyword filter applied at fetch time (mirrors FilterConfig)
CREATE TABLE system_filter_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    category TEXT NOT NULL,             -- 'primary' | 'domain' | 'career' | 'faculty' | 'compute' | 'exclusion'
    source_user_id INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (keyword, category),
    FOREIGN KEY (source_user_id) REFERENCES users(id)
);

-- Per-user broadcast list
CREATE TABLE broadcast_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    unsubscribe_token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    unsubscribed_at TEXT,
    UNIQUE (owner_user_id, email),
    FOREIGN KEY (owner_user_id) REFERENCES users(id)
);

-- Source bootstrap state (ported from src/state.py)
CREATE TABLE source_bootstrap (
    source_name TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    bootstrapped_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Fetch + email history (ported)
CREATE TABLE fetch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    fetch_window_start TEXT NOT NULL,
    fetch_window_end TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    count INTEGER NOT NULL DEFAULT 0,
    error_msg TEXT,
    created_at TEXT NOT NULL
);
-- (UserEmailHistory already exists in web/models/email_pref.py)
```

### 5.2 Modified tables

`opportunities` (existing) — add columns for fields currently held only in `state.db`:

```sql
ALTER TABLE opportunities ADD COLUMN opportunity_status TEXT DEFAULT 'open';
ALTER TABLE opportunities ADD COLUMN deadline_type TEXT DEFAULT 'fixed';
ALTER TABLE opportunities ADD COLUMN resource_type TEXT;
ALTER TABLE opportunities ADD COLUMN resource_provider TEXT;
ALTER TABLE opportunities ADD COLUMN resource_scale TEXT;
ALTER TABLE opportunities ADD COLUMN allocation_details TEXT;
ALTER TABLE opportunities ADD COLUMN eligibility TEXT;
ALTER TABLE opportunities ADD COLUMN access_url TEXT;
ALTER TABLE opportunities ADD COLUMN system_status TEXT DEFAULT 'pending_email';
-- system_status: 'pending_email' | 'emailed' | 'archived'
-- (most of these already exist on the SQLAlchemy model — verify before generating migration)
```

### 5.3 Auto-sync from admin's `UserKeyword`

Implementation: a SQLAlchemy event listener on `UserKeyword` (insert/update/delete) for the admin user (configurable via `ADMIN_USER_ID` setting; defaults to `1`).

```python
# web/services/keyword_sync.py
@event.listens_for(UserKeyword, 'after_insert')
@event.listens_for(UserKeyword, 'after_update')
@event.listens_for(UserKeyword, 'after_delete')
def sync_admin_keywords(mapper, connection, target):
    if target.user_id != settings.admin_user_id:
        return
    # Sync to system_search_terms (primary, domain, career, faculty categories)
    # Sync to system_filter_keywords (all categories incl. exclusion)
    ...
```

This also runs idempotently at the start of every fetch (defensive — covers the case where the admin edited keywords directly via SQL or the listener was missed).

For Project B the listener becomes "for any active user" with deduplication.

### 5.4 Migration script

One-time script at `scripts/migrate_state_db.py`:

1. Open `data/state.db` (read-only) and `data/platform.db` (read-write).
2. Run Alembic upgrade to head on `platform.db` (creates new tables, adds columns).
3. Copy `seen_opportunities` rows → `opportunities` (upsert by `composite_id`). Map `status='emailed'` → `system_status='emailed'`.
4. Copy `fetch_history` rows.
5. Copy `email_history` rows → `UserEmailHistory` for admin user.
6. Copy `source_bootstrap` rows.
7. Seed `system_search_terms` and `system_filter_keywords` from admin's `UserKeyword` (or, if admin has none, from `conf/filter.yaml` and `conf/sources/*.yaml::search_keywords` as a one-time bootstrap).
8. Move `data/state.db` → `data/state.db.legacy` (do not delete; keep for ~30 days).
9. Print summary: rows migrated, bootstrap state, next steps.

## 6. Component-level design

### 6.1 New: `web/services/fetch_runner.py`

Public function: `async def run_fetch(db: AsyncSession) -> FetchResult`.

Wraps the orchestration currently in `src/weekly_fetch.run_pipeline`. Differences:

- Reads search terms / filter keywords from DB (not `conf/*.yaml`).
- Writes opportunities via SQLAlchemy ORM (not raw SQLite).
- Returns a structured result (counts, errors) for HTTP endpoints / CLI.

Reuses **unchanged**: `src/fetcher/*`, `src/filter/*`, `src/summarizer.py`, `src/models.Opportunity` dataclass.

### 6.2 New: `web/services/email_dispatcher.py`

Public function: `async def dispatch_due_users(db: AsyncSession) -> list[DispatchResult]`.

Per due user: build digest, expand recipient list with broadcast list, render unsubscribe tokens, send, mark emailed, regenerate static history.

Reuses unchanged: `src/emailer.Emailer`, `templates/digest.html`, `web/services/email_scheduler.*`.

### 6.3 New: `web/services/keyword_sync.py`

SQLAlchemy event listeners + idempotent sync function. Sync is one direction: admin's `UserKeyword` → `system_*` tables. Other users' edits don't propagate (in v1).

### 6.4 New: `web/services/opportunity_writer.py`

`async def upsert_opportunity(db, opp: Opportunity) -> bool` — handles the dedup logic currently in `StateDB.store_opportunity` (composite_id + URL + title-similarity check), translated to SQLAlchemy.

### 6.5 New: `web/scheduler.py`

APScheduler `AsyncIOScheduler` wired into FastAPI lifespan. Two jobs:

- `weekly_fetch` — Thursday 12:00 MT, triggers `fetch_runner.run_fetch`.
- `digest_dispatcher` — hourly, triggers `email_dispatcher.dispatch_due_users` (the function internally checks who's due based on user prefs).

Job execution wrapped in a try/except that logs to `outputs/logs/scheduler.log`. On failure, recorded in `fetch_history` / `UserEmailHistory` with `success=0` and an `error_msg`.

### 6.6 New: `web/cli.py`

Click-based CLI with subcommands:

- `python -m web.cli fetch` — manual one-shot fetch (bypasses scheduler).
- `python -m web.cli email-digest [--user-id N | --all-due] [--test]` — manual digest send.
- `python -m web.cli regenerate-history` — re-run history page generation.
- `python -m web.cli migrate-state-db` — wraps `scripts/migrate_state_db.py`.

`fetch_now.sh` and `email_now.sh` become 2-line wrappers around these.

### 6.7 New: `web/routers/broadcast.py`

REST endpoints:

- `GET /api/v1/broadcast/recipients` — list current user's recipients.
- `POST /api/v1/broadcast/recipients` — add (generates unsubscribe token).
- `DELETE /api/v1/broadcast/recipients/{id}` — remove.
- `GET /unsubscribe/{token}` — public, no auth, marks recipient inactive and returns confirmation HTML.

### 6.8 Deletions

- `web/services/seed_opportunities.py` — bridge no longer needed.
- `web/main.py:lifespan` — remove the `seed()` call.
- `src/weekly_fetch.py::main` — keep file for now but `main()` becomes a thin wrapper over `web/cli.py fetch`.
- `src/weekly_email.py::main` — same treatment.
- `launchd/*.plist` — replace with a single plist that starts `uv run uvicorn web.main:app` as a long-running service.

## 7. Configuration changes

### 7.1 `web/config.py` additions

```python
admin_user_id: int = 1
admin_email: str = ""               # used to identify admin user on first run
scheduler_enabled: bool = True       # set False for one-off CLI invocations
fetch_cron_day_of_week: str = "thu"  # APScheduler cron syntax
fetch_cron_hour: int = 12
fetch_cron_minute: int = 0
fetch_cron_timezone: str = "America/Denver"
digest_check_interval_minutes: int = 60
```

### 7.2 `conf/filter.yaml` and `conf/sources/*.yaml::search_keywords`

After migration, `conf/filter.yaml` becomes a **bootstrap-only artifact** — read once by the migration script when admin has no keywords yet, never read at runtime again. Same for `search_keywords` blocks inside `conf/sources/*.yaml`.

The remainder of `conf/sources/*.yaml` (the source URLs themselves) stays authoritative.

### 7.3 `docker-compose.yml`

Drop the `db` service, drop `DATABASE_URL` override (default in-container path = `sqlite+aiosqlite:////data/platform.db`), mount `./data` as a volume for persistence.

### 7.4 Environment variables

Drop: `DATABASE_URL` (default to SQLite path).
Keep: `OPENAI_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `JWT_SECRET_KEY`, `GRANTS_GOV_API_KEY`.

## 8. Error handling and observability

- **Fetch failures**: Per-source exceptions caught in `fetch_runner` (already done via `asyncio.gather(return_exceptions=True)`). Source-level failure recorded in `fetch_history`. Pipeline continues with surviving sources.
- **Summarizer failures**: Already retried via `tenacity` in `src/summarizer`. Fallback: store opportunity with empty summary and a `summary_pending=True` flag (new field) for retry later.
- **Email send failures**: Per-recipient try/except. One bounce doesn't fail the whole batch. Logged + recorded in `UserEmailHistory`.
- **APScheduler failures**: Job exceptions logged at ERROR. Misfire grace period 1 hour. If FastAPI restarts mid-job, the job re-runs at the next scheduled time (no resume — fetches are idempotent on dedup).
- **Logging**: Structured logs to `outputs/logs/` (existing) plus stdout. Log levels: `INFO` for milestones, `WARNING` for per-source failures, `ERROR` for job-level failures.

## 9. Testing strategy

### 9.1 Unit tests (new + ported)

- `tests/test_keyword_sync.py` — admin keyword edits propagate to `system_*` tables; non-admin edits don't.
- `tests/test_opportunity_writer.py` — dedup logic (composite_id, URL, title similarity).
- `tests/test_fetch_runner.py` — mocked fetchers + filter; assert pipeline order, dedup, summarization.
- `tests/test_email_dispatcher.py` — mocked SMTP; verify recipient expansion (user + broadcast list), unsubscribe token rendering, `mark_emailed` called.
- `tests/test_broadcast.py` — REST CRUD, unsubscribe flow.
- Existing `tests/test_filter.py`, `tests/test_fetchers.py`, `tests/test_emailer.py` — should pass unchanged (they test `src/` library code).
- `tests/test_phase{1..4}.py` — review and port any state.db-specific assertions to platform.db.

### 9.2 Integration tests

- `tests/test_consolidated_pipeline.py` — end-to-end: trigger `fetch_runner.run_fetch` against a SQLite fixture, assert opportunities written, assert digest rendered, assert history regenerated.
- `tests/test_migration.py` — feed a fixture `state.db`, run `migrate_state_db.py` against an empty `platform.db`, assert row counts and field mappings.

### 9.3 Manual verification

- Run `python -m web.cli fetch` against staging DB; eyeball the digest HTML.
- Add a test broadcast recipient, send digest, click unsubscribe link, confirm row marked inactive.
- Restart FastAPI; confirm scheduler picks up jobs without firing immediately.

## 10. Migration plan

Sequential rollout, single environment (no canary):

1. **Branch.** `git checkout -b consolidate-pipeline-platform`.
2. **Schema first.** Generate Alembic migration for new tables + column adds. Run on a copy of `platform.db`. Verify schema.
3. **Code in pieces** (each piece testable in isolation):
   1. `keyword_sync.py` + tests.
   2. `opportunity_writer.py` + tests.
   3. `fetch_runner.py` + tests.
   4. `email_dispatcher.py` + tests.
   5. `scheduler.py` + tests.
   6. `cli.py` + tests.
   7. `routers/broadcast.py` + tests.
4. **Migration script.** Write `migrate_state_db.py`. Test against a copy of production `state.db`.
5. **Wire into `main.py`.** Add scheduler to lifespan; remove `seed()` call.
6. **Cutover** (single window, ideally Friday morning so first new-system fetch is the following Thursday):
   - Stop existing launchd jobs (`launchctl unload`).
   - Stop FastAPI.
   - Back up `data/`.
   - Run `python -m web.cli migrate-state-db`.
   - Start FastAPI with new code (scheduler kicks in).
   - Run `python -m web.cli fetch` once manually to verify; eyeball digest output.
7. **Update launchd.** Replace two task plists with one service plist that runs `uv run uvicorn web.main:app`.
8. **Watch first scheduled fetch** (Thursday noon MT). Verify digest (Thursday 8 PM MT).
9. **Delete `seed_opportunities.py`** and other obsolete code. Commit cleanup separately.
10. **Archive** `data/state.db.legacy` after 30 days of clean operation.

## 11. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Migration loses opportunities | Low | High | Dry-run on copy; row-count assertions; keep `state.db.legacy` |
| APScheduler misfires (job runs late or twice) | Medium | Low | Dedup on `composite_id` makes double-fetch a no-op; misfire grace 1h |
| FastAPI crash → no scheduled fetch | Low | Medium | Add a launchd `KeepAlive` directive; missed fetch next week catches up via 7-day window |
| Per-user digest sends to wrong users | Low | High | Test coverage on recipient expansion; staging dry-run |
| SQLite `database is locked` under concurrent writes | Medium | Low | WAL mode + `PRAGMA busy_timeout=5000`; serialize fetch writes within a single transaction |
| Admin keyword edit doesn't propagate to `system_*` | Medium | Medium | Idempotent sync at fetch start as backstop; explicit test |
| Broadcast unsubscribe link leaks (token guessable) | Low | Medium | UUID4 tokens; not enumerable |

## 12. Open questions for the reviewer

1. **APScheduler vs cron-hits-endpoint for v1** — settled on APScheduler, but if there's a deployment concern (e.g., planned multi-worker uvicorn), revisit.
2. **Broadcast list size cap?** Should we limit to e.g. 25 recipients per user to discourage spam-list misuse?
3. **Admin-user identification on fresh installs.** Current proposal: `ADMIN_USER_ID=1` env var defaulting to first registered user. Should we instead require an explicit `ADMIN_EMAIL` and look up the ID at runtime?
4. **Should `email_dispatcher` regenerate the static history page after every per-user send, or only after the admin's send?** Current proposal: every send. Cheap; ensures freshness.
5. **The `system_filter_keywords` exclusion category for non-admin users (Project B prep)**: should other users' personal exclusions also propagate, or stay user-local? Current proposal: stay user-local; system-level exclusions remain admin-only.

## 13. Appendix — file-level change summary

**New files**
- `web/services/fetch_runner.py`
- `web/services/email_dispatcher.py`
- `web/services/keyword_sync.py`
- `web/services/opportunity_writer.py`
- `web/scheduler.py`
- `web/cli.py`
- `web/routers/broadcast.py`
- `web/models/broadcast.py`
- `web/models/system_keywords.py`
- `web/models/source_bootstrap.py`
- `web/models/fetch_history.py`
- `scripts/migrate_state_db.py`
- `alembic/versions/<timestamp>_consolidate_schema.py`
- Tests (see §9)

**Modified**
- `web/main.py` — add scheduler to lifespan; drop `seed()` call.
- `web/config.py` — add admin/scheduler settings.
- `web/models/opportunity.py` — verify all `state.db` columns are present.
- `pyproject.toml` — add `apscheduler`, `click`; remove `asyncpg`.
- `docker-compose.yml` — drop `db` service.
- `scripts/fetch_now.sh`, `scripts/email_now.sh` — 2-line wrappers around `web/cli.py`.
- `launchd/*.plist` — replace with single FastAPI service plist.
- `README.md`, `CLAUDE.md` — reflect single-system architecture.

**Deleted**
- `web/services/seed_opportunities.py`

**Archived (kept as-is for now; library only)**
- `src/weekly_fetch.py`, `src/weekly_email.py` — `main()` becomes a deprecation notice pointing to `web/cli.py`. Other functions remain importable from `web/services/fetch_runner.py`.

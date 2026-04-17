# Consolidate Internal Pipeline and Web Platform — Design

**Date:** 2026-04-16
**Status:** Draft v2 — revised after Codex review (job `task-mo2a6875-qwt8cu`, session `019d993d-03ca-71b2-b45e-0036bf05ef98`)
**Author:** Boyu Yu (with Claude)

## Revision history

- **2026-04-16 v2:** revised based on Codex rescue review. Major changes:
  - **D4 reversed**: APScheduler-in-process replaced by **launchd → `python -m web.cli` per job**. Reason: `src/summarizer.py` and `src/emailer.py` make blocking calls inside `async def`; running these in the FastAPI event loop would stall the API.
  - **Per-user email delivery state** (`user_email_deliveries` table) added — replaces a global `opportunities.system_status` flag, which would have broken multi-user delivery (Codex C3).
  - **`system_search_terms` gains a `target_source` column** to preserve per-source search distinction (NSF/NIH/Grants.gov each have different keywords today).
  - **All `system_*` FKs are UUID** (matches `web/models/user.py:16`).
  - **Schema reconciliation made an explicit prerequisite** — `alembic.ini` still points at Postgres, `web/main.py` still uses `create_all()`, and `platform.db` already drifts from the ORM. This must be cleaned up before consolidation migrations.
  - **Keyword sync mechanism changed** from SQLAlchemy mapper events to session-level `after_flush` listener (or explicit sync from the keyword router).
  - **Cutover hardened** — FastAPI restarts without launchd jobs re-armed; smoke-test must pass before re-arming.
  - **Open questions §12 resolved** with Codex's recommendations.
  - Smaller fixes: drop `compute` from `system_filter_keywords` categories (compute opps already bypass the filter), include Grants.gov approaching-deadlines pass, honor `day_of_week`/`time_of_day` in due logic, refactor `HistoryGenerator`/`Emailer` boundaries, multi-session transaction boundaries in fetch_runner, ADMIN_EMAIL bootstrap (not `ADMIN_USER_ID=1`), broadcast list capped at 25.
- **2026-04-16 v1:** initial draft.

## 1. Context

The repository currently runs **two coexisting systems** that share opportunity data via a one-way bridge:

- **Internal pipeline (`src/`)** — single-user Python CLI driven by `conf/*.yaml`. Runs on launchd every Thursday: noon (fetch) and 8 PM (email). Writes to `data/state.db` (SQLite). Generates a static history page at `docs/index.html`. Owns all fetchers, the keyword filter, the LLM borderline filter, the summarizer, and the SMTP digest.
- **Web platform (`web/` + `frontend/`)** — multi-user FastAPI + React app with its own DB (`data/platform.db` SQLite or `funding_platform` Postgres). Per-user keyword profiles, scoring, bookmarks, dismissals, AI chat, document uploads, and email preferences. Does not fetch its own opportunities; copies them from `data/state.db` on startup via `web/services/seed_opportunities.py`.

This split is historical. It causes:

- Two databases to keep in sync (`seed_opportunities.py` is a leaky bridge).
- Two scoring layers that drift (YAML in `src/`, DB in `web/`).
- Confused ownership of the opportunity schema.
- The platform's `email_scheduler.py` is built but unwired; per-user digests don't actually go out.
- The platform's `web/main.py:18` calls `create_all()` on startup, bypassing Alembic; the live `platform.db` schema has already drifted from the ORM.

This design consolidates everything into `web/`, with `src/` retained as a fetch/filter/summarize **library** invoked by a CLI (`web/cli.py`) that launchd schedules. FastAPI itself runs no background jobs.

## 2. Goals and non-goals

### 2.1 Goals (Project A — this spec)

- One database (SQLite, WAL mode) as the single source of truth.
- Scheduling via existing launchd → `python -m web.cli {fetch,email-digest}`.
- Admin user account (identified by `ADMIN_EMAIL`, persisted via existing `users.is_admin`) drives the system fetch via `system_search_terms` and `system_filter_keywords`, auto-synced from the admin's `UserKeyword` rows.
- **Behavior parity with today**: same Thursday-noon fetch, same Thursday-8pm digest content, same static history page, same OpenAI cost — *plus* the Grants.gov approaching-deadlines pass that already runs today.
- Per-user broadcast lists (≤25 recipients/user); tokenized unsubscribe.
- In-app per-user history view in addition to the global static page.
- D3-shaped data model: when Project B arrives, the only change is swapping the auto-sync source from "admin user" to "union of all users" — no re-architecture.
- Per-user delivery state via `user_email_deliveries` so multiple users can independently track what they've received.

### 2.2 Non-goals (deferred to Project B)

- Per-user fetch agents.
- Union-of-users `system_search_terms`.
- Embedding-based semantic matching beyond what `web/services/scoring.py` already does.
- Public registration of arbitrary users (registration already works; this spec doesn't expand the audience).
- Postgres support (drop for now; can return when scale demands it).

## 3. Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Broadcast list per user (CC colleagues, no login required), capped at 25/user | Lowest-friction colleague onboarding; the current static recipient list has 5 entries, so 25 is generous |
| D2 | Admin user account drives the system fetch; identified via `ADMIN_EMAIL` env → `users.is_admin` flag | Matches "internal system is just my account" framing; `is_admin` already exists at `web/models/user.py:25` |
| D3 | `system_search_terms(term, target_source, ...)` + `system_filter_keywords` tables, seeded from admin's `UserKeyword`; D3-ready (Project B swaps source to union-of-users) | Sub-linear scaling; preserves per-source search-term distinction (NSF/NIH/Grants.gov each have their own search term lists today) |
| D4 | **launchd → `python -m web.cli` per job** (NOT APScheduler in-process). FastAPI runs no background jobs. | `src/summarizer.py:49` and `src/emailer.py:124` make blocking sync calls inside `async def`; in-process scheduler would stall the API event loop and require `--workers 1`. CLI process per job is simpler and parallelism-safe. |
| D5 | One-time migration of `data/state.db` → `data/platform.db`; archive `state.db.legacy` only after smoke test passes | Clean cut-over, preserves history, reversible |
| D6 | Both global static `docs/index.html` (regenerated only after admin's digest) and in-app per-user history view (backed by `user_email_deliveries`) | Public archive + logged-in personalization, without per-user-send page churn |
| D7 | Keep fetch-time relevance filter, but source it from `system_filter_keywords` (DB) instead of `conf/filter.yaml`. Numeric thresholds (`keyword_threshold`, `llm_threshold`, borderline range) move to `web/config.py` (with sensible defaults matching today). | Cost-flat, behavior parity, world-scale upgrade is one query change |
| D8 | SQLite-only (drop Postgres); WAL mode; `PRAGMA busy_timeout=5000` | Scale doesn't justify Postgres; eliminates dev pain; simplifies Docker |
| D9 | `conf/sources/*.yaml` source endpoint list stays in YAML | Source endpoints change rarely; version-controlled |
| D10 | Repurpose `fetch_now.sh` and `email_now.sh` as `python -m web.cli fetch` / `email-digest [--user-email ...]` wrappers | Same UX; same DB |
| D11 | Tokenized unsubscribe link (UUID4) in every broadcast email; recipients_remove on click | Standard practice; legal/anti-spam |
| D12 | Auto-sync from admin's `UserKeyword` via session-level `after_flush` listener (not mapper events). Backstop: idempotent re-sync at start of every fetch. | Mapper events have flush restrictions per SQLAlchemy docs; session-level events run safely inside the parent transaction |
| D13 | Port `source_bootstrap` table directly into platform DB | Same logic, same behavior |
| D14 | Per-user "already sent" state in a new `user_email_deliveries(user_id, opportunity_id, sent_at)` table — NOT a global `opportunities.system_status` column | Multi-user correct; required to deliver the same opp to multiple users without one user's send blocking another's |
| D15 | **Schema reconciliation precedes consolidation.** Fix `alembic.ini` to SQLite, drop `create_all()` from `web/main.py:18`, generate a baseline migration that captures current `platform.db` drift, then layer consolidation migrations on top. | Without this, every subsequent migration risks fighting the drift |

## 4. Architecture

### 4.1 Component layout (post-consolidation)

```
┌──────────────────────────────────────────────────────────────┐
│  launchd (per-job CLI processes)                              │
│                                                               │
│  ┌─────────────────────────────┐ ┌──────────────────────────┐│
│  │ thu 12:00 MT                 │ │ hourly                   ││
│  │ uv run python -m web.cli    │ │ uv run python -m web.cli ││
│  │   fetch                      │ │   email-digest --due     ││
│  └────────────┬────────────────┘ └──────────────┬───────────┘│
│               │                                  │            │
└───────────────┼──────────────────────────────────┼────────────┘
                │                                  │
                ▼                                  ▼
       ┌─────────────────┐                ┌────────────────────┐
       │ web/cli.py       │                │ web/cli.py          │
       └────────┬─────────┘                └─────────┬──────────┘
                │                                    │
        ┌───────▼─────────┐               ┌──────────▼───────────┐
        │ web/services/    │               │ web/services/         │
        │  fetch_runner    │  ←—— shared ——→  email_dispatcher   │
        │  opportunity_    │               │  email_scheduler      │
        │   writer         │               │                       │
        │  auto_scorer     │               │                       │
        └───────┬─────────┘               └──────────┬───────────┘
                │                                    │
                │   ┌──────────────────────────┐    │
                │   │ src/  (library only)      │    │
                └──→│  fetchers, filter,        │←───┘
                    │  summarizer, history,     │
                    │  emailer                  │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                       ┌──────────────────────┐
                       │ data/platform.db      │
                       │ (SQLite, WAL)         │
                       └─────────┬────────────┘
                                 ▲
                                 │
       ┌─────────────────────────┴──────────────────────────┐
       │ FastAPI app (web/main.py)                          │
       │   HTTP routers, auth, scoring, in-app UI            │
       │   NO background jobs                                │
       └─────────────────────────────────────────────────────┘
```

### 4.2 What changes vs. today

| Area | Before | After |
|------|--------|-------|
| Databases | `data/state.db` (SQLite) + `data/platform.db` (SQLite) or Postgres | `data/platform.db` (SQLite, WAL) only |
| Scheduling | launchd → `python -m src.weekly_fetch` / `weekly_email` | launchd → `python -m web.cli fetch` / `email-digest --due` (per-job process) |
| Fetch trigger | CLI script + cron | Same shape — CLI script + launchd, but writing to platform DB and reading config from DB |
| Filter source | `conf/filter.yaml` | `system_filter_keywords` table, auto-synced from admin's `UserKeyword`. Thresholds in `web/config.py`. |
| Search-term source (NSF/NIH/Grants.gov queries) | `conf/sources/government.yaml::*.search_keywords` (per-source) | `system_search_terms(term, target_source)` table, auto-synced from admin's `UserKeyword`, partitioned by `target_source` |
| Sources list (URLs) | `conf/sources/*.yaml` | unchanged — stays in YAML |
| Per-user "already emailed" state | Global `seen_opportunities.status='emailed'` in `state.db` | Per-user `user_email_deliveries(user_id, opportunity_id, sent_at)` join table |
| Per-user digest sender | None (built but unwired; ignores `day_of_week`/`time_of_day`) | `python -m web.cli email-digest --due`, hourly via launchd; honors prefs |
| Static history page | Generated from `state.db` after Thursday email | Generated from `platform.db` after admin's digest only (per-user freshness lives in the in-app view) |
| Bridge code | `web/services/seed_opportunities.py` | Deleted |
| Postgres support | Yes | Removed (`Dockerfile.web:18`, `docker-compose.yml:20` updated; asyncpg dropped if present) |
| Schema management | `Base.metadata.create_all()` at startup, no Alembic versions on disk | Alembic migrations are authoritative; `create_all()` removed from lifespan |

### 4.3 Data flow — Thursday noon fetch (consolidated)

1. launchd fires `uv run python -m web.cli fetch` at Thu 12:00 MT.
2. CLI opens an `AsyncSession`, reads `system_search_terms` (grouped by `target_source`) and `system_filter_keywords`, plus thresholds from `web/config.py`. Backstop sync from admin's `UserKeyword` runs first (idempotent — see §5.3). Closes the session before remote I/O begins.
3. `fetch_runner.run_fetch` invokes the existing `src/` fetchers in parallel — NSF, NIH, Grants.gov each get *their* term list; web scrapers (industry, university, compute) and the Grants.gov approaching-deadlines pass run unchanged. No DB session is held during HTTP/LLM calls.
4. Returned `Opportunity` dataclasses go through `KeywordFilter` → `LLMFilter` borderline pass → curated compute bypass (unchanged) → `Summarizer`.
5. Survivors are written via short-lived sessions (one transaction per source's batch, not one giant transaction). `opportunity_writer.upsert_opportunity` handles dedup (composite_id + URL + title-similarity, logic ported from `src/state.py`).
6. **Auto-score step**: for every newly-stored opportunity, `auto_scorer.score_for_all_active_users` writes a `UserOpportunityScore` row per active user. Without this step, the per-user digest finds nothing to send.
7. `fetch_history` row recorded.
8. Bootstrap state updated.
9. Static `docs/index.html` is regenerated *if and only if* the admin's digest is also being generated this run (per D6, the static page tracks the admin's emailed set).
10. CLI exits cleanly. Exit code communicates success/failure to launchd and any monitoring.

### 4.4 Data flow — per-user digest

1. launchd fires `uv run python -m web.cli email-digest --due` hourly.
2. CLI calls `email_dispatcher.dispatch_due_users(db_session, now)`.
3. `email_scheduler.get_users_due_for_email` is **rewritten** to honor `frequency` AND `day_of_week` AND `time_of_day` (current implementation at `web/services/email_scheduler.py:32` only checks `frequency`, despite `day_of_week`/`time_of_day` existing on the model).
4. For each due user:
   1. Compute opportunities to include: scored above the user's `min_score`, deadline within the user's `deadline_lookahead_days`, NOT already in `user_email_deliveries` for this user.
   2. Build digest HTML — adapter layer translates ORM rows + scores into the dict shape `Emailer.compose()` expects (see §6.1).
   3. Recipients = `[user.email] + active_broadcast_recipients(user_id)`. Each broadcast recipient's email gets its own copy with their unsubscribe token in the footer (admin's own email gets none).
   4. Send via `Emailer.send` (per-recipient try/except; one bounce doesn't fail the batch).
   5. Insert `user_email_deliveries` rows for each opportunity sent.
   6. Insert `UserEmailHistory` row.
   7. Update `last_sent_at` on `UserEmailPref`.
5. After all due users processed: if the admin user was among them, regenerate `docs/index.html`.

### 4.5 Concurrency contract

- launchd guarantees only one `web.cli fetch` runs at a time (per-job `KeepAlive: false`, `LaunchOnlyOnce: true`-style discipline by exit code). Manual `web.cli fetch` invocations check for an advisory lock file (`data/.fetch.lock`) and refuse if held.
- FastAPI is read-mostly; SQLite WAL allows concurrent readers + a single writer, so CLI fetch (writer) and FastAPI (reader) don't block each other.
- Multi-worker FastAPI is fine because no background jobs run inside FastAPI.

## 5. Data model changes

All migrations expressed as Alembic revisions in `alembic/versions/`. SQLite-compatible; no Postgres-only types. UUID columns use `CHAR(32)` on SQLite (SQLAlchemy's automatic fallback for `UUID(as_uuid=True)`); existing model definitions are unchanged.

### 5.0 Schema reconciliation (prerequisite, before any consolidation migration)

This is its own commit / migration revision, landed *first*:

1. Update `alembic.ini:4` from Postgres URL to `sqlite+aiosqlite:///data/platform.db`.
2. Remove the `create_all()` call from `web/main.py:18` (the lifespan).
3. Generate a baseline Alembic revision that captures the current ORM schema, then a `001_baseline_reconciliation` revision that adds the columns the live `platform.db` is missing (`opportunities.opportunity_status` / `deadline_type` / `resource_*` / `eligibility` / `access_url` if absent; `user_opportunity_scores.{keyword,profile,behavior,urgency}_score` if absent). Run on a copy first; verify.
4. After this, all schema changes are Alembic-only.

### 5.1 New tables

```sql
-- Search terms used for API queries (NSF/NIH/Grants.gov)
CREATE TABLE system_search_terms (
    id              CHAR(32) PRIMARY KEY,           -- UUID
    term            VARCHAR(256) NOT NULL,
    target_source   VARCHAR(64) NOT NULL,           -- 'nsf' | 'nih' | 'grants_gov' | 'all'
    source_user_id  CHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_active       BOOLEAN NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL,
    UNIQUE (term, target_source, source_user_id)
);
CREATE INDEX ix_system_search_terms_target_active ON system_search_terms(target_source, is_active);

-- Keyword filter applied at fetch time (mirrors FilterConfig)
CREATE TABLE system_filter_keywords (
    id              CHAR(32) PRIMARY KEY,
    keyword         VARCHAR(256) NOT NULL,
    category        VARCHAR(32) NOT NULL,           -- 'primary' | 'domain' | 'career' | 'faculty' | 'exclusion'
    source_user_id  CHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_active       BOOLEAN NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL,
    UNIQUE (keyword, category, source_user_id)
);
-- NOTE: 'compute' deliberately omitted — compute opps already bypass the keyword filter
-- (see src/weekly_fetch.py:395). Adding it would be misleading.

-- Per-user broadcast list (recipients of a user's digest)
CREATE TABLE broadcast_recipients (
    id                  CHAR(32) PRIMARY KEY,
    owner_user_id       CHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email               VARCHAR(320) NOT NULL,
    name                VARCHAR(256),
    is_active           BOOLEAN NOT NULL DEFAULT 1,
    unsubscribe_token   CHAR(36) NOT NULL UNIQUE,    -- UUID4 string form
    created_at          DATETIME NOT NULL,
    unsubscribed_at     DATETIME,
    UNIQUE (owner_user_id, email)
);
-- Application-level cap of 25 active recipients per owner_user_id
-- (validated in web/routers/broadcast.py POST handler)

-- Per-user delivery state (replaces global emailed flag)
CREATE TABLE user_email_deliveries (
    id              CHAR(32) PRIMARY KEY,
    user_id         CHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    opportunity_id  CHAR(32) NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    sent_at         DATETIME NOT NULL,
    UNIQUE (user_id, opportunity_id)
);
CREATE INDEX ix_user_email_deliveries_user_sent ON user_email_deliveries(user_id, sent_at);

-- Source bootstrap state (ported from src/state.py:61)
CREATE TABLE source_bootstrap (
    source_name      VARCHAR(64) PRIMARY KEY,
    source_type      VARCHAR(32) NOT NULL,
    bootstrapped_at  DATETIME NOT NULL,
    created_at       DATETIME NOT NULL
);

-- Fetch + email history (ported)
CREATE TABLE fetch_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              VARCHAR(64) NOT NULL,
    fetch_window_start  DATETIME NOT NULL,
    fetch_window_end    DATETIME NOT NULL,
    success             BOOLEAN NOT NULL DEFAULT 1,
    count               INTEGER NOT NULL DEFAULT 0,
    error_msg           TEXT,
    created_at          DATETIME NOT NULL
);
-- (UserEmailHistory already exists in web/models/email_pref.py — extend if needed)
```

### 5.2 Modified tables

`opportunities` (existing) — most columns already exist on the SQLAlchemy model (`web/models/opportunity.py`); the *live* DB is what's missing them. Reconciliation in §5.0 covers this. **No `system_status` column is added** — per-user state lives in `user_email_deliveries`.

### 5.3 Auto-sync from admin's `UserKeyword`

**Mechanism**: a session-level `after_flush` listener registered on the global `Session` factory.

```python
# web/services/keyword_sync.py
from sqlalchemy import event
from web.database import async_session  # the AsyncSession factory

@event.listens_for(async_session.sync_session_class, "after_flush")
def sync_admin_keywords(session, flush_context):
    admin_user_id = _resolve_admin_user_id(session)
    touched = [obj for obj in session.new | session.dirty | session.deleted
               if isinstance(obj, UserKeyword) and obj.user_id == admin_user_id]
    if not touched:
        return
    _resync_system_tables(session, admin_user_id)
```

`after_flush` runs inside the parent transaction; if the parent rolls back, the system-table writes roll back too. `after_commit` would be wrong here (cannot emit SQL on the same connection), and mapper-level events have flush restrictions per the SQLAlchemy docs.

**Backstop**: `fetch_runner` calls `_resync_system_tables(session, admin_user_id)` at the start of every fetch — covers cases where the admin edited keywords directly via SQL or the listener was somehow missed.

For Project B, the listener becomes "for any active user" with appropriate dedup.

### 5.4 Migration script

`scripts/migrate_state_db.py`:

1. Verify schema reconciliation (§5.0) is complete on `platform.db` (Alembic revision check).
2. Open `data/state.db` (read-only) and `data/platform.db` (read-write, SQLite WAL).
3. Apply consolidation Alembic revision (creates new tables in §5.1).
4. Resolve admin user via `ADMIN_EMAIL` → `users` row (`is_admin=true`). Fail loudly if not found.
5. Copy `seen_opportunities` rows → `opportunities` (upsert by `composite_id`).
6. For rows where `state.db.status='emailed'`, insert a `user_email_deliveries(admin_user_id, opportunity_id, fetched_at)` row.
7. Copy `fetch_history` rows.
8. Copy `email_history` rows → `UserEmailHistory` for admin user.
9. Copy `source_bootstrap` rows.
10. Seed `system_search_terms` and `system_filter_keywords` from admin's `UserKeyword` rows. If admin has none yet, do a one-time bootstrap from `conf/filter.yaml` and `conf/sources/*.yaml::search_keywords` (preserving `target_source` per source).
11. Print summary: rows migrated, deliveries created, bootstrap state.
12. Verify counts (assertions). Exit non-zero on mismatch.
13. **Do not** rename `state.db` here — that happens after smoke test (§10).

## 6. Component-level design

### 6.1 New: `web/services/fetch_runner.py`

Public function: `async def run_fetch(now: datetime) -> FetchResult`.

Owns its own session lifecycle. Opens short-lived sessions for: (a) initial config read + admin keyword resync, (b) each source-batch write, (c) post-fetch bookkeeping (fetch_history, bootstrap state). No session is held across HTTP or LLM calls.

Reuses unchanged from `src/`: `fetcher/*`, `filter/*`, `summarizer.py`, `models.Opportunity` dataclass, `fetcher/grants_gov.GrantsGovFetcher.fetch_approaching_deadlines`.

### 6.2 New: `web/services/email_dispatcher.py`

Public function: `async def dispatch_due_users(now: datetime) -> list[DispatchResult]`.

Per due user: build digest, expand recipient list with broadcast list, render unsubscribe tokens, send, write `user_email_deliveries` + `UserEmailHistory`. Adapter helper translates `(Opportunity, UserOpportunityScore)` tuples into the dict shape `Emailer.compose()` expects (see §6.4).

### 6.3 New: `web/services/keyword_sync.py`

Session-level `after_flush` listener (§5.3) plus the idempotent `_resync_system_tables` helper.

### 6.4 New: `web/services/email_compose_adapter.py`

`Emailer.compose()` (in `src/emailer.py:43`) expects pre-grouped dict lists, not ORM rows. This adapter takes `(Opportunity, UserOpportunityScore)` tuples and groups them by `source_type` into the shape `compose()` accepts — without modifying `src/emailer.py`. Keeps the `src/` library boundary clean.

### 6.5 New: `web/services/auto_scorer.py`

`async def score_new_opportunities(opportunity_ids: list[UUID]) -> None` — for each newly-stored opportunity, runs `web/services/scoring.py` for all active users. Called from `fetch_runner` at the end of each source batch. Without this, per-user digests find no scored opps.

### 6.6 New: `web/services/opportunity_writer.py`

`async def upsert_opportunity(session, opp: Opportunity) -> tuple[Opportunity, bool]` — handles the dedup logic currently in `StateDB.store_opportunity` (composite_id + URL + title-similarity), translated to SQLAlchemy. Returns the (DB row, was_new).

### 6.7 New: `web/cli.py`

Click-based CLI:

- `python -m web.cli fetch` — runs `fetch_runner.run_fetch(now=datetime.utcnow())`. Acquires `data/.fetch.lock` advisory file lock; refuses if held. Exit code 0 on success, non-zero on failure.
- `python -m web.cli email-digest [--due | --user-email EMAIL] [--test]` — runs `email_dispatcher.dispatch_due_users` (default `--due`) or sends to a single user. `--test` sends only to the user's own email, skipping broadcast list and not writing `user_email_deliveries`.
- `python -m web.cli regenerate-history` — re-runs the static history generator.
- `python -m web.cli migrate-state-db` — wraps `scripts/migrate_state_db.py`.

`fetch_now.sh` and `email_now.sh` become 2-line wrappers around these subcommands.

### 6.8 New: `web/routers/broadcast.py`

REST endpoints (auth required except `/unsubscribe/{token}`):

- `GET /api/v1/broadcast/recipients` — list current user's recipients.
- `POST /api/v1/broadcast/recipients` — add (validates ≤25 active recipients per user; generates UUID4 unsubscribe token).
- `DELETE /api/v1/broadcast/recipients/{id}` — remove.
- `GET /unsubscribe/{token}` — public, no auth, marks recipient inactive, returns confirmation HTML.

### 6.9 Modified: `web/services/email_scheduler.py`

Rewrite `get_users_due_for_email` to honor `frequency` AND `day_of_week` AND `time_of_day` from `UserEmailPref`. Drop the assumption that `last_sent_at + N days` is enough.

### 6.10 Refactor: `src/history_generator.py` boundary

Currently hard-wired to `StateDB`. Extract a small `HistoryDataSource` protocol (just the methods the generator uses) and provide a `PlatformDBSource` implementation in `web/services/`. `HistoryGenerator` itself stays library code.

### 6.11 Deletions

- `web/services/seed_opportunities.py`
- `web/main.py:lifespan` — remove `seed()` call AND `create_all()` call (the latter via §5.0)
- `src/weekly_fetch.py::main` and `src/weekly_email.py::main` — replaced by deprecation stubs that print "use `python -m web.cli`" and exit non-zero. Other functions stay importable.
- `launchd/com.boyu.funding-agent.weekly.plist` and `daily.plist` — replaced by two new plists that invoke `web/cli` subcommands.

## 7. Configuration changes

### 7.1 `web/config.py` additions

```python
# Admin
admin_email: str = ""                            # required at runtime
# Filter thresholds (relocated from conf/filter.yaml)
keyword_threshold: float = 0.3
llm_threshold: float = 0.5
borderline_min: float = 0.2
borderline_max: float = 0.6
# Database
sqlite_busy_timeout_ms: int = 5000
sqlite_wal_mode: bool = True
```

(No scheduler settings — there is no in-process scheduler.)

### 7.2 `conf/filter.yaml` and `conf/sources/*.yaml::search_keywords`

After migration, both become **bootstrap-only artifacts** read once by the migration script and never again at runtime. The source URL list in `conf/sources/*.yaml` remains authoritative.

### 7.3 `Dockerfile.web` and `docker-compose.yml`

- `Dockerfile.web:18` — drop the Postgres-related installs.
- `docker-compose.yml:20` — drop the `db` service and Postgres env vars; mount `./data` as a volume; default `DATABASE_URL` to SQLite.
- Add a small sidecar container (or document how to set up host cron) that runs the launchd-equivalent CLI invocations on a schedule. For now, document the pattern; users on Mac use launchd, users on Linux use cron.

### 7.4 Environment variables

- New: `ADMIN_EMAIL` (required for migration script + keyword sync).
- Drop: `DATABASE_URL` (default to SQLite path).
- Keep: `OPENAI_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `JWT_SECRET_KEY`, `GRANTS_GOV_API_KEY`.

## 8. Error handling and observability

- **Fetch failures**: per-source exceptions caught in `fetch_runner` (already done via `asyncio.gather(return_exceptions=True)`). Source-level failure recorded in `fetch_history`. Pipeline continues with surviving sources.
- **Summarizer failures**: already retried via `tenacity`. Fallback: store opportunity with empty `summary` and skip the row in digest until the summary arrives in a later run (no `summary_pending` column needed — empty summary is the signal).
- **Email send failures**: per-recipient try/except. One bounce doesn't fail the batch. `UserEmailHistory` row records `success=false` with `error_msg`.
- **CLI exit codes**: 0 success, 1 partial failure, 2 fatal. launchd's `StandardErrorPath` captures stderr.
- **Failure alerting (new)**: when `web.cli fetch` exits non-zero or zero-stored-with-zero-success-sources, an alert email goes to `admin_email` (uses the same Gmail SMTP). Cheap; saves the user from "noticing on Friday morning."
- **Lock contention**: `web.cli fetch` refuses to start if `data/.fetch.lock` is held by a running process. Stale lock detection via PID check.
- **Logging**: structured logs to `outputs/logs/cli-{fetch,email}.log` plus stdout. INFO for milestones, WARNING for per-source failures, ERROR for job-level failures.
- **Backups**: SQLite backup via `sqlite3 data/platform.db ".backup data/backups/platform-YYYYMMDD.db"` from a daily launchd plist; keep last 14. Documented in README.

## 9. Testing strategy

### 9.1 Unit tests (new + ported)

- `tests/test_keyword_sync.py` — admin keyword edits propagate via `after_flush`; non-admin edits don't; rollback of parent tx rolls back the sync.
- `tests/test_opportunity_writer.py` — dedup logic (composite_id, URL, title similarity).
- `tests/test_fetch_runner.py` — mocked fetchers + filter; assert pipeline order, dedup, summarization, auto-score invocation, multi-session boundaries (no session held across LLM calls).
- `tests/test_email_dispatcher.py` — mocked SMTP; verify recipient expansion (user + broadcast list), unsubscribe token rendering, `user_email_deliveries` insertions, NOT re-sending to a user who already received an opp.
- `tests/test_email_scheduler_due_logic.py` — `day_of_week` and `time_of_day` honored.
- `tests/test_broadcast.py` — REST CRUD, recipient cap (25), unsubscribe flow.
- `tests/test_auto_scorer.py` — newly-stored opps get a `UserOpportunityScore` row per active user.
- Existing `tests/test_filter.py`, `tests/test_fetchers.py`, `tests/test_emailer.py` — should pass unchanged (they test `src/` library code).
- `tests/test_phase{1..4}.py` — review and port any state.db-specific assertions to platform.db.

### 9.2 Integration tests

- `tests/test_consolidated_pipeline.py` — end-to-end: invoke `web/cli fetch` against a SQLite fixture; assert opportunities written, scores computed, digest renderable.
- `tests/test_migration.py` — feed a fixture `state.db`, run `migrate_state_db.py` against an empty `platform.db`, assert row counts and field mappings, including `user_email_deliveries` for the admin user from the old `status='emailed'` rows.
- `tests/test_concurrent_fetch_lock.py` — second `web.cli fetch` invocation refuses while first holds the lock.

### 9.3 Manual verification

- Run `python -m web.cli fetch` against a staging copy; eyeball the digest HTML.
- Add a test broadcast recipient, send digest with `--test`, click unsubscribe, confirm row marked inactive.
- Restart FastAPI; confirm no scheduler activity (since none exists).
- Disable launchd plists and verify no scheduled fetches occur.

## 10. Migration plan

1. **Branch.** `git checkout -b consolidate-pipeline-platform`.
2. **§5.0 schema reconciliation first** (separate commit):
   1. Update `alembic.ini` to SQLite.
   2. Generate baseline Alembic revision capturing current ORM.
   3. Generate `001_baseline_reconciliation` adding columns missing in live `platform.db`.
   4. Remove `create_all()` from `web/main.py:18` lifespan.
   5. Run on a copy of `platform.db`. Verify schema. Land the commit.
3. **Code in pieces** (each its own PR or commit, testable in isolation):
   1. `keyword_sync.py` + tests.
   2. `opportunity_writer.py` + tests.
   3. `auto_scorer.py` + tests.
   4. `email_compose_adapter.py` + `HistoryDataSource` protocol.
   5. `email_scheduler.py` due-logic rewrite + tests.
   6. `fetch_runner.py` + tests.
   7. `email_dispatcher.py` + tests.
   8. `cli.py` + lock file handling + tests.
   9. `routers/broadcast.py` + tests.
4. **Migration script** (`scripts/migrate_state_db.py`) + tests against a copy of production `state.db`.
5. **Wire into `main.py`.** Drop `seed()` call. (No scheduler to wire — that's the whole point.)
6. **Cutover** (single window, ideally Friday morning so the first new-system fetch is the following Thursday):
   1. `launchctl unload` both old plists. **Verify** with `pgrep -f weekly_fetch` and `pgrep -f weekly_email` that no processes are running. Wait if they are.
   2. Stop FastAPI.
   3. Back up `data/` (`cp -a data data.bak.YYYYMMDD`).
   4. Run `python -m web.cli migrate-state-db`. Verify counts and assertions.
   5. Start FastAPI (no scheduler activity expected).
   6. Smoke: `python -m web.cli fetch` (manual, end-to-end). Eyeball summarized digest output. Check `user_email_deliveries` and `fetch_history` rows.
   7. Smoke: `python -m web.cli email-digest --user-email ${ADMIN_EMAIL} --test`. Eyeball the email.
   8. **Only after smokes pass**: `mv data/state.db data/state.db.legacy`.
   9. Install new launchd plists. `launchctl load` them. Confirm next-trigger times via `launchctl print`.
7. **Watch first scheduled fetch** (Thursday noon MT). Verify digest (Thursday 8 PM MT).
8. **Delete `seed_opportunities.py`** and other obsolete code as cleanup commits.
9. **Archive** `data/state.db.legacy` after 30 days of clean operation.

## 11. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Migration loses opportunities | Low | High | Dry-run on copy; row-count assertions; keep `state.db.legacy` 30 days |
| Schema reconciliation fights Alembic autogenerate (column type mismatches) | Medium | Medium | Run autogenerate against a copy of live `platform.db`; review SQL by hand before applying |
| Two `web.cli fetch` invocations race | Low | Medium | File-lock at `data/.fetch.lock` with PID check |
| FastAPI multi-worker breaks something | Low | Low | Architecture explicitly avoids in-process scheduling; SQLite WAL allows concurrent read; documented in README |
| Per-user digest sends to wrong users | Low | High | Test coverage on recipient expansion; staging dry-run; `--test` mode skips `user_email_deliveries` writes |
| SQLite `database is locked` under fetch + heavy web read | Medium | Low | WAL mode + `PRAGMA busy_timeout=5000`; per-batch transactions in fetch_runner |
| Admin keyword edit doesn't propagate to `system_*` | Low | Medium | Idempotent re-sync at fetch start as backstop; explicit test |
| Broadcast unsubscribe link guessable | Low | Medium | UUID4 tokens; not enumerable |
| `auto_scorer` slow with many users | Medium | Low | Score in batches; only newly-stored opps; user count is small in v1 |
| Event-loop blocking from sync OpenAI calls | n/a | n/a | Architecture mitigation: CLI process per job, no event loop to block |

## 12. Open questions — resolutions

(Original v1 questions, now answered per Codex review.)

1. **APScheduler vs cron-hits-endpoint vs launchd-CLI** — **launchd → `python -m web.cli`** wins. Avoids event-loop blocking and multi-worker coordination problems that come with in-process schedulers.
2. **Broadcast list cap** — **25 active recipients per user** in v1 (current static list has 5; 25 is generous without enabling spam).
3. **Admin identification on fresh installs** — `ADMIN_EMAIL` env var resolved to `users.id` at runtime; the user's `is_admin` flag (already at `web/models/user.py:25`) is the persistent marker. No `ADMIN_USER_ID=1`.
4. **Static history regen frequency** — only after the **admin's** digest send, not per-user. Per-user freshness lives in the in-app authenticated view backed by `user_email_deliveries`.
5. **Non-admin exclusions** — stay user-local. Promoting one user's exclusions to system scope is a product bug. `web/services/scoring.py:317` already supports per-user exclusion via `UserKeyword.category='exclusion'`.

## 13. Appendix — file-level change summary

**New files**
- `web/services/fetch_runner.py`
- `web/services/email_dispatcher.py`
- `web/services/keyword_sync.py`
- `web/services/opportunity_writer.py`
- `web/services/email_compose_adapter.py`
- `web/services/auto_scorer.py`
- `web/cli.py`
- `web/routers/broadcast.py`
- `web/models/broadcast.py`
- `web/models/system_keywords.py`
- `web/models/source_bootstrap.py`
- `web/models/fetch_history.py`
- `web/models/user_email_delivery.py`
- `scripts/migrate_state_db.py`
- `alembic/versions/<ts>_baseline.py` (reconciliation)
- `alembic/versions/<ts>_consolidate_schema.py`
- `launchd/com.boyu.funding-agent.fetch.plist` (new)
- `launchd/com.boyu.funding-agent.email.plist` (new)
- `launchd/com.boyu.funding-agent.backup.plist` (new, daily DB backup)
- Tests (see §9)

**Modified**
- `alembic.ini` — SQLite URL.
- `web/main.py` — drop `seed()` call AND `create_all()` call.
- `web/config.py` — add admin/threshold settings.
- `web/services/email_scheduler.py` — rewrite due logic to honor `day_of_week`/`time_of_day`.
- `src/history_generator.py` — accept a `HistoryDataSource` protocol.
- `pyproject.toml` — add `apscheduler` no longer needed; add `click` for the CLI.
- `Dockerfile.web` — drop Postgres installs.
- `docker-compose.yml` — drop `db` service; SQLite default.
- `scripts/fetch_now.sh`, `scripts/email_now.sh` — 2-line wrappers around `web/cli.py`.
- `README.md`, `CLAUDE.md` — reflect single-system architecture.

**Deleted**
- `web/services/seed_opportunities.py`
- `launchd/com.boyu.funding-agent.weekly.plist`
- `launchd/com.boyu.funding-agent.daily.plist`

**Library, kept as-is or near-as-is**
- `src/fetcher/*`, `src/filter/*`, `src/summarizer.py`, `src/emailer.py`, `src/models.py`, `src/utils.py` — pure library code; no DB coupling.
- `src/weekly_fetch.py::main` and `src/weekly_email.py::main` — replaced with deprecation stubs; importable functions stay.
- `src/state.py` — kept for migration script's read path; deleted after legacy archive period.

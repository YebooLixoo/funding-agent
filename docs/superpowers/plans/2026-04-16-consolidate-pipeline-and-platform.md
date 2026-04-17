# Consolidate Internal Pipeline and Web Platform — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the single-user `src/` pipeline and the multi-user `web/` platform into one system: one SQLite DB, scheduled by launchd → `python -m web.cli`, admin user account drives system-wide search terms and filter, per-user broadcast lists, in-app + static history.

**Architecture:** FastAPI hosts no background work. A new `web/cli.py` (Click-based) is the entry point launchd invokes. CLI calls `web/services/{fetch_runner,email_dispatcher}` which reuse `src/` as a pure library. Per-user delivery state lives in a new `user_email_deliveries` table; system-wide search terms live in `system_search_terms(target_source)`; admin's `UserKeyword` rows auto-sync to system tables via session-level `after_flush`.

**Tech Stack:** Python 3.10+ (`uv`), FastAPI, SQLAlchemy async + Alembic, SQLite (WAL), Click for CLI, OpenAI Python SDK, Jinja2 templates, smtplib (Gmail SMTP), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-04-16-consolidate-pipeline-and-platform-design.md`

---

## File Structure

**New files:**
- `web/models/system_keywords.py` — SQLAlchemy models for `system_search_terms` + `system_filter_keywords`.
- `web/models/broadcast.py` — `BroadcastRecipient` model.
- `web/models/user_email_delivery.py` — per-user "already sent" join table.
- `web/models/source_bootstrap.py` — bootstrap state.
- `web/models/fetch_history.py` — pipeline run history.
- `web/services/keyword_sync.py` — session `after_flush` listener + idempotent re-sync helper.
- `web/services/opportunity_writer.py` — `upsert_opportunity` with composite_id + URL + title-similarity dedup.
- `web/services/auto_scorer.py` — score new opps for all active users.
- `web/services/email_compose_adapter.py` — translate `(Opportunity, UserOpportunityScore)` rows into the dict shape `Emailer.compose()` expects.
- `web/services/history_data_source.py` — `HistoryDataSource` protocol + `PlatformDBSource`.
- `web/services/fetch_runner.py` — orchestrate one fetch run.
- `web/services/email_dispatcher.py` — orchestrate one round of due-user digest sends.
- `web/cli.py` — Click CLI: `fetch`, `email-digest`, `regenerate-history`, `migrate-state-db`.
- `web/routers/broadcast.py` — REST CRUD + `/unsubscribe/{token}`.
- `web/schemas/broadcast.py` — Pydantic schemas.
- `scripts/migrate_state_db.py` — one-time `state.db` → `platform.db` import.
- `alembic/versions/<ts>_baseline.py` — Alembic baseline reflecting current ORM.
- `alembic/versions/<ts>_reconcile_drift.py` — adds columns missing in live `platform.db`.
- `alembic/versions/<ts>_consolidate_schema.py` — creates the new tables above.
- `launchd/com.boyu.funding-agent.fetch.plist` — Thursday noon `web.cli fetch`.
- `launchd/com.boyu.funding-agent.email.plist` — hourly `web.cli email-digest --due`.
- `launchd/com.boyu.funding-agent.backup.plist` — daily SQLite `.backup`.
- `tests/test_keyword_sync.py`, `test_opportunity_writer.py`, `test_auto_scorer.py`, `test_email_compose_adapter.py`, `test_email_scheduler_due_logic.py`, `test_fetch_runner.py`, `test_email_dispatcher.py`, `test_broadcast.py`, `test_cli.py`, `test_migration.py`, `test_consolidated_pipeline.py`.

**Modified files:**
- `alembic.ini` — `sqlalchemy.url` → SQLite.
- `alembic/env.py` — already imports `from web.models import *`; verify new models register.
- `web/main.py` — drop `seed_opportunities.seed()` call AND the `Base.metadata.create_all()` call from lifespan.
- `web/database.py` — enable WAL + busy_timeout PRAGMAs on connect.
- `web/config.py` — add `admin_email`, `keyword_threshold`, `llm_threshold`, `borderline_min`, `borderline_max`, `sqlite_busy_timeout_ms`, `sqlite_wal_mode`.
- `web/services/email_scheduler.py` — rewrite `get_users_due_for_email` to honor `frequency` + `day_of_week` + `time_of_day`; add `_already_delivered` filter via `user_email_deliveries`.
- `web/models/__init__.py` — export new models.
- `src/history_generator.py` — accept a `HistoryDataSource` protocol instead of `StateDB`.
- `pyproject.toml` — add `click`, `aiosqlite`, `pydantic-settings` (verify already present), `apscheduler` (NOT added — was a v1 mistake).
- `Dockerfile.web` — drop Postgres installs; switch to SQLite.
- `docker-compose.yml` — drop `db` service; mount `./data` volume; default `DATABASE_URL` to SQLite.
- `scripts/fetch_now.sh`, `scripts/email_now.sh` — 2-line wrappers around `web/cli.py`.
- `README.md`, `CLAUDE.md` — reflect single-system architecture.

**Deleted files:**
- `web/services/seed_opportunities.py`
- `launchd/com.boyu.funding-agent.weekly.plist`
- `launchd/com.boyu.funding-agent.daily.plist`

---

## Task Ordering and Dependencies

**Phase 0 — Schema reconciliation prerequisite (Task 1).** Must land first.
**Phase 1 — Models (Task 2).** Pure SQLAlchemy; no logic.
**Phase 2 — Consolidation migration (Task 3).** Alembic revision creating new tables.
**Phase 3 — Core services (Tasks 4–10).** Independent of each other; can be parallelized by subagents.
**Phase 4 — Orchestration (Tasks 11–12).** `fetch_runner` and `email_dispatcher`; depend on Phase 3.
**Phase 5 — Surface area (Tasks 13–14).** CLI and broadcast router.
**Phase 6 — Migration script (Task 15).** Reads from `state.db`, writes to `platform.db`.
**Phase 7 — Wire-up + cleanup (Task 16).** Drop seed bridge; new launchd plists; docker; docs.

---

## Task 1: Schema Reconciliation Prerequisite

**Goal:** Make Alembic the authoritative schema source, point at SQLite, and capture current ORM state in a baseline migration. Then add columns the live DB is missing.

**Files:**
- Modify: `alembic.ini`
- Modify: `web/main.py:18`
- Create: `alembic/versions/<ts>_baseline.py`
- Create: `alembic/versions/<ts>_reconcile_drift.py`
- Test: manual verification (no unit test needed — verified by `alembic upgrade head` against a copy)

- [ ] **Step 1: Back up the current `platform.db`**

```bash
cp data/platform.db data/platform.db.before-reconcile
```

- [ ] **Step 2: Update `alembic.ini` to SQLite**

Change `alembic.ini:4` from:
```
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/funding_platform
```
to:
```
sqlalchemy.url = sqlite+aiosqlite:///data/platform.db
```

- [ ] **Step 3: Drop `create_all()` and `seed()` from `web/main.py` lifespan**

Remove lines 19-27 of `web/main.py` (the `Base.metadata.create_all` block and the `seed()` block). The lifespan body should reduce to `yield; await engine.dispose()`.

- [ ] **Step 4: Generate the baseline migration**

Note: `alembic/env.py:19` reads the URL from `alembic.ini` (not from `DATABASE_URL`). Step 2 already pointed `alembic.ini` at the live `data/platform.db`. To autogenerate against the safe **copy** instead, temporarily change the URL or use `-x url=...`:

```bash
uv run alembic -x url=sqlite+aiosqlite:///data/platform.db.before-reconcile \
  revision --autogenerate -m "baseline"
```

If `alembic/env.py` doesn't yet honor `-x url=...`, add this single line near the top of `run_async_migrations` (before the engine creation):

```python
section = config.get_section(config.config_ini_section, {})
if config.cmd_opts and getattr(config.cmd_opts, "x", None):
    overrides = dict(opt.split("=", 1) for opt in config.cmd_opts.x if "=" in opt)
    if "url" in overrides:
        section["sqlalchemy.url"] = overrides["url"]
```

Inspect the generated file in `alembic/versions/`. It should reflect the *current ORM state* (all existing tables). If autogenerate produces unwanted DROP statements (because the live DB has extra columns), edit those out — keep only CREATE/ADD operations that match the ORM.

- [ ] **Step 5: Generate the drift-reconciliation migration**

Open `data/platform.db.before-reconcile` with `sqlite3` and compare each table's columns to the ORM. For every column present in the ORM but missing from the live DB, write a manual revision:

```bash
uv run alembic revision -m "reconcile drift"
```

Inside the generated file's `upgrade()`, add `op.add_column(...)` calls for any columns the live DB is missing — typically `opportunities.opportunity_status`, `opportunities.deadline_type`, the `resource_*` fields, and `user_opportunity_scores.{keyword,profile,behavior,urgency}_score`.

- [ ] **Step 6: Stamp the baseline against the live DB and apply reconciliation**

```bash
cp data/platform.db data/platform.db.bak
uv run alembic stamp <baseline_revision_id>
uv run alembic upgrade head
```

(No `DATABASE_URL=` prefix needed — `alembic.ini` was permanently changed in Step 2.) Verify: `sqlite3 data/platform.db ".schema opportunities"` shows the missing columns.

- [ ] **Step 7: Smoke-start FastAPI and confirm it boots without `create_all`**

```bash
DATABASE_URL="sqlite+aiosqlite:///data/platform.db" uv run uvicorn web.main:app --port 8000 &
curl -s http://localhost:8000/health
kill %1
```

Expected: `{"status":"ok"}` and no errors in stderr about missing tables.

- [ ] **Step 8: Commit**

```bash
git add alembic.ini alembic/versions/ web/main.py
git commit -m "chore: switch alembic to sqlite, drop create_all, reconcile drift"
```

---

## Task 2: New SQLAlchemy Models

**Goal:** Add ORM definitions for the five new tables. No business logic yet.

**Files:**
- Create: `web/models/system_keywords.py`
- Create: `web/models/broadcast.py`
- Create: `web/models/user_email_delivery.py`
- Create: `web/models/source_bootstrap.py`
- Create: `web/models/fetch_history.py`
- Modify: `web/models/__init__.py`
- Test: `tests/test_models_import.py`

- [ ] **Step 1: Write a failing import test**

```python
# tests/test_models_import.py
def test_new_models_importable():
    from web.models import (
        SystemSearchTerm, SystemFilterKeyword,
        BroadcastRecipient, UserEmailDelivery,
        SourceBootstrap, FetchHistory,
    )
    assert all([
        SystemSearchTerm, SystemFilterKeyword,
        BroadcastRecipient, UserEmailDelivery,
        SourceBootstrap, FetchHistory,
    ])
```

Run: `uv run pytest tests/test_models_import.py -v`. Expected: FAIL with `ImportError`.

- [ ] **Step 2: Create `web/models/system_keywords.py`**

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from web.database import Base


class SystemSearchTerm(Base):
    __tablename__ = "system_search_terms"
    __table_args__ = (
        UniqueConstraint("term", "target_source", "source_user_id", name="uq_sst_term_src_user"),
        Index("ix_sst_target_active", "target_source", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term: Mapped[str] = mapped_column(String(256), nullable=False)
    target_source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SystemFilterKeyword(Base):
    __tablename__ = "system_filter_keywords"
    __table_args__ = (
        UniqueConstraint("keyword", "category", "source_user_id", name="uq_sfk_kw_cat_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keyword: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    source_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 3: Create `web/models/broadcast.py`**

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from web.database import Base


class BroadcastRecipient(Base):
    __tablename__ = "broadcast_recipients"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "email", name="uq_broadcast_owner_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    unsubscribe_token: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Create `web/models/user_email_delivery.py`**

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from web.database import Base


class UserEmailDelivery(Base):
    __tablename__ = "user_email_deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_user_opp_delivery"),
        Index("ix_user_email_deliveries_user_sent", "user_id", "sent_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 5: Create `web/models/source_bootstrap.py` and `web/models/fetch_history.py`**

```python
# web/models/source_bootstrap.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from web.database import Base


class SourceBootstrap(Base):
    __tablename__ = "source_bootstrap"

    source_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    bootstrapped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# web/models/fetch_history.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from web.database import Base


class FetchHistory(Base):
    __tablename__ = "fetch_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    fetch_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetch_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 6: Update `web/models/__init__.py`**

Append:
```python
from web.models.system_keywords import SystemSearchTerm, SystemFilterKeyword
from web.models.broadcast import BroadcastRecipient
from web.models.user_email_delivery import UserEmailDelivery
from web.models.source_bootstrap import SourceBootstrap
from web.models.fetch_history import FetchHistory
```
And extend `__all__` with all six names.

- [ ] **Step 7: Run import test**

`uv run pytest tests/test_models_import.py -v` — expected PASS.

- [ ] **Step 8: Commit**

```bash
git add web/models/ tests/test_models_import.py
git commit -m "feat: add models for system keywords, broadcast, deliveries, bootstrap, fetch history"
```

---

## Task 3: Alembic Consolidation Migration

**Goal:** Generate the migration that creates the new tables.

**Files:**
- Create: `alembic/versions/<ts>_consolidate_schema.py`
- Test: manual verification via `alembic upgrade` and `downgrade`

- [ ] **Step 1: Generate the autogenerated migration**

```bash
DATABASE_URL="sqlite+aiosqlite:///data/platform.db" \
  uv run alembic revision --autogenerate -m "consolidate schema"
```

- [ ] **Step 2: Review the generated revision**

Open the new file in `alembic/versions/`. Verify:
- All five new tables are created (`system_search_terms`, `system_filter_keywords`, `broadcast_recipients`, `user_email_deliveries`, `source_bootstrap`, `fetch_history`).
- All FKs reference `users(id)` / `opportunities(id)` correctly.
- Indexes (`ix_sst_target_active`, `ix_user_email_deliveries_user_sent`) are present.
- No extraneous DROP/ALTER statements (autogenerate sometimes proposes drops if it sees drift — remove those).

- [ ] **Step 3: Apply against a copy and test downgrade**

```bash
cp data/platform.db data/platform.db.test
DATABASE_URL="sqlite+aiosqlite:///data/platform.db.test" uv run alembic upgrade head
sqlite3 data/platform.db.test ".tables" | grep -E "system_search_terms|broadcast_recipients|user_email_deliveries"
DATABASE_URL="sqlite+aiosqlite:///data/platform.db.test" uv run alembic downgrade -1
sqlite3 data/platform.db.test ".tables" | grep -c system_search_terms  # expect 0
rm data/platform.db.test
```

- [ ] **Step 4: Apply against the real DB**

```bash
cp data/platform.db data/platform.db.before-consolidate
DATABASE_URL="sqlite+aiosqlite:///data/platform.db" uv run alembic upgrade head
```

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat: alembic migration for consolidation tables"
```

---

## Task 4: Enable SQLite WAL + busy_timeout in `web/database.py`

**Goal:** SQLite must run in WAL mode for concurrent reader + writer; busy_timeout prevents transient lock errors.

**Files:**
- Modify: `web/database.py`
- Test: `tests/test_sqlite_pragmas.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_sqlite_pragmas.py
import pytest
from sqlalchemy import text
from web.database import async_session


@pytest.mark.asyncio
async def test_wal_and_busy_timeout_enabled():
    async with async_session() as s:
        mode = (await s.execute(text("PRAGMA journal_mode"))).scalar()
        timeout = (await s.execute(text("PRAGMA busy_timeout"))).scalar()
    assert mode == "wal"
    assert timeout >= 5000
```

Run: `uv run pytest tests/test_sqlite_pragmas.py -v` — expected FAIL.

- [ ] **Step 2: Add a connect-time PRAGMA listener in `web/database.py`**

After the `engine = create_async_engine(...)` line, add:

```python
from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _conn_record):
    if "sqlite" not in settings.database_url:
        return
    cur = dbapi_conn.cursor()
    if settings.sqlite_wal_mode:
        cur.execute("PRAGMA journal_mode=WAL")
    cur.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
    cur.close()
```

Add the two settings to `web/config.py`:
```python
sqlite_wal_mode: bool = True
sqlite_busy_timeout_ms: int = 5000
```

- [ ] **Step 3: Run test, verify pass; commit**

```bash
uv run pytest tests/test_sqlite_pragmas.py -v
git add web/database.py web/config.py tests/test_sqlite_pragmas.py
git commit -m "feat: enable WAL mode and busy_timeout for SQLite"
```

---

## Task 5: `opportunity_writer.py` — dedup + upsert

**Goal:** Port `StateDB.store_opportunity`'s dedup logic (composite_id + URL + title-similarity ≥0.80) to SQLAlchemy.

**Files:**
- Create: `web/services/opportunity_writer.py`
- Test: `tests/test_opportunity_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_opportunity_writer.py
import pytest
from web.services.opportunity_writer import upsert_opportunity
from src.models import Opportunity as OppDC


@pytest.mark.asyncio
async def test_inserts_new_opportunity(db_session):
    opp = OppDC(source="nsf", source_id="X1", title="T", description="d", url="https://e.com/1")
    row, was_new = await upsert_opportunity(db_session, opp)
    assert was_new is True
    assert row.composite_id == "nsf_X1"


@pytest.mark.asyncio
async def test_dedup_by_composite_id(db_session):
    opp = OppDC(source="nsf", source_id="X1", title="T", description="d", url="https://e.com/1")
    await upsert_opportunity(db_session, opp)
    _, was_new = await upsert_opportunity(db_session, opp)
    assert was_new is False


@pytest.mark.asyncio
async def test_dedup_by_url(db_session):
    a = OppDC(source="nsf", source_id="X1", title="T1", description="d", url="https://same.com")
    b = OppDC(source="nih", source_id="Y1", title="T2", description="d", url="https://same.com")
    await upsert_opportunity(db_session, a)
    _, was_new = await upsert_opportunity(db_session, b)
    assert was_new is False


@pytest.mark.asyncio
async def test_dedup_by_title_similarity(db_session):
    a = OppDC(source="nsf", source_id="X1",
              title="AI Research Initiative", description="d", url="https://a.com")
    b = OppDC(source="nih", source_id="Y1",
              title="Ai research initiative!", description="d", url="https://b.com")
    await upsert_opportunity(db_session, a)
    _, was_new = await upsert_opportunity(db_session, b)
    assert was_new is False
```

Run: FAIL with `ImportError`.

- [ ] **Step 2: Create `web/services/opportunity_writer.py`**

```python
from __future__ import annotations
import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.opportunity import Opportunity as OppRow

if TYPE_CHECKING:
    from src.models import Opportunity as OppDC


_TITLE_THRESHOLD = 0.80


def _normalize(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", title.lower().strip()))


async def upsert_opportunity(db: AsyncSession, opp: "OppDC") -> tuple[OppRow, bool]:
    composite_id = f"{opp.source}_{opp.source_id}"

    # 1. dedup by composite_id
    existing = (await db.execute(
        select(OppRow).where(OppRow.composite_id == composite_id)
    )).scalar_one_or_none()
    if existing:
        return existing, False

    # 2. dedup by URL
    if opp.url:
        existing = (await db.execute(
            select(OppRow).where(OppRow.url == opp.url)
        )).scalar_one_or_none()
        if existing:
            return existing, False

    # 3. dedup by title-similarity
    norm = _normalize(opp.title)
    candidates = (await db.execute(select(OppRow.id, OppRow.title))).all()
    for row_id, row_title in candidates:
        if SequenceMatcher(None, norm, _normalize(row_title or "")).ratio() >= _TITLE_THRESHOLD:
            existing = await db.get(OppRow, row_id)
            return existing, False

    # 4. insert
    row = OppRow(
        composite_id=composite_id,
        source=opp.source,
        source_id=opp.source_id,
        title=opp.title,
        description=opp.description,
        url=opp.url,
        source_type=opp.source_type,
        deadline=opp.deadline.isoformat() if opp.deadline else None,
        posted_date=opp.posted_date.isoformat() if opp.posted_date else None,
        funding_amount=opp.funding_amount,
        keywords=opp.keywords,
        summary=opp.summary,
        opportunity_status=opp.opportunity_status,
        deadline_type=opp.deadline_type,
        resource_type=opp.resource_type,
        resource_provider=opp.resource_provider,
        resource_scale=opp.resource_scale,
        allocation_details=opp.allocation_details,
        eligibility=opp.eligibility,
        access_url=opp.access_url,
    )
    db.add(row)
    await db.flush()
    return row, True
```

- [ ] **Step 3: Create `tests/conftest.py` with shared async fixtures**

`tests/conftest.py` does **not** exist today; each test file (e.g., `tests/test_phase1.py`) hand-rolls its own engine and session. Consolidate into a shared conftest now to avoid duplication across all the new test files this plan adds:

```python
# tests/conftest.py
from __future__ import annotations
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from web.database import Base
import web.models  # noqa: F401 — register all model tables on Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def admin_user(db_session):
    from web.models.user import User
    u = User(email="admin@test", password_hash="x", full_name="Admin", is_admin=True, is_active=True)
    db_session.add(u)
    await db_session.flush()
    return u
```

Verify by running any existing test: `uv run pytest tests/test_filter.py -v`.

- [ ] **Step 4: Run tests, verify pass, commit**

```bash
uv run pytest tests/test_opportunity_writer.py -v
git add web/services/opportunity_writer.py tests/test_opportunity_writer.py tests/conftest.py
git commit -m "feat: opportunity_writer with composite_id, URL, title-similarity dedup"
```

---

## Task 6: `keyword_sync.py` — admin keyword auto-sync

**Goal:** When admin's `UserKeyword` rows change, mirror them into `system_search_terms` and `system_filter_keywords`. Use session-level `after_flush` (NOT mapper events).

**Files:**
- Create: `web/services/keyword_sync.py`
- Test: `tests/test_keyword_sync.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_keyword_sync.py
import pytest
from sqlalchemy import select
from web.models.keyword import UserKeyword
from web.models.system_keywords import SystemSearchTerm, SystemFilterKeyword
from web.models.user import User
from web.services.keyword_sync import resync_system_tables, register_listener


@pytest.fixture
async def admin_user(db_session):
    u = User(email="admin@x", password_hash="x", full_name="A", is_admin=True)
    db_session.add(u); await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_resync_creates_system_terms(db_session, admin_user):
    db_session.add(UserKeyword(user_id=admin_user.id, keyword="machine learning", category="primary"))
    await db_session.flush()
    await resync_system_tables(db_session, admin_user.id)
    rows = (await db_session.execute(select(SystemSearchTerm))).scalars().all()
    assert len(rows) >= 1
    assert any(r.term == "machine learning" for r in rows)


@pytest.mark.asyncio
async def test_resync_creates_filter_keywords_for_all_categories(db_session, admin_user):
    for cat in ["primary", "domain", "career", "faculty", "exclusion"]:
        db_session.add(UserKeyword(user_id=admin_user.id, keyword=f"kw_{cat}", category=cat))
    await db_session.flush()
    await resync_system_tables(db_session, admin_user.id)
    rows = (await db_session.execute(select(SystemFilterKeyword))).scalars().all()
    assert {r.category for r in rows} == {"primary", "domain", "career", "faculty", "exclusion"}


@pytest.mark.asyncio
async def test_resync_removes_deleted_keywords(db_session, admin_user):
    kw = UserKeyword(user_id=admin_user.id, keyword="old", category="primary")
    db_session.add(kw); await db_session.flush()
    await resync_system_tables(db_session, admin_user.id)
    await db_session.delete(kw); await db_session.flush()
    await resync_system_tables(db_session, admin_user.id)
    remaining = (await db_session.execute(
        select(SystemSearchTerm).where(SystemSearchTerm.term == "old")
    )).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_listener_does_not_fire_for_non_admin(db_session, admin_user):
    register_listener()
    other = User(email="o@x", password_hash="x", full_name="O", is_admin=False)
    db_session.add(other); await db_session.flush()
    db_session.add(UserKeyword(user_id=other.id, keyword="ignored", category="primary"))
    await db_session.commit()
    rows = (await db_session.execute(
        select(SystemSearchTerm).where(SystemSearchTerm.term == "ignored")
    )).scalars().all()
    assert rows == []
```

Run: FAIL with ImportError.

- [ ] **Step 2: Implement `web/services/keyword_sync.py`**

```python
from __future__ import annotations
import logging
import uuid
from sqlalchemy import event, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from web.database import async_session
from web.models.keyword import UserKeyword
from web.models.system_keywords import SystemSearchTerm, SystemFilterKeyword
from web.models.user import User

logger = logging.getLogger(__name__)

_SEARCH_TERM_CATEGORIES = {"primary", "domain", "career", "faculty"}
_FILTER_KEYWORD_CATEGORIES = {"primary", "domain", "career", "faculty", "exclusion"}
# 'compute' deliberately omitted (compute opps bypass the filter; see src/weekly_fetch.py:395)
# 'custom' folded into 'primary' to match scoring.py:77 behavior

_SOURCE_TARGETS = ("nsf", "nih", "grants_gov")  # one search-term row per (term, source)


async def resync_system_tables(db: AsyncSession, admin_user_id: uuid.UUID) -> None:
    """Idempotent: rebuild system_* tables from admin's active UserKeyword rows."""
    user_keywords = (await db.execute(
        select(UserKeyword).where(
            UserKeyword.user_id == admin_user_id, UserKeyword.is_active.is_(True)
        )
    )).scalars().all()

    # 1. SystemFilterKeyword: one row per (keyword, category)
    desired_filter = {
        (kw.keyword.lower(), kw.category if kw.category != "custom" else "primary")
        for kw in user_keywords
        if (kw.category if kw.category != "custom" else "primary") in _FILTER_KEYWORD_CATEGORIES
    }
    existing_filter = (await db.execute(
        select(SystemFilterKeyword).where(SystemFilterKeyword.source_user_id == admin_user_id)
    )).scalars().all()
    existing_filter_keys = {(r.keyword, r.category) for r in existing_filter}
    to_add_filter = desired_filter - existing_filter_keys
    to_remove_filter = existing_filter_keys - desired_filter
    for keyword, category in to_add_filter:
        db.add(SystemFilterKeyword(
            keyword=keyword, category=category,
            source_user_id=admin_user_id, is_active=True,
        ))
    if to_remove_filter:
        await db.execute(
            delete(SystemFilterKeyword).where(
                SystemFilterKeyword.source_user_id == admin_user_id,
                SystemFilterKeyword.keyword.in_([k for k, _ in to_remove_filter]),
            )
        )

    # 2. SystemSearchTerm: one row per (term, target_source) — fan out across NSF/NIH/Grants.gov
    desired_terms = {
        kw.keyword.lower() for kw in user_keywords
        if (kw.category if kw.category != "custom" else "primary") in _SEARCH_TERM_CATEGORIES
    }
    desired_st = {(t, src) for t in desired_terms for src in _SOURCE_TARGETS}
    existing_st = (await db.execute(
        select(SystemSearchTerm).where(SystemSearchTerm.source_user_id == admin_user_id)
    )).scalars().all()
    existing_st_keys = {(r.term, r.target_source) for r in existing_st}
    to_add_st = desired_st - existing_st_keys
    for term, src in to_add_st:
        db.add(SystemSearchTerm(
            term=term, target_source=src,
            source_user_id=admin_user_id, is_active=True,
        ))
    to_remove_terms = {t for t, _ in (existing_st_keys - desired_st)}
    if to_remove_terms:
        await db.execute(
            delete(SystemSearchTerm).where(
                SystemSearchTerm.source_user_id == admin_user_id,
                SystemSearchTerm.term.in_(to_remove_terms),
            )
        )
    await db.flush()


_LISTENER_REGISTERED = False


def register_listener() -> None:
    """Idempotently install a session after_flush hook that resyncs admin keywords."""
    global _LISTENER_REGISTERED
    if _LISTENER_REGISTERED:
        return

    @event.listens_for(async_session.sync_session_class, "after_flush")
    def _on_flush(sync_session: Session, _flush_context):
        admin_id = _resolve_admin_id_sync(sync_session)
        if admin_id is None:
            return
        touched = [obj for obj in (sync_session.new | sync_session.dirty | sync_session.deleted)
                   if isinstance(obj, UserKeyword) and obj.user_id == admin_id]
        if not touched:
            return
        # Synchronously resync via a nested sync helper; we cannot await inside a sync listener,
        # so we use the sync-flavored ORM via the bound connection directly.
        _resync_sync(sync_session, admin_id)

    _LISTENER_REGISTERED = True


def _resolve_admin_id_sync(sync_session: Session) -> uuid.UUID | None:
    from web.config import get_settings
    email = get_settings().admin_email
    if not email:
        return None
    user = sync_session.execute(
        select(User).where(User.email == email, User.is_admin.is_(True))
    ).scalar_one_or_none()
    return user.id if user else None


def _resync_sync(sync_session: Session, admin_user_id: uuid.UUID) -> None:
    """Synchronous mirror of resync_system_tables for use inside flush listener."""
    # (Mirror the async version using sync_session.execute / sync_session.add)
    # (Implementation parallels resync_system_tables but with sync calls.)
    ...  # See full implementation in commit
```

> **Note for implementer:** the `_resync_sync` body is the synchronous mirror of `resync_system_tables`. Implementing both keeps the listener safe (sync-only inside flush) while exposing an async helper for explicit calls from `fetch_runner` and routers.

- [ ] **Step 3: Run tests, verify pass**

`uv run pytest tests/test_keyword_sync.py -v`

- [ ] **Step 4: Commit**

```bash
git add web/services/keyword_sync.py tests/test_keyword_sync.py
git commit -m "feat: keyword_sync with after_flush listener and idempotent resync"
```

---

## Task 7: `auto_scorer.py` — score new opportunities

**Goal:** After new opps are written, compute `UserOpportunityScore` for each active user using existing `web/services/scoring.py`.

**⚠️ Reality check:** `web/services/scoring.py` only exposes `score_opportunity_for_user(db, user_id, opportunity_id)` (line 308) and `score_all_opportunities_for_user(db, user_id)` (line 407). There is no bulk-by-id helper. Task 7 must add one before the auto_scorer can use it.

**Files:**
- Modify: `web/services/scoring.py` — add `score_opportunities_for_user(db, user_id, opportunity_ids)` that loops `score_opportunity_for_user`
- Create: `web/services/auto_scorer.py`
- Test: `tests/test_auto_scorer.py`

- [ ] **Step 1: Add the bulk-by-id helper to `web/services/scoring.py`**

Append to the file:

```python
async def score_opportunities_for_user(
    db: AsyncSession, user_id, opportunity_ids: list
) -> int:
    """Score a specific list of opportunities for one user. Returns count scored."""
    n = 0
    for oid in opportunity_ids:
        try:
            await score_opportunity_for_user(db, user_id, oid)
            n += 1
        except Exception:
            logger.exception(f"score_opportunities_for_user: failed user={user_id} opp={oid}")
    return n
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_auto_scorer.py
import pytest
from sqlalchemy import select
from web.models.user import User
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.services.auto_scorer import score_new_opportunities


@pytest.mark.asyncio
async def test_scores_new_opps_for_each_active_user(db_session):
    u1 = User(email="u1@x", password_hash="x", full_name="U1", is_active=True)
    u2 = User(email="u2@x", password_hash="x", full_name="U2", is_active=True)
    inactive = User(email="i@x", password_hash="x", full_name="I", is_active=False)
    opp = Opportunity(composite_id="nsf_X1", source="nsf", source_id="X1", title="t",
                      description="machine learning research")
    db_session.add_all([u1, u2, inactive, opp])
    await db_session.flush()

    await score_new_opportunities(db_session, [opp.id])

    scores = (await db_session.execute(select(UserOpportunityScore))).scalars().all()
    assert {s.user_id for s in scores} == {u1.id, u2.id}
```

Run: FAIL.

- [ ] **Step 3: Implement `web/services/auto_scorer.py`**

```python
from __future__ import annotations
import logging
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.user import User
from web.services.scoring import score_opportunities_for_user

logger = logging.getLogger(__name__)


async def score_new_opportunities(db: AsyncSession, opportunity_ids: list[uuid.UUID]) -> None:
    """Compute UserOpportunityScore for each active user × given opportunities."""
    if not opportunity_ids:
        return
    users = (await db.execute(
        select(User).where(User.is_active.is_(True))
    )).scalars().all()
    for user in users:
        try:
            await score_opportunities_for_user(db, user.id, opportunity_ids)
        except Exception:
            logger.exception(f"auto_scorer: failed for user {user.id}")
```

- [ ] **Step 4: Run test, commit**

```bash
uv run pytest tests/test_auto_scorer.py -v
git add web/services/auto_scorer.py web/services/scoring.py tests/test_auto_scorer.py
git commit -m "feat: auto_scorer + bulk-by-id helper in scoring.py"
```

---

## Task 8: `email_compose_adapter.py` — ORM rows → Emailer dict shape

**Goal:** Translate `(Opportunity, UserOpportunityScore)` tuples into the dict structure `src/emailer.py:43::compose()` expects (grouped by `source_type`).

**Files:**
- Create: `web/services/email_compose_adapter.py`
- Test: `tests/test_email_compose_adapter.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_email_compose_adapter.py
from web.services.email_compose_adapter import group_by_source_type


def test_groups_by_source_type():
    class O:
        def __init__(self, st): self.source_type = st; self.title = "t"; self.composite_id = "c"
        def __getattr__(self, k): return None
    rows = [(O("government"), None), (O("industry"), None), (O("compute"), None)]
    out = group_by_source_type(rows)
    assert set(out.keys()) >= {"government_opps", "industry_opps", "compute_opps"}
    assert len(out["government_opps"]) == 1
```

Run: FAIL.

- [ ] **Step 2: Implement adapter**

```python
# web/services/email_compose_adapter.py
from __future__ import annotations
from collections import defaultdict


def group_by_source_type(rows):
    """rows: iterable of (Opportunity ORM row, UserOpportunityScore | None)."""
    buckets = defaultdict(list)
    for opp, score in rows:
        d = {
            "composite_id": opp.composite_id,
            "title": opp.title,
            "url": opp.url,
            "deadline": opp.deadline,
            "deadline_type": getattr(opp, "deadline_type", "fixed"),
            "opportunity_status": getattr(opp, "opportunity_status", "open"),
            "summary": opp.summary,
            "funding_amount": opp.funding_amount,
            "source": opp.source,
            "source_type": opp.source_type,
            "relevance_score": (score.relevance_score if score else None),
            "resource_type": getattr(opp, "resource_type", None),
            "resource_provider": getattr(opp, "resource_provider", None),
            "resource_scale": getattr(opp, "resource_scale", None),
            "allocation_details": getattr(opp, "allocation_details", None),
            "eligibility": getattr(opp, "eligibility", None),
            "access_url": getattr(opp, "access_url", None),
        }
        key = f"{opp.source_type or 'government'}_opps"
        buckets[key].append(d)
    return dict(buckets)
```

- [ ] **Step 3: Run test, commit**

```bash
uv run pytest tests/test_email_compose_adapter.py -v
git add web/services/email_compose_adapter.py tests/test_email_compose_adapter.py
git commit -m "feat: adapter from ORM rows to Emailer.compose dict shape"
```

---

## Task 9: `HistoryDataSource` protocol + `PlatformDBSource`

**Goal:** Decouple `src/history_generator.py` from `StateDB` so the same generator works against the platform DB.

**Files:**
- Create: `web/services/history_data_source.py`
- Modify: `src/history_generator.py`
- Test: `tests/test_history_data_source.py`

- [ ] **Step 1: Read `src/history_generator.py` and identify all `StateDB` calls**

Likely just `db.get_emailed_opportunities()`. Confirm.

- [ ] **Step 2: Define a small protocol**

```python
# web/services/history_data_source.py
from __future__ import annotations
from typing import Protocol
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.opportunity import Opportunity
from web.models.user_email_delivery import UserEmailDelivery
from web.models.user import User


class HistoryDataSource(Protocol):
    def get_emailed_opportunities(self) -> list[dict]: ...


class PlatformDBSource:
    """Sync facade over async data, suitable for HistoryGenerator's sync interface.
    Build the rows ahead of time from an async caller, then pass into the generator.
    """
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def get_emailed_opportunities(self) -> list[dict]:
        return self._rows


async def fetch_admin_emailed_opportunities(db: AsyncSession, admin_email: str) -> list[dict]:
    admin = (await db.execute(
        select(User).where(User.email == admin_email, User.is_admin.is_(True))
    )).scalar_one()
    q = (
        select(Opportunity)
        .join(UserEmailDelivery, UserEmailDelivery.opportunity_id == Opportunity.id)
        .where(UserEmailDelivery.user_id == admin.id)
        .order_by(UserEmailDelivery.sent_at.desc())
    )
    opps = (await db.execute(q)).scalars().all()
    return [_to_dict(o) for o in opps]


def _to_dict(o: Opportunity) -> dict:
    return {
        "composite_id": o.composite_id,
        "title": o.title,
        "url": o.url,
        "deadline": o.deadline,
        "summary": o.summary,
        "funding_amount": o.funding_amount,
        "source": o.source,
        "source_type": o.source_type or "government",
        "deadline_type": o.deadline_type,
        "opportunity_status": o.opportunity_status,
        "resource_type": o.resource_type,
        "resource_provider": o.resource_provider,
        "resource_scale": o.resource_scale,
        "allocation_details": o.allocation_details,
        "eligibility": o.eligibility,
        "access_url": o.access_url,
    }
```

- [ ] **Step 3: Update `src/history_generator.py`**

Change the `generate(db)` signature to `generate(source)` where `source` quacks like the protocol. Replace `db.get_emailed_opportunities()` with `source.get_emailed_opportunities()`.

- [ ] **Step 4: Test**

```python
# tests/test_history_data_source.py
import pytest
from web.services.history_data_source import PlatformDBSource


def test_platformdbsource_returns_rows():
    rows = [{"composite_id": "x", "title": "T", "url": "u", "deadline": None,
             "summary": "s", "funding_amount": None, "source": "nsf",
             "source_type": "government", "deadline_type": "fixed",
             "opportunity_status": "open"}]
    s = PlatformDBSource(rows)
    assert s.get_emailed_opportunities() == rows
```

Run, commit:
```bash
uv run pytest tests/test_history_data_source.py -v
git add web/services/history_data_source.py src/history_generator.py tests/test_history_data_source.py
git commit -m "refactor: HistoryDataSource protocol decouples generator from StateDB"
```

---

## Task 10: `email_scheduler.py` due-logic rewrite

**Goal:** Honor `frequency` AND `day_of_week` AND `time_of_day` in `get_users_due_for_email`. Add helper to filter out opps already in `user_email_deliveries`.

**Files:**
- Modify: `web/services/email_scheduler.py`
- Test: `tests/test_email_scheduler_due_logic.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_email_scheduler_due_logic.py
import pytest
from datetime import datetime, timedelta, timezone
from web.models.user import User
from web.models.email_pref import UserEmailPref
from web.services.email_scheduler import get_users_due_for_email


@pytest.mark.asyncio
async def test_weekly_thursday_8pm_due_only_on_thursday_at_or_after_8pm(db_session):
    u = User(email="a@x", password_hash="x", full_name="A", is_active=True)
    db_session.add(u); await db_session.flush()
    db_session.add(UserEmailPref(user_id=u.id, is_subscribed=True, frequency="weekly",
                                  day_of_week=4, time_of_day="20:00", last_sent_at=None))
    await db_session.flush()

    thu_8pm = datetime(2026, 4, 16, 20, 0, tzinfo=timezone.utc)  # Thursday
    fri_8am = datetime(2026, 4, 17, 8, 0, tzinfo=timezone.utc)
    wed_8pm = datetime(2026, 4, 15, 20, 0, tzinfo=timezone.utc)

    assert (await get_users_due_for_email(db_session, now=wed_8pm)) == []
    assert len(await get_users_due_for_email(db_session, now=thu_8pm)) == 1
    # Friday: still considered "due this week" if not yet sent this week
    assert len(await get_users_due_for_email(db_session, now=fri_8am)) == 1


@pytest.mark.asyncio
async def test_no_double_send_within_frequency_window(db_session):
    u = User(email="b@x", password_hash="x", full_name="B", is_active=True)
    db_session.add(u); await db_session.flush()
    last_sent = datetime(2026, 4, 16, 20, 0, tzinfo=timezone.utc)
    db_session.add(UserEmailPref(user_id=u.id, is_subscribed=True, frequency="weekly",
                                  day_of_week=4, time_of_day="20:00", last_sent_at=last_sent))
    await db_session.flush()
    assert (await get_users_due_for_email(db_session, now=last_sent + timedelta(hours=1))) == []
```

Run: FAIL (current logic ignores `day_of_week`/`time_of_day`).

- [ ] **Step 2: Rewrite `get_users_due_for_email`**

In `web/services/email_scheduler.py`:

```python
from datetime import datetime, time, timedelta, timezone
# ... existing imports ...

_FREQUENCY_DAYS = {"daily": 1, "weekly": 7, "biweekly": 14}


async def get_users_due_for_email(db, *, now: datetime | None = None) -> list:
    if now is None:
        now = datetime.now(timezone.utc)
    prefs = (await db.execute(
        select(UserEmailPref).where(UserEmailPref.is_subscribed.is_(True))
    )).scalars().all()
    due_user_ids = []
    for pref in prefs:
        gap = _FREQUENCY_DAYS.get(pref.frequency, 7)
        # Schedule fires on day_of_week at time_of_day; "due" means now ≥ scheduled time
        # AND last_sent_at is None or older than (gap-1) days.
        if pref.last_sent_at is not None and (now - pref.last_sent_at).days < (gap - 1):
            continue
        if not _now_is_at_or_after_scheduled_slot(pref, now):
            continue
        due_user_ids.append(pref.user_id)
    if not due_user_ids:
        return []
    res = await db.execute(
        select(User).where(User.id.in_(due_user_ids), User.is_active.is_(True))
    )
    return list(res.scalars().all())


def _now_is_at_or_after_scheduled_slot(pref: UserEmailPref, now: datetime) -> bool:
    """True if `now` is on the configured day-of-week (or later in the same week) AND past the time-of-day."""
    h, m = (int(x) for x in pref.time_of_day.split(":"))
    scheduled_dow = pref.day_of_week  # 0=Mon..6=Sun, matching Python's weekday()
    today_dow = now.weekday()
    if today_dow < scheduled_dow:
        return False
    if today_dow == scheduled_dow:
        return (now.hour, now.minute) >= (h, m)
    return True  # later in the same week — still in "due window"
```

Add a helper for the dispatcher:

```python
async def get_undelivered_opportunity_ids(db, user_id, candidate_opportunity_ids):
    from web.models.user_email_delivery import UserEmailDelivery
    if not candidate_opportunity_ids:
        return []
    delivered = (await db.execute(
        select(UserEmailDelivery.opportunity_id).where(
            UserEmailDelivery.user_id == user_id,
            UserEmailDelivery.opportunity_id.in_(candidate_opportunity_ids),
        )
    )).scalars().all()
    delivered_set = set(delivered)
    return [oid for oid in candidate_opportunity_ids if oid not in delivered_set]
```

- [ ] **Step 3: Run tests, commit**

```bash
uv run pytest tests/test_email_scheduler_due_logic.py -v
git add web/services/email_scheduler.py tests/test_email_scheduler_due_logic.py
git commit -m "feat: due logic honors day_of_week and time_of_day; add undelivered helper"
```

---

## Task 11: `fetch_runner.py` — orchestrate one fetch run

**Goal:** Glue. Open short-lived sessions; resync admin keywords; run `src/` fetchers per-source-with-its-terms; filter; summarize; upsert; auto-score; record history; bootstrap.

**Files:**
- Create: `web/services/fetch_runner.py`
- Test: `tests/test_fetch_runner.py`

- [ ] **Step 1: Write failing tests** — assert pipeline order, multi-session boundaries, auto-score invocation, error isolation per source.

```python
# tests/test_fetch_runner.py
import pytest
from unittest.mock import AsyncMock, patch
from web.services.fetch_runner import run_fetch


@pytest.mark.asyncio
async def test_run_fetch_writes_opps_and_history(db_session_factory, admin_user):
    with patch("web.services.fetch_runner._collect_opportunities", new=AsyncMock(return_value=[
        _fake_opp("nsf", "X1"), _fake_opp("nih", "Y1"),
    ])), patch("web.services.fetch_runner._summarize", new=AsyncMock(side_effect=lambda x: x)):
        result = await run_fetch(now=_dt())
    assert result.stored_count == 2
    assert result.fetch_history_id is not None


@pytest.mark.asyncio
async def test_run_fetch_isolates_per_source_errors(db_session_factory, admin_user):
    # Mock one fetcher raising, others returning
    ...
```

(Quick fakes; full code in commit.)

- [ ] **Step 2: Implement**

```python
# web/services/fetch_runner.py
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from web.config import get_settings
from web.database import async_session
from web.models.user import User
from web.models.system_keywords import SystemSearchTerm, SystemFilterKeyword
from web.models.fetch_history import FetchHistory
from web.services.keyword_sync import resync_system_tables
from web.services.opportunity_writer import upsert_opportunity
from web.services.auto_scorer import score_new_opportunities

# src/ library imports
from src.fetcher import get_fetcher
from src.fetcher.web_scraper import WebScraperFetcher
from src.fetcher.grants_gov import GrantsGovFetcher
from src.filter.keyword_filter import FilterConfig, KeywordFilter
from src.filter.llm_filter import LLMFilter
from src.summarizer import Summarizer
from src.utils import last_thursday_noon_mt, now_mt

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    stored_count: int
    fetch_history_id: int | None
    errors: list[str]


async def run_fetch(now: datetime | None = None) -> FetchResult:
    settings = get_settings()
    now_dt = now or now_mt()

    # Phase 1 — config snapshot (short session, no remote I/O)
    async with async_session() as s:
        admin = (await s.execute(
            select(User).where(User.email == settings.admin_email, User.is_admin.is_(True))
        )).scalar_one()
        await resync_system_tables(s, admin.id)
        search_terms = (await s.execute(
            select(SystemSearchTerm.term, SystemSearchTerm.target_source).where(
                SystemSearchTerm.is_active.is_(True),
                SystemSearchTerm.source_user_id == admin.id,
            )
        )).all()
        filter_kws = (await s.execute(
            select(SystemFilterKeyword.keyword, SystemFilterKeyword.category).where(
                SystemFilterKeyword.is_active.is_(True),
                SystemFilterKeyword.source_user_id == admin.id,
            )
        )).all()
        await s.commit()

    # Phase 2 — remote fetch + LLM (NO session held)
    by_source: dict[str, list[str]] = {}
    for term, src in search_terms:
        by_source.setdefault(src, []).append(term)

    window_end = now_dt
    # Read window_start from fetch_history later if desired; for now use last_thursday_noon_mt
    window_start = last_thursday_noon_mt()

    raw_opps, errors = await _collect_opportunities(by_source, window_start, window_end)

    # Filter
    kw_filter = KeywordFilter(_to_filter_config(filter_kws, settings))
    accepted, borderline = kw_filter.filter([o for o in raw_opps if o.source_type != "compute"])
    if borderline:
        accepted += await LLMFilter(model=settings.llm_model).filter_borderline(
            borderline, threshold=settings.llm_threshold
        )
    accepted += [o for o in raw_opps if o.source_type == "compute"]

    # Summarize
    accepted = await Summarizer(model=settings.llm_model).summarize_batch(accepted)

    # Phase 3 — write in short transactions
    stored_ids = []
    async with async_session() as s:
        for opp in accepted:
            row, was_new = await upsert_opportunity(s, opp)
            if was_new:
                stored_ids.append(row.id)
        await s.commit()

    # Phase 4 — auto-score, history
    if stored_ids:
        async with async_session() as s:
            await score_new_opportunities(s, stored_ids)
            await s.commit()

    fh_id = None
    async with async_session() as s:
        fh = FetchHistory(
            source="all", fetch_window_start=window_start, fetch_window_end=window_end,
            success=True, count=len(stored_ids),
            error_msg="; ".join(errors) if errors else None,
        )
        s.add(fh); await s.flush(); fh_id = fh.id
        await s.commit()

    return FetchResult(stored_count=len(stored_ids), fetch_history_id=fh_id, errors=errors)


async def _collect_opportunities(by_source, window_start, window_end):
    """Fan out fetchers; isolate per-source errors."""
    # ...port logic from src/weekly_fetch.fetch_government / fetch_industry / fetch_university /
    # fetch_compute / fetch_approaching_deadlines, but use `by_source` instead of YAML.
    ...
```

> **Note for implementer:** the `_collect_opportunities` body is structurally the same as `src/weekly_fetch.py`'s `fetch_government` + `fetch_industry` + `fetch_university` + `fetch_compute` + `fetch_approaching_deadlines`, except it consumes `by_source` (per-source term lists from the DB) instead of `gov_cfg.nsf.search_keywords` etc. Source URL lists still come from `conf/sources/*.yaml`. **Include the approaching-deadlines pass** — it was missed in v1.

- [ ] **Step 3: Run tests, commit**

```bash
uv run pytest tests/test_fetch_runner.py -v
git add web/services/fetch_runner.py tests/test_fetch_runner.py web/config.py
git commit -m "feat: fetch_runner orchestrates DB-backed fetch with multi-session boundaries"
```

---

## Task 12: `email_dispatcher.py` — per-user digest sender

**Goal:** For each due user: build digest, expand recipients with broadcast list, send, write `user_email_deliveries` + `UserEmailHistory`. Regenerate static history if admin was processed.

**Files:**
- Create: `web/services/email_dispatcher.py`
- Test: `tests/test_email_dispatcher.py`

- [ ] **Step 1: Failing tests** — recipient expansion, no double-send, unsubscribe-token rendering, history regen iff admin.

```python
# tests/test_email_dispatcher.py
import pytest
from unittest.mock import AsyncMock, patch
from web.services.email_dispatcher import dispatch_due_users


@pytest.mark.asyncio
async def test_dispatch_sends_to_user_plus_active_broadcast_list(db_session, admin_user, ...):
    # Setup: admin due, has 2 active broadcast recipients
    # Mock Emailer.send
    # Assert send called with the right recipient list
    ...

@pytest.mark.asyncio
async def test_dispatch_writes_user_email_deliveries(...):
    ...

@pytest.mark.asyncio
async def test_dispatch_skips_already_delivered_opps(...):
    ...

@pytest.mark.asyncio
async def test_history_regen_only_for_admin_run(...):
    ...
```

- [ ] **Step 2: Implement** (skeleton — flesh out from skeleton)

```python
# web/services/email_dispatcher.py
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select

from web.database import async_session
from web.config import get_settings
from web.models.user import User
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.models.email_pref import UserEmailPref, UserEmailHistory
from web.models.user_email_delivery import UserEmailDelivery
from web.models.broadcast import BroadcastRecipient
from web.services.email_scheduler import (
    get_users_due_for_email, get_undelivered_opportunity_ids,
)
from web.services.email_compose_adapter import group_by_source_type
from web.services.history_data_source import (
    fetch_admin_emailed_opportunities, PlatformDBSource,
)
from src.emailer import Emailer
from src.history_generator import HistoryGenerator

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    user_id: object
    sent: int
    success: bool


async def dispatch_due_users(now: datetime | None = None) -> list[DispatchResult]:
    settings = get_settings()
    now_dt = now or datetime.now(timezone.utc)

    async with async_session() as s:
        users = await get_users_due_for_email(s, now=now_dt)

    results = []
    admin_processed = False
    for user in users:
        async with async_session() as s:
            res = await _dispatch_one(s, user, settings)
            results.append(res)
            if user.email == settings.admin_email:
                admin_processed = True
            await s.commit()

    if admin_processed:
        async with async_session() as s:
            rows = await fetch_admin_emailed_opportunities(s, settings.admin_email)
        HistoryGenerator(output_dir="docs").generate(PlatformDBSource(rows))

    return results


async def _dispatch_one(s, user, settings) -> DispatchResult:
    pref = (await s.execute(
        select(UserEmailPref).where(UserEmailPref.user_id == user.id)
    )).scalar_one()

    # Candidate opps: scored above min_score, not already delivered
    cand = (await s.execute(
        select(Opportunity, UserOpportunityScore).join(
            UserOpportunityScore,
            (UserOpportunityScore.opportunity_id == Opportunity.id) &
            (UserOpportunityScore.user_id == user.id) &
            (UserOpportunityScore.relevance_score >= pref.min_relevance_score) &
            (UserOpportunityScore.is_dismissed.is_(False))
        )
    )).all()
    cand_ids = [c[0].id for c in cand]
    new_ids = set(await get_undelivered_opportunity_ids(s, user.id, cand_ids))
    rows_to_send = [(opp, score) for opp, score in cand if opp.id in new_ids]
    if not rows_to_send:
        return DispatchResult(user.id, 0, True)

    grouped = group_by_source_type(rows_to_send)

    # Recipients: user + active broadcast list
    bcasts = (await s.execute(
        select(BroadcastRecipient).where(
            BroadcastRecipient.owner_user_id == user.id,
            BroadcastRecipient.is_active.is_(True),
        )
    )).scalars().all()

    emailer = Emailer(
        smtp_host="smtp.gmail.com", smtp_port=587, use_tls=True,
        archive_dir="outputs/digests",
    )
    date_str = datetime.now().strftime("%B %d, %Y")
    history_url = settings.history_url or None

    # Send to user (no unsubscribe token) and each broadcast recipient (with their token)
    success = True
    for recipient_email, token in [(user.email, None)] + [(b.email, b.unsubscribe_token) for b in bcasts]:
        html = emailer.compose(
            **{k: v for k, v in grouped.items() if k.endswith("_opps")},
            upcoming_deadlines=[],  # populate from a query if you keep that section
            date_str=date_str,
            history_url=history_url,
            unsubscribe_token=token,
        )
        ok = emailer.send(recipients=[recipient_email],
                          subject=f"Funding Digest: {date_str} ({len(rows_to_send)})",
                          html_body=html)
        success = success and ok

    # Record deliveries + history
    for opp_id in new_ids:
        s.add(UserEmailDelivery(user_id=user.id, opportunity_id=opp_id))
    s.add(UserEmailHistory(
        user_id=user.id, sent_at=datetime.now(timezone.utc),
        opportunity_count=len(new_ids), opportunity_ids=[str(i) for i in new_ids],
        success=success,
    ))
    pref.last_sent_at = datetime.now(timezone.utc)
    return DispatchResult(user.id, len(new_ids), success)


async def dispatch_one_user(user_email: str, *, test_mode: bool = False) -> list[DispatchResult]:
    """Dispatch a digest to a single user identified by email. Used by `web.cli email-digest --user-email`.

    test_mode=True skips broadcast list expansion and skips writing user_email_deliveries
    (so the same opps remain unsent for the next real run).
    """
    settings = get_settings()
    async with async_session() as s:
        user = (await s.execute(
            select(User).where(User.email == user_email, User.is_active.is_(True))
        )).scalar_one()
        # Reuse _dispatch_one but optionally short-circuit broadcast/persistence
        # by passing flags. (Implementer: add `test_mode` kwarg threading to
        # _dispatch_one so it skips bcasts and skips s.add(UserEmailDelivery(...)).)
        res = await _dispatch_one(s, user, settings, test_mode=test_mode)
        if not test_mode:
            await s.commit()
        else:
            await s.rollback()
    return [res]
```

> **Note:** `Emailer.compose()` doesn't currently accept an `unsubscribe_token` kwarg. Either (a) add it to `compose()` as a small additive change and render `{% if unsubscribe_token %}<a href="{{base}}/unsubscribe/{{token}}">unsubscribe</a>{% endif %}` in `templates/digest.html`, or (b) post-process the HTML by string substitution. Prefer (a) — the change is local and tested.

- [ ] **Step 3: Run tests, commit**

```bash
uv run pytest tests/test_email_dispatcher.py -v
git add web/services/email_dispatcher.py tests/test_email_dispatcher.py src/emailer.py templates/digest.html
git commit -m "feat: email_dispatcher with broadcast list + per-user delivery + admin-only history regen"
```

---

## Task 13: `web/cli.py` — Click CLI + advisory file lock

**Goal:** Single entry point launchd invokes. Subcommands: `fetch`, `email-digest`, `regenerate-history`, `migrate-state-db`. `fetch` acquires `data/.fetch.lock` (PID-checked).

**Files:**
- Create: `web/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add `click` to `pyproject.toml`**

In the `[project] dependencies` block:
```toml
"click>=8.1",
```
Run `uv sync`.

- [ ] **Step 2: Failing tests** — invocation surface, exit codes, lock-file behavior.

```python
# tests/test_cli.py
import os
from click.testing import CliRunner
from web.cli import cli


def test_fetch_command_exists():
    result = CliRunner().invoke(cli, ["fetch", "--help"])
    assert result.exit_code == 0


def test_fetch_lock_file_blocks_concurrent(tmp_path, monkeypatch):
    # Create a stale lock pointing at PID 1 (init, definitely alive),
    # invoke fetch, expect non-zero exit.
    ...
```

- [ ] **Step 3: Implement**

```python
# web/cli.py
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path
import click

from dotenv import load_dotenv

LOCK_PATH = Path("data/.fetch.lock")


@click.group()
def cli():
    """Funding Agent administrative CLI."""
    load_dotenv()


@cli.command()
def fetch():
    """Run a fetch pipeline run."""
    if not _acquire_lock():
        click.echo("Another fetch is already running. Exiting.", err=True)
        sys.exit(1)
    try:
        from web.services.fetch_runner import run_fetch
        result = asyncio.run(run_fetch())
        click.echo(f"stored={result.stored_count} errors={len(result.errors)}")
        sys.exit(0 if not result.errors else 1)
    finally:
        _release_lock()


@cli.command("email-digest")
@click.option("--due", "mode", flag_value="due", default=True)
@click.option("--user-email", "user_email", default=None)
@click.option("--test", is_flag=True, default=False)
def email_digest(mode, user_email, test):
    from web.services.email_dispatcher import dispatch_due_users, dispatch_one_user
    if user_email:
        results = asyncio.run(dispatch_one_user(user_email, test_mode=test))
    else:
        results = asyncio.run(dispatch_due_users())
    click.echo(f"dispatched={len(results)}")


@cli.command("regenerate-history")
def regenerate_history():
    from web.services.history_data_source import fetch_admin_emailed_opportunities, PlatformDBSource
    from src.history_generator import HistoryGenerator
    from web.database import async_session
    from web.config import get_settings

    settings = get_settings()
    async def _run():
        async with async_session() as s:
            rows = await fetch_admin_emailed_opportunities(s, settings.admin_email)
        HistoryGenerator(output_dir="docs").generate(PlatformDBSource(rows))
    asyncio.run(_run())


@cli.command("migrate-state-db")
def migrate_state_db():
    from scripts.migrate_state_db import main as run_migration
    run_migration()


def _acquire_lock() -> bool:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip())
            os.kill(pid, 0)  # signal 0 = check process exists
            return False
        except (ValueError, ProcessLookupError):
            LOCK_PATH.unlink(missing_ok=True)  # stale
    LOCK_PATH.write_text(str(os.getpid()))
    return True


def _release_lock() -> None:
    LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Run tests, manual smoke**

```bash
uv run pytest tests/test_cli.py -v
uv run python -m web.cli --help
uv run python -m web.cli fetch --help
```

- [ ] **Step 5: Commit**

```bash
git add web/cli.py tests/test_cli.py pyproject.toml uv.lock
git commit -m "feat: web/cli entry point with fetch lock and digest subcommands"
```

---

## Task 14: Broadcast model + REST router

**Goal:** REST CRUD for broadcast recipients, capped at 25 active per user, plus public `/unsubscribe/{token}`.

**Files:**
- Create: `web/schemas/broadcast.py`
- Create: `web/routers/broadcast.py`
- Modify: `web/main.py` (register router)
- Test: `tests/test_broadcast.py`

- [ ] **Step 1: Schemas**

```python
# web/schemas/broadcast.py
from pydantic import BaseModel, EmailStr


class BroadcastRecipientCreate(BaseModel):
    email: EmailStr
    name: str | None = None


class BroadcastRecipientOut(BaseModel):
    id: str
    email: EmailStr
    name: str | None
    is_active: bool

    class Config:
        from_attributes = True
```

- [ ] **Step 2: Failing tests**

```python
# tests/test_broadcast.py
import pytest
from httpx import AsyncClient
from web.main import app


@pytest.mark.asyncio
async def test_create_recipient(auth_headers):
    async with AsyncClient(app=app, base_url="http://t") as c:
        r = await c.post("/api/v1/broadcast/recipients",
                         json={"email": "x@y.com", "name": "X"}, headers=auth_headers)
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_cap_at_25_recipients(auth_headers):
    async with AsyncClient(app=app, base_url="http://t") as c:
        for i in range(25):
            await c.post("/api/v1/broadcast/recipients",
                         json={"email": f"u{i}@y"}, headers=auth_headers)
        r = await c.post("/api/v1/broadcast/recipients",
                         json={"email": "extra@y"}, headers=auth_headers)
    assert r.status_code == 400
    assert "25" in r.text or "limit" in r.text.lower()


@pytest.mark.asyncio
async def test_unsubscribe_link_marks_inactive(db_session, broadcast_recipient_factory):
    rec = await broadcast_recipient_factory()
    async with AsyncClient(app=app, base_url="http://t") as c:
        r = await c.get(f"/unsubscribe/{rec.unsubscribe_token}")
    assert r.status_code == 200
    await db_session.refresh(rec)
    assert rec.is_active is False
```

- [ ] **Step 3: Implement router**

```python
# web/routers/broadcast.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import get_db
from web.dependencies import get_current_user
from web.models.user import User
from web.models.broadcast import BroadcastRecipient
from web.schemas.broadcast import BroadcastRecipientCreate, BroadcastRecipientOut

router = APIRouter(prefix="/broadcast", tags=["broadcast"])

MAX_ACTIVE = 25


@router.get("/recipients", response_model=list[BroadcastRecipientOut])
async def list_recipients(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(BroadcastRecipient).where(BroadcastRecipient.owner_user_id == user.id)
    )).scalars().all()
    return [BroadcastRecipientOut(id=str(r.id), email=r.email, name=r.name, is_active=r.is_active)
            for r in rows]


@router.post("/recipients", response_model=BroadcastRecipientOut, status_code=201)
async def add_recipient(
    body: BroadcastRecipientCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    active_count = (await db.execute(
        select(BroadcastRecipient).where(
            BroadcastRecipient.owner_user_id == user.id,
            BroadcastRecipient.is_active.is_(True),
        )
    )).scalars().all()
    if len(active_count) >= MAX_ACTIVE:
        raise HTTPException(400, f"Recipient limit ({MAX_ACTIVE}) reached")

    row = BroadcastRecipient(
        owner_user_id=user.id, email=body.email, name=body.name,
        unsubscribe_token=str(uuid.uuid4()),
    )
    db.add(row); await db.flush()
    return BroadcastRecipientOut(id=str(row.id), email=row.email, name=row.name, is_active=True)


@router.delete("/recipients/{rid}", status_code=204)
async def remove_recipient(
    rid: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = (await db.execute(
        select(BroadcastRecipient).where(
            BroadcastRecipient.id == rid,
            BroadcastRecipient.owner_user_id == user.id,
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404)
    await db.delete(r)


# public — no auth
public_router = APIRouter(tags=["public"])


@public_router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(
        select(BroadcastRecipient).where(BroadcastRecipient.unsubscribe_token == token)
    )).scalar_one_or_none()
    if r and r.is_active:
        r.is_active = False
        r.unsubscribed_at = datetime.now(timezone.utc)
    return HTMLResponse("<h1>You have been unsubscribed.</h1>")
```

In `web/main.py`, after the existing router registrations, add:
```python
from web.routers import broadcast
app.include_router(broadcast.router, prefix=prefix)
app.include_router(broadcast.public_router)  # /unsubscribe is unauthenticated, no prefix
```

- [ ] **Step 4: Run tests, commit**

```bash
uv run pytest tests/test_broadcast.py -v
git add web/schemas/broadcast.py web/routers/broadcast.py web/main.py tests/test_broadcast.py
git commit -m "feat: broadcast recipients CRUD with 25-cap and tokenized unsubscribe"
```

---

## Task 15: Migration script `scripts/migrate_state_db.py`

**Goal:** One-time copy from `state.db` (sqlite3) into `platform.db` (SQLAlchemy ORM).

**Files:**
- Create: `scripts/migrate_state_db.py`
- Test: `tests/test_migration.py`

- [ ] **Step 1: Failing test** with a fixture mini-`state.db`.

```python
# tests/test_migration.py
import sqlite3
import pytest
from pathlib import Path
from scripts.migrate_state_db import migrate
from web.database import async_session
from web.models.opportunity import Opportunity
from web.models.user_email_delivery import UserEmailDelivery
from sqlalchemy import select


@pytest.mark.asyncio
async def test_migration_copies_opps_and_emails(tmp_path, admin_user):
    # Build a minimal state.db
    sd = tmp_path / "state.db"
    conn = sqlite3.connect(sd)
    conn.executescript(open("src/state.py").read().split('"""')[2])  # crude — or duplicate the SCHEMA
    conn.execute(
        "INSERT INTO seen_opportunities VALUES "
        "('nsf_X1','nsf','government','t','https://e.com/1','d','sum',NULL,NULL,NULL,NULL,0.5,"
        "'open','fixed',NULL,NULL,NULL,NULL,NULL,NULL,'emailed','2026-01-01T00:00:00')"
    )
    conn.commit(); conn.close()

    await migrate(state_db_path=sd, admin_email=admin_user.email)

    async with async_session() as s:
        opps = (await s.execute(select(Opportunity))).scalars().all()
        deliveries = (await s.execute(select(UserEmailDelivery))).scalars().all()
    assert len(opps) == 1
    assert len(deliveries) == 1
```

- [ ] **Step 2: Implement** (skeleton, fill in mappings)

```python
# scripts/migrate_state_db.py
from __future__ import annotations
import asyncio
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import select
from web.database import async_session
from web.config import get_settings
from web.models.user import User
from web.models.opportunity import Opportunity
from web.models.user_email_delivery import UserEmailDelivery
from web.models.fetch_history import FetchHistory
from web.models.email_pref import UserEmailHistory
from web.models.source_bootstrap import SourceBootstrap
from web.services.opportunity_writer import upsert_opportunity
from src.models import Opportunity as OppDC


async def migrate(state_db_path: Path, admin_email: str) -> dict:
    if not state_db_path.exists():
        return {"opps": 0, "deliveries": 0, "fetch_history": 0, "email_history": 0, "bootstrap": 0}

    conn = sqlite3.connect(str(state_db_path))
    conn.row_factory = sqlite3.Row

    async with async_session() as s:
        admin = (await s.execute(
            select(User).where(User.email == admin_email, User.is_admin.is_(True))
        )).scalar_one()

        opps_copied = 0
        deliveries_copied = 0
        for r in conn.execute("SELECT * FROM seen_opportunities"):
            dc = OppDC(
                source=r["source"], source_id=r["composite_id"].split("_", 1)[1],
                title=r["title"], description=r["description"] or "", url=r["url"],
                source_type=r["source_type"],
                summary=r["summary"] or "",
                relevance_score=r["relevance_score"] or 0.0,
                opportunity_status=r["opportunity_status"] or "open",
                deadline_type=r["deadline_type"] or "fixed",
                resource_type=r["resource_type"], resource_provider=r["resource_provider"],
                resource_scale=r["resource_scale"], allocation_details=r["allocation_details"],
                eligibility=r["eligibility"], access_url=r["access_url"],
            )
            row, was_new = await upsert_opportunity(s, dc)
            if was_new:
                opps_copied += 1
            if r["status"] == "emailed":
                # idempotent: skip if delivery already exists
                exists = (await s.execute(
                    select(UserEmailDelivery).where(
                        UserEmailDelivery.user_id == admin.id,
                        UserEmailDelivery.opportunity_id == row.id,
                    )
                )).scalar_one_or_none()
                if not exists:
                    s.add(UserEmailDelivery(user_id=admin.id, opportunity_id=row.id))
                    deliveries_copied += 1

        # fetch_history
        fh_copied = 0
        for r in conn.execute("SELECT * FROM fetch_history"):
            s.add(FetchHistory(
                source=r["source"],
                fetch_window_start=r["fetch_window_start"],
                fetch_window_end=r["fetch_window_end"],
                success=bool(r["success"]),
                count=r["count"],
                error_msg=r["error_msg"],
            ))
            fh_copied += 1

        # email_history → UserEmailHistory for admin
        eh_copied = 0
        for r in conn.execute("SELECT * FROM email_history"):
            s.add(UserEmailHistory(
                user_id=admin.id,
                sent_at=r["sent_at"],
                opportunity_count=r["opportunity_count"],
                success=bool(r["success"]),
                error_msg=r["error_msg"],
            ))
            eh_copied += 1

        # source_bootstrap
        sb_copied = 0
        for r in conn.execute("SELECT * FROM source_bootstrap"):
            s.add(SourceBootstrap(
                source_name=r["source_name"], source_type=r["source_type"],
                bootstrapped_at=r["bootstrapped_at"], created_at=r["created_at"],
            ))
            sb_copied += 1

        await s.commit()

    conn.close()
    return {
        "opps": opps_copied, "deliveries": deliveries_copied,
        "fetch_history": fh_copied, "email_history": eh_copied, "bootstrap": sb_copied,
    }


def main():
    settings = get_settings()
    if not settings.admin_email:
        print("ADMIN_EMAIL not set", file=sys.stderr); sys.exit(2)
    summary = asyncio.run(migrate(Path("data/state.db"), settings.admin_email))
    print("Migration complete:", summary)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run test, commit**

```bash
uv run pytest tests/test_migration.py -v
git add scripts/migrate_state_db.py tests/test_migration.py
git commit -m "feat: migrate state.db to platform.db with delivery records"
```

---

## Task 16: Wire-up + cleanup

**Goal:** Drop the bridge, install new launchd plists, update Docker, scripts, README, CLAUDE.md.

**Files:**
- Delete: `web/services/seed_opportunities.py`, `launchd/com.boyu.funding-agent.daily.plist`, `launchd/com.boyu.funding-agent.weekly.plist`
- Modify: `scripts/fetch_now.sh`, `scripts/email_now.sh`, `Dockerfile.web`, `docker-compose.yml`, `README.md`, `CLAUDE.md`
- Create: `launchd/com.boyu.funding-agent.fetch.plist`, `launchd/com.boyu.funding-agent.email.plist`, `launchd/com.boyu.funding-agent.backup.plist`
- Test: existing test suite continues to pass; smoke verify FastAPI boots without seed.

- [ ] **Step 1: Delete `web/services/seed_opportunities.py`**

```bash
git rm web/services/seed_opportunities.py
```

- [ ] **Step 2: Verify `web/main.py` no longer imports `seed_opportunities`**

Confirm Task 1 already removed the call. Smoke-start and hit `/health`.

- [ ] **Step 3: Replace `scripts/fetch_now.sh`**

```bash
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m web.cli fetch
```

- [ ] **Step 4: Replace `scripts/email_now.sh`**

```bash
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "--prod" ]; then
    uv run python -m web.cli email-digest --due
else
    uv run python -m web.cli email-digest --user-email "$ADMIN_EMAIL" --test
fi
```

- [ ] **Step 5: Create new launchd plists**

`launchd/com.boyu.funding-agent.fetch.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.boyu.funding-agent.fetch</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/boyu/.local/bin/uv</string>
        <string>run</string><string>python</string><string>-m</string><string>web.cli</string><string>fetch</string>
    </array>
    <key>WorkingDirectory</key><string>/Users/boyu/funding-agent</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key><integer>4</integer>
        <key>Hour</key><integer>12</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key><string>/Users/boyu/funding-agent/outputs/logs/cli-fetch.log</string>
    <key>StandardErrorPath</key><string>/Users/boyu/funding-agent/outputs/logs/cli-fetch.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key><string>/Users/boyu/.local/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

`launchd/com.boyu.funding-agent.email.plist` — same shape, but `StartInterval=3600` for hourly, args end with `email-digest --due`.

`launchd/com.boyu.funding-agent.backup.plist` — daily at 02:00, runs `sqlite3 data/platform.db ".backup data/backups/platform-$(date +%Y%m%d).db"` via a small shell wrapper.

- [ ] **Step 6: Update Dockerfile + docker-compose**

`Dockerfile.web`: drop any postgres-related apt installs; ensure SQLite `aiosqlite` is in the deps (already via `uv sync`).
`docker-compose.yml`: remove the `db` service block and its dependency; add `volumes: - ./data:/app/data`; default `DATABASE_URL` env var to `sqlite+aiosqlite:////app/data/platform.db`.

- [ ] **Step 7: Update `README.md` and `CLAUDE.md`**

In `README.md`, remove Postgres setup steps; replace with: "Just `uv sync` and run." Replace the "internal pipeline vs platform" architecture diagram with the new single-system one.

In `CLAUDE.md`, replace the "Two coexisting systems" preamble with the consolidated reality. Update the commands section.

- [ ] **Step 8: Full test run**

```bash
uv run pytest tests/ -v
```

All tests should pass. If anything in `tests/test_phase{1..4}.py` references `state.db` directly, port to `platform.db`.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: drop seed_opportunities bridge, install web.cli launchd plists, update docs"
```

---

## Cutover (operational, not part of code commits)

Per spec §10.6, executed manually by Boyu in a single window:

1. `launchctl unload launchd/com.boyu.funding-agent.daily.plist launchd/com.boyu.funding-agent.weekly.plist`
2. Verify no `weekly_fetch` / `weekly_email` processes alive: `pgrep -f weekly_fetch; pgrep -f weekly_email`. Wait for any to finish.
3. Stop FastAPI.
4. `cp -a data data.bak.$(date +%Y%m%d)`.
5. `ADMIN_EMAIL=bo.yu@utah.edu uv run python -m web.cli migrate-state-db`. Inspect summary.
6. Start FastAPI; `curl -s http://localhost:8000/health`.
7. `ADMIN_EMAIL=bo.yu@utah.edu uv run python -m web.cli fetch` — eyeball output.
8. `ADMIN_EMAIL=bo.yu@utah.edu uv run python -m web.cli email-digest --user-email bo.yu@utah.edu --test` — eyeball email.
9. `mv data/state.db data/state.db.legacy` only if smokes pass.
10. `launchctl load launchd/com.boyu.funding-agent.fetch.plist launchd/com.boyu.funding-agent.email.plist launchd/com.boyu.funding-agent.backup.plist`
11. Watch `outputs/logs/cli-fetch.log` after the first scheduled trigger (next Thursday 12:00 MT).

---

## Plan Review

After all tasks land, run the full suite + smoke:
```bash
uv run pytest tests/ -v
uv run python -m web.cli fetch  # against staging
uv run python -m web.cli email-digest --user-email "$ADMIN_EMAIL" --test
```

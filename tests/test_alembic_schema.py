"""``alembic upgrade head`` must create exactly the tables and columns the ORM declares.

Column names only: types and constraints are not compared.

Alembic is authoritative (nothing calls ``create_all`` at startup), but the test
suite builds its DB with ``create_all`` and the live DB predates alembic, so a
model column without a migration goes unnoticed everywhere except a fresh
install. That is how ``opportunities.agency`` shipped without one.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

import web.models  # noqa: F401 — register every table on Base.metadata
from web.database import Base

_REPO = Path(__file__).resolve().parents[1]
_PRE_AGENCY_REVISION = "52886e4f11fd"


def _alembic_config(db_path: Path) -> Config:
    cfg = Config()  # no ini file, so alembic leaves pytest's logging alone
    cfg.set_main_option("script_location", str(_REPO / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    return cfg


def _columns(db_path: Path) -> dict[str, set[str]]:
    con = sqlite3.connect(db_path)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {t: {r[1] for r in con.execute(f"PRAGMA table_info('{t}')")} for t in tables}
    finally:
        con.close()


def test_fresh_upgrade_builds_the_orm_schema(tmp_path):
    db = tmp_path / "fresh.db"
    command.upgrade(_alembic_config(db), "head")

    actual = _columns(db)
    drift = {
        table.name: sorted({c.name for c in table.columns} ^ actual.get(table.name, set()))
        for table in Base.metadata.sorted_tables
    }
    assert {name: cols for name, cols in drift.items() if cols} == {}


def test_agency_migration_tolerates_a_preexisting_column(tmp_path):
    """The live DB got ``opportunities.agency`` outside alembic (March 2026)."""
    db = tmp_path / "live_like.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, _PRE_AGENCY_REVISION)
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE opportunities ADD COLUMN agency VARCHAR(128)")
    con.commit()
    con.close()

    command.upgrade(cfg, "head")
    assert "agency" in _columns(db)["opportunities"]

    command.downgrade(cfg, _PRE_AGENCY_REVISION)
    assert "agency" not in _columns(db)["opportunities"]

from __future__ import annotations

import uuid as _uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from web.database import get_db
from web.dependencies import get_current_user
from web.models.broadcast import BroadcastRecipient
from web.models.user import User
from web.routers import broadcast as broadcast_router_mod


@pytest_asyncio.fixture
async def test_app(db_session):
    app = FastAPI()
    app.include_router(broadcast_router_mod.router, prefix="/api/v1")
    app.include_router(broadcast_router_mod.public_router)

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return app


def _set_current_user(app, user):
    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override


@pytest.mark.asyncio
async def test_create_recipient(db_session, test_app, admin_user):
    _set_current_user(test_app, admin_user)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/api/v1/broadcast/recipients",
            json={"email": "x@y.com", "name": "X"},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "x@y.com"
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_list_recipients(db_session, test_app, admin_user):
    _set_current_user(test_app, admin_user)
    db_session.add(
        BroadcastRecipient(
            owner_user_id=admin_user.id,
            email="a@b",
            name="A",
            is_active=True,
            unsubscribe_token=str(_uuid.uuid4()),
        )
    )
    await db_session.commit()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/v1/broadcast/recipients")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    assert r.json()[0]["email"] == "a@b"


@pytest.mark.asyncio
async def test_cap_at_25_active_recipients(db_session, test_app, admin_user):
    _set_current_user(test_app, admin_user)
    for i in range(25):
        db_session.add(
            BroadcastRecipient(
                owner_user_id=admin_user.id,
                email=f"u{i}@y",
                is_active=True,
                unsubscribe_token=str(_uuid.uuid4()),
            )
        )
    await db_session.commit()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/api/v1/broadcast/recipients", json={"email": "extra@y"}
        )
    assert r.status_code == 400, r.text
    assert "25" in r.text or "limit" in r.text.lower()


@pytest.mark.asyncio
async def test_delete_recipient(db_session, test_app, admin_user):
    _set_current_user(test_app, admin_user)
    rec = BroadcastRecipient(
        owner_user_id=admin_user.id,
        email="d@y",
        is_active=True,
        unsubscribe_token=str(_uuid.uuid4()),
    )
    db_session.add(rec)
    await db_session.commit()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.delete(f"/api/v1/broadcast/recipients/{rec.id}")
    assert r.status_code == 204, r.text
    remaining = (
        await db_session.execute(select(BroadcastRecipient))
    ).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_unsubscribe_link_marks_inactive(db_session, test_app, admin_user):
    rec = BroadcastRecipient(
        owner_user_id=admin_user.id,
        email="u@y",
        is_active=True,
        unsubscribe_token=str(_uuid.uuid4()),
    )
    db_session.add(rec)
    await db_session.commit()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get(f"/unsubscribe/{rec.unsubscribe_token}")
    assert r.status_code == 200, r.text
    assert "unsubscribed" in r.text.lower()
    await db_session.refresh(rec)
    assert rec.is_active is False
    assert rec.unsubscribed_at is not None


@pytest.mark.asyncio
async def test_user_cannot_delete_others_recipient(
    db_session, test_app, admin_user
):
    other = User(
        email="o@x", password_hash="x", full_name="O", is_active=True
    )
    db_session.add(other)
    await db_session.flush()
    rec = BroadcastRecipient(
        owner_user_id=other.id,
        email="d@y",
        is_active=True,
        unsubscribe_token=str(_uuid.uuid4()),
    )
    db_session.add(rec)
    await db_session.commit()
    _set_current_user(test_app, admin_user)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.delete(f"/api/v1/broadcast/recipients/{rec.id}")
    assert r.status_code == 404, r.text

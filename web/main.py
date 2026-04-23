from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.config import get_settings
from web.database import engine
from web.middleware import RateLimitMiddleware
from web.routers import auth, users, opportunities, keywords, filter_settings, scoring, documents, chat, email, fetch, broadcast

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

# Middleware (order matters: last added = first executed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

# Routers
prefix = settings.api_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(users.router, prefix=prefix)
app.include_router(opportunities.router, prefix=prefix)
app.include_router(keywords.router, prefix=prefix)
app.include_router(filter_settings.router, prefix=prefix)
app.include_router(scoring.router, prefix=prefix)
app.include_router(documents.router, prefix=prefix)
app.include_router(chat.router, prefix=prefix)
app.include_router(email.router, prefix=prefix)
app.include_router(fetch.router, prefix=prefix)
app.include_router(broadcast.router, prefix=prefix)
app.include_router(broadcast.public_router)  # /unsubscribe is unauthenticated, no prefix


@app.get("/health")
async def health():
    return {"status": "ok"}

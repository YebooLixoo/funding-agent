from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "Funding Agent Platform"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/funding_platform"

    # SQLite tuning
    sqlite_wal_mode: bool = True
    sqlite_busy_timeout_ms: int = 5000

    # JWT
    secret_key: str = "CHANGE-ME-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]

    # File uploads
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 20

    # OpenAI (reuse from .env)
    openai_api_key: str = ""

    # Email (reuse from .env)
    gmail_address: str = ""
    gmail_app_password: str = ""

    # Fetch runner / filtering (Task 11)
    admin_email: str = ""
    keyword_threshold: float = 0.3
    llm_threshold: float = 0.5
    borderline_min: float = 0.2
    borderline_max: float = 0.6
    llm_model: str = "gpt-5.2"
    history_url: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

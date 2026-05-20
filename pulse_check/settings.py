"""Environment-driven runtime configuration.

Single source of truth for env-var-backed settings. Read via `get_settings()`,
which is cached so a process-wide Settings instance is shared.

Consumed by:
- `pulse_check.storage.session` (DATABASE_URL)
- `pulse_check.tagging` (OLLAMA_HOST, OLLAMA_MODEL) — future wave
- `pulse_check.synthesis` (ANTHROPIC_API_KEY, ANTHROPIC_*_MODEL) — future wave
- alembic/env.py (DATABASE_URL)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///data/pulse_check.db", alias="DATABASE_URL")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_sonnet_model: str = Field(default="claude-sonnet-4-6", alias="ANTHROPIC_SONNET_MODEL")
    anthropic_haiku_model: str = Field(
        default="claude-haiku-4-5-20251001", alias="ANTHROPIC_HAIKU_MODEL"
    )

    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="qwen2.5:7b-q4_K_M", alias="OLLAMA_MODEL")

    scrape_cache_dir: str = Field(default="data/scrape_cache", alias="SCRAPE_CACHE_DIR")
    scheduler_db_path: str = Field(default="data/scheduler_state.db", alias="SCHEDULER_DB_PATH")
    playwright_profile_dir: str = Field(
        default="data/playwright_profiles", alias="PLAYWRIGHT_PROFILE_DIR"
    )
    refresh_state_path: str = Field(
        default="data/refresh_state.json", alias="REFRESH_STATE_PATH"
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="data/pulse_check.log", alias="LOG_FILE")

    # FastAPI server + CORS. Single port serves both API (under /api/*) and
    # the built frontend (static files at /). Override via env for alternate
    # deployment slots. CORS origins matter only for the dev workflow where
    # the Vite dev server runs separately on 5173 and calls the API
    # cross-origin; in unified prod mode the frontend is same-origin.
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8765, alias="API_PORT")
    api_allowed_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        alias="API_ALLOWED_ORIGINS",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached Settings instance."""
    return Settings()

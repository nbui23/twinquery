"""Configuration helpers for local development."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DATABASE_URL = "postgresql://twinquery:twinquery@localhost:5433/twinquery"


def _load_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    """Load simple KEY=VALUE pairs without adding a dependency."""
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _setting(name: str, default: str) -> str:
    return os.getenv(name) or _load_dotenv().get(name, default)


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    ollama_base_url: str
    ollama_model: str
    embedding_model: str
    sql_row_limit: int
    log_level: str


def get_settings() -> Settings:
    return Settings(
        app_env=_setting("APP_ENV", "local"),
        database_url=_setting("DATABASE_URL", DEFAULT_DATABASE_URL),
        ollama_base_url=_setting("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=_setting("OLLAMA_MODEL", "qwen2.5:7b"),
        embedding_model=_setting("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        sql_row_limit=int(_setting("SQL_ROW_LIMIT", "100")),
        log_level=_setting("LOG_LEVEL", "INFO"),
    )


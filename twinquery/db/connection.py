"""Database connection helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from twinquery.agents.validator import validate_readonly_sql
from twinquery.config import get_settings

QueryParams = Mapping[str, Any] | Sequence[Any] | None


class DatabaseError(RuntimeError):
    """Raised when a database operation fails."""


def get_connection() -> Any:
    """Create a psycopg connection using the configured DATABASE_URL."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise DatabaseError(
            "psycopg is required for database access. Install project dependencies first."
        ) from exc

    settings = get_settings()
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row)
    except Exception as exc:
        raise DatabaseError(f"Could not connect to database: {exc}") from exc


def run_readonly_query(sql: str, params: QueryParams = None) -> list[dict[str, Any]]:
    """Run a validated read-only query and return rows as dictionaries."""
    is_valid, error = validate_readonly_sql(sql)
    if not is_valid:
        raise ValueError(error or "SQL query failed validation.")

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
    except DatabaseError:
        raise
    except Exception as exc:
        raise DatabaseError(f"Read-only query failed: {exc}") from exc

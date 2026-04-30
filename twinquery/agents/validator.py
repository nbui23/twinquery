"""Guardrails for generated SQL."""

from __future__ import annotations

import re


DESTRUCTIVE_KEYWORDS = {
    "alter",
    "analyze",
    "attach",
    "call",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "execute",
    "grant",
    "insert",
    "listen",
    "merge",
    "notify",
    "reindex",
    "refresh",
    "replace",
    "reset",
    "revoke",
    "set",
    "truncate",
    "unlisten",
    "update",
    "vacuum",
}

SYSTEM_FUNCTIONS = {
    "current_setting",
    "dblink",
    "lo_export",
    "lo_import",
    "pg_cancel_backend",
    "pg_read_file",
    "pg_reload_conf",
    "pg_sleep",
    "pg_terminate_backend",
}

ALLOWED_PREFIXES = ("select", "with")


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip()).lower()


def _tokens(sql: str) -> set[str]:
    return set(re.findall(r"[a-z_][a-z0-9_]*", sql.lower()))


def _has_limit(normalized: str) -> bool:
    return bool(re.search(r"\blimit\s+\d+\b", normalized))


def _is_aggregate_query(normalized: str) -> bool:
    aggregate_patterns = (
        r"\bcount\s*\(",
        r"\bavg\s*\(",
        r"\bsum\s*\(",
        r"\bmin\s*\(",
        r"\bmax\s*\(",
        r"\bgroup\s+by\b",
    )
    return any(re.search(pattern, normalized) for pattern in aggregate_patterns)


def _has_multiple_statements(sql: str) -> bool:
    stripped = sql.strip()
    if ";" not in stripped:
        return False
    return bool(stripped.rstrip().rstrip(";").count(";"))


def validate_readonly_sql(sql: str) -> tuple[bool, str]:
    """Validate SQL before execution."""
    if not sql or not sql.strip():
        return False, "SQL is empty."

    stripped = sql.strip()
    normalized = normalize_sql(stripped.rstrip(";"))

    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        return False, "SQL comments are not allowed."
    if _has_multiple_statements(stripped):
        return False, "Multiple SQL statements are not allowed."
    if ";" in stripped.rstrip(";"):
        return False, "Semicolon chaining is not allowed."
    if not normalized.startswith(ALLOWED_PREFIXES):
        return False, "Only SELECT or read-only WITH queries are allowed."

    tokens = _tokens(normalized)
    blocked = sorted(tokens & DESTRUCTIVE_KEYWORDS)
    if blocked:
        return False, f"Destructive or unsafe SQL keyword blocked: {blocked[0]}."

    system_functions = sorted(tokens & SYSTEM_FUNCTIONS)
    if system_functions:
        return False, f"System function blocked: {system_functions[0]}."

    if normalized.startswith("with") and not re.search(r"\)\s*select\b", normalized):
        return False, "WITH queries must end in SELECT."

    if not _has_limit(normalized) and not _is_aggregate_query(normalized):
        return False, "Non-aggregate SELECT queries must include LIMIT."

    return True, "SQL is read-only and safe to execute."


def is_read_only_select(sql: str) -> bool:
    return validate_readonly_sql(sql)[0]


def validate_sql(sql: str) -> tuple[bool, str | None]:
    valid, message = validate_readonly_sql(sql)
    return valid, None if valid else message


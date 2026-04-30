"""Deterministic SQL templates for map-safe building queries."""

from __future__ import annotations

import re


MAP_SELECT_COLUMNS = """
    id,
    name,
    building_type,
    year_built,
    floor_area_m2,
    estimated_energy_intensity_kwh_m2,
    retrofit_priority_score,
    height_m,
    data_quality_note,
    ST_AsGeoJSON(geom) AS geometry_json
"""


def safe_limit(limit: int, maximum: int = 100) -> int:
    return max(1, min(int(limit), maximum))


def build_top_energy_intensity_query(limit: int = 25) -> str:
    return f"""
    SELECT
{MAP_SELECT_COLUMNS}
    FROM buildings
    WHERE geom IS NOT NULL
    ORDER BY estimated_energy_intensity_kwh_m2 DESC NULLS LAST
    LIMIT {safe_limit(limit, 100)}
    """


def build_high_retrofit_priority_query(threshold: float = 75, limit: int = 100) -> str:
    safe_threshold = max(0.0, min(float(threshold), 100.0))
    return f"""
    SELECT
{MAP_SELECT_COLUMNS}
    FROM buildings
    WHERE geom IS NOT NULL
      AND retrofit_priority_score >= {safe_threshold:.2f}
    ORDER BY retrofit_priority_score DESC NULLS LAST
    LIMIT {safe_limit(limit, 100)}
    """


def build_older_buildings_query(year: int = 1980, limit: int = 100) -> str:
    safe_year = max(1850, min(int(year), 2030))
    return f"""
    SELECT
{MAP_SELECT_COLUMNS}
    FROM buildings
    WHERE geom IS NOT NULL
      AND year_built < {safe_year}
    ORDER BY year_built ASC NULLS LAST
    LIMIT {safe_limit(limit, 100)}
    """


def build_building_type_query(building_type: str, limit: int = 100) -> str:
    normalized = re.sub(r"[^a-z0-9_ -]", "", building_type.lower()).strip()
    if not normalized:
        normalized = "building"
    escaped = normalized.replace("'", "''")
    return f"""
    SELECT
{MAP_SELECT_COLUMNS}
    FROM buildings
    WHERE geom IS NOT NULL
      AND building_type ILIKE '%{escaped}%'
    ORDER BY retrofit_priority_score DESC NULLS LAST
    LIMIT {safe_limit(limit, 100)}
    """


def build_default_map_query(limit: int = 100) -> str:
    return f"""
    SELECT
{MAP_SELECT_COLUMNS}
    FROM buildings
    WHERE geom IS NOT NULL
    ORDER BY retrofit_priority_score DESC NULLS LAST
    LIMIT {safe_limit(limit, 100)}
    """


def choose_fallback_query(question: str) -> tuple[str, str]:
    text = question.lower()
    limit = extract_limit(text) or 100

    if "energy intensity" in text or "eui" in text or "highest energy" in text:
        return build_top_energy_intensity_query(limit=min(limit, 25)), "top_energy_intensity"
    if "retrofit" in text or "priority" in text:
        threshold = extract_threshold(text) or 75
        return build_high_retrofit_priority_query(threshold=threshold, limit=limit), "high_retrofit_priority"
    if "older" in text or "built before" in text or "before 1980" in text:
        year = extract_year(text) or 1980
        return build_older_buildings_query(year=year, limit=limit), "older_buildings"

    for building_type in ("school", "office", "retail", "warehouse", "residential", "municipal", "community"):
        if building_type in text:
            return build_building_type_query(building_type, limit=limit), f"building_type:{building_type}"

    return build_default_map_query(limit=limit), "default_map"


def extract_limit(text: str) -> int | None:
    match = re.search(r"\btop\s+(\d{1,3})\b|\blimit\s+(\d{1,3})\b", text)
    if not match:
        return None
    value = next(group for group in match.groups() if group)
    return safe_limit(int(value), 100)


def extract_year(text: str) -> int | None:
    match = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", text)
    return int(match.group(1)) if match else None


def extract_threshold(text: str) -> float | None:
    match = re.search(r"\b(?:above|over|greater than|>=)\s*(\d{1,3}(?:\.\d+)?)\b", text)
    return float(match.group(1)) if match else None

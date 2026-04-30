"""GeoJSON conversion helpers for database result rows."""

from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal
from typing import Any


GEOMETRY_KEYS = {"geometry_json", "geom", "centroid"}
FEATURE_PROPERTY_KEYS = {
    "id",
    "name",
    "building_type",
    "year_built",
    "floor_area_m2",
    "estimated_energy_intensity_kwh_m2",
    "retrofit_priority_score",
    "height_m",
    "data_quality_note",
}
NUMERIC_PROPERTY_KEYS = {
    "height_m": float,
    "estimated_energy_intensity_kwh_m2": float,
    "retrofit_priority_score": float,
    "floor_area_m2": float,
    "year_built": int,
}


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def property_safe(key: str, value: Any) -> Any:
    if value is None:
        return None
    caster = NUMERIC_PROPERTY_KEYS.get(key)
    if caster is None:
        return json_safe(value)
    try:
        return caster(value)
    except (TypeError, ValueError):
        return None


def parse_geometry_json(row: dict[str, Any]) -> dict[str, Any] | None:
    value = row.get("geometry_json")
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def row_to_feature(row: dict[str, Any]) -> dict[str, Any] | None:
    geometry = parse_geometry_json(row)
    if not geometry:
        return None
    properties = {
        key: property_safe(key, row.get(key))
        for key in FEATURE_PROPERTY_KEYS
        if key in row and key not in GEOMETRY_KEYS
    }
    return {
        "type": "Feature",
        "id": properties.get("id"),
        "properties": properties,
        "geometry": geometry,
    }


def rows_to_feature_collection(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    features = [feature for row in rows if (feature := row_to_feature(row))]
    return {"type": "FeatureCollection", "features": features}


def bbox_from_features(features: Iterable[dict[str, Any]]) -> list[float] | None:
    points = [
        point
        for feature in features
        if isinstance(feature, dict) and isinstance(feature.get("geometry"), dict)
        for point in _iter_positions(feature["geometry"])
    ]
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def feature_collection_bbox(feature_collection: dict[str, Any]) -> list[float] | None:
    return bbox_from_features(feature_collection.get("features", []))


def highlight_ids_from_rows(rows: Iterable[dict[str, Any]]) -> list[Any]:
    ids = []
    for row in rows:
        value = row.get("id") or row.get("source_id")
        if value is not None:
            ids.append(json_safe(value))
    return ids


def _iter_positions(geometry: dict[str, Any]) -> Iterable[tuple[float, float]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        yield float(coordinates[0]), float(coordinates[1])
    elif geometry_type in {"Polygon", "MultiPolygon", "MultiPoint", "LineString", "MultiLineString"}:
        yield from _walk_coordinates(coordinates)
    elif geometry_type == "GeometryCollection":
        for child in geometry.get("geometries", []):
            if isinstance(child, dict):
                yield from _iter_positions(child)


def _walk_coordinates(value: Any) -> Iterable[tuple[float, float]]:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], int | float)
        and isinstance(value[1], int | float)
    ):
        yield float(value[0]), float(value[1])
        return
    if isinstance(value, list):
        for item in value:
            yield from _walk_coordinates(item)

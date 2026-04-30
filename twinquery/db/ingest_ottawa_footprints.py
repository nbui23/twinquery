"""Ingest sampled Ottawa building footprints from GeoOttawa ArcGIS REST."""

from __future__ import annotations

import argparse
import random
from typing import Any

import requests

from twinquery.db.connection import get_connection
from twinquery.db.seed_buildings import run_schema


DEFAULT_SOURCE_URL = "https://maps.ottawa.ca/arcgis/rest/services/TopographicMapping/MapServer/3/query"
DEFAULT_NOTE = "Real Ottawa building footprint geometry with synthetic/demo retrofit attributes."
BUILDING_TYPES = ["residential", "office", "school", "retail", "warehouse", "municipal", "community"]
HEATING_FUELS = ["natural_gas", "electricity", "district_energy", "heating_oil", "propane"]


def fetch_ottawa_footprints(
    source_url: str = DEFAULT_SOURCE_URL,
    *,
    limit: int = 500,
    offset: int = 0,
    bbox: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "f": "geojson",
        "where": "1=1",
        "outFields": "*",
        "outSR": 4326,
        "returnGeometry": "true",
        "resultRecordCount": limit,
        "resultOffset": offset,
    }
    if bbox:
        params.update(
            {
                "geometry": bbox,
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
            }
        )
    response = requests.get(source_url, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"Expected GeoJSON FeatureCollection, got {data.get('type') or data.keys()}")
    return data


def normalize_geometry(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not geometry:
        return None
    geometry_type = geometry.get("type")
    if geometry_type == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [geometry.get("coordinates", [])]}
    if geometry_type == "MultiPolygon":
        return geometry
    return None


def estimate_attributes(feature: dict[str, Any], index: int, rng: random.Random) -> dict[str, Any] | None:
    geometry = normalize_geometry(feature.get("geometry"))
    if geometry is None:
        return None
    properties = feature.get("properties") or {}
    source_id = str(
        properties.get("OBJECTID")
        or properties.get("objectid")
        or properties.get("GlobalID")
        or properties.get("globalid")
        or f"ottawa-footprint-{index}"
    )
    shape_area = _positive_float(properties.get("Shape_Area") or properties.get("shape_area"), None)
    floor_area = shape_area if shape_area and shape_area > 10 else round(rng.uniform(80, 1800), 2)
    building_type = rng.choice(BUILDING_TYPES)
    year_built = rng.randint(1920, 2022)
    height_m = round(rng.uniform(4, 32), 2)
    eui = round(rng.uniform(105, 325), 2)
    retrofit_score = round(min(100, max(0, (2026 - year_built) / 1.6 + max(0, eui - 160) / 4)), 2)
    energy_use = round(floor_area * eui, 2)
    fuel = rng.choices(HEATING_FUELS, weights=[48, 26, 10, 8, 8], k=1)[0]
    ghg_factor = {
        "natural_gas": 0.182,
        "electricity": 0.030,
        "district_energy": 0.095,
        "heating_oil": 0.268,
        "propane": 0.214,
    }[fuel]

    return {
        "source_id": source_id,
        "source_dataset": "open_ottawa_building_footprints",
        "source_name": "Open Ottawa Building Footprints",
        "is_real_geometry": True,
        "name": f"Ottawa Building {source_id}",
        "building_type": building_type,
        "owner_type": "unknown",
        "year_built": year_built,
        "floor_area_m2": round(max(1, floor_area), 2),
        "energy_use_kwh_year": energy_use,
        "estimated_energy_intensity_kwh_m2": eui,
        "heating_fuel": fuel,
        "ghg_emissions_kgco2e_year": round(energy_use * ghg_factor, 2),
        "retrofit_priority_score": retrofit_score,
        "address": "",
        "city": "Ottawa",
        "province": "ON",
        "height_m": height_m,
        "data_quality_note": DEFAULT_NOTE,
        "data_quality_notes": DEFAULT_NOTE,
        "geometry": geometry,
    }


def insert_footprints(records: list[dict[str, Any]]) -> int:
    insert_sql = """
    WITH footprint AS (
        SELECT ST_SetSRID(ST_GeomFromGeoJSON(%(geometry_json)s), 4326)::geometry(MultiPolygon, 4326) AS geom
    ), located AS (
        SELECT geom, ST_PointOnSurface(geom)::geometry(Point, 4326) AS centroid
        FROM footprint
    )
    INSERT INTO buildings (
        source_id, source_dataset, source_name, is_real_geometry, name, building_type, owner_type,
        year_built, floor_area_m2, energy_use_kwh_year, estimated_energy_intensity_kwh_m2,
        heating_fuel, ghg_emissions_kgco2e_year, retrofit_priority_score, address, city, province,
        latitude, longitude, height_m, data_quality_note, data_quality_notes, geom, centroid
    )
    SELECT
        %(source_id)s, %(source_dataset)s, %(source_name)s, %(is_real_geometry)s, %(name)s,
        %(building_type)s, %(owner_type)s, %(year_built)s, %(floor_area_m2)s,
        %(energy_use_kwh_year)s, %(estimated_energy_intensity_kwh_m2)s, %(heating_fuel)s,
        %(ghg_emissions_kgco2e_year)s, %(retrofit_priority_score)s, %(address)s, %(city)s,
        %(province)s, ST_Y(centroid), ST_X(centroid), %(height_m)s, %(data_quality_note)s,
        %(data_quality_notes)s, geom, centroid
    FROM located
    """
    prepared = [{**record, "geometry_json": _json_dumps(record["geometry"])} for record in records]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(insert_sql, prepared)
        conn.commit()
    return len(records)


def ingest_ottawa_footprints(
    *,
    source_url: str = DEFAULT_SOURCE_URL,
    limit: int = 500,
    offset: int = 0,
    bbox: str | None = None,
    reset: bool = False,
    seed: int = 20260429,
) -> int:
    if reset:
        run_schema()
    data = fetch_ottawa_footprints(source_url, limit=limit, offset=offset, bbox=bbox)
    rng = random.Random(seed)
    records = [
        record
        for index, feature in enumerate(data.get("features", []), start=offset + 1)
        if (record := estimate_attributes(feature, index, rng)) is not None
    ]
    if not records:
        return 0
    return insert_footprints(records)


def _positive_float(value: Any, default: float | None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest sampled Ottawa building footprints into TwinQuery.")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL, help="ArcGIS REST query endpoint.")
    parser.add_argument("--limit", type=int, default=500, help="Maximum features to fetch. Defaults to 500.")
    parser.add_argument("--offset", type=int, default=0, help="ArcGIS result offset for pagination.")
    parser.add_argument("--bbox", help="Optional WGS84 bbox: min_lon,min_lat,max_lon,max_lat.")
    parser.add_argument("--reset", action="store_true", help="Recreate the local schema before inserting.")
    parser.add_argument("--seed", type=int, default=20260429, help="Seed for deterministic demo attributes.")
    args = parser.parse_args()

    count = ingest_ottawa_footprints(
        source_url=args.source_url,
        limit=args.limit,
        offset=args.offset,
        bbox=args.bbox,
        reset=args.reset,
        seed=args.seed,
    )
    print(f"Inserted {count} Ottawa building footprints.")


if __name__ == "__main__":
    main()

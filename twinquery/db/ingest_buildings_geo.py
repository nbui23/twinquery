"""Ingest real building polygons from GeoJSON or GeoPackage into PostGIS."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from twinquery.db.connection import get_connection
from twinquery.db.seed_buildings import run_schema


FIELD_ALIASES = {
    "source_id": ("source_id", "id", "fid", "objectid", "osm_id", "building_id", "uid"),
    "name": ("name", "building_name", "bldg_name", "address", "addr_full"),
    "building_type": ("building_type", "type", "use", "building", "occupancy", "class"),
    "owner_type": ("owner_type", "owner", "ownership"),
    "year_built": ("year_built", "built_year", "year", "yr_built", "construction_year"),
    "floor_area_m2": ("floor_area_m2", "floor_area", "area_m2", "gross_area", "gfa"),
    "energy_use_kwh_year": ("energy_use_kwh_year", "energy_kwh", "annual_energy_kwh"),
    "estimated_energy_intensity_kwh_m2": ("estimated_energy_intensity_kwh_m2", "eui", "energy_intensity", "kwh_m2"),
    "heating_fuel": ("heating_fuel", "fuel", "heat_fuel"),
    "ghg_emissions_kgco2e_year": ("ghg_emissions_kgco2e_year", "ghg_kgco2e", "emissions_kgco2e"),
    "retrofit_priority_score": ("retrofit_priority_score", "priority", "retrofit_score"),
    "address": ("address", "addr_full", "street_address"),
    "city": ("city", "municipality", "muni"),
    "province": ("province", "state", "region"),
    "height_m": ("height_m", "height", "height_metres", "height_meters"),
}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if value != value:
            return False
    except ValueError:
        return True
    try:
        return value != ""
    except ValueError:
        return True


def _clean_properties(properties: dict[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): value for key, value in properties.items() if _has_value(value)}


def _first(properties: dict[str, Any], field: str, default: Any) -> Any:
    for alias in FIELD_ALIASES[field]:
        if alias.lower() in properties:
            return properties[alias.lower()]
    return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _stable_score(seed: str, minimum: float, maximum: float) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    fraction = int(digest[:8], 16) / 0xFFFFFFFF
    return round(minimum + fraction * (maximum - minimum), 2)


def _geometry_json(geometry: dict[str, Any]) -> str | None:
    geometry_type = geometry.get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        return None
    return json.dumps(geometry)


def iter_geojson_features(path: Path) -> Iterable[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        yield from data.get("features", [])
    elif data.get("type") == "Feature":
        yield data
    elif data.get("type") in {"Polygon", "MultiPolygon"}:
        yield {"type": "Feature", "properties": {}, "geometry": data}
    else:
        raise ValueError(f"Unsupported GeoJSON object type: {data.get('type')}")


def iter_geopackage_features(path: Path) -> Iterable[dict[str, Any]]:
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError(
            "GeoPackage ingestion requires geopandas. Install project dependencies or use GeoJSON."
        ) from exc

    gdf = gpd.read_file(path)
    if gdf.crs is not None and str(gdf.crs).lower() not in {"epsg:4326", "4326"}:
        gdf = gdf.to_crs("EPSG:4326")
    for _, row in gdf.iterrows():
        geometry = row.get("geometry")
        if geometry is None:
            continue
        yield {
            "type": "Feature",
            "properties": {key: row[key] for key in gdf.columns if key != "geometry"},
            "geometry": geometry.__geo_interface__,
        }


def iter_features(path: Path) -> Iterable[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".geojson", ".json"}:
        yield from iter_geojson_features(path)
        return
    if suffix in {".gpkg", ".geopackage"}:
        yield from iter_geopackage_features(path)
        return
    raise ValueError("Input must be a .geojson, .json, or .gpkg file.")


def normalize_feature(feature: dict[str, Any], index: int, source_dataset: str) -> dict[str, Any] | None:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return None
    geometry_text = _geometry_json(geometry)
    if geometry_text is None:
        return None

    properties = _clean_properties(feature.get("properties") or {})
    source_id = str(_first(properties, "source_id", f"{source_dataset}:{index}"))
    name = str(_first(properties, "name", f"Building {source_id}"))
    building_type = str(_first(properties, "building_type", "unknown"))
    floor_area = _float(_first(properties, "floor_area_m2", 250.0), 250.0)
    eui = _float(_first(properties, "estimated_energy_intensity_kwh_m2", 180.0), 180.0)
    energy_use = _float(_first(properties, "energy_use_kwh_year", floor_area * eui), floor_area * eui)
    priority = _float(_first(properties, "retrofit_priority_score", _stable_score(source_id, 25, 85)), 50.0)
    height = _float(_first(properties, "height_m", _stable_score(source_id + ":height", 6, 35)), 12.0)

    estimated_fields = [
        field
        for field in (
            "floor_area_m2",
            "estimated_energy_intensity_kwh_m2",
            "energy_use_kwh_year",
            "retrofit_priority_score",
            "height_m",
        )
        if not any(alias.lower() in properties for alias in FIELD_ALIASES[field])
    ]

    return {
        "source_id": source_id,
        "source_dataset": source_dataset,
        "name": name,
        "building_type": building_type,
        "owner_type": str(_first(properties, "owner_type", "unknown")),
        "year_built": _int(_first(properties, "year_built", 1975), 1975),
        "floor_area_m2": max(1.0, floor_area),
        "energy_use_kwh_year": max(0.0, energy_use),
        "estimated_energy_intensity_kwh_m2": max(0.0, eui),
        "heating_fuel": str(_first(properties, "heating_fuel", "unknown")),
        "ghg_emissions_kgco2e_year": max(0.0, _float(_first(properties, "ghg_emissions_kgco2e_year", energy_use * 0.08), energy_use * 0.08)),
        "retrofit_priority_score": max(0.0, min(100.0, priority)),
        "address": str(_first(properties, "address", "")),
        "city": str(_first(properties, "city", "unknown")),
        "province": str(_first(properties, "province", "unknown")),
        "height_m": max(0.0, height),
        "data_quality_notes": (
            "Estimated placeholder fields: " + ", ".join(estimated_fields)
            if estimated_fields
            else "Source attributes loaded directly where possible."
        ),
        "geometry_json": geometry_text,
    }


def insert_records(records: list[dict[str, Any]], replace: bool = False) -> int:
    insert_sql = """
    WITH footprint AS (
        SELECT ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geometry_json)s), 4326))::geometry(MultiPolygon, 4326) AS geom
    ), located AS (
        SELECT geom, ST_PointOnSurface(geom)::geometry(Point, 4326) AS centroid
        FROM footprint
    )
    INSERT INTO buildings (
        source_id, source_dataset, name, building_type, owner_type, year_built, floor_area_m2,
        energy_use_kwh_year, estimated_energy_intensity_kwh_m2, heating_fuel, ghg_emissions_kgco2e_year,
        retrofit_priority_score, address, city, province, latitude, longitude,
        geom, centroid, height_m, data_quality_notes
    )
    SELECT
        %(source_id)s, %(source_dataset)s, %(name)s, %(building_type)s, %(owner_type)s, %(year_built)s, %(floor_area_m2)s,
        %(energy_use_kwh_year)s, %(estimated_energy_intensity_kwh_m2)s, %(heating_fuel)s, %(ghg_emissions_kgco2e_year)s,
        %(retrofit_priority_score)s, %(address)s, %(city)s, %(province)s,
        ST_Y(centroid), ST_X(centroid), geom, centroid, %(height_m)s, %(data_quality_notes)s
    FROM located
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            if replace:
                cur.execute("DELETE FROM buildings")
            cur.executemany(insert_sql, records)
        conn.commit()
    return len(records)


def ingest_buildings_geo(
    path: str | Path,
    source_dataset: str | None = None,
    *,
    reset_schema: bool = False,
    replace: bool = False,
) -> int:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if reset_schema:
        run_schema()
    dataset = source_dataset or input_path.stem
    records = [
        record
        for index, feature in enumerate(iter_features(input_path), start=1)
        if (record := normalize_feature(feature, index, dataset)) is not None
    ]
    if not records:
        return 0
    return insert_records(records, replace=replace)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest building polygons into the TwinQuery PostGIS schema.")
    parser.add_argument("path", help="Path to a local GeoJSON or GeoPackage file.")
    parser.add_argument("--source-dataset", help="Dataset label stored with each building.")
    parser.add_argument("--reset-schema", action="store_true", help="Recreate the schema before ingesting.")
    parser.add_argument("--replace", action="store_true", help="Delete existing buildings before ingesting.")
    args = parser.parse_args()

    count = ingest_buildings_geo(
        args.path,
        source_dataset=args.source_dataset,
        reset_schema=args.reset_schema,
        replace=args.replace,
    )
    print(f"Ingested {count} building polygons.")


if __name__ == "__main__":
    main()

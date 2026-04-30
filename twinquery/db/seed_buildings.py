"""Seed deterministic synthetic Ottawa/Gatineau building-stock data."""

from __future__ import annotations

import random
import json
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from twinquery.db.connection import get_connection


SEED = 20260429
BUILDING_COUNT = 100
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


@dataclass(frozen=True)
class BuildingProfile:
    building_type: str
    base_eui: int
    floor_area_range: tuple[int, int]


BUILDING_PROFILES = [
    BuildingProfile("multifamily", 255, (1800, 22000)),
    BuildingProfile("office", 230, (1200, 18000)),
    BuildingProfile("school", 210, (2500, 16000)),
    BuildingProfile("library", 200, (900, 7500)),
    BuildingProfile("community_centre", 240, (800, 9000)),
    BuildingProfile("retail", 285, (700, 12000)),
    BuildingProfile("warehouse", 145, (2500, 26000)),
    BuildingProfile("municipal_office", 225, (1000, 11000)),
]

OWNER_TYPES = ["municipal", "private", "non_profit", "provincial", "federal"]
HEATING_FUELS = ["natural_gas", "electricity", "district_energy", "heating_oil", "propane"]
MEASURE_TYPES = [
    "air_sealing",
    "roof_insulation",
    "window_upgrade",
    "heat_pump_feasibility",
    "controls_optimization",
    "led_lighting",
    "heat_recovery_ventilation",
]

CITY_CENTRES = {
    "Ottawa": {"province": "ON", "lat": 45.4215, "lon": -75.6972},
    "Gatineau": {"province": "QC", "lat": 45.4765, "lon": -75.7013},
}

GHG_FACTORS = {
    "natural_gas": Decimal("0.182"),
    "electricity": Decimal("0.030"),
    "district_energy": Decimal("0.095"),
    "heating_oil": Decimal("0.268"),
    "propane": Decimal("0.214"),
}

BENCHMARKS = [
    ("multifamily", 170, 245, "Synthetic benchmark for apartment-style buildings."),
    ("office", 165, 225, "Synthetic benchmark for administrative office buildings."),
    ("school", 150, 205, "Synthetic benchmark for schools and education facilities."),
    ("library", 145, 195, "Synthetic benchmark for public library buildings."),
    ("community_centre", 170, 235, "Synthetic benchmark for mixed-use community facilities."),
    ("retail", 190, 280, "Synthetic benchmark for retail and service buildings."),
    ("warehouse", 95, 145, "Synthetic benchmark for warehouse and storage buildings."),
    ("municipal_office", 155, 215, "Synthetic benchmark for local government offices."),
]


def run_schema() -> None:
    """Create a fresh local schema from schema.sql."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()


def energy_multiplier(year_built: int, heating_fuel: str, rng: random.Random) -> float:
    age_factor = max(0.0, (2026 - year_built) / 100)
    fuel_factor = {
        "natural_gas": 1.05,
        "electricity": 0.88,
        "district_energy": 0.96,
        "heating_oil": 1.18,
        "propane": 1.12,
    }[heating_fuel]
    return max(0.65, 0.86 + age_factor + rng.uniform(-0.18, 0.20)) * fuel_factor


def retrofit_priority(year_built: int, eui: float, median_eui: int, fuel: str) -> float:
    age_points = min(35, max(0, 2026 - year_built) / 2.5)
    energy_points = min(45, max(0, (eui / median_eui - 0.75) * 45))
    fuel_points = {"heating_oil": 14, "propane": 10, "natural_gas": 8, "district_energy": 4, "electricity": 2}[fuel]
    return round(min(100, age_points + energy_points + fuel_points), 2)


def generate_buildings(count: int = BUILDING_COUNT, seed: int = SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    buildings: list[dict[str, Any]] = []
    street_names = ["Bank", "Rideau", "Elgin", "Somerset", "Preston", "Wellington", "Laurier", "Main"]

    for idx in range(1, count + 1):
        profile = rng.choice(BUILDING_PROFILES)
        city = rng.choice(list(CITY_CENTRES.keys()))
        centre = CITY_CENTRES[city]
        year_built = rng.randint(1935, 2022)
        floor_area = round(rng.uniform(*profile.floor_area_range), 2)
        heating_fuel = rng.choices(HEATING_FUELS, weights=[48, 25, 12, 8, 7], k=1)[0]
        eui = round(profile.base_eui * energy_multiplier(year_built, heating_fuel, rng), 2)
        energy_use = round(floor_area * eui, 2)
        emissions = round(float(Decimal(str(energy_use)) * GHG_FACTORS[heating_fuel]), 2)
        priority = retrofit_priority(year_built, eui, profile.base_eui, heating_fuel)
        lat = round(centre["lat"] + rng.uniform(-0.075, 0.075), 6)
        lon = round(centre["lon"] + rng.uniform(-0.105, 0.105), 6)
        address = f"{rng.randint(10, 999)} {rng.choice(street_names)} St"

        buildings.append(
            {
                "source_id": f"synthetic-{idx:03d}",
                "source_dataset": "synthetic_seed",
                "source_name": "synthetic_seed",
                "is_real_geometry": False,
                "name": f"Synthetic {profile.building_type.replace('_', ' ').title()} {idx:03d}",
                "building_type": profile.building_type,
                "owner_type": rng.choice(OWNER_TYPES),
                "year_built": year_built,
                "floor_area_m2": floor_area,
                "energy_use_kwh_year": energy_use,
                "estimated_energy_intensity_kwh_m2": eui,
                "heating_fuel": heating_fuel,
                "ghg_emissions_kgco2e_year": emissions,
                "retrofit_priority_score": priority,
                "address": address,
                "city": city,
                "province": centre["province"],
                "latitude": lat,
                "longitude": lon,
                "height_m": round(rng.uniform(6, 45), 2),
                "data_quality_note": "Synthetic footprint and attributes for local demos.",
            }
        )

    return buildings


def footprint_geojson(longitude: float, latitude: float, floor_area_m2: float) -> str:
    """Create a small square demo footprint around a centroid as GeoJSON."""
    side_m = max(18.0, min(95.0, float(floor_area_m2) ** 0.5))
    half_lat = (side_m / 2) / 111_320
    half_lon = half_lat / max(0.2, abs(math.cos(math.radians(latitude))))
    coordinates = [
        [
            [longitude - half_lon, latitude - half_lat],
            [longitude + half_lon, latitude - half_lat],
            [longitude + half_lon, latitude + half_lat],
            [longitude - half_lon, latitude + half_lat],
            [longitude - half_lon, latitude - half_lat],
        ]
    ]
    return json.dumps({"type": "Polygon", "coordinates": coordinates})


def generate_measures(building_id: int, building: dict[str, Any], seed: int = SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed + building_id)
    measure_count = rng.randint(2, 4)
    selected = rng.sample(MEASURE_TYPES, measure_count)
    floor_area = float(building["floor_area_m2"])
    priority = float(building["retrofit_priority_score"])
    measures: list[dict[str, Any]] = []

    for measure_type in selected:
        savings = round(rng.uniform(4, 22) + priority / 18, 2)
        ghg_savings = round(savings * rng.uniform(0.75, 1.25), 2)
        cost = round(floor_area * rng.uniform(18, 95), 2)
        payback = round(max(1.5, cost / max(1, float(building["energy_use_kwh_year"]) * savings / 100 * 0.14)), 2)
        measures.append(
            {
                "building_id": building_id,
                "measure_type": measure_type,
                "estimated_cost_cad": cost,
                "estimated_energy_savings_pct": min(45, savings),
                "estimated_ghg_savings_pct": min(55, ghg_savings),
                "payback_years": payback,
                "notes": "Synthetic retrofit measure for local TwinQuery demos.",
            }
        )

    return measures


def insert_benchmarks(cur: Any) -> None:
    cur.executemany(
        """
        INSERT INTO energy_benchmarks (
            building_type, target_kwh_m2_year, median_kwh_m2_year, notes
        )
        VALUES (%s, %s, %s, %s)
        """,
        BENCHMARKS,
    )


def insert_buildings(cur: Any, buildings: list[dict[str, Any]]) -> list[int]:
    inserted_ids: list[int] = []
    insert_sql = """
    INSERT INTO buildings (
        source_id, source_dataset, source_name, is_real_geometry, name, building_type, owner_type, year_built, floor_area_m2,
        energy_use_kwh_year, estimated_energy_intensity_kwh_m2, heating_fuel, ghg_emissions_kgco2e_year,
        retrofit_priority_score, address, city, province, latitude, longitude,
        geom, centroid, height_m, data_quality_note
    )
    VALUES (
        %(source_id)s, %(source_dataset)s, %(source_name)s, %(is_real_geometry)s, %(name)s, %(building_type)s, %(owner_type)s, %(year_built)s, %(floor_area_m2)s,
        %(energy_use_kwh_year)s, %(estimated_energy_intensity_kwh_m2)s, %(heating_fuel)s, %(ghg_emissions_kgco2e_year)s,
        %(retrofit_priority_score)s, %(address)s, %(city)s, %(province)s,
        %(latitude)s, %(longitude)s,
        ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geometry_json)s), 4326))::geometry(MultiPolygon, 4326),
        ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)::geometry(Point, 4326),
        %(height_m)s, %(data_quality_note)s
    )
    RETURNING id
    """
    for building in buildings:
        record = {
            **building,
            "geometry_json": footprint_geojson(
                float(building["longitude"]),
                float(building["latitude"]),
                float(building["floor_area_m2"]),
            ),
        }
        cur.execute(insert_sql, record)
        inserted_ids.append(cur.fetchone()["id"])
    return inserted_ids


def insert_measures(cur: Any, buildings: list[dict[str, Any]], building_ids: list[int]) -> None:
    measures = [
        measure
        for building_id, building in zip(building_ids, buildings, strict=True)
        for measure in generate_measures(building_id, building)
    ]
    cur.executemany(
        """
        INSERT INTO retrofit_measures (
            building_id, measure_type, estimated_cost_cad,
            estimated_energy_savings_pct, estimated_ghg_savings_pct,
            payback_years, notes
        )
        VALUES (
            %(building_id)s, %(measure_type)s, %(estimated_cost_cad)s,
            %(estimated_energy_savings_pct)s, %(estimated_ghg_savings_pct)s,
            %(payback_years)s, %(notes)s
        )
        """,
        measures,
    )


def seed() -> None:
    """Reset schema and insert deterministic synthetic data."""
    run_schema()
    buildings = generate_buildings()
    with get_connection() as conn:
        with conn.cursor() as cur:
            insert_benchmarks(cur)
            building_ids = insert_buildings(cur, buildings)
            insert_measures(cur, buildings, building_ids)
        conn.commit()
    print(f"Seeded {len(buildings)} synthetic buildings and retrofit measures.")


if __name__ == "__main__":
    seed()

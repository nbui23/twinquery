from pathlib import Path


def test_schema_file_exists() -> None:
    schema_path = Path("twinquery/db/schema.sql")
    assert schema_path.exists()


def test_schema_defines_required_tables_and_geometry() -> None:
    schema = Path("twinquery/db/schema.sql").read_text(encoding="utf-8").lower()
    assert "create table buildings" in schema
    assert "create table retrofit_measures" in schema
    assert "create table energy_benchmarks" in schema
    assert "source_id text" in schema
    assert "source_name text" in schema
    assert "is_real_geometry boolean" in schema
    assert "data_quality_note text" in schema
    assert "estimated_energy_intensity_kwh_m2 numeric" in schema
    assert "height_m numeric" in schema
    assert "geometry(multipolygon, 4326)" in schema
    assert "centroid geometry(point, 4326)" in schema

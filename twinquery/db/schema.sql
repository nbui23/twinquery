CREATE EXTENSION IF NOT EXISTS postgis;

DROP TABLE IF EXISTS retrofit_measures;
DROP TABLE IF EXISTS energy_benchmarks;
DROP TABLE IF EXISTS buildings;

CREATE TABLE buildings (
    id SERIAL PRIMARY KEY,
    source_id TEXT,
    source_dataset TEXT,
    source_name TEXT,
    is_real_geometry BOOLEAN NOT NULL DEFAULT false,
    name TEXT NOT NULL,
    building_type TEXT NOT NULL,
    owner_type TEXT NOT NULL,
    year_built INTEGER NOT NULL CHECK (year_built BETWEEN 1850 AND 2030),
    floor_area_m2 NUMERIC(12, 2) NOT NULL CHECK (floor_area_m2 > 0),
    energy_use_kwh_year NUMERIC(14, 2) NOT NULL CHECK (energy_use_kwh_year >= 0),
    estimated_energy_intensity_kwh_m2 NUMERIC(8, 2) NOT NULL CHECK (estimated_energy_intensity_kwh_m2 >= 0),
    heating_fuel TEXT NOT NULL,
    ghg_emissions_kgco2e_year NUMERIC(14, 2) NOT NULL CHECK (ghg_emissions_kgco2e_year >= 0),
    retrofit_priority_score NUMERIC(5, 2) NOT NULL CHECK (
        retrofit_priority_score >= 0
        AND retrofit_priority_score <= 100
    ),
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    province TEXT NOT NULL,
    latitude NUMERIC(9, 6) NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL,
    height_m NUMERIC(8, 2) NOT NULL CHECK (height_m >= 0),
    data_quality_note TEXT NOT NULL DEFAULT '',
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
    centroid GEOMETRY(Point, 4326) NOT NULL
);

CREATE TABLE retrofit_measures (
    id SERIAL PRIMARY KEY,
    building_id INTEGER NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    measure_type TEXT NOT NULL,
    estimated_cost_cad NUMERIC(14, 2) NOT NULL CHECK (estimated_cost_cad >= 0),
    estimated_energy_savings_pct NUMERIC(5, 2) NOT NULL CHECK (
        estimated_energy_savings_pct >= 0
        AND estimated_energy_savings_pct <= 100
    ),
    estimated_ghg_savings_pct NUMERIC(5, 2) NOT NULL CHECK (
        estimated_ghg_savings_pct >= 0
        AND estimated_ghg_savings_pct <= 100
    ),
    payback_years NUMERIC(5, 2) CHECK (payback_years >= 0),
    notes TEXT NOT NULL
);

CREATE TABLE energy_benchmarks (
    id SERIAL PRIMARY KEY,
    building_type TEXT UNIQUE NOT NULL,
    target_kwh_m2_year NUMERIC(8, 2) NOT NULL CHECK (target_kwh_m2_year > 0),
    median_kwh_m2_year NUMERIC(8, 2) NOT NULL CHECK (median_kwh_m2_year > 0),
    notes TEXT NOT NULL
);

CREATE INDEX buildings_geom_gix ON buildings USING GIST (geom);
CREATE INDEX buildings_centroid_gix ON buildings USING GIST (centroid);
CREATE INDEX buildings_source_id_idx ON buildings (source_id);
CREATE INDEX buildings_city_idx ON buildings (city);
CREATE INDEX buildings_type_idx ON buildings (building_type);
CREATE INDEX buildings_priority_idx ON buildings (retrofit_priority_score DESC);
CREATE INDEX retrofit_measures_building_id_idx ON retrofit_measures (building_id);
CREATE INDEX retrofit_measures_payback_idx ON retrofit_measures (payback_years);

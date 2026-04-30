-- TwinQuery sample SQL queries.
-- All records are synthetic and intended for local portfolio demos.

-- Top 10 buildings by energy intensity.
SELECT
    id,
    name,
    building_type,
    city,
    estimated_energy_intensity_kwh_m2 AS kwh_m2_year
FROM buildings
ORDER BY kwh_m2_year DESC
LIMIT 10;

-- Buildings built before 1980.
SELECT
    id,
    name,
    building_type,
    year_built,
    heating_fuel,
    retrofit_priority_score
FROM buildings
WHERE year_built < 1980
ORDER BY year_built ASC;

-- Buildings within 3 km of downtown Ottawa.
SELECT
    id,
    name,
    city,
    ROUND(ST_Distance(centroid::geography, ST_SetSRID(ST_MakePoint(-75.6972, 45.4215), 4326)::geography)) AS distance_m
FROM buildings
WHERE ST_DWithin(centroid::geography, ST_SetSRID(ST_MakePoint(-75.6972, 45.4215), 4326)::geography, 3000)
ORDER BY distance_m ASC;

-- Buildings with high retrofit priority.
SELECT
    id,
    name,
    building_type,
    owner_type,
    retrofit_priority_score,
    ghg_emissions_kgco2e_year
FROM buildings
WHERE retrofit_priority_score >= 70
ORDER BY retrofit_priority_score DESC
LIMIT 20;

-- Average energy intensity by building type.
SELECT
    b.building_type,
    ROUND(AVG(b.estimated_energy_intensity_kwh_m2), 2) AS avg_kwh_m2_year,
    eb.target_kwh_m2_year,
    eb.median_kwh_m2_year,
    COUNT(*) AS building_count
FROM buildings b
LEFT JOIN energy_benchmarks eb ON eb.building_type = b.building_type
GROUP BY b.building_type, eb.target_kwh_m2_year, eb.median_kwh_m2_year
ORDER BY avg_kwh_m2_year DESC;

-- Retrofit measures with fastest payback.
SELECT
    b.name,
    b.building_type,
    rm.measure_type,
    rm.estimated_cost_cad,
    rm.estimated_energy_savings_pct,
    rm.estimated_ghg_savings_pct,
    rm.payback_years
FROM retrofit_measures rm
JOIN buildings b ON b.id = rm.building_id
ORDER BY rm.payback_years ASC
LIMIT 15;

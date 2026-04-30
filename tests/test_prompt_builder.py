from twinquery.llm.prompts import build_map_text_to_sql_prompt, build_sql_prompt, build_text_to_sql_prompt


def test_build_sql_prompt_includes_question_and_schema() -> None:
    prompt = build_sql_prompt(
        question="Show the highest EUI buildings",
        schema_summary="buildings(id, name, energy_use_kwh_year)",
    )
    assert "Show the highest EUI buildings" in prompt
    assert "buildings(id, name, energy_use_kwh_year)" in prompt
    assert "Only generate read-only SELECT" in prompt


def test_text_to_sql_prompt_includes_guardrails() -> None:
    prompt = build_text_to_sql_prompt(
        user_question="Find buildings near downtown Ottawa",
        schema_summary="buildings(id, geom geometry(MultiPolygon, 4326), centroid geometry(Point, 4326))",
    )
    assert "PostgreSQL SQL only" in prompt
    assert "PostGIS" in prompt
    assert "Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE" in prompt
    assert "Include LIMIT 25" in prompt
    assert "ST_AsGeoJSON(geom) AS geometry_json" in prompt
    assert "Do not use markdown fences" in prompt


def test_map_prompt_includes_geometry_json_guidance() -> None:
    prompt = build_map_text_to_sql_prompt(
        user_question="Show the top 20 buildings with highest energy intensity",
        schema_summary="buildings(id, geom geometry(MultiPolygon, 4326))",
    )

    assert "ST_AsGeoJSON(geom) AS geometry_json" in prompt
    assert "estimated_energy_intensity_kwh_m2" in prompt
    assert "LIMIT 100 or less" in prompt
    assert "Never return huge full-city geometry queries" in prompt

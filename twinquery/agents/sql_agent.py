"""Safe local Text-to-SQL agent."""

from __future__ import annotations

import re
from collections.abc import Callable
from collections.abc import Iterator
from typing import Any

from twinquery.agents.validator import validate_readonly_sql
from twinquery.agents.map_sql import choose_fallback_query
from twinquery.db.connection import run_readonly_query
from twinquery.db.geojson import feature_collection_bbox, highlight_ids_from_rows, rows_to_feature_collection
from twinquery.llm.ollama_client import generate
from twinquery.llm.prompts import build_map_text_to_sql_prompt, build_text_to_sql_prompt


SCHEMA_SUMMARY = """
Table buildings:
- id, source_id, source_name, is_real_geometry, name, building_type, owner_type, year_built, floor_area_m2
- energy_use_kwh_year, estimated_energy_intensity_kwh_m2, heating_fuel, ghg_emissions_kgco2e_year
- retrofit_priority_score, address, city, province, latitude, longitude, height_m, data_quality_note
- geom geometry(MultiPolygon, 4326), centroid geometry(Point, 4326)

Table retrofit_measures:
- id, building_id, measure_type, estimated_cost_cad
- estimated_energy_savings_pct, estimated_ghg_savings_pct, payback_years, notes

Table energy_benchmarks:
- id, building_type, target_kwh_m2_year, median_kwh_m2_year, notes

Useful expressions:
- energy intensity: estimated_energy_intensity_kwh_m2
- join measures: retrofit_measures.building_id = buildings.id
- map geometry: ST_AsGeoJSON(geom) AS geometry_json
- distance query: ST_DWithin(centroid::geography, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography, radius_m)
"""


def get_schema_summary() -> str:
    return SCHEMA_SUMMARY.strip()


def extract_sql(model_output: str) -> str:
    """Extract SQL from LLM output without trusting markdown wrappers."""
    text = model_output.strip()
    fence_match = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    sql_match = re.search(r"\b(with|select)\b.*", text, flags=re.IGNORECASE | re.DOTALL)
    return sql_match.group(0).strip() if sql_match else text


def draft_sql(question: str, llm_generate: Callable[[str], str] = generate) -> str:
    prompt = build_text_to_sql_prompt(question, get_schema_summary())
    return extract_sql(llm_generate(prompt))


def draft_map_sql(question: str, llm_generate: Callable[[str], str] = generate) -> str:
    prompt = build_map_text_to_sql_prompt(question, get_schema_summary())
    return extract_sql(llm_generate(prompt))


def generate_sql_for_question(
    user_question: str,
    llm_generate: Callable[[str], str] = generate,
) -> str:
    return draft_sql(user_question, llm_generate=llm_generate)


def validate_generated_sql(sql: str) -> tuple[bool, str]:
    return validate_readonly_sql(sql)


def execute_validated_sql(
    sql: str,
    query_runner: Callable[[str], list[dict[str, Any]]] = run_readonly_query,
) -> list[dict[str, Any]]:
    valid, message = validate_readonly_sql(sql)
    if not valid:
        raise ValueError(message)
    return query_runner(sql)


def answer_structured_query(
    user_question: str,
    llm_generate: Callable[[str], str] = generate,
    query_runner: Callable[[str], list[dict[str, Any]]] = run_readonly_query,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "question": user_question,
        "sql": "",
        "valid": False,
        "validation_message": "",
        "rows": [],
        "row_count": 0,
        "error": None,
    }

    try:
        sql = draft_sql(user_question, llm_generate=llm_generate)
        result["sql"] = sql
        valid, message = validate_readonly_sql(sql)
        result["valid"] = valid
        result["validation_message"] = message
        if not valid:
            result["error"] = message
            return result

        rows = query_runner(sql)
        result["rows"] = rows
        result["row_count"] = len(rows)
        return result
    except Exception as exc:
        result["error"] = str(exc)
        if not result["validation_message"]:
            result["validation_message"] = "Text-to-SQL pipeline failed before validation completed."
        return result


def answer_map_query(
    user_question: str,
    llm_generate: Callable[[str], str] = generate,
    query_runner: Callable[[str], list[dict[str, Any]]] = run_readonly_query,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "question": user_question,
        "sql": "",
        "rows": [],
        "geojson": {"type": "FeatureCollection", "features": []},
        "bbox": None,
        "highlight_ids": [],
        "fallback_used": False,
        "fallback_reason": None,
        "map_metrics_available": {
            "height_m": True,
            "estimated_energy_intensity_kwh_m2": True,
            "retrofit_priority_score": True,
        },
        "error": None,
    }

    try:
        sql = draft_map_sql(user_question, llm_generate=llm_generate)
        result["sql"] = sql
        valid, message = validate_readonly_sql(sql)
        if not valid:
            sql, template_name = choose_fallback_query(user_question)
            result["sql"] = sql
            result["fallback_used"] = True
            result["fallback_reason"] = f"Generated SQL failed validation: {message}. Used {template_name} template."
        elif "geometry_json" not in sql.lower() or "st_asgeojson" not in sql.lower():
            sql, template_name = choose_fallback_query(user_question)
            result["sql"] = sql
            result["fallback_used"] = True
            result["fallback_reason"] = f"Generated SQL did not include geometry_json. Used {template_name} template."

        try:
            rows = query_runner(sql)
        except Exception as exc:
            if "does not exist" not in str(exc).lower():
                raise
            columns = get_building_columns(query_runner)
            fallback_sql = building_map_select_sql(columns, limit=100)
            result["sql"] = fallback_sql
            result["fallback_used"] = True
            result["fallback_reason"] = f"Generated SQL referenced unavailable columns: {exc}."
            rows = query_runner(fallback_sql)
        feature_collection = rows_to_feature_collection(rows)
        result["rows"] = rows
        result["geojson"] = feature_collection
        result["bbox"] = feature_collection_bbox(feature_collection)
        result["highlight_ids"] = highlight_ids_from_rows(rows)
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result


def get_building_columns(query_runner: Callable[[str], list[dict[str, Any]]] = run_readonly_query) -> set[str]:
    return {
        row["column_name"]
        for row in query_runner(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'buildings'
            LIMIT 200
            """
        )
        if row.get("column_name")
    }


def building_map_select_sql(columns: set[str], limit: int = 1000) -> str:
    safe_limit = max(1, min(limit, 5000))
    source_id_expr = "source_id" if "source_id" in columns else "NULL::text AS source_id"
    data_quality_expr = "data_quality_note" if "data_quality_note" in columns else "''::text AS data_quality_note"
    eui_expr = (
        "estimated_energy_intensity_kwh_m2"
        if "estimated_energy_intensity_kwh_m2" in columns
        else "ROUND(energy_use_kwh_year / NULLIF(floor_area_m2, 0), 2) AS estimated_energy_intensity_kwh_m2"
    )
    height_expr = "height_m" if "height_m" in columns else "0::numeric AS height_m"
    return f"""
    SELECT
        id,
        {source_id_expr},
        name,
        building_type,
        year_built,
        floor_area_m2,
        retrofit_priority_score,
        {eui_expr},
        {height_expr},
        {data_quality_expr},
        ST_AsGeoJSON(geom::geometry) AS geometry_json
    FROM buildings
    ORDER BY retrofit_priority_score DESC NULLS LAST, id
    LIMIT {safe_limit}
    """


def get_buildings_geojson(
    limit: int = 1000,
    query_runner: Callable[[str], list[dict[str, Any]]] = run_readonly_query,
) -> dict[str, Any]:
    try:
        columns = get_building_columns(query_runner)
        rows = query_runner(building_map_select_sql(columns, limit=limit))
        feature_collection = rows_to_feature_collection(rows)
        return {
            "geojson": feature_collection,
            "bbox": feature_collection_bbox(feature_collection),
            "highlight_ids": highlight_ids_from_rows(rows),
            "rows": rows,
            "error": None,
        }
    except Exception as exc:
        return {
            "geojson": {"type": "FeatureCollection", "features": []},
            "bbox": None,
            "highlight_ids": [],
            "rows": [],
            "error": str(exc),
        }


def iter_structured_query_events(
    user_question: str,
    llm_generate: Callable[[str], str] = generate,
    query_runner: Callable[[str], list[dict[str, Any]]] = run_readonly_query,
) -> Iterator[dict[str, Any]]:
    """Yield Text-to-SQL progress events for curl-friendly streaming."""
    result: dict[str, Any] = {
        "question": user_question,
        "sql": "",
        "valid": False,
        "validation_message": "",
        "rows": [],
        "row_count": 0,
        "error": None,
    }

    yield {"event": "started", "message": "Building schema-aware Text-to-SQL prompt."}
    prompt = build_text_to_sql_prompt(user_question, get_schema_summary())

    try:
        yield {"event": "ollama", "message": "Waiting for local Ollama SQL generation."}
        result["sql"] = extract_sql(llm_generate(prompt))

        yield {
            "event": "sql_generated",
            "message": "SQL generated. Validating read-only guardrails.",
            "sql": result["sql"],
        }
        valid, message = validate_readonly_sql(str(result["sql"]))
        result["valid"] = valid
        result["validation_message"] = message

        if not valid:
            result["error"] = message
            yield {"event": "blocked", "message": message, "result": result}
            return

        yield {"event": "executing_sql", "message": "SQL passed guardrails. Running read-only query."}
        rows = query_runner(str(result["sql"]))
        result["rows"] = rows
        result["row_count"] = len(rows)

        yield {"event": "complete", "message": f"Returned {len(rows)} rows.", "result": result}
    except Exception as exc:
        result["error"] = str(exc)
        if not result["validation_message"]:
            result["validation_message"] = "Text-to-SQL pipeline failed before validation completed."
        yield {"event": "error", "message": str(exc), "result": result}

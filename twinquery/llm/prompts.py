"""Prompt builders for local LLM calls."""

from __future__ import annotations


SQL_SYSTEM_PROMPT = """You generate safe PostgreSQL/PostGIS SELECT queries only.
Use only known schema objects. Do not modify data. Return SQL only."""


def build_text_to_sql_prompt(user_question: str, schema_summary: str) -> str:
    return (
        "You are TwinQuery's local Text-to-SQL model.\n"
        "Generate PostgreSQL SQL only.\n"
        "Use PostGIS functions such as ST_DWithin, ST_MakePoint, ST_Distance, and geography casts when the user asks about location, radius, proximity, or distance.\n"
        "When the user asks for buildings, maps, highlights, locations, nearby places, within-distance filters, highest/lowest rankings, retrofit candidates, or energy intensity, prefer selecting id, name, building_type, year_built, floor_area_m2, estimated_energy_intensity_kwh_m2, retrofit_priority_score, height_m, and ST_AsGeoJSON(geom) AS geometry_json.\n"
        "Use estimated_energy_intensity_kwh_m2 where available instead of recalculating energy intensity.\n"
        "Only generate read-only SELECT queries or read-only WITH CTE queries ending in SELECT.\n"
        "Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, VACUUM, or COPY.\n"
        "Prefer explicit columns over SELECT *.\n"
        "Include LIMIT 25 unless the user explicitly asks for another limit or the query is an aggregate summary.\n"
        "Return only SQL. Do not use markdown fences. Do not explain.\n\n"
        f"Schema:\n{schema_summary.strip()}\n\n"
        f"User question:\n{user_question.strip()}\n\n"
        "SQL:"
    )


def build_map_text_to_sql_prompt(user_question: str, schema_summary: str) -> str:
    return (
        "You are TwinQuery's local Text-to-SQL model for map results.\n"
        "Generate PostgreSQL/PostGIS SQL only.\n"
        "Only generate read-only SELECT queries or read-only WITH CTE queries ending in SELECT.\n"
        "Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, VACUUM, or COPY.\n"
        "Return rows that can be highlighted on a map.\n"
        "When the query returns individual buildings, include these columns when possible: "
        "id, name, building_type, year_built, floor_area_m2, estimated_energy_intensity_kwh_m2, "
        "retrofit_priority_score, height_m, data_quality_note, and ST_AsGeoJSON(geom) AS geometry_json.\n"
        "Use estimated_energy_intensity_kwh_m2 where available.\n"
        "Use ST_DWithin and ST_Distance with centroid::geography for distance and proximity filters where appropriate.\n"
        "Prefer explicit columns over SELECT *.\n"
        "Always include LIMIT 100 or less for map queries unless the user asks for fewer results.\n"
        "Never return huge full-city geometry queries by default.\n"
        "Return only SQL. Do not use markdown fences. Do not explain.\n\n"
        f"Schema:\n{schema_summary.strip()}\n\n"
        f"User question:\n{user_question.strip()}\n\n"
        "SQL:"
    )


def build_sql_prompt(question: str, schema_summary: str) -> str:
    return build_text_to_sql_prompt(question, schema_summary)


def summarize_top_rows(rows: list[dict[str, Any]], limit: int = 5) -> str:
    """Summarize top database rows for LLM context."""
    if not rows:
        return "No matching buildings found in the database."

    summary_lines = []
    for i, row in enumerate(rows[:limit]):
        name = row.get("name") or f"Building {row.get('id')}"
        btype = row.get("building_type", "Unknown type")
        year = row.get("year_built", "Unknown year")
        eui = row.get("estimated_energy_intensity_kwh_m2")
        priority = row.get("retrofit_priority_score")
        height = row.get("height_m")
        note = row.get("data_quality_note", "")

        line = f"- {name} ({btype}): Built {year}."
        if eui is not None:
            line += f" Energy Intensity: {eui:.1f} kWh/m2."
        if priority is not None:
            line += f" Retrofit Priority: {priority:.1f}/100."
        if height is not None:
            line += f" Height: {height:.1f}m."
        if note:
            line += f" Note: {note}"
        summary_lines.append(line)

    summary = "\n".join(summary_lines)
    if len(rows) > limit:
        summary += f"\n... and {len(rows) - limit} more matching buildings."
    return summary


def build_hybrid_synthesis_prompt(
    question: str,
    rows: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]],
    sql: str,
    data_quality_note: str = "Ottawa geometries are real, but energy/retrofit attributes are synthetic demo estimates.",
) -> str:
    """Build a grounded synthesis prompt for the hybrid agent."""
    from twinquery.agents.rag_agent import format_context_for_synthesis
    from twinquery.constants import DATA_QUALITY_DISCLAIMER

    row_summary = summarize_top_rows(rows)
    rag_blocks = "\n\n".join(format_context_for_synthesis(retrieved_context))

    return (
        "You are TwinQuery's Digital Twin analyst.\n"
        "Your goal is to answer the user's question using BOTH the database results (map highlights) and the retrieved retrofit guidance.\n\n"
        "--- DATABASE FINDINGS ---\n"
        f"SQL used: {sql}\n"
        f"Results summary:\n{row_summary}\n\n"
        "--- RETRIEVED GUIDANCE ---\n"
        f"{rag_blocks or 'No specific guidance found.'}\n\n"
        "--- INSTRUCTIONS ---\n"
        "1. Synthesize a concise, stakeholder-friendly answer.\n"
        "2. Ground your answer in the provided database findings and retrieved guidance.\n"
        "3. Cite source filenames from the retrieved guidance (e.g., [retrofit_guidelines.md]).\n"
        f"4. DATA QUALITY: {data_quality_note or DATA_QUALITY_DISCLAIMER}\n"
        "5. If the database found no matches, explain why and suggest what to look for instead.\n"
        "6. If the guidance is missing, focus on the database findings but mention that specific guidance wasn't found.\n\n"
        f"User Question: {question}\n\n"
        "Answer:"
    )

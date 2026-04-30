"""Streamlit entry point for the TwinQuery demo UI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import requests
import streamlit as st

try:
    import pydeck as pdk
except ImportError:  # pragma: no cover - exercised by local app runtime
    pdk = None


from twinquery.constants import DATA_QUALITY_DISCLAIMER

API_BASE_URL = os.getenv("STREAMLIT_API_BASE_URL", "http://localhost:8000")


MODES = [
    "Hybrid Digital Twin Query",
    "Map query",
    "Document RAG",
    "Text-to-SQL only",
    "Agentic answer",
]


def get_api_health() -> dict[str, object]:
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=3)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        return {"status": "unavailable", "detail": str(exc)}


def post_query(path: str, question: str) -> dict[str, object]:
    try:
        response = requests.post(
            f"{API_BASE_URL}{path}",
            json={"question": question},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        return {
            "question": question,
            "sql": "",
            "generated_sql": "",
            "valid": False,
            "validation_message": "API request failed.",
            "final_answer": "",
            "rows": [],
            "rag_context": [],
            "row_count": 0,
            "trace_steps": [],
            "trace_id": None,
            "latency_ms": None,
            "errors": [str(exc)],
            "error": str(exc),
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
        }


def bbox_view_state(bbox: list[float] | None) -> object:
    if bbox and len(bbox) == 4:
        west, south, east, north = bbox
        return pdk.ViewState(
            longitude=(west + east) / 2,
            latitude=(south + north) / 2,
            zoom=12,
            pitch=45,
        )
    return pdk.ViewState(longitude=-75.6972, latitude=45.4215, zoom=11, pitch=45)


def color_expression(color_metric: str) -> str:
    if color_metric == "estimated_energy_intensity_kwh_m2":
        # Replacing Math.max(80, ...) with ternary
        return "[255, (220 - properties.estimated_energy_intensity_kwh_m2 * 0.45) < 80 ? 80 : (220 - properties.estimated_energy_intensity_kwh_m2 * 0.45), 40, 190]"
    if color_metric == "year_built":
        # Replacing Math.max(70, ...) with ternary
        return "[(230 - (2026 - properties.year_built) * 2) < 70 ? 70 : (230 - (2026 - properties.year_built) * 2), 120, 230, 185]"
    # Replacing Math.max(80, ...) with ternary
    return "[255, (230 - properties.retrofit_priority_score * 1.5) < 80 ? 80 : (230 - properties.retrofit_priority_score * 1.5), 35, 190]"


def elevation_expression(enabled: bool, metric: str, scale_factor: float) -> int | str:
    if not enabled:
        return 0
    safe_scale = max(0.1, min(scale_factor, 10.0))
    # Replacing Math.min(180, Math.max(0, ...)) with nested ternaries
    # val = (properties.{metric} || 0) * {safe_scale}
    # res = val > 180 ? 180 : (val < 0 ? 0 : val)
    val_expr = f"((properties.{metric} || 0) * {safe_scale})"
    return f"{val_expr} > 180 ? 180 : ({val_expr} < 0 ? 0 : {val_expr})"


def render_building_map(
    result_geojson: dict[str, object],
    bbox: list[float] | None,
    *,
    extrude: bool,
    extrusion_metric: str,
    scale_factor: float,
    color_metric: str,
) -> None:
    if pdk is None:
        st.warning("PyDeck is not installed, so map rendering is unavailable.")
        return

    try:
        highlight_layer = pdk.Layer(
            "GeoJsonLayer",
            result_geojson,
            pickable=True,
            stroked=True,
            filled=True,
            extruded=extrude,
            wireframe=extrude,
            get_elevation=elevation_expression(extrude, extrusion_metric, scale_factor),
            get_fill_color=color_expression(color_metric),
            get_line_color=[140, 38, 16, 230],
            line_width_min_pixels=1,
        )
        deck = pdk.Deck(
            layers=[highlight_layer],
            initial_view_state=bbox_view_state(bbox),
            tooltip={
                "html": (
                    "<b>{name}</b><br/>"
                    "Type: {building_type}<br/>"
                    "Year built: {year_built}<br/>"
                    "Energy intensity: {estimated_energy_intensity_kwh_m2} kWh/m2<br/>"
                    "Retrofit score: {retrofit_priority_score}<br/>"
                    "Height: {height_m} m<br/>"
                    "{data_quality_note}"
                ),
                "style": {"backgroundColor": "#1f2933", "color": "white"},
            },
        )
        st.pydeck_chart(deck, width="stretch")
    except Exception as exc:
        st.warning(f"Map rendering failed: {exc}")


st.set_page_config(page_title="TwinQuery", page_icon="TQ", layout="wide")

st.title("TwinQuery")
st.caption("Local LangGraph agent for synthetic building-stock and retrofit analytics.")

health = get_api_health()
st.metric(
    "API status",
    str(health.get("status", "unknown")),
    help="Shows whether the Streamlit UI can reach the FastAPI backend health endpoint.",
)

mode = st.radio(
    "Mode",
    MODES,
    horizontal=True,
    help=(
        "Hybrid Digital Twin Query: map/table from PostGIS plus retrofit guidance for explanation. "
        "Map query: building selection plus map polygons (SQL/PostGIS, no docs). "
        "Document RAG: guidance docs only, no database access. "
        "Text-to-SQL only: SQL and table results, no map. "
        "Agentic answer: experimental planner/routing mode that classifies the question and combines sources."
    ),
)

map_options: dict[str, object] = {
    "extrude": False,
    "extrusion_metric": "height_m",
    "scale_factor": 1.0,
    "color_metric": "retrofit_priority_score",
}
if mode == "Map query":
    col_extrude, col_metric = st.columns([1, 2])
    with col_extrude:
        map_options["extrude"] = st.checkbox(
            "Enable 3D extrusion",
            value=False,
            help="Extrude returned polygons by the selected metric.",
        )
    with col_metric:
        map_options["extrusion_metric"] = st.selectbox(
            "Extrusion metric",
            ["height_m", "estimated_energy_intensity_kwh_m2", "retrofit_priority_score"],
            help="Metric used to calculate extrusion height when 3D is enabled.",
        )
    col_scale, col_color = st.columns([1, 2])
    with col_scale:
        map_options["scale_factor"] = st.slider(
            "Scale factor",
            min_value=0.1,
            max_value=10.0,
            value=1.0,
            step=0.1,
            help="Multiplier for extrusion height. Output is capped to keep the map readable.",
        )
    with col_color:
        map_options["color_metric"] = st.selectbox(
            "Color metric",
            ["retrofit_priority_score", "estimated_energy_intensity_kwh_m2", "year_built"],
            help="Metric used to color returned polygons.",
        )

with st.form("question-form"):
    question = st.text_area(
        "Natural-language building query",
        value="Which buildings have the highest energy intensity?",
        help=(
            "Ask about the synthetic building stock, energy metrics, retrofit priorities, "
            "or comparisons between buildings."
        ),
    )
    submitted = st.form_submit_button(
        "Run",
        help="Send this question to the selected TwinQuery endpoint.",
    )

if submitted:
    if not question.strip():
        st.warning("Enter a question to continue.")
    elif mode == "Hybrid Digital Twin Query":
        progress = st.progress(0, text="Analyzing question and data sources...")
        with st.spinner("Querying map data, retrieving guidance, and synthesizing answer..."):
            result = post_query("/query/hybrid", question)
        progress.progress(80, text="Preparing results...")

        if result.get("error"):
            st.warning(str(result["error"]))
        if result.get("fallback_used"):
            st.info(
                "The map portion of this query was adjusted using a deterministic template."
            )

        st.subheader(
            "Synthesized Answer",
            help="Integrated analysis grounded in both database results and retrieved guidance.",
        )
        if result.get("answer"):
            st.write(str(result["answer"]))
        else:
            st.warning("No synthesized answer returned.")

        st.subheader("Building Map")
        result_geojson = result.get("geojson", {"type": "FeatureCollection", "features": []})
        if isinstance(result_geojson, dict) and result_geojson.get("features"):
            render_building_map(
                result_geojson,
                result.get("bbox") if isinstance(result.get("bbox"), list) else None,
                extrude=bool(map_options["extrude"]),
                extrusion_metric=str(map_options["extrusion_metric"]),
                scale_factor=float(map_options["scale_factor"]),
                color_metric=str(map_options["color_metric"]),
            )
        else:
            st.warning("Geometry was unavailable for this query.")

        st.subheader("Sources", help="Local documents used for retrofit guidance.")
        sources = result.get("sources", [])
        if sources:
            st.write(sources)
        else:
            st.caption("No sources retrieved.")

        with st.expander("Show SQL and Table Rows", expanded=False):
            st.code(str(result.get("sql", "")), language="sql")
            rows = result.get("rows", [])
            if rows:
                st.dataframe(rows, width="stretch")
            else:
                st.caption("No rows returned.")

        with st.expander("Retrieved Guidance Chunks", expanded=False):
            chunks = result.get("retrieved_context", [])
            if chunks:
                for chunk in chunks:
                    if isinstance(chunk, dict):
                        st.caption(f"{chunk.get('source', 'unknown')} | {chunk.get('section', 'Untitled')}")
                        st.write(chunk.get("text", ""))
            else:
                st.caption("No chunks retrieved.")
        progress.progress(100, text="Complete.")
    elif mode == "Map query":
        progress = st.progress(0, text="Sending map query...")
        with st.spinner("Generating map SQL and fetching building geometries..."):
            result = post_query("/query/map", question)
        progress.progress(80, text="Rendering map results...")

        if result.get("error"):
            st.warning(str(result["error"]))
        if result.get("fallback_used"):
            st.info(
                "The generated SQL was adjusted using a deterministic map-query template "
                "to ensure safe geometry output."
            )

        st.subheader(
            "Building Map",
            help="Returned query result polygons are highlighted on a 2D Ottawa-centered map.",
        )
        result_geojson = result.get("geojson", {"type": "FeatureCollection", "features": []})
        if isinstance(result_geojson, dict) and result_geojson.get("features"):
            render_building_map(
                result_geojson,
                result.get("bbox") if isinstance(result.get("bbox"), list) else None,
                extrude=bool(map_options["extrude"]),
                extrusion_metric=str(map_options["extrusion_metric"]),
                scale_factor=float(map_options["scale_factor"]),
                color_metric=str(map_options["color_metric"]),
            )
        else:
            st.warning("Geometry was unavailable for this query.")

        st.subheader(
            "Generated SQL",
            help="The map SQL should include ST_AsGeoJSON(geom) AS geometry_json for highlightable results.",
        )
        st.code(str(result.get("sql", "")), language="sql")

        st.subheader(
            "Rows",
            help="Tabular fallback for map queries and the source of highlighted feature properties.",
        )
        rows = result.get("rows", [])
        if rows:
            st.dataframe(rows, width="stretch")
        else:
            st.caption("No rows returned.")
        progress.progress(100, text="Complete.")
    elif mode == "Document RAG":
        progress = st.progress(0, text="Retrieving local guidance chunks...")
        with st.spinner("Retrieving local documents and asking the local model..."):
            result = post_query("/query/rag", question)
        progress.progress(80, text="Preparing document answer...")

        if result.get("error"):
            st.warning(str(result["error"]))

        st.subheader(
            "Answer",
            help="Answer generated from retrieved local guidance chunks only.",
        )
        if result.get("answer"):
            st.write(str(result["answer"]))
        else:
            st.warning("No document answer returned.")

        st.subheader("Sources", help="Local markdown files retrieved for this answer.")
        sources = result.get("sources", [])
        if sources:
            st.write(sources)
        else:
            st.caption("No sources returned.")

        with st.expander("Retrieved Chunks", expanded=False):
            chunks = result.get("retrieved_context", [])
            if chunks:
                for chunk in chunks:
                    if isinstance(chunk, dict):
                        st.caption(
                            f"{chunk.get('source', 'unknown')} | {chunk.get('section', 'Untitled')} | score={chunk.get('score', '')}"
                        )
                        st.write(chunk.get("text", ""))
            else:
                st.caption("No chunks returned.")
        progress.progress(100, text="Complete.")
    elif mode == "Text-to-SQL only":
        progress = st.progress(0, text="Checking question...")
        progress.progress(25, text="Sending question to SQL endpoint...")
        with st.spinner("Generating SQL and querying the building dataset..."):
            result = post_query("/query/sql", question)
        progress.progress(75, text="Preparing SQL results...")

        valid = bool(result.get("valid"))
        if valid:
            st.success(str(result.get("validation_message", "SQL valid.")))
        else:
            st.error(str(result.get("validation_message", "SQL invalid.")))

        if result.get("error"):
            st.warning(str(result["error"]))

        st.subheader(
            "Generated SQL",
            help="The read-only SQL generated from your natural-language question.",
        )
        st.code(str(result.get("sql", "")), language="sql")

        st.subheader(
            "Rows",
            help="Database rows returned by the generated SQL query.",
        )
        rows = result.get("rows", [])
        if rows:
            st.dataframe(rows, width="stretch")
        else:
            st.caption("No rows returned.")
        progress.progress(100, text="Complete.")
    else:
        progress = st.progress(0, text="Checking question...")
        progress.progress(20, text="Starting agent workflow...")
        with st.spinner("Planning, querying data, retrieving documents, and synthesizing an answer..."):
            result = post_query("/query/agent", question)
        progress.progress(80, text="Preparing agent results...")

        st.subheader(
            "Answer",
            help="The synthesized response produced from database results and retrieved guidance.",
        )
        if result.get("final_answer"):
            st.write(str(result["final_answer"]))
        else:
            st.warning("No final answer returned.")

        if result.get("errors"):
            st.subheader(
                "Errors",
                help="Backend or agent errors returned during this run.",
            )
            st.write(result["errors"])

        st.subheader(
            "Generated SQL",
            help="The SQL generated by the agent before validation and execution.",
        )
        st.code(str(result.get("generated_sql", "")), language="sql")

        st.subheader(
            "Rows",
            help="Database rows used as structured evidence for the final answer.",
        )
        rows = result.get("rows", [])
        if rows:
            st.dataframe(rows, width="stretch")
        else:
            st.caption("No rows returned.")

        st.subheader(
            "Retrieved Documents",
            help="Retrofit guidance chunks retrieved by the RAG step and passed to the synthesizer.",
        )
        chunks = result.get("rag_context", [])
        if chunks:
            for chunk in chunks:
                if isinstance(chunk, dict):
                    st.caption(f"{chunk.get('source', 'unknown')} | score={chunk.get('score', '')}")
                    st.write(chunk.get("text", ""))
        else:
            st.caption("No document chunks retrieved.")

        with st.expander("Agent Trace", expanded=True):
            st.caption("Detailed execution metadata for debugging and evaluation.")
            st.write({"trace_id": result.get("trace_id"), "latency_ms": result.get("latency_ms")})
            st.write("Planner decision and node steps")
            st.write(result.get("trace_steps", []))
            st.write("Generated SQL")
            st.code(str(result.get("generated_sql", "")), language="sql")
            st.write("Validation/errors")
            st.write(result.get("errors", []))
            st.write("Retrieved docs")
            st.write([chunk.get("source") for chunk in chunks if isinstance(chunk, dict)])
        progress.progress(100, text="Complete.")

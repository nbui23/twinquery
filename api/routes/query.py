"""Query endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from twinquery.agents.graph import run_agent_query
from twinquery.agents.hybrid_agent import answer_hybrid_question
from twinquery.agents.rag_agent import answer_document_question
from twinquery.agents.sql_agent import answer_map_query, answer_structured_query, get_buildings_geojson, iter_structured_query_events
from twinquery.observability.logging import get_trace, read_traces


router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Plain-English analytics question.")


class QueryResponse(BaseModel):
    answer: str
    implemented: bool = False


class SqlQueryResponse(BaseModel):
    question: str
    sql: str
    valid: bool
    validation_message: str
    rows: list[dict[str, Any]]
    row_count: int
    error: str | None = None


class AgentQueryResponse(BaseModel):
    trace_id: str | None = None
    latency_ms: float | None = None
    final_answer: str
    generated_sql: str
    rows: list[dict[str, Any]]
    rag_context: list[dict[str, Any]]
    trace_steps: list[str]
    errors: list[str]


class MapQueryResponse(BaseModel):
    question: str
    sql: str
    rows: list[dict[str, Any]]
    geojson: dict[str, Any]
    bbox: list[float] | None = None
    highlight_ids: list[Any]
    fallback_used: bool = False
    fallback_reason: str | None = None
    map_metrics_available: dict[str, bool]
    error: str | None = None


class RagQueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[str]
    retrieved_context: list[dict[str, Any]]
    error: str | None = None


class HybridQueryResponse(BaseModel):
    question: str
    answer: str
    sql: str
    rows: list[dict[str, Any]]
    geojson: dict[str, Any]
    bbox: list[float] | None = None
    highlight_ids: list[Any]
    sources: list[str]
    retrieved_context: list[dict[str, Any]]
    fallback_used: bool = False
    fallback_reason: str | None = None
    error: str | None = None


@router.post("", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    return QueryResponse(
        answer=(
            "TwinQuery received the question. Use /query/sql for the local "
            "Text-to-SQL prototype."
        ),
        implemented=False,
    )


@router.post("/sql", response_model=SqlQueryResponse)
def query_sql(request: QueryRequest) -> dict[str, Any]:
    return answer_structured_query(request.question)


@router.post("/sql/stream")
def query_sql_stream(request: QueryRequest) -> StreamingResponse:
    def event_lines():
        for event in iter_structured_query_events(request.question):
            yield json.dumps(event, default=str) + "\n"

    return StreamingResponse(event_lines(), media_type="application/x-ndjson")


@router.post("/agent", response_model=AgentQueryResponse)
def query_agent(request: QueryRequest) -> dict[str, Any]:
    state = run_agent_query(request.question)
    return {
        "final_answer": state["final_answer"],
        "trace_id": state.get("trace_id"),
        "latency_ms": state.get("latency_ms"),
        "generated_sql": state["generated_sql"],
        "rows": state["rows"],
        "rag_context": state["rag_context"],
        "trace_steps": state["trace_steps"],
        "errors": state["errors"],
    }


@router.post("/map", response_model=MapQueryResponse)
def query_map(request: QueryRequest) -> dict[str, Any]:
    return answer_map_query(request.question)


@router.post("/rag", response_model=RagQueryResponse)
def query_rag(request: QueryRequest) -> dict[str, Any]:
    return answer_document_question(request.question)


@router.post("/hybrid", response_model=HybridQueryResponse)
def query_hybrid(request: QueryRequest) -> dict[str, Any]:
    return answer_hybrid_question(request.question)


@router.get("/map/buildings")
def list_map_buildings(limit: int = 1000) -> dict[str, Any]:
    return get_buildings_geojson(limit=limit)


@router.get("/traces")
def list_traces(limit: int = 20) -> list[dict[str, Any]]:
    return read_traces(limit=limit)


@router.get("/traces/{trace_id}")
def read_trace(trace_id: str) -> dict[str, Any]:
    trace = get_trace(trace_id)
    if trace is None:
        return {"error": "trace_not_found", "trace_id": trace_id}
    return trace

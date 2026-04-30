"""Structured LangGraph state for TwinQuery agents."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


Intent = Literal[
    "structured_data_query",
    "document_policy_query",
    "hybrid_query",
    "unsupported",
]


class TwinQueryState(TypedDict):
    user_question: str
    intent: Intent
    plan: list[str]
    generated_sql: str
    sql_valid: bool
    validation_message: str
    rows: list[dict[str, Any]]
    rag_context: list[dict[str, Any]]
    final_answer: str
    errors: list[str]
    trace_steps: list[str]
    trace_id: str | None
    latency_ms: float | None


def initial_state(user_question: str) -> TwinQueryState:
    return {
        "user_question": user_question,
        "intent": "unsupported",
        "plan": [],
        "generated_sql": "",
        "sql_valid": False,
        "validation_message": "",
        "rows": [],
        "rag_context": [],
        "final_answer": "",
        "errors": [],
        "trace_steps": [],
        "trace_id": None,
        "latency_ms": None,
    }

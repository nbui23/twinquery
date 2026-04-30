"""Trace structures for local agent observability."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class TraceStep:
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AgentTrace:
    trace_id: str
    timestamp: str
    user_question: str
    steps: list[str]
    generated_sql: str
    validation_result: dict[str, Any]
    retrieved_sources: list[str]
    final_answer: str
    errors: list[str]
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def new_trace_id() -> str:
    return str(uuid4())


def create_agent_trace(
    user_question: str,
    steps: list[str],
    generated_sql: str,
    sql_valid: bool,
    validation_message: str,
    rag_context: list[dict[str, Any]],
    final_answer: str,
    errors: list[str],
    latency_ms: float,
    trace_id: str | None = None,
) -> AgentTrace:
    retrieved_sources = sorted(
        {
            str(item.get("source"))
            for item in rag_context
            if isinstance(item, dict) and item.get("source")
        }
    )
    return AgentTrace(
        trace_id=trace_id or new_trace_id(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_question=user_question,
        steps=steps,
        generated_sql=generated_sql,
        validation_result={"sql_valid": sql_valid, "message": validation_message},
        retrieved_sources=retrieved_sources,
        final_answer=final_answer,
        errors=errors,
        latency_ms=round(latency_ms, 2),
    )


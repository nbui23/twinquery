"""Grounded answer synthesis for TwinQuery."""

from __future__ import annotations

from typing import Any


def _format_row_preview(rows: list[dict[str, Any]], limit: int = 5) -> str:
    if not rows:
        return "No database rows were returned."

    lines: list[str] = []
    for index, row in enumerate(rows[:limit], start=1):
        compact = ", ".join(f"{key}={value}" for key, value in list(row.items())[:6])
        lines.append(f"{index}. {compact}")
    if len(rows) > limit:
        lines.append(f"... plus {len(rows) - limit} more rows.")
    return "\n".join(lines)


def synthesize_agent_answer(
    question: str,
    intent: str,
    generated_sql: str,
    sql_valid: bool,
    validation_message: str,
    rows: list[dict[str, Any]],
    rag_context: list[Any],
    errors: list[str],
) -> str:
    if intent == "unsupported":
        return (
            "I can help with local building-stock SQL questions, retrofit guidance questions, "
            "or questions that combine both. This request is outside the current TwinQuery scope."
        )

    sources: list[str] = []
    if rows:
        sources.append("synthetic database rows")
    if rag_context:
        sources.append("local retrofit documents")
    if not sources:
        sources.append("no retrieved evidence")

    parts: list[str] = []

    if rows:
        parts.append("Database results (primary answer):")
        parts.append(_format_row_preview(rows))

    if rag_context:
        source_labels: list[str] = []
        context_lines: list[str] = []
        for item in rag_context[:2]:
            if isinstance(item, dict):
                source = str(item.get("source", "unknown_source"))
                section = str(item.get("section", "Untitled"))
                source_labels.append(source)
                context_lines.append(f"[{source} | {section}] {item.get('text', '')}")
            else:
                context_lines.append(str(item))
        header = (
            "Supporting guidance from local documents:"
            if rows
            else "Document context:"
        )
        parts.append(header)
        parts.append("\n".join(context_lines))
        if source_labels:
            parts.append(f"Citations: {', '.join(sorted(set(source_labels)))}.")

    if not rows and not rag_context and not errors:
        if intent == "document_policy_query":
            parts.append(
                "Local documents do not contain enough information to answer this question."
            )
        else:
            parts.append("No matching evidence was retrieved.")

    parts.append(f"Sources used: {', '.join(sources)}.")
    parts.append("Limitation: the building-stock data is synthetic and intended for local demos.")

    if errors:
        parts.append(f"Errors: {'; '.join(errors)}")

    if generated_sql:
        status = "valid" if sql_valid else "blocked"
        parts.append(f"SQL status: {status}. {validation_message}")

    return "\n\n".join(parts)


def synthesize_answer(question: str, rows: list[dict[str, object]], context: list[str]) -> str:
    return synthesize_agent_answer(
        question=question,
        intent="hybrid_query" if rows and context else "structured_data_query",
        generated_sql="",
        sql_valid=True,
        validation_message="",
        rows=[dict(row) for row in rows],
        rag_context=context,
        errors=[],
    )

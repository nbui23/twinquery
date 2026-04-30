"""Hybrid agent combining SQL/Map results and RAG guidance."""

from __future__ import annotations

from typing import Any

from collections.abc import Callable

from twinquery.agents.rag_agent import retrieve_guidance
from twinquery.agents.sql_agent import answer_map_query
from twinquery.llm.ollama_client import generate
from twinquery.llm.prompts import build_hybrid_synthesis_prompt


def answer_hybrid_question(
    question: str,
    *,
    map_query: Callable[[str], dict[str, Any]] = answer_map_query,
    retriever: Callable[[str, int], list[dict[str, Any]]] = retrieve_guidance,
    llm_generate: Callable[[str], str] = generate,
) -> dict[str, Any]:
    """
    Main entry point for hybrid queries.
    Combines SQL/PostGIS results (map highlights) with RAG guidance.
    """
    # 1. Map/SQL Pipeline
    map_result = map_query(question)
    
    # Extract data for RAG and Synthesis
    rows = map_result.get("rows", [])
    sql = map_result.get("sql", "N/A")
    
    # 2. RAG Retrieval
    # We use the original question, but could optionally augment it with row context
    retrieved_context = retriever(question, 4)
    
    sources = sorted(
        {
            str(chunk.get("source"))
            for chunk in retrieved_context
            if chunk.get("source") and chunk.get("source") != "missing_index"
        }
    )
    
    # 3. Grounded Synthesis
    # If the LLM call fails, we still want to return the map results
    answer = ""
    error = map_result.get("error")
    
    try:
        prompt = build_hybrid_synthesis_prompt(
            question=question,
            rows=rows,
            retrieved_context=retrieved_context,
            sql=sql
        )
        answer = llm_generate(prompt)
    except Exception as exc:
        if not error:
            error = str(exc)
        answer = "Hybrid synthesis could not be completed. Showing map results only."

    # 4. Consolidate Result
    return {
        "question": question,
        "answer": answer,
        "sql": sql,
        "rows": rows,
        "geojson": map_result.get("geojson", {}),
        "bbox": map_result.get("bbox"),
        "highlight_ids": map_result.get("highlight_ids", []),
        "sources": list(sources),
        "retrieved_context": retrieved_context,
        "fallback_used": map_result.get("fallback_used", False),
        "fallback_reason": map_result.get("fallback_reason"),
        "error": error,
    }

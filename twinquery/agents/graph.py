"""LangGraph orchestration for TwinQuery."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from twinquery.agents.planner import build_plan
from twinquery.agents.rag_agent import retrieve_guidance
from twinquery.agents.sql_agent import execute_validated_sql, generate_sql_for_question, validate_generated_sql
from twinquery.agents.state import TwinQueryState, initial_state
from twinquery.agents.synthesizer import synthesize_agent_answer
from twinquery.llm.ollama_client import generate
from twinquery.observability.logging import write_trace
from twinquery.observability.traces import create_agent_trace


QueryRunner = Callable[[str], list[dict[str, Any]]]
Retriever = Callable[[str], list[dict[str, Any]]]
LlmGenerate = Callable[[str], str]


def _append_trace(state: TwinQueryState, step: str) -> list[str]:
    return [*state.get("trace_steps", []), step]


def build_graph(
    llm_generate: LlmGenerate = generate,
    query_runner: QueryRunner | None = None,
    retriever: Retriever = retrieve_guidance,
):
    runner = query_runner

    def plan_query(state: TwinQueryState) -> dict[str, Any]:
        intent, plan = build_plan(state["user_question"])
        return {
            "intent": intent,
            "plan": plan,
            "trace_steps": _append_trace(state, f"plan_query:{intent}"),
        }

    def generate_sql(state: TwinQueryState) -> dict[str, Any]:
        try:
            sql = generate_sql_for_question(state["user_question"], llm_generate=llm_generate)
            return {
                "generated_sql": sql,
                "trace_steps": _append_trace(state, "generate_sql:ok"),
            }
        except Exception as exc:
            return {
                "errors": [*state.get("errors", []), str(exc)],
                "trace_steps": _append_trace(state, "generate_sql:error"),
            }

    def validate_sql(state: TwinQueryState) -> dict[str, Any]:
        valid, message = validate_generated_sql(state.get("generated_sql", ""))
        return {
            "sql_valid": valid,
            "validation_message": message,
            "trace_steps": _append_trace(state, f"validate_sql:{'ok' if valid else 'blocked'}"),
        }

    def execute_sql(state: TwinQueryState) -> dict[str, Any]:
        if not state.get("sql_valid"):
            return {
                "errors": [*state.get("errors", []), state.get("validation_message", "SQL invalid.")],
                "trace_steps": _append_trace(state, "execute_sql:skipped"),
            }
        try:
            rows = execute_validated_sql(state["generated_sql"], query_runner=runner) if runner else execute_validated_sql(state["generated_sql"])
            return {
                "rows": rows,
                "trace_steps": _append_trace(state, f"execute_sql:{len(rows)}_rows"),
            }
        except Exception as exc:
            return {
                "errors": [*state.get("errors", []), str(exc)],
                "trace_steps": _append_trace(state, "execute_sql:error"),
            }

    def retrieve_docs(state: TwinQueryState) -> dict[str, Any]:
        try:
            context = retriever(state["user_question"])
            sources = sorted(
                {
                    str(item.get("source"))
                    for item in context
                    if isinstance(item, dict) and item.get("source")
                }
            )
            return {
                "rag_context": context,
                "trace_steps": _append_trace(
                    state,
                    f"retrieve_docs:{len(context)}_chunks:{','.join(sources) or 'no_sources'}",
                ),
            }
        except Exception as exc:
            return {
                "errors": [*state.get("errors", []), str(exc)],
                "trace_steps": _append_trace(state, "retrieve_docs:error"),
            }

    def synthesize_answer(state: TwinQueryState) -> dict[str, Any]:
        answer = synthesize_agent_answer(
            question=state["user_question"],
            intent=state["intent"],
            generated_sql=state.get("generated_sql", ""),
            sql_valid=state.get("sql_valid", False),
            validation_message=state.get("validation_message", ""),
            rows=state.get("rows", []),
            rag_context=state.get("rag_context", []),
            errors=state.get("errors", []),
        )
        return {
            "final_answer": answer,
            "trace_steps": _append_trace(state, "synthesize_answer:ok"),
        }

    def handle_error(state: TwinQueryState) -> dict[str, Any]:
        return {
            "final_answer": (
                "I can answer local building-stock analytics and retrofit guidance questions. "
                "This request is outside the current TwinQuery scope."
            ),
            "trace_steps": _append_trace(state, "handle_error:unsupported"),
        }

    def route_after_plan(state: TwinQueryState) -> str:
        return {
            "structured_data_query": "generate_sql",
            "document_policy_query": "retrieve_docs",
            "hybrid_query": "generate_sql",
            "unsupported": "handle_error",
        }[state["intent"]]

    def route_after_execute(state: TwinQueryState) -> str:
        return "retrieve_docs" if state["intent"] == "hybrid_query" else "synthesize_answer"

    graph = StateGraph(TwinQueryState)
    graph.add_node("plan_query", plan_query)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("validate_sql", validate_sql)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("retrieve_docs", retrieve_docs)
    graph.add_node("synthesize_answer", synthesize_answer)
    graph.add_node("handle_error", handle_error)

    graph.set_entry_point("plan_query")
    graph.add_conditional_edges("plan_query", route_after_plan)
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_edge("validate_sql", "execute_sql")
    graph.add_conditional_edges("execute_sql", route_after_execute)
    graph.add_edge("retrieve_docs", "synthesize_answer")
    graph.add_edge("synthesize_answer", END)
    graph.add_edge("handle_error", END)
    return graph.compile()


def run_agent_query(
    user_question: str,
    llm_generate: LlmGenerate = generate,
    query_runner: QueryRunner | None = None,
    retriever: Retriever = retrieve_guidance,
) -> TwinQueryState:
    started = time.perf_counter()
    graph = build_graph(llm_generate=llm_generate, query_runner=query_runner, retriever=retriever)
    state = graph.invoke(initial_state(user_question))
    latency_ms = (time.perf_counter() - started) * 1000
    trace = create_agent_trace(
        user_question=user_question,
        steps=state.get("trace_steps", []),
        generated_sql=state.get("generated_sql", ""),
        sql_valid=state.get("sql_valid", False),
        validation_message=state.get("validation_message", ""),
        rag_context=state.get("rag_context", []),
        final_answer=state.get("final_answer", ""),
        errors=state.get("errors", []),
        latency_ms=latency_ms,
    )
    state["trace_id"] = trace.trace_id
    state["latency_ms"] = trace.latency_ms
    write_trace(trace)
    return state


def run_placeholder(question: str) -> TwinQueryState:
    return initial_state(question)

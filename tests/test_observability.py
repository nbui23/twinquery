import json

from twinquery.agents.graph import run_agent_query
from twinquery.observability.logging import get_trace, read_traces, write_trace
from twinquery.observability.traces import create_agent_trace


def test_trace_object_can_be_serialized() -> None:
    trace = create_agent_trace(
        user_question="Which buildings have highest energy intensity?",
        steps=["plan_query:structured_data_query"],
        generated_sql="SELECT id FROM buildings LIMIT 1;",
        sql_valid=True,
        validation_message="ok",
        rag_context=[{"source": "retrofit_guidelines.md"}],
        final_answer="Sources used: synthetic database rows.",
        errors=[],
        latency_ms=12.5,
        trace_id="trace-test",
    )

    payload = trace.to_dict()
    assert payload["trace_id"] == "trace-test"
    assert json.loads(json.dumps(payload))["retrieved_sources"] == ["retrofit_guidelines.md"]


def test_trace_is_written_to_jsonl(tmp_path) -> None:
    path = tmp_path / "traces.jsonl"
    trace = create_agent_trace(
        user_question="Question",
        steps=["step"],
        generated_sql="",
        sql_valid=False,
        validation_message="",
        rag_context=[],
        final_answer="Answer",
        errors=[],
        latency_ms=1.0,
        trace_id="abc",
    )

    write_trace(trace, path=path)

    assert read_traces(path=path)[0]["trace_id"] == "abc"
    assert get_trace("abc", path=path)["final_answer"] == "Answer"


def test_graph_output_includes_trace_steps() -> None:
    def fake_llm(prompt: str) -> str:
        return "SELECT id, name FROM buildings LIMIT 25;"

    def fake_query_runner(sql: str) -> list[dict[str, object]]:
        return [{"id": 1, "name": "Synthetic Office 001"}]

    def fake_retriever(question: str) -> list[dict[str, object]]:
        return [{"source": "retrofit_guidelines.md", "text": "Guidance", "score": 1.0}]

    state = run_agent_query(
        "Which buildings should be retrofitted and why?",
        llm_generate=fake_llm,
        query_runner=fake_query_runner,
        retriever=fake_retriever,
    )

    assert state["trace_steps"]
    assert state["trace_id"]
    assert state["latency_ms"] is not None
    assert any("retrieve_docs" in step for step in state["trace_steps"])

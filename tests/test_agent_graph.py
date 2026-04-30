from twinquery.agents.graph import run_agent_query


def fake_llm(prompt: str) -> str:
    return "SELECT id, name FROM buildings LIMIT 25;"


def fake_query_runner(sql: str) -> list[dict[str, object]]:
    return [{"id": 1, "name": "Synthetic Office 001"}]


def fake_retriever(question: str) -> list[str]:
    return ["retrofit_guidelines.md: Use observed data before making retrofit claims."]


def test_graph_returns_structured_output() -> None:
    state = run_agent_query(
        "Which buildings have the highest energy intensity?",
        llm_generate=fake_llm,
        query_runner=fake_query_runner,
        retriever=fake_retriever,
    )

    assert state["intent"] == "structured_data_query"
    assert state["generated_sql"] == "SELECT id, name FROM buildings LIMIT 25;"
    assert state["rows"][0]["name"] == "Synthetic Office 001"
    assert "synthetic database rows" in state["final_answer"]
    assert state["trace_steps"][-1] == "synthesize_answer:ok"


def test_graph_unsupported_query_does_not_crash() -> None:
    state = run_agent_query(
        "Send an email to the building owner",
        llm_generate=fake_llm,
        query_runner=fake_query_runner,
        retriever=fake_retriever,
    )

    assert state["intent"] == "unsupported"
    assert state["rows"] == []
    assert "outside the current TwinQuery scope" in state["final_answer"]
    assert state["errors"] == []


def test_graph_validation_failure_routes_safely() -> None:
    def unsafe_llm(prompt: str) -> str:
        return "DROP TABLE buildings;"

    def fail_query_runner(sql: str) -> list[dict[str, object]]:
        raise AssertionError("unsafe SQL must not execute")

    state = run_agent_query(
        "Which buildings have the highest energy intensity?",
        llm_generate=unsafe_llm,
        query_runner=fail_query_runner,
        retriever=fake_retriever,
    )

    assert state["sql_valid"] is False
    assert state["rows"] == []
    assert state["errors"]
    assert "blocked" in state["validation_message"].lower() or "allowed" in state["validation_message"].lower()


def test_graph_hybrid_uses_sql_and_docs() -> None:
    state = run_agent_query(
        "Which buildings should be retrofitted and why?",
        llm_generate=fake_llm,
        query_runner=fake_query_runner,
        retriever=fake_retriever,
    )

    assert state["intent"] == "hybrid_query"
    assert state["rows"]
    assert state["rag_context"]
    assert "local retrofit documents" in state["final_answer"]

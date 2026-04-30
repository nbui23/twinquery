from twinquery.agents.sql_agent import answer_structured_query, extract_sql, iter_structured_query_events


def test_extract_sql_from_markdown() -> None:
    output = """Here is SQL:
```sql
SELECT id, name FROM buildings LIMIT 25;
```
"""
    assert extract_sql(output) == "SELECT id, name FROM buildings LIMIT 25;"


def test_sql_agent_with_mocked_llm_and_query_runner() -> None:
    def fake_llm(prompt: str) -> str:
        assert "Only generate read-only SELECT" in prompt
        return "SELECT id, name FROM buildings LIMIT 25;"

    def fake_query_runner(sql: str) -> list[dict[str, object]]:
        assert sql == "SELECT id, name FROM buildings LIMIT 25;"
        return [{"id": 1, "name": "Synthetic Office 001"}]

    result = answer_structured_query(
        "Which buildings have the highest energy intensity?",
        llm_generate=fake_llm,
        query_runner=fake_query_runner,
    )

    assert result["valid"] is True
    assert result["row_count"] == 1
    assert result["rows"][0]["name"] == "Synthetic Office 001"
    assert result["error"] is None


def test_sql_agent_returns_validation_error_before_query_runner() -> None:
    def fake_llm(prompt: str) -> str:
        return "DROP TABLE buildings;"

    def fake_query_runner(sql: str) -> list[dict[str, object]]:
        raise AssertionError("query runner must not be called")

    result = answer_structured_query(
        "Delete all buildings",
        llm_generate=fake_llm,
        query_runner=fake_query_runner,
    )

    assert result["valid"] is False
    assert result["rows"] == []
    assert "blocked" in str(result["error"]).lower() or "allowed" in str(result["error"]).lower()


def test_sql_agent_stream_events_show_progress() -> None:
    def fake_llm(prompt: str) -> str:
        return "SELECT id, name FROM buildings LIMIT 25;"

    def fake_query_runner(sql: str) -> list[dict[str, object]]:
        return [{"id": 1, "name": "Synthetic Office 001"}]

    events = list(
        iter_structured_query_events(
            "Which buildings have the highest energy intensity?",
            llm_generate=fake_llm,
            query_runner=fake_query_runner,
        )
    )

    assert [event["event"] for event in events] == [
        "started",
        "ollama",
        "sql_generated",
        "executing_sql",
        "complete",
    ]
    assert events[-1]["result"]["row_count"] == 1

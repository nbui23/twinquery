from typing import Any
from fastapi.testclient import TestClient
from api.main import app
from twinquery.agents.hybrid_agent import answer_hybrid_question
from twinquery.llm.prompts import build_hybrid_synthesis_prompt, summarize_top_rows

def test_summarize_top_rows_truncates() -> None:
    rows = [{"name": f"B{i}", "building_type": "Office", "year_built": 2000} for i in range(10)]
    summary = summarize_top_rows(rows, limit=5)
    assert "B0" in summary
    assert "B4" in summary
    assert "B5" not in summary
    assert "... and 5 more matching buildings." in summary

def test_summarize_top_rows_handles_missing_fields() -> None:
    rows = [{"id": 123}]
    summary = summarize_top_rows(rows)
    assert "Building 123" in summary
    assert "Unknown type" in summary

def test_hybrid_prompt_includes_all_components() -> None:
    question = "Test question?"
    rows = [{"name": "Test Building"}]
    retrieved = [{"source": "test.md", "section": "S1", "text": "Test guidance."}]
    sql = "SELECT * FROM test;"
    
    prompt = build_hybrid_synthesis_prompt(question, rows, retrieved, sql)
    
    assert "--- DATABASE FINDINGS ---" in prompt
    assert "--- RETRIEVED GUIDANCE ---" in prompt
    assert "Test Building" in prompt
    assert "test.md" in prompt
    assert "SELECT * FROM test;" in prompt
    assert question in prompt

def test_answer_hybrid_question_successful_run() -> None:
    def fake_map_query(q: str) -> dict[str, Any]:
        return {
            "sql": "SELECT * FROM buildings;",
            "rows": [{"name": "Map Building"}],
            "geojson": {"type": "FeatureCollection", "features": []},
            "highlight_ids": [1],
            "error": None
        }
    
    def fake_retriever(q: str, k: int) -> list[dict[str, Any]]:
        return [{"source": "guidance.md", "text": "Retrofit info.", "score": 0.9}]
    
    def fake_llm(p: str) -> str:
        return "Synthesized answer with guidance.md and Map Building."

    result = answer_hybrid_question(
        "Show buildings and explain retrofits.",
        map_query=fake_map_query,
        retriever=fake_retriever,
        llm_generate=fake_llm
    )

    assert result["answer"] == "Synthesized answer with guidance.md and Map Building."
    assert result["sql"] == "SELECT * FROM buildings;"
    assert result["sources"] == ["guidance.md"]
    assert len(result["rows"]) == 1
    assert result["error"] is None

def test_answer_hybrid_question_handles_missing_rag() -> None:
    def fake_map_query(q: str) -> dict[str, Any]:
        return {"sql": "SELECT...", "rows": [], "error": None}
    
    def fake_retriever(q: str, k: int) -> list[dict[str, Any]]:
        return []
    
    def fake_llm(p: str) -> str:
        assert "No specific guidance found." in p
        return "Found nothing in DB or RAG."

    result = answer_hybrid_question("?", map_query=fake_map_query, retriever=fake_retriever, llm_generate=fake_llm)
    assert "Found nothing" in result["answer"]
    assert result["sources"] == []

def test_answer_hybrid_question_handles_map_error() -> None:
    def fake_map_query(q: str) -> dict[str, Any]:
        return {"sql": "N/A", "rows": [], "error": "Database down"}
    
    def fake_retriever(q: str, k: int) -> list[dict[str, Any]]:
        return []
    
    def fake_llm(p: str) -> str:
        return "Fallback answer."

    result = answer_hybrid_question("?", map_query=fake_map_query, retriever=fake_retriever, llm_generate=fake_llm)
    assert result["error"] == "Database down"
    assert result["answer"] == "Fallback answer."

def test_hybrid_api_route_shape(monkeypatch) -> None:
    def fake_hybrid_handler(q: str) -> dict[str, Any]:
        return {
            "question": q,
            "answer": "Test answer",
            "sql": "SELECT 1",
            "rows": [],
            "geojson": {"type": "FeatureCollection", "features": []},
            "sources": ["test.md"],
            "retrieved_context": [],
            "highlight_ids": [],
            "error": None
        }
    
    monkeypatch.setattr("api.routes.query.answer_hybrid_question", fake_hybrid_handler)
    client = TestClient(app)
    
    response = client.post("/query/hybrid", json={"question": "Hybrid test"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Test answer"
    assert "question" in data
    assert "sql" in data
    assert "rows" in data
    assert "geojson" in data
    assert "bbox" in data
    assert "highlight_ids" in data
    assert "sources" in data
    assert "retrieved_context" in data
    assert "fallback_used" in data
    assert "fallback_reason" in data
    assert "error" in data

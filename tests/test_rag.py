from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from twinquery.agents.rag_agent import answer_document_question, build_grounded_rag_prompt, format_context_for_synthesis, retrieve_guidance
from twinquery.agents.synthesizer import synthesize_agent_answer
from twinquery.rag.ingest_docs import build_chunks, list_documents
from twinquery.rag.retriever import retrieve_context


def test_ingestion_functions_import_and_build_chunks() -> None:
    assert list_documents()
    chunks = build_chunks()
    assert chunks
    assert {"text", "source", "section", "chunk_id"} <= set(chunks[0])


def test_markdown_chunking_preserves_source_metadata(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "demo.md").write_text("# Demo\n\n## Section A\n\nOne two three four five.", encoding="utf-8")

    chunks = build_chunks(docs_dir=docs_dir, chunk_size=3, chunk_overlap=1)

    assert chunks
    assert chunks[0]["source"] == "demo.md"
    assert "Section A" in {chunk["section"] for chunk in chunks}
    assert chunks[0]["chunk_id"].startswith("demo-")


def test_retriever_returns_expected_type() -> None:
    chunks = retrieve_context("heat pump retrofit", k=2)
    assert isinstance(chunks, list)
    assert chunks
    assert {"text", "source", "score"} <= set(chunks[0])


def test_retriever_missing_index_returns_clean_message(tmp_path: Path) -> None:
    chunks = retrieve_context("anything", k=1, index_dir=tmp_path / "missing")

    assert chunks
    assert {"text", "source", "score"} <= set(chunks[0])


def test_rag_context_format_includes_source_filename() -> None:
    chunks = [{"source": "heat_pump_notes.md", "section": "Candidate Buildings", "text": "Heat pump context."}]
    formatted = format_context_for_synthesis(chunks)
    assert "heat_pump_notes.md" in formatted[0]


def test_grounded_rag_prompt_requires_retrieved_context_only() -> None:
    prompt = build_grounded_rag_prompt(
        "What should I do?",
        [{"source": "retrofit_guidelines.md", "section": "Screening", "text": "Use observed data.", "score": 0.9}],
    )

    assert "Answer using only the retrieved context" in prompt
    assert "Do not present synthetic demo guidance as authoritative policy" in prompt
    assert "retrofit_guidelines.md" in prompt


def test_answer_document_question_with_mocks() -> None:
    def fake_retriever(question: str, k: int) -> list[dict[str, object]]:
        assert k == 4
        return [
            {
                "source": "heat_pump_notes.md",
                "section": "Candidate Buildings",
                "text": "Heat pumps need load and electrical checks.",
                "score": 0.8,
            }
        ]

    def fake_llm(prompt: str) -> str:
        assert "using only the retrieved context" in prompt.lower()
        return "Heat pump screening should check loads and electrical capacity. Source: heat_pump_notes.md"

    result = answer_document_question("What about heat pumps?", retriever=fake_retriever, llm_generate=fake_llm)

    assert result["error"] is None
    assert result["sources"] == ["heat_pump_notes.md"]
    assert "heat_pump_notes.md" in result["answer"]


def test_rag_api_route_shape_with_mock(monkeypatch) -> None:
    def fake_answer_document_question(question: str) -> dict[str, object]:
        return {
            "question": question,
            "answer": "Use observed data. Source: retrofit_guidelines.md",
            "sources": ["retrofit_guidelines.md"],
            "retrieved_context": [{"source": "retrofit_guidelines.md", "section": "Screening", "text": "Use observed data.", "score": 1.0}],
            "error": None,
        }

    monkeypatch.setattr("api.routes.query.answer_document_question", fake_answer_document_question)
    client = TestClient(app)

    response = client.post("/query/rag", json={"question": "What guidance applies?"})

    assert response.status_code == 200
    assert response.json()["sources"] == ["retrofit_guidelines.md"]
    assert response.json()["retrieved_context"][0]["source"] == "retrofit_guidelines.md"


def test_retrieve_guidance_returns_citation_chunks() -> None:
    chunks = retrieve_guidance("What does the retrofit guidance say about envelope upgrades?", k=2)
    assert chunks
    assert chunks[0]["source"].endswith(".md")


def test_synthesizer_includes_citation_source_labels() -> None:
    answer = synthesize_agent_answer(
        question="What does the guide say about heat pumps?",
        intent="document_policy_query",
        generated_sql="",
        sql_valid=False,
        validation_message="",
        rows=[],
        rag_context=[
            {
                "source": "heat_pump_notes.md",
                "section": "Candidate Buildings",
                "text": "Heat pump feasibility depends on load and electrical capacity.",
                "score": 0.8,
            }
        ],
        errors=[],
    )
    assert "Citations: heat_pump_notes.md." in answer
    assert "local retrofit documents" in answer

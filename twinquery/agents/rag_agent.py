"""RAG helper functions for graph nodes and synthesis."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from twinquery.llm.ollama_client import generate
from twinquery.rag.retriever import retrieve_context


def retrieve_guidance(question: str, k: int = 4) -> list[dict[str, Any]]:
    return retrieve_context(question, k=k)


def format_context_for_synthesis(chunks: list[dict[str, Any]]) -> list[str]:
    formatted: list[str] = []
    for chunk in chunks:
        source = chunk.get("source", "unknown_source")
        section = chunk.get("section", "Untitled")
        text = chunk.get("text", "")
        formatted.append(f"[{source} | {section}] {text}")
    return formatted


def build_grounded_rag_prompt(question: str, chunks: list[dict[str, Any]]) -> str:
    context_blocks = "\n\n".join(format_context_for_synthesis(chunks))
    return (
        "You are TwinQuery's local document QA assistant.\n"
        "Answer using only the retrieved context below.\n"
        "Cite source filenames inline or at the end.\n"
        "If the context does not contain enough information, say that the local docs do not contain enough information.\n"
        "Do not present synthetic demo guidance as authoritative policy.\n"
        "Keep the answer concise and practical.\n\n"
        f"Question:\n{question.strip()}\n\n"
        f"Retrieved context:\n{context_blocks or 'No retrieved context.'}\n\n"
        "Answer:"
    )


def answer_document_question(
    question: str,
    *,
    retriever: Callable[[str, int], list[dict[str, Any]]] = retrieve_context,
    llm_generate: Callable[[str], str] = generate,
    k: int = 4,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "question": question,
        "answer": "",
        "sources": [],
        "retrieved_context": [],
        "error": None,
    }
    try:
        chunks = retriever(question, k)
        result["retrieved_context"] = chunks
        result["sources"] = sorted(
            {
                str(chunk.get("source"))
                for chunk in chunks
                if chunk.get("source") and chunk.get("source") != "missing_index"
            }
        )
        if chunks and chunks[0].get("error") == "missing_index":
            result["error"] = str(chunks[0]["text"])
            result["answer"] = "The local RAG index is missing. Run `python -m twinquery.rag.ingest_docs` first."
            return result

        prompt = build_grounded_rag_prompt(question, chunks)
        result["answer"] = llm_generate(prompt)
        return result
    except Exception as exc:
        result["error"] = str(exc)
        if not result["answer"]:
            result["answer"] = "Document RAG could not complete with the local index and model."
        return result

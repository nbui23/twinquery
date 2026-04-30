"""Local vector retriever with lexical fallback."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from twinquery.config import get_settings
from twinquery.rag.ingest_docs import DOCS_DIR, EMBEDDINGS_PATH, INDEX_PATH, build_chunks


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", text.lower()) if len(token) > 3}


def _load_index(
    metadata_path: Path = INDEX_PATH,
    embeddings_path: Path = EMBEDDINGS_PATH,
) -> list[dict[str, Any]]:
    if not metadata_path.exists() or not embeddings_path.exists():
        return []
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    embeddings = json.loads(embeddings_path.read_text(encoding="utf-8"))
    return [
        {**record, "embedding": embedding}
        for record, embedding in zip(metadata, embeddings, strict=False)
    ]


def _embed_query(question: str) -> list[float]:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(get_settings().embedding_model)
    vector = model.encode([question], normalize_embeddings=True)[0]
    return [float(value) for value in vector]


def _lexical_retrieve(question: str, k: int) -> list[dict[str, Any]]:
    terms = _tokenize(question)
    records = build_chunks()
    scored: list[dict[str, Any]] = []
    for record in records:
        text_terms = _tokenize(record["text"])
        overlap = len(terms & text_terms)
        if overlap or not terms:
            scored.append({**record, "score": float(overlap)})

    scored.sort(key=lambda item: item["score"], reverse=True)
    return [
        {
            "text": item["text"],
            "source": item["source"],
            "section": item["section"],
            "chunk_id": item["chunk_id"],
            "score": item["score"],
        }
        for item in scored[:k]
    ]


def retrieve_context(
    question: str,
    k: int = 4,
    *,
    index_dir: Path | None = None,
) -> list[dict[str, Any]]:
    metadata_path = (index_dir / "metadata.json") if index_dir else INDEX_PATH
    embeddings_path = (index_dir / "embeddings.json") if index_dir else EMBEDDINGS_PATH
    records = _load_index(metadata_path=metadata_path, embeddings_path=embeddings_path)
    if not records:
        lexical = _lexical_retrieve(question, k)
        if lexical:
            return lexical
        return [
            {
                "text": "RAG index is missing. Run `python -m twinquery.rag.ingest_docs` to build it.",
                "source": "missing_index",
                "section": "Index unavailable",
                "chunk_id": "missing-index",
                "score": 0.0,
                "error": "missing_index",
            }
        ]

    try:
        query_embedding = _embed_query(question)
    except Exception:
        return _lexical_retrieve(question, k)

    scored = [
        {
            "text": record["text"],
            "source": record["source"],
            "section": record.get("section", ""),
            "chunk_id": record.get("chunk_id", ""),
            "score": round(_cosine(query_embedding, record["embedding"]), 4),
        }
        for record in records
    ]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:k]


def retrieve(query: str, limit: int = 3) -> list[dict[str, Any]]:
    return retrieve_context(query, k=limit)


def docs_dir() -> Path:
    return DOCS_DIR

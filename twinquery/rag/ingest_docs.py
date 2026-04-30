"""Local markdown ingestion for TwinQuery RAG."""

from __future__ import annotations

import json
import re
import argparse
from pathlib import Path
from typing import Any

from twinquery.config import get_settings


DOCS_DIR = Path(__file__).parent / "docs"
INDEX_DIR = Path(__file__).parent / "index"
INDEX_PATH = INDEX_DIR / "metadata.json"
EMBEDDINGS_PATH = INDEX_DIR / "embeddings.json"
CHUNK_WORDS = 120
CHUNK_OVERLAP = 30


def list_documents(docs_dir: Path = DOCS_DIR) -> list[Path]:
    return sorted(docs_dir.glob("*.md"))


def _section_title(lines: list[str]) -> str:
    for line in lines:
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return "Untitled"


def load_markdown_sections(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^##\s+)", text, flags=re.MULTILINE)
    sections: list[dict[str, str]] = []
    for block in blocks:
        clean = block.strip()
        if not clean:
            continue
        lines = clean.splitlines()
        sections.append({"title": _section_title(lines), "text": clean})
    return sections


def chunk_text(text: str, chunk_words: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    if len(words) <= chunk_words:
        return [text.strip()]

    chunks: list[str] = []
    start = 0
    step = max(1, chunk_words - overlap)
    while start < len(words):
        chunk = " ".join(words[start : start + chunk_words]).strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def build_chunks(
    docs_dir: Path = DOCS_DIR,
    chunk_size: int = CHUNK_WORDS,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for path in list_documents(docs_dir):
        for section in load_markdown_sections(path):
            for chunk in chunk_text(section["text"], chunk_words=chunk_size, overlap=chunk_overlap):
                chunk_id = f"{path.stem}-{len(chunks):04d}"
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "source": path.name,
                        "section": section["title"],
                        "text": chunk,
                    }
                )
    return chunks


def embed_texts(texts: list[str], embedding_model: str | None = None) -> list[list[float]]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required to build the RAG index. "
            "Install dependencies with `pip install -r requirements.txt`."
        ) from exc

    model = SentenceTransformer(embedding_model or get_settings().embedding_model)
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    return [[float(value) for value in vector] for vector in vectors]


def ingest(
    docs_dir: Path = DOCS_DIR,
    index_dir: Path = INDEX_DIR,
    embedding_model: str | None = None,
    chunk_size: int = CHUNK_WORDS,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> dict[str, Any]:
    chunks = build_chunks(docs_dir=docs_dir, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    embeddings = embed_texts([chunk["text"] for chunk in chunks], embedding_model=embedding_model)
    index_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = index_dir / "metadata.json"
    embeddings_path = index_dir / "embeddings.json"
    metadata_path.write_text(json.dumps(chunks, indent=2), encoding="utf-8")
    embeddings_path.write_text(json.dumps(embeddings), encoding="utf-8")
    return {
        "metadata_path": str(metadata_path),
        "embeddings_path": str(embeddings_path),
        "chunk_count": len(chunks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local TwinQuery markdown RAG index.")
    parser.add_argument("--docs-dir", type=Path, default=DOCS_DIR)
    parser.add_argument("--index-dir", type=Path, default=INDEX_DIR)
    parser.add_argument("--embedding-model", default=get_settings().embedding_model)
    parser.add_argument("--chunk-size", type=int, default=CHUNK_WORDS)
    parser.add_argument("--chunk-overlap", type=int, default=CHUNK_OVERLAP)
    args = parser.parse_args()

    result = ingest(
        docs_dir=args.docs_dir,
        index_dir=args.index_dir,
        embedding_model=args.embedding_model,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

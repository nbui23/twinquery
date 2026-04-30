# TwinQuery

Local AI copilot for building-stock analytics and retrofit triage. Asks plain-English questions against a PostGIS building database and optional local retrofit guidance docs, then returns SQL results, map polygons, and grounded answers with no cloud APIs required.

## Stack

| Layer | Tech |
|-------|------|
| API | FastAPI |
| UI | Streamlit + PyDeck |
| Database | PostgreSQL / PostGIS (Docker) |
| Agent | LangGraph |
| LLM | Ollama (local) |
| Embeddings | sentence-transformers (local) |

## Quick Start

```bash
make setup   # create venv, install deps, start DB, copy .env
make seed    # populate synthetic building data
make dev     # API in background (:8000) + UI in foreground (:8501)
```

Optional — local LLM (needed for SQL generation and synthesis):
```bash
# Terminal A — keep open
make ollama

# Terminal B — run once after ollama is up
make pull-model
```

Optional — RAG index over local guidance docs:
```bash
make ingest
```

Run `make help` for all targets.

## Query Modes

| Mode | What it does |
|------|-------------|
| **Hybrid Digital Twin Query** | PostGIS building results + RAG retrofit guidance |
| **Map query** | Building polygons on map (SQL → PostGIS) |
| **Document RAG** | Guidance docs only |
| **Text-to-SQL only** | SQL + tabular rows |
| **Agentic answer** | LangGraph planner routes across all sources |

Example queries:
- *Show me the buildings with the highest energy intensity and explain the recommended HVAC retrofits based on local guidance.*
    - Use with Hybrid
- *Which buildings have the highest energy intensity?*
- *Show high-energy buildings and explain retrofit options*
- *What retrofit measures apply to older buildings?*
- *Show schools built before 1980 with high retrofit priority*

## API

```bash
curl -X POST http://localhost:8000/query/hybrid \
  -H "Content-Type: application/json" \
  -d '{"question":"Which buildings should be retrofitted and why?"}'
```

Routes: `/query/hybrid`, `/query/map`, `/query/rag`, `/query/sql`, `/query/sql/stream`, `/query/agent`

## Tests

```bash
pytest
```

## Data

Synthetic Ottawa/Gatineau-area building stock (100 records). Energy, retrofit, and height attributes are demo estimates. Real Ottawa footprint geometry can be ingested via:

```bash
python -m twinquery.db.ingest_ottawa_footprints --limit 500 --reset
```

## License

MIT

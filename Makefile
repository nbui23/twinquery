.PHONY: setup seed ingest api ui ollama dev test lint help

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
STREAMLIT := $(VENV)/bin/streamlit
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

# ── Setup ─────────────────────────────────────────────────────────────────────

setup: $(VENV)/bin/activate requirements.txt
	$(PIP) install -r requirements.txt
	@[ -f .env ] || cp .env.example .env && echo "Created .env from .env.example"
	docker compose up -d db
	@echo "Setup complete. Run 'make seed' to populate the database."

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

seed:
	$(PYTHON) -m twinquery.db.seed_buildings

ingest:
	$(PYTHON) -m twinquery.rag.ingest_docs

# ── Services ──────────────────────────────────────────────────────────────────

api:
	$(UVICORN) api.main:app --reload

ui:
	$(STREAMLIT) run app/streamlit_app.py

ollama:
	ollama serve

pull-model:
	ollama pull qwen2.5:7b

# ── Dev (all at once) ─────────────────────────────────────────────────────────

dev:
	@echo "Starting API (background) and UI (foreground). Press Ctrl+C to stop UI."
	@echo "API logs → /tmp/twinquery-api.log"
	$(UVICORN) api.main:app --reload > /tmp/twinquery-api.log 2>&1 & echo "API PID: $$!"
	$(STREAMLIT) run app/streamlit_app.py

stop:
	@pkill -f "uvicorn api.main:app" && echo "API stopped" || echo "API not running"
	@pkill -f "streamlit run app/streamlit_app.py" && echo "UI stopped" || echo "UI not running"

# ── Quality ───────────────────────────────────────────────────────────────────

test:
	$(PYTEST) -q

lint:
	$(RUFF) check .

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  make setup       Create venv, install deps, start DB, copy .env"
	@echo "  make seed        Seed synthetic building data"
	@echo "  make ingest      Build local RAG index from docs"
	@echo "  make ollama      Start Ollama LLM server (blocking)"
	@echo "  make pull-model  Pull qwen2.5:7b model (run after ollama)"
	@echo "  make api         Start FastAPI server on :8000"
	@echo "  make ui          Start Streamlit UI on :8501"
	@echo "  make dev         Start API in background + UI in foreground"
	@echo "  make stop        Kill API and UI processes"
	@echo "  make test        Run pytest"
	@echo "  make lint        Run ruff"
	@echo ""

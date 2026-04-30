"""Local structured logging for TwinQuery."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from twinquery.config import get_settings
from twinquery.observability.traces import AgentTrace


LOG_DIR = Path("logs")
TRACE_LOG_PATH = LOG_DIR / "twinquery_traces.jsonl"


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def write_trace(trace: AgentTrace, path: Path = TRACE_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")


def read_traces(limit: int = 20, path: Path = TRACE_LOG_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = [json.loads(line) for line in lines[-limit:]]
    return list(reversed(records))


def get_trace(trace_id: str, path: Path = TRACE_LOG_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("trace_id") == trace_id:
            return record
    return None

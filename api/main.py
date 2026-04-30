"""FastAPI application factory for TwinQuery."""

from __future__ import annotations

from fastapi import FastAPI

from api.routes.health import router as health_router
from api.routes.query import router as query_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="TwinQuery API",
        version="0.1.0",
        description="Local API for building-stock and retrofit analytics.",
    )
    app.include_router(health_router)
    app.include_router(query_router, prefix="/query", tags=["query"])
    return app


app = create_app()


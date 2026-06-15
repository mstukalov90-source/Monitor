"""MONITOR M2M HTTP API."""

from __future__ import annotations

from fastapi import FastAPI

from collector.api.routes.photos import router as photos_router

app = FastAPI(
    title="MONITOR M2M API",
    version="1.0.0",
    description="Machine-to-machine API for ingesting genplan photo metadata.",
)

app.include_router(photos_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

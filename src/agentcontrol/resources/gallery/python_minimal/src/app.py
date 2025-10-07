from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Python Minimal Gallery Sample")


@app.get("/healthz", summary="Health check")
def healthcheck() -> dict[str, str]:
    """Return a simple heartbeat response."""
    return {"status": "ok"}

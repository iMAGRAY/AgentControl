from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Monorepo Backend")


@app.get("/api/info", summary="Describe the monorepo sample")
def get_info() -> dict[str, str]:
    return {"message": "Hello from the monorepo backend"}

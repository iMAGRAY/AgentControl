"""Backend service placeholder."""

def handler(event: dict | None = None) -> dict:
    return {"message": "backend-ok", "input": event or {}}

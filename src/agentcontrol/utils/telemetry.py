"""Lightweight telemetry events (opt-in)."""

from __future__ import annotations

import json
import os
import time
from importlib import resources
from typing import Any, Iterable, Iterator

from agentcontrol.settings import RuntimeSettings

LEVELS = {"info", "warn", "error"}

_DISABLE_VALUES = {"0", "false", "no", "off"}

try:  # pragma: no cover - dependency is expected but guard defensively
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None  # type: ignore[assignment]

_TELEMETRY_VALIDATOR = None


def telemetry_enabled() -> bool:
    value = os.getenv("AGENTCONTROL_TELEMETRY", "1").lower()
    return value not in _DISABLE_VALUES


def record_event(settings: RuntimeSettings, event: str, payload: dict[str, Any] | None = None, **extra: Any) -> None:
    record_structured_event(settings, event, payload=payload, **extra)


def record_structured_event(
    settings: RuntimeSettings,
    event: str,
    *,
    payload: dict[str, Any] | None = None,
    level: str = "info",
    status: str | None = None,
    component: str | None = None,
    correlation_id: str | None = None,
    duration_ms: float | None = None,
) -> None:
    if not telemetry_enabled():
        return
    record: dict[str, Any] = {
        "ts": time.time(),
        "event": event,
        "payload": payload or {},
        "level": level,
    }
    if status:
        record["status"] = status
    if component:
        record["component"] = component
    if correlation_id:
        record["correlationId"] = correlation_id
    if duration_ms is not None:
        record["durationMs"] = duration_ms
    _validate_record(record)
    _validate_against_schema(record)
    log_path = settings.log_dir / "telemetry.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def iter_events(settings: RuntimeSettings) -> Iterator[dict[str, Any]]:
    log_path = settings.log_dir / "telemetry.jsonl"
    if not log_path.exists():
        return iter(())
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def summarize(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    by_event: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for evt in events:
        name = evt.get("event", "unknown")
        by_event[name] = by_event.get(name, 0) + 1
        status = evt.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        total += 1
    return {"total": total, "by_event": by_event, "by_status": by_status}


def clear(settings: RuntimeSettings) -> None:
    log_path = settings.log_dir / "telemetry.jsonl"
    if log_path.exists():
        log_path.unlink()


def _validate_record(record: dict[str, Any]) -> None:
    if not isinstance(record.get("event"), str) or not record["event"].strip():
        raise ValueError("Telemetry event must have non-empty string 'event'")
    if not isinstance(record.get("payload"), dict):
        raise ValueError("Telemetry payload must be a dict")
    level = record.get("level", "info")
    if level not in LEVELS:
        raise ValueError(f"Telemetry level '{level}' is not supported")
    if "durationMs" in record and record["durationMs"] is not None:
        if not isinstance(record["durationMs"], (int, float)) or record["durationMs"] < 0:
            raise ValueError("Telemetry durationMs must be a non-negative number")
    record["ts"] = float(record.get("ts", time.time()))


def _telemetry_validator():  # pragma: no cover - trivial cache
    global _TELEMETRY_VALIDATOR
    if _TELEMETRY_VALIDATOR is not None or jsonschema is None:
        return _TELEMETRY_VALIDATOR
    schema_resource = resources.files("agentcontrol.resources") / "telemetry.schema.json"
    with resources.as_file(schema_resource) as schema_path:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    _TELEMETRY_VALIDATOR = jsonschema.Draft202012Validator(schema)  # type: ignore[attr-defined]
    return _TELEMETRY_VALIDATOR


def _validate_against_schema(record: dict[str, Any]) -> None:
    validator = _telemetry_validator()
    if validator is None:
        return
    validator.validate(record)

"""Lightweight telemetry events (opt-in)."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Iterable, Iterator

from agentcontrol.settings import RuntimeSettings

_DISABLE_VALUES = {"0", "false", "no", "off"}


def telemetry_enabled() -> bool:
    value = os.getenv("AGENTCONTROL_TELEMETRY", "1").lower()
    return value not in _DISABLE_VALUES


def record_event(settings: RuntimeSettings, event: str, payload: dict[str, Any] | None = None) -> None:
    if not telemetry_enabled():
        return
    record = {
        "ts": time.time(),
        "event": event,
        "payload": payload or {},
    }
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
    for evt in events:
        name = evt.get("event", "unknown")
        by_event[name] = by_event.get(name, 0) + 1
        total += 1
    return {"total": total, "by_event": by_event}


def clear(settings: RuntimeSettings) -> None:
    log_path = settings.log_dir / "telemetry.jsonl"
    if log_path.exists():
        log_path.unlink()

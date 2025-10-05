"""Runtime helper utilities for autonomous agents."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, Iterator

from agentcontrol.utils.telemetry import iter_events


def stream_events(log_dir: Path, *, follow: bool = False, poll_interval: float = 0.5) -> Iterator[dict[str, object]]:
    """Yield telemetry events from the runtime log, optionally following new entries."""

    settings = type("_S", (), {"log_dir": log_dir})  # lightweight proxy
    for event in iter_events(settings):
        yield event
    if not follow:
        return

    log_path = log_dir / "telemetry.jsonl"
    position = log_path.stat().st_size if log_path.exists() else 0
    while True:
        if not log_path.exists():
            time.sleep(poll_interval)
            continue
        with log_path.open("r", encoding="utf-8") as fh:
            fh.seek(position)
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
            position = fh.tell()
        time.sleep(poll_interval)


def load_manifest(project_root: Path) -> dict[str, object]:
    """Load `.agentcontrol/runtime.json` for a project."""

    path = project_root / ".agentcontrol" / "runtime.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))

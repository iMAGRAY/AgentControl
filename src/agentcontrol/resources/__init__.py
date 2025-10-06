"""Packaged resources for AgentControl."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Dict, Iterable

import yaml

__all__ = ["load_profile_payloads"]


@lru_cache(maxsize=1)
def load_profile_payloads() -> Iterable[Dict[str, object]]:
    """Return default bootstrap profile payloads shipped with the package."""

    package = __name__ + ".profiles"
    profiles_dir = resources.files(package)
    payloads: list[dict[str, object]] = []
    for entry in profiles_dir.iterdir():
        if not entry.name.endswith(".yaml"):
            continue
        raw = entry.read_text("utf-8")
        payload = yaml.safe_load(raw) or {}
        payload["__source__"] = entry.name
        payloads.append(payload)
    payloads.sort(key=lambda item: str(item.get("id")))
    return tuple(payloads)

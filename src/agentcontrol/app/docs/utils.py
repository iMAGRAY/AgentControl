"""Shared helper utilities for documentation tooling."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO8601 without microseconds."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_mtime(path: Path) -> str:
    """Return file modification time in ISO8601 (UTC)."""

    stat = path.stat()
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_title(text: str, *, fallback: str) -> str:
    """Extract the first heading or return fallback."""

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        return stripped[:120]
    return fallback


def extract_summary(text: str, *, limit: int = 240) -> str:
    """Extract the leading paragraph up to limit characters."""

    lines = text.splitlines()
    summary_lines: List[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if summary_lines:
                break
            continue
        if stripped.startswith("#"):
            capture = True
            continue
        if not capture and not summary_lines:
            capture = True
        if capture:
            summary_lines.append(stripped)
            if len(" ".join(summary_lines)) >= limit:
                break
    summary = " ".join(summary_lines)[:limit]
    return summary or "Нет краткого описания."


def truncate_summary(text: str, *, limit: int = 240) -> str:
    """Trim summary to limit characters, preserving sentence ending."""

    trimmed = text.strip()
    if len(trimmed) <= limit:
        return trimmed
    return trimmed[: limit - 3].rstrip() + "..."


def safe_relpath(path: Path, base: Path) -> str:
    """Return POSIX relative path when possible, otherwise absolute."""

    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)

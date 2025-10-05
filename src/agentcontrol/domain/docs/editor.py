"""Managed region editing utilities with atomic guarantees."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import re

from .events import ManagedRegionChange
from .value_objects import InsertionPolicy

START_TEMPLATE = "<!-- agentcontrol:start:{marker} -->"
END_TEMPLATE = "<!-- agentcontrol:end:{marker} -->"


class ManagedRegionCorruptionError(RuntimeError):
    """Raised when managed markers are unbalanced or duplicated."""

    def __init__(self, marker: str, reason: str) -> None:
        self.marker = marker
        self.reason = reason
        super().__init__(f"Managed region '{marker}' is corrupted: {reason}")


@dataclass(frozen=True)
class ManagedRegionApplyResult:
    changed: bool
    changes: List[ManagedRegionChange]


@dataclass(frozen=True)
class RegionOperation:
    content: Optional[str]
    insertion: Optional[InsertionPolicy] = None


class ManagedRegionEngine:
    """Applies updates to managed doc regions atomically."""

    def apply(
        self,
        file_path: Path,
        operations: Dict[str, Union[Optional[str], Tuple[Optional[str], Optional[InsertionPolicy]], "RegionOperation"]],
    ) -> ManagedRegionApplyResult:
        ensure_directory(file_path)
        text = file_path.read_text(encoding="utf-8", errors="surrogatepass") if file_path.exists() else ""
        changed = False
        changes: List[ManagedRegionChange] = []

        for marker, payload in operations.items():
            op = self._coerce_operation(payload)
            text, update = self._apply_single(file_path, text, marker, op)
            if update.changed:
                changed = True
            changes.append(update)

        if changed:
            _atomic_write(file_path, _ensure_trailing_newline(text))
        return ManagedRegionApplyResult(changed=changed, changes=changes)

    def read(self, file_path: Path, marker: str) -> Optional[str]:
        if not file_path.exists():
            return None
        text = file_path.read_text(encoding="utf-8", errors="surrogatepass")
        match = self._locate(text, marker)
        if match is None:
            return None
        return match.group(1).strip("\n")

    def _apply_single(
        self,
        file_path: Path,
        text: str,
        marker: str,
        operation: RegionOperation,
    ) -> tuple[str, ManagedRegionChange]:
        match = self._locate(text, marker)
        start = START_TEMPLATE.format(marker=marker)
        end = END_TEMPLATE.format(marker=marker)

        payload = operation.content
        if payload is None:
            if match is None:
                return text, ManagedRegionChange(section="unknown", marker=marker, changed=False, path=file_path.as_posix())
            new_text = text[: match.start()] + text[match.end():]
            return new_text, ManagedRegionChange(section="unknown", marker=marker, changed=True, path=file_path.as_posix())

        normalized = payload.strip("\n")
        replacement = f"{start}\n{normalized}\n{end}"

        if match is None:
            new_text = self._insert_with_policy(text, replacement, operation.insertion)
            return new_text, ManagedRegionChange(section="unknown", marker=marker, changed=True, path=file_path.as_posix())

        current = match.group(1).strip("\n")
        if current == normalized:
            return text, ManagedRegionChange(section="unknown", marker=marker, changed=False, path=file_path.as_posix())

        new_text = text[: match.start()] + replacement + text[match.end():]
        return new_text, ManagedRegionChange(section="unknown", marker=marker, changed=True, path=file_path.as_posix())

    @staticmethod
    def _coerce_operation(
        payload: Union[Optional[str], Tuple[Optional[str], Optional[InsertionPolicy]], "RegionOperation"],
    ) -> RegionOperation:
        if isinstance(payload, RegionOperation):
            return payload
        if isinstance(payload, tuple):
            content, insertion = payload
            return RegionOperation(content=content, insertion=insertion)
        return RegionOperation(content=payload, insertion=None)

    def _locate(self, text: str, marker: str) -> Optional[re.Match[str]]:
        start = START_TEMPLATE.format(marker=marker)
        end = END_TEMPLATE.format(marker=marker)
        start_count = text.count(start)
        end_count = text.count(end)
        if start_count != end_count:
            raise ManagedRegionCorruptionError(marker, "unbalanced start/end markers")
        if start_count > 1:
            raise ManagedRegionCorruptionError(marker, "duplicate marker blocks found")
        if start_count == 0:
            return None
        pattern = re.compile(rf"{re.escape(start)}(.*?){re.escape(end)}", re.DOTALL)
        match = pattern.search(text)
        if match is None:
            raise ManagedRegionCorruptionError(marker, "marker delimiters missing or malformed")
        return match

    def _insert_with_policy(
        self,
        text: str,
        replacement: str,
        insertion: Optional[InsertionPolicy],
    ) -> str:
        if insertion is None:
            new_text = text
            if not new_text.endswith("\n") and new_text:
                new_text += "\n"
            return new_text + replacement + "\n"

        if insertion.kind == "after_heading":
            pattern = re.compile(rf"^{re.escape(insertion.value.strip())}\s*$", re.MULTILINE)
            match = pattern.search(text)
            if match:
                insert_pos = match.end()
                prefix = ""
                if insert_pos < len(text) and text[insert_pos] != "\n":
                    prefix = "\n"
                suffix = "" if replacement.endswith("\n") else "\n"
                return text[:insert_pos] + prefix + replacement + suffix + text[insert_pos:]

        if insertion.kind == "before_marker":
            target_marker = START_TEMPLATE.format(marker=insertion.value)
            idx = text.find(target_marker)
            if idx != -1:
                prefix = "" if idx == 0 or text[idx - 1] == "\n" else "\n"
                suffix = "" if replacement.endswith("\n") else "\n"
                return text[:idx] + prefix + replacement + suffix + text[idx:]

        # Fallback to append
        new_text = text
        if not new_text.endswith("\n") and new_text:
            new_text += "\n"
        return new_text + replacement + "\n"


def ensure_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, data: str) -> None:
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data.encode("utf-8", errors="surrogatepass"))
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _ensure_trailing_newline(text: str) -> str:
    return text if not text or text.endswith("\n") else text + "\n"


ENGINE = ManagedRegionEngine()

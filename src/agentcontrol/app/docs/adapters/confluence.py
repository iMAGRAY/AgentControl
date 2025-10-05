"""Confluence REST adapter (generates payloads for external sync)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from agentcontrol.app.docs.adapters import AdapterAction, ExternalAdapter
from agentcontrol.domain.docs.value_objects import SectionConfig

STATE_DIR = Path(".agentcontrol/state/docs/confluence")


class ConfluenceAdapter(ExternalAdapter):
    """Generates JSON payloads for Confluence page updates."""

    def diff(self, project_root: Path, spec: SectionConfig, expected: Mapping[str, object] | None) -> List[Dict[str, object]]:
        payload_path = self._payload_path(project_root, spec)
        status = "missing"
        if payload_path.exists():
            status = "pending"
        return [
            {
                "name": spec.options.get("title", spec.marker or spec.mode),
                "status": status,
                "path": str(payload_path),
            }
        ]

    def apply(
        self,
        project_root: Path,
        spec: SectionConfig,
        expected: Mapping[str, object] | None,
        backup_root: Path,
    ) -> List[AdapterAction]:
        payload_path = self._payload_path(project_root, spec)
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._build_payload(spec, expected)
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return [AdapterAction(spec.options.get("title", spec.mode), payload_path, "generated")]

    def capture(self, project_root: Path, spec: SectionConfig) -> Dict[str, object]:
        payload_path = self._payload_path(project_root, spec)
        if payload_path.exists():
            data = json.loads(payload_path.read_text(encoding="utf-8"))
        else:
            data = {}
        return {"path": str(payload_path), "payload": data}

    def rollback(self, project_root: Path, spec: SectionConfig, backup_root: Path) -> List[AdapterAction]:
        payload_path = self._payload_path(project_root, spec)
        backup_path = (backup_root / payload_path.relative_to(project_root)).resolve()
        if not backup_path.exists():
            return []
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
        return [AdapterAction(spec.options.get("title", spec.mode), payload_path, "restored")]

    def _payload_path(self, project_root: Path, spec: SectionConfig) -> Path:
        options = spec.options or {}
        if spec.target:
            return (project_root / spec.target).resolve()
        slug = options.get("slug") or options.get("title", "architecture-overview").lower().replace(" ", "-")
        return (project_root / STATE_DIR / f"{slug}.json").resolve()

    def _build_payload(self, spec: SectionConfig, expected: Mapping[str, object] | None) -> Dict[str, object]:
        options = spec.options or {}
        content = expected.get("architecture_overview") if isinstance(expected, Mapping) else None
        return {
            "space": options.get("space"),
            "ancestorId": options.get("ancestor_id"),
            "title": options.get("title", "Architecture Overview"),
            "slug": options.get("slug"),
            "payload": {
                "content": content,
            },
        }

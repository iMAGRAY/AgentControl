"""Docusaurus sidebar adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from agentcontrol.app.docs.adapters import AdapterAction, ExternalAdapter
from agentcontrol.domain.docs.value_objects import SectionConfig


class DocusaurusSidebarAdapter(ExternalAdapter):
    """Maintains Docusaurus sidebar JSON entries."""

    def diff(self, project_root: Path, spec: SectionConfig, expected: Mapping[str, object] | None) -> List[Dict[str, object]]:
        sidebar, path = self._load_sidebar(project_root, spec)
        status = "missing"
        if sidebar is not None and self._entry_exists(sidebar, spec):
            status = "match"
        return [
            {
                "name": spec.options.get("category", spec.marker or spec.mode),
                "status": status,
                "path": str(path) if path else None,
            }
        ]

    def apply(
        self,
        project_root: Path,
        spec: SectionConfig,
        expected: Mapping[str, object] | None,
        backup_root: Path,
    ) -> List[AdapterAction]:
        sidebar, path = self._load_sidebar(project_root, spec)
        if path is None:
            raise FileNotFoundError("Docusaurus sidebar file not found")
        data = sidebar or {}
        original = json.dumps(data, sort_keys=True)
        self._ensure_entry(data, spec)
        updated = json.dumps(data, sort_keys=True)
        if updated == original:
            return [AdapterAction(spec.options.get("category", spec.mode), path, "noop")]
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_path = backup_root / path.relative_to(project_root)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return [AdapterAction(spec.options.get("category", spec.mode), path, "updated")]

    def capture(self, project_root: Path, spec: SectionConfig) -> Dict[str, object]:
        sidebar, path = self._load_sidebar(project_root, spec)
        return {
            "path": str(path) if path else None,
            "sidebar": sidebar,
        }

    def rollback(self, project_root: Path, spec: SectionConfig, backup_root: Path) -> List[AdapterAction]:
        path = self._target_path(project_root, spec)
        backup_path = (backup_root / path.relative_to(project_root)).resolve()
        if not backup_path.exists():
            return []
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
        return [AdapterAction(spec.options.get("category", spec.mode), path, "restored")]

    # Helpers
    def _target_path(self, project_root: Path, spec: SectionConfig) -> Path:
        if not spec.target:
            raise ValueError("Docusaurus adapter requires 'target'")
        return (project_root / spec.target).resolve()

    def _load_sidebar(self, project_root: Path, spec: SectionConfig) -> tuple[Optional[Dict[str, object]], Optional[Path]]:
        path = self._target_path(project_root, spec)
        if not path.exists():
            return None, path
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data, path

    def _ensure_entry(self, sidebar: Dict[str, object], spec: SectionConfig) -> None:
        options = spec.options or {}
        sidebar_key = options.get("sidebar", "docs")
        doc_id = options.get("doc_id", "architecture-overview")
        category = options.get("category", "Architecture")
        entries = sidebar.setdefault(sidebar_key, [])
        if not isinstance(entries, list):
            raise ValueError("Sidebar entries must be a list")
        target_entry = {"type": "doc", "id": doc_id}
        category_entry = next((item for item in entries if isinstance(item, dict) and item.get("label") == category), None)
        if category_entry is None:
            category_entry = {"type": "category", "label": category, "items": []}
            entries.append(category_entry)
        items = category_entry.setdefault("items", [])
        if not isinstance(items, list):
            raise ValueError("Category items must be a list")
        if any(item == target_entry for item in items):
            return
        items.append(target_entry)

    def _entry_exists(self, sidebar: Dict[str, object], spec: SectionConfig) -> bool:
        options = spec.options or {}
        sidebar_key = options.get("sidebar", "docs")
        doc_id = options.get("doc_id", "architecture-overview")
        category = options.get("category", "Architecture")
        entries = sidebar.get(sidebar_key, [])
        if not isinstance(entries, list):
            return False
        for item in entries:
            if isinstance(item, dict) and item.get("label") == category:
                items = item.get("items", [])
                if isinstance(items, list) and any(entry == {"type": "doc", "id": doc_id} for entry in items):
                    return True
        return False

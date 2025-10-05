"""MkDocs navigation adapter."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import yaml

from agentcontrol.app.docs.adapters import AdapterAction, ExternalAdapter
from agentcontrol.domain.docs.value_objects import SectionConfig


class MkDocsNavAdapter(ExternalAdapter):
    """Ensures MkDocs nav contains architecture entries."""

    def diff(self, project_root: Path, spec: SectionConfig, expected: Mapping[str, object] | None) -> List[Dict[str, object]]:
        nav, path = self._load_nav(project_root, spec)
        entry = self._normalise_entry(spec)
        status = "missing"
        if nav is not None and self._entry_exists(nav, entry):
            status = "match"
        return [
            {
                "name": spec.options.get("name", spec.marker or spec.mode),
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
        nav, path = self._load_nav(project_root, spec)
        if path is None:
            raise FileNotFoundError("MkDocs configuration file not found")
        nav_root = nav if isinstance(nav, dict) else {}
        original = copy.deepcopy(nav_root)
        self._ensure_nav(nav_root, spec)
        if nav_root == original:
            return [AdapterAction(spec.options.get("name", spec.mode), path, "noop")]
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_path = backup_root / path.relative_to(project_root)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(yaml.safe_dump(nav_root, sort_keys=False), encoding="utf-8")
        return [AdapterAction(spec.options.get("name", spec.mode), path, "updated")]

    def capture(self, project_root: Path, spec: SectionConfig) -> Dict[str, object]:
        nav, path = self._load_nav(project_root, spec)
        return {
            "path": str(path) if path else None,
            "nav": nav,
        }

    def rollback(self, project_root: Path, spec: SectionConfig, backup_root: Path) -> List[AdapterAction]:
        path = self._target_path(project_root, spec)
        backup_path = (backup_root / path.relative_to(project_root)).resolve()
        if not backup_path.exists():
            return []
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
        return [AdapterAction(spec.options.get("name", spec.mode), path, "restored")]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _target_path(self, project_root: Path, spec: SectionConfig) -> Path:
        if not spec.target:
            raise ValueError("MkDocs adapter requires 'target' to be defined")
        return (project_root / spec.target).resolve()

    def _load_nav(self, project_root: Path, spec: SectionConfig) -> tuple[Optional[Mapping[str, object]], Optional[Path]]:
        path = self._target_path(project_root, spec)
        if not path.exists():
            return None, path
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data, path

    def _ensure_nav(self, nav_root: Mapping[str, object], spec: SectionConfig) -> None:
        entry = self._normalise_entry(spec)
        insert_after = spec.options.get("insert_after") if spec.options else None
        nav_list = nav_root.setdefault("nav", [])
        if not isinstance(nav_list, list):
            raise ValueError("MkDocs nav must be a list")
        if self._entry_exists(nav_list, entry):
            return
        insert_index = self._find_insert_index(nav_list, insert_after) if insert_after else len(nav_list)
        nav_list.insert(insert_index, entry)

    def _entry_exists(self, nav_list: List[object], entry: object) -> bool:
        for item in nav_list:
            if item == entry:
                return True
        return False

    def _find_insert_index(self, nav_list: List[object], insert_after: str) -> int:
        for idx, item in enumerate(nav_list):
            if isinstance(item, dict) and insert_after in item:
                return idx + 1
            if isinstance(item, str) and item == insert_after:
                return idx + 1
        return len(nav_list)

    def _normalise_entry(self, spec: SectionConfig) -> object:
        options = spec.options or {}
        entry = options.get("entry")
        if entry is None:
            title = options.get("title", "Architecture")
            doc_path = options.get("doc", spec.target)
            entry = {title: doc_path}
        return entry

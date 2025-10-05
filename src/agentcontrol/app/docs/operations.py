"""High-level documentation bridge operations for CLI commands."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from agentcontrol.app.architecture import generate_doc_sections_for
from agentcontrol.app.docs.adapters import AdapterAction
from agentcontrol.app.docs.adapters.confluence import ConfluenceAdapter
from agentcontrol.app.docs.adapters.docusaurus import DocusaurusSidebarAdapter
from agentcontrol.app.docs.adapters.mkdocs import MkDocsNavAdapter
from agentcontrol.domain.docs.aggregate import DocsBridgeAggregate, DocsBridgeContext
from agentcontrol.domain.docs.constants import remediation_for
from agentcontrol.domain.docs.editor import ENGINE, ManagedRegionCorruptionError, RegionOperation
from agentcontrol.domain.docs.value_objects import DocsBridgeConfig, DocsBridgeConfigError, InsertionPolicy, SectionConfig
from agentcontrol.utils.docs_bridge import (
    DEFAULT_CONFIG_RELATIVE,
    load_docs_bridge_config,
    update_managed_region,
    write_file,
)

BACKUP_ROOT = Path(".agentcontrol/state/docs/history")
STATE_FILE = Path(".agentcontrol/state/docs/state.json")

ADAPTERS = {
    "mkdocs": MkDocsNavAdapter(),
    "mkdocs_nav": MkDocsNavAdapter(),
    "docusaurus": DocusaurusSidebarAdapter(),
    "docusaurus_sidebar": DocusaurusSidebarAdapter(),
    "confluence": ConfluenceAdapter(),
}


@dataclass
class DiffEntry:
    name: str
    status: str
    detail: Dict[str, object]


class DocsCommandService:
    """Implements doc bridge CLI operations (list, diff, repair, adopt, rollback)."""

    def __init__(self) -> None:
        self._stat_cache: Dict[Path, tuple[int, bool]] = {}
        self._content_cache: Dict[Path, tuple[int, str]] = {}

    def list_sections(self, project_root: Path) -> Dict[str, object]:
        config, config_path = load_docs_bridge_config(project_root)
        aggregate = self._aggregate(project_root, config, config_path)
        payload = aggregate.inspect(include_status=True)
        payload["generatedAt"] = _now_iso()
        return payload

    def diff_sections(self, project_root: Path, *, sections: Optional[Iterable[str]] = None) -> Dict[str, object]:
        config, config_path = load_docs_bridge_config(project_root)
        aggregate = self._aggregate(project_root, config, config_path)
        target_sections = set(sections) if sections else None
        doc_sections = generate_doc_sections_for(project_root)
        expected_map = self._expected_section_map(doc_sections)
        diffs: List[DiffEntry] = []

        root_base = config.absolute_root(project_root)
        for name, spec in config.iter_sections():
            if target_sections and name not in target_sections:
                continue
            section_diff = self._diff_for_section(project_root, root_base, aggregate, spec, name, expected_map)
            diffs.extend(section_diff)

        return {
            "generatedAt": _now_iso(),
            "configPath": str((project_root / DEFAULT_CONFIG_RELATIVE).resolve()),
            "diff": [entry.detail | {"name": entry.name, "status": entry.status} for entry in diffs],
        }

    def repair_sections(
        self,
        project_root: Path,
        *,
        sections: Optional[Iterable[str]] = None,
        entries: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        config, config_path = load_docs_bridge_config(project_root)
        aggregate = self._aggregate(project_root, config, config_path)
        doc_sections = generate_doc_sections_for(project_root)
        expected_map = self._expected_section_map(doc_sections)
        root_base = config.absolute_root(project_root)
        selected_sections = set(sections) if sections else None
        selected_entries = set(entries) if entries else None

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_root = (project_root / BACKUP_ROOT / timestamp).resolve()
        actions: List[Dict[str, object]] = []

        for name, spec in config.iter_sections():
            if selected_sections and name not in selected_sections:
                continue
            action_records = self._repair_section(
                project_root,
                root_base,
                aggregate,
                spec,
                name,
                expected_map,
                backup_root,
                selected_entries,
            )
            actions.extend(action_records)

        self._write_state_snapshot(project_root, config, aggregate)

        return {
            "generatedAt": _now_iso(),
            "configPath": str(config_path),
            "backup": str(backup_root) if actions else None,
            "actions": actions,
        }

    def adopt_sections(
        self,
        project_root: Path,
        *,
        sections: Optional[Iterable[str]] = None,
        entries: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        config, config_path = load_docs_bridge_config(project_root)
        aggregate = self._aggregate(project_root, config, config_path)
        root_base = config.absolute_root(project_root)
        selected_sections = set(sections) if sections else None
        selected_entries = set(entries) if entries else None

        snapshot: Dict[str, object] = {"generatedAt": _now_iso(), "sections": {}}

        for name, spec in config.iter_sections():
            if selected_sections and name not in selected_sections:
                continue
            captured = self._capture_section_state(project_root, root_base, aggregate, spec, name, selected_entries)
            snapshot["sections"][name] = captured

        state_path = (project_root / STATE_FILE).resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"generatedAt": snapshot["generatedAt"], "configPath": str(config_path), "statePath": str(state_path)}

    def rollback_sections(
        self,
        project_root: Path,
        *,
        timestamp: str,
        sections: Optional[Iterable[str]] = None,
        entries: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        config, config_path = load_docs_bridge_config(project_root)
        aggregate = self._aggregate(project_root, config, config_path)
        root_base = config.absolute_root(project_root)
        selected_sections = set(sections) if sections else None
        selected_entries = set(entries) if entries else None

        backup_root = (project_root / BACKUP_ROOT / timestamp).resolve()
        if not backup_root.exists():
            raise FileNotFoundError(f"Backup timestamp {timestamp} not found under {backup_root.parent}")

        actions: List[Dict[str, object]] = []
        for name, spec in config.iter_sections():
            if selected_sections and name not in selected_sections:
                continue
            actions.extend(
                self._restore_section(project_root, root_base, aggregate, spec, name, backup_root, selected_entries)
            )

        self._write_state_snapshot(project_root, config, aggregate)
        return {
            "generatedAt": _now_iso(),
            "configPath": str(config_path),
            "backup": str(backup_root),
            "actions": actions,
        }

    def sync_sections(
        self,
        project_root: Path,
        *,
        mode: str = "repair",
        sections: Optional[Iterable[str]] = None,
        entries: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        if mode not in {"repair", "adopt"}:
            raise ValueError(f"Unsupported sync mode '{mode}'")

        sections_filter = set(sections) if sections else None
        entries_filter = set(entries) if entries else None

        diff_before = self.diff_sections(project_root, sections=sections)
        mismatches: List[Dict[str, object]] = []
        for entry in diff_before["diff"]:
            status = entry.get("status")
            if status == "match":
                continue
            name = str(entry.get("name", ""))
            section_name, _, entry_id = name.partition(":")
            if sections_filter and section_name not in sections_filter:
                continue
            if entries_filter and entry_id and entry_id not in entries_filter:
                continue
            mismatches.append(entry)

        target_sections = sorted({item.get("name", "").split(":", 1)[0] for item in mismatches if item.get("name")})

        step_payload: Optional[Dict[str, object]] = None
        if target_sections:
            if mode == "repair":
                step_payload = self.repair_sections(project_root, sections=target_sections)
            else:
                step_payload = self.adopt_sections(project_root, sections=target_sections)

        diff_after = self.diff_sections(project_root, sections=sections)
        remaining = [entry for entry in diff_after["diff"] if entry.get("status") != "match"]

        steps: List[Dict[str, object]] = [
            {"step": "diff-before", "diff": diff_before["diff"]},
        ]
        if target_sections:
            steps.append({"step": mode, "payload": step_payload})
        else:
            steps.append({"step": mode, "skipped": True})
        steps.append({"step": "diff-after", "diff": diff_after["diff"]})

        return {
            "generatedAt": _now_iso(),
            "mode": mode,
            "sections": target_sections,
            "steps": steps,
            "status": "ok" if not remaining else "warning",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        project_root: Path,
        config: DocsBridgeConfig,
        config_path: Path,
    ) -> DocsBridgeAggregate:
        context = DocsBridgeContext(
            project_root=project_root.resolve(),
            config=config,
            config_path=config_path.resolve(),
        )
        return DocsBridgeAggregate(context)

    def _expected_section_map(self, doc_sections) -> Dict[str, object]:
        return {
            "architecture_overview": doc_sections.architecture_overview,
            "adr_index": doc_sections.adr_index,
            "rfc_index": doc_sections.rfc_index,
            "adr_entry": doc_sections.adr_entries,
            "rfc_entry": doc_sections.rfc_entries,
        }

    def _path_exists(self, path: Path) -> bool:
        resolved = path.resolve()
        cached = self._stat_cache.get(resolved)
        try:
            stat = resolved.stat()
        except FileNotFoundError:
            self._stat_cache[resolved] = (0, False)
            return False
        stamp = stat.st_mtime_ns
        if cached and cached[0] == stamp:
            return cached[1]
        self._stat_cache[resolved] = (stamp, True)
        return True

    def _read_text(self, path: Path) -> str:
        resolved = path.resolve()
        stat = resolved.stat()
        cached = self._content_cache.get(resolved)
        if cached and cached[0] == stat.st_mtime_ns:
            return cached[1]
        content = resolved.read_text(encoding="utf-8")
        self._content_cache[resolved] = (stat.st_mtime_ns, content)
        return content

    def _external_adapter(self, spec: SectionConfig):
        adapter_name = (spec.adapter or "").lower()
        if adapter_name not in ADAPTERS:
            raise DocsBridgeConfigError(f"Unsupported external adapter '{spec.adapter}'", code="DOC_BRIDGE_INVALID_CONFIG")
        return ADAPTERS[adapter_name]

    def _diff_for_section(
        self,
        project_root: Path,
        root_base: Path,
        aggregate: DocsBridgeAggregate,
        spec: SectionConfig,
        name: str,
        expected_map: Dict[str, object],
    ) -> List[DiffEntry]:
        results: List[DiffEntry] = []
        if spec.mode == "managed":
            results.append(
                self._diff_managed_section(project_root, root_base, aggregate, spec, name, expected_map.get(name))
            )
        elif spec.mode == "file":
            results.extend(
                self._diff_file_section(project_root, root_base, spec, name, expected_map.get(name))
            )
        elif spec.mode == "external":
            adapter = self._external_adapter(spec)
            for item in adapter.diff(project_root, spec, expected_map):
                results.append(DiffEntry(item.get("name", name), item.get("status", "unknown"), item))
        return [entry for entry in results if entry is not None]

    def _diff_managed_section(
        self,
        project_root: Path,
        root_base: Path,
        aggregate: DocsBridgeAggregate,
        spec: SectionConfig,
        name: str,
        expected_content: Optional[str],
    ) -> DiffEntry:
        marker = spec.marker or f"agentcontrol-{name}"
        path = spec.resolve_path(root_base)
        detail = {
            "path": str(path),
            "marker": marker,
        }
        if not self._path_exists(path):
            return DiffEntry(name, "missing_file", detail)
        try:
            actual = aggregate.read_managed_region(path, marker)
        except ManagedRegionCorruptionError as exc:
            detail["error"] = str(exc)
            detail["code"] = "DOC_SECTION_MARKER_CORRUPTED"
            detail["remediation"] = remediation_for("DOC_SECTION_MARKER_CORRUPTED")
            return DiffEntry(name, "corrupted", detail)
        if actual is None:
            detail["remediation"] = remediation_for("DOC_SECTION_MISSING_MARKER")
            return DiffEntry(name, "missing_marker", detail)
        expected = (expected_content or "").strip("\n")
        actual_stripped = actual.strip("\n")
        if expected == actual_stripped:
            return DiffEntry(name, "match", detail)
        detail["expectedHash"] = _hash(expected)
        detail["actualHash"] = _hash(actual_stripped)
        detail["remediation"] = remediation_for("DOC_SECTION_MISSING_MARKER")
        return DiffEntry(name, "differs", detail)

    def _diff_file_section(
        self,
        project_root: Path,
        root_base: Path,
        spec: SectionConfig,
        name: str,
        expected_entries: Optional[Dict[str, str]],
    ) -> List[DiffEntry]:
        entries: List[DiffEntry] = []
        expected = expected_entries or {}
        if spec.target:
            path = spec.resolve_path(root_base)
            status = self._compare_file(path, expected.get("default", ""))
            entries.append(DiffEntry(name, status, {"path": str(path)}))
            return entries
        if spec.target_template:
            for entry_id, content in expected.items():
                path = spec.resolve_path(root_base, entry_id)
                status = self._compare_file(path, content)
                entries.append(
                    DiffEntry(
                        f"{name}:{entry_id}",
                        status,
                        {
                            "path": str(path),
                            "entry": entry_id,
                            "expectedHash": None if status == "missing_file" else _hash(content.strip("\n")),
                        },
                    )
                )
        return entries

    def _compare_file(self, path: Path, expected_content: str) -> str:
        if not self._path_exists(path):
            return "missing_file"
        actual = self._read_text(path).strip("\n")
        if actual == (expected_content or "").strip("\n"):
            return "match"
        return "differs"

    def _repair_section(
        self,
        project_root: Path,
        root_base: Path,
        aggregate: DocsBridgeAggregate,
        spec: SectionConfig,
        name: str,
        expected_map: Dict[str, object],
        backup_root: Path,
        selected_entries: Optional[set[str]],
    ) -> List[Dict[str, object]]:
        actions: List[Dict[str, object]] = []
        backup_root.mkdir(parents=True, exist_ok=True)
        if spec.mode == "managed":
            expected = str(expected_map.get(name, ""))
            marker = spec.marker or f"agentcontrol-{name}"
            target = spec.resolve_path(root_base)
            _backup_file(target, backup_root, project_root)
            changed = update_managed_region(target, marker, expected, insertion=spec.insertion)
            actions.append({
                "name": name,
                "path": str(target),
                "action": "updated" if changed else "noop",
            })
        elif spec.mode == "file":
            expected_entries = expected_map.get(name, {}) if isinstance(expected_map.get(name, {}), dict) else {}
            if spec.target:
                target = spec.resolve_path(root_base)
                _backup_file(target, backup_root, project_root)
                payload = expected_entries.get("default", "")
                write_file(target, payload if payload.endswith("\n") else payload + "\n")
                actions.append({"name": name, "path": str(target), "action": "updated"})
            elif spec.target_template:
                for entry_id, content in expected_entries.items():
                    if selected_entries and entry_id not in selected_entries:
                        continue
                    target = spec.resolve_path(root_base, entry_id)
                    _backup_file(target, backup_root, project_root)
                    payload = content if content.endswith("\n") else content + "\n"
                    write_file(target, payload)
                    actions.append({
                        "name": f"{name}:{entry_id}",
                        "path": str(target),
                        "action": "updated",
                    })
        elif spec.mode == "external":
            adapter = self._external_adapter(spec)
            adapter_actions = adapter.apply(project_root, spec, expected_map, backup_root)
            actions.extend(_adapter_actions_to_dict(adapter_actions))
        return actions

    def _restore_section(
        self,
        project_root: Path,
        root_base: Path,
        aggregate: DocsBridgeAggregate,
        spec: SectionConfig,
        name: str,
        backup_root: Path,
        selected_entries: Optional[set[str]],
    ) -> List[Dict[str, object]]:
        actions: List[Dict[str, object]] = []
        if spec.mode == "managed":
            target = spec.resolve_path(root_base)
            backup_file = _backup_target_for(project_root, backup_root, target)
            if not backup_file.exists():
                return actions
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(backup_file.read_text(encoding="utf-8"), encoding="utf-8")
            actions.append({"name": name, "path": str(target), "action": "restored"})
        elif spec.mode == "file":
            if spec.target:
                target = spec.resolve_path(root_base)
                backup_file = _backup_target_for(project_root, backup_root, target)
                if backup_file.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(backup_file.read_text(encoding="utf-8"), encoding="utf-8")
                    actions.append({"name": name, "path": str(target), "action": "restored"})
            elif spec.target_template:
                template = spec.target_template
                for entry_backup in backup_root.rglob("*"):
                    if not entry_backup.is_file():
                        continue
                    rel = entry_backup.relative_to(backup_root)
                    entry_id = _infer_entry_id(template, rel.as_posix())
                    if entry_id is None:
                        continue
                    if selected_entries and entry_id not in selected_entries:
                        continue
                    target = spec.resolve_path(root_base, entry_id)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(entry_backup.read_text(encoding="utf-8"), encoding="utf-8")
                    actions.append({
                        "name": f"{name}:{entry_id}",
                        "path": str(target),
                        "action": "restored",
                    })
        elif spec.mode == "external":
            adapter = self._external_adapter(spec)
            adapter_actions = adapter.rollback(project_root, spec, backup_root)
            actions.extend(_adapter_actions_to_dict(adapter_actions))
        return actions

    def _capture_section_state(
        self,
        project_root: Path,
        root_base: Path,
        aggregate: DocsBridgeAggregate,
        spec: SectionConfig,
        name: str,
        selected_entries: Optional[set[str]],
    ) -> Dict[str, object]:
        if spec.mode == "managed":
            marker = spec.marker or f"agentcontrol-{name}"
            path = spec.resolve_path(root_base)
            content = None
            if path.exists():
                try:
                    content = aggregate.read_managed_region(path, marker)
                except ManagedRegionCorruptionError:
                    content = None
            return {"mode": "managed", "path": str(path), "marker": marker, "content": content}
        records: Dict[str, object] = {"mode": "file", "entries": {}}
        if spec.target:
            path = spec.resolve_path(root_base)
            records["entries"]["default"] = path.read_text(encoding="utf-8") if path.exists() else None
            records["path"] = str(path)
            return records
        if spec.target_template:
            template = spec.target_template
            entries = {}
            search_root = (root_base / template.format(id="")).parent
            if search_root.exists():
                for file in search_root.rglob("*.md"):
                    entry_id = _infer_entry_id(template, file.relative_to(root_base).as_posix())
                    if entry_id is None:
                        continue
                    if selected_entries and entry_id not in selected_entries:
                        continue
                    entries[entry_id] = file.read_text(encoding="utf-8")
            records["entries"] = entries
            return records
        if spec.mode == "external":
            adapter = self._external_adapter(spec)
            return adapter.capture(project_root, spec)
        return records

    def _write_state_snapshot(
        self,
        project_root: Path,
        config: DocsBridgeConfig,
        aggregate: DocsBridgeAggregate,
    ) -> None:
        root_base = config.absolute_root(project_root)
        snapshot = {
            "generatedAt": _now_iso(),
            "sections": {},
        }
        for name, spec in config.iter_sections():
            snapshot["sections"][name] = self._capture_section_state(project_root, root_base, aggregate, spec, name, None)
        state_path = (project_root / STATE_FILE).resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _backup_file(target: Path, backup_root: Path, project_root: Path) -> None:
    if not target.exists():
        return
    relative = target.resolve().relative_to(project_root.resolve())
    backup_path = (backup_root / relative).resolve()
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")


def _backup_target_for(project_root: Path, backup_root: Path, target: Path) -> Path:
    relative = target.resolve().relative_to(project_root.resolve())
    return (backup_root / relative).resolve()


def _infer_entry_id(template: str, relative_path: str) -> Optional[str]:
    if "{id}" not in template:
        return None
    prefix = template.split("{id}")[0]
    suffix = template.split("{id}")[1]
    if relative_path.startswith(prefix) and relative_path.endswith(suffix):
        return relative_path[len(prefix) : len(relative_path) - len(suffix)]
    return None


def _hash(content: str) -> str:
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _adapter_actions_to_dict(actions: List[AdapterAction]) -> List[Dict[str, object]]:
    payload: List[Dict[str, object]] = []
    for action in actions:
        payload.append(
            {
                "name": action.name,
                "path": str(action.path) if action.path else None,
                "action": action.action,
            }
        )
    return payload


def available_external_adapters() -> List[str]:
    return sorted(ADAPTERS.keys())

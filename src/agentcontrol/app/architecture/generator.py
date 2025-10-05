"""Architecture manifest rendering utilities (docs, dashboards, tasks)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import yaml

from agentcontrol.app.architecture.progress import (
    PHASE_ORDER,
    compute_phase_progress,
    status_from_progress,
    status_score,
    utc_now_iso,
    weighted_numeric_average,
    weighted_status_average,
)


@dataclass
class TaskProgress:
    percent: float
    completed: int
    total: int


@dataclass
class DocSections:
    architecture_overview: str
    adr_index: str
    rfc_index: str
    adr_entries: Dict[str, str]
    rfc_entries: Dict[str, str]


def load_manifest_from_path(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def ensure_json_serialisable(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dt.datetime):
        if value.tzinfo:
            return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return value.replace(microsecond=0).isoformat() + "Z"
    if isinstance(value, dict):
        return {key: ensure_json_serialisable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [ensure_json_serialisable(item) for item in value]
    if isinstance(value, tuple):
        return [ensure_json_serialisable(item) for item in value]
    return str(value)


def compute_task_progress(tasks: List[dict]) -> TaskProgress:
    if not tasks:
        return TaskProgress(percent=0.0, completed=0, total=0)
    total = len(tasks)
    completed = sum(1 for task in tasks if task["status"] == "done")
    percent = float(weighted_status_average(tasks, "status", "size_points"))
    return TaskProgress(percent=percent, completed=completed, total=total)


def organise_entities(manifest: dict) -> Tuple[Dict[str, dict], Dict[str, dict], Dict[str, dict]]:
    tasks = {task["id"]: task for task in manifest.get("tasks", [])}
    big_tasks = {big["id"]: big for big in manifest.get("big_tasks", [])}
    epics = {epic["id"]: epic for epic in manifest.get("epics", [])}
    return tasks, big_tasks, epics


def enrich_manifest(manifest: dict) -> dict:
    tasks, big_tasks, epics = organise_entities(manifest)

    for big_id, big in big_tasks.items():
        big_task_tasks = [task for task in tasks.values() if task.get("big_task") == big_id]
        progress = compute_task_progress(big_task_tasks)
        big.setdefault("metrics", {})["progress_pct"] = int(round(progress.percent))
        big["stats"] = {"done": progress.completed, "total": progress.total}

    for epic_id, epic in epics.items():
        relevant_big_tasks = [big for big in big_tasks.values() if big.get("parent_epic") == epic_id]
        if relevant_big_tasks:
            epic_progress = weighted_numeric_average(
                (
                    {
                        "value": big["metrics"]["progress_pct"],
                        "size_points": big.get("size_points", 1),
                    }
                    for big in relevant_big_tasks
                ),
                "value",
                "size_points",
            )
        else:
            epic_progress = int(round(status_score(epic.get("status", "planned")) * 100))
        epic.setdefault("metrics", {})["progress_pct"] = epic_progress

    program = manifest.setdefault("program", {})
    meta = program.get("meta", {})
    epics_list = list(epics.values())
    if epics_list:
        program_progress = weighted_numeric_average(
            (
                {
                    "value": epic["metrics"]["progress_pct"],
                    "size_points": epic.get("size_points", 0),
                }
                for epic in epics_list
            ),
            "value",
            "size_points",
        )
    else:
        program_progress = 0.0
    program.setdefault("progress", {})["progress_pct"] = program_progress
    program.setdefault("progress", {}).setdefault("health", "green")
    phase_map = compute_phase_progress(manifest.get("tasks", []), program.get("milestones", []), int(program_progress))
    program.setdefault("progress", {})["phase_progress"] = phase_map
    milestones = program.get("milestones", [])
    for milestone in milestones:
        title = milestone.get("title")
        phase_value = phase_map.get(title, program_progress)
        milestone["status"] = status_from_progress(int(phase_value))
    meta.setdefault("updated_at", manifest.get("updated_at"))
    manifest["tasks_map"] = tasks
    manifest["big_tasks_map"] = big_tasks
    manifest["epics_map"] = epics
    return manifest


def render_program_section(manifest: dict) -> str:
    program_meta = manifest["program"]["meta"].copy()
    program_progress = manifest["program"]["progress"].copy()
    milestones = manifest["program"].get("milestones", [])

    program_block = program_meta | program_progress
    program_block["phase_progress"] = manifest["program"]["progress"].get("phase_progress", program_progress.get("phase_progress", {}))
    program_block["milestones"] = milestones
    program_block = ensure_json_serialisable(program_block)

    yaml_dump = yaml.dump(program_block, sort_keys=False, allow_unicode=True).strip()
    lines = ["## Program", "```yaml", yaml_dump, "```", "", "## Epics"]
    epics_data = []
    for epic in manifest["epics_map"].values():
        epic_block = {
            "id": epic["id"],
            "title": epic["title"],
            "type": epic.get("type"),
            "status": epic.get("status"),
            "priority": epic.get("priority"),
            "metrics": epic.get("metrics", {}),
        }
        epics_data.append(epic_block)
    lines.append(json.dumps(epics_data, ensure_ascii=False, indent=2))
    return "\n".join(lines) + "\n"


def render_tasks_board(manifest: dict) -> str:
    tasks = manifest.get("tasks", [])
    serialised = ensure_json_serialisable(tasks)
    return json.dumps({"tasks": serialised}, ensure_ascii=False, indent=2) + "\n"


def render_dashboard(manifest: dict) -> str:
    systems = manifest.get("systems", [])
    epics = manifest["epics_map"]
    big_tasks = manifest["big_tasks_map"]
    tasks = manifest["tasks_map"]
    generated_marker = manifest.get("updated_at") or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    dashboard = {
        "generated_at": generated_marker,
        "manifest_version": manifest["version"],
        "manifest_updated_at": manifest["updated_at"],
        "program_progress_pct": manifest["program"]["progress"]["progress_pct"],
        "systems": systems,
        "epics": list(epics.values()),
        "big_tasks": list(big_tasks.values()),
        "tasks": list(tasks.values()),
    }
    return json.dumps(ensure_json_serialisable(dashboard), ensure_ascii=False, indent=2) + "\n"


def render_architecture_overview(manifest: dict) -> str:
    program = manifest["program"]
    systems = manifest.get("systems", [])
    big_tasks = manifest["big_tasks_map"]
    tasks = manifest["tasks_map"]

    lines = [
        "# Architecture Overview",
        "",
        "## Program Snapshot",
        f"- Program ID: {program['meta']['program_id']}",
        f"- Name: {program['meta']['name']}",
        f"- Version: {manifest['version']}",
        f"- Updated: {ensure_json_serialisable(manifest['updated_at'])}",
        f"- Progress: {program['progress']['progress_pct']}% (health: {program['progress']['health']})",
        "",
        "## Systems",
        "| ID | Name | Purpose | ADR | RFC | Status | Dependencies | Roadmap Phase | Key Metrics |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for system in systems:
        deps = ", ".join(system.get("dependencies", [])) or "—"
        metrics = ", ".join(f"{k}={v}" for k, v in system.get("metrics", {}).items()) or "—"
        rfc = system.get("rfc") or "—"
        line = f"| {system['id']} | {system['name']} | {system['purpose']} | {system['adr']} | {rfc} | {system['status']} | {deps} | {system['roadmap_phase']} | {metrics} |"
        lines.append(line)
    lines.extend([
        "",
        "## Traceability",
        "| Task ID | Title | Status | Owner | System | Big Task | Epic | Phase |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for task in tasks.values():
        big = big_tasks.get(task.get("big_task"), {})
        row = "| {id} | {title} | {status} | {owner} | {system} | {big_task} | {epic} | {phase} |".format(
            id=task.get("id"),
            title=task.get("title"),
            status=task.get("status"),
            owner=task.get("owner"),
            system=task.get("system"),
            big_task=task.get("big_task"),
            epic=big.get("parent_epic", "—"),
            phase=task.get("roadmap_phase", "—"),
        )
        lines.append(row)
    return "\n".join(lines) + "\n"


def render_adr_files(manifest: dict) -> Tuple[str, Dict[str, str]]:
    adr_entries = manifest.get("adr", [])
    lines = ["# Architecture Decision Record Index", "", "| ADR | Title | Status | Date | Systems |", "| --- | --- | --- | --- | --- |"]
    entry_map: Dict[str, str] = {}
    for adr in adr_entries:
        systems = ", ".join(adr.get("related_systems", [])) or "—"
        lines.append(f"| {adr['id']} | {adr['title']} | {adr['status']} | {adr['date']} | {systems} |")
        content = "\n".join([
            f"# {adr['id']} — {adr['title']}",
            "",
            f"**Status:** {adr['status']} (date: {adr['date']})",
            f"**Authors:** {', '.join(adr.get('authors', [])) or '—'}",
            "",
            "## Context",
            adr.get("context", ""),
            "",
            "## Decision",
            adr.get("decision", ""),
            "",
            "## Consequences",
            adr.get("consequences", ""),
            "",
            f"**Related Systems:** {', '.join(adr.get('related_systems', [])) or '—'}",
            f"**Supersedes:** {', '.join(adr.get('supersedes', [])) or '—'}",
            f"**Superseded by:** {', '.join(adr.get('superseded_by', [])) or '—'}",
        ])
        entry_map[adr["id"]] = content + "\n"
    return "\n".join(lines) + "\n", entry_map


def render_rfc_files(manifest: dict) -> Tuple[str, Dict[str, str]]:
    rfc_entries = manifest.get("rfc", [])
    lines = ["# Request for Comments Index", "", "| RFC | Title | Status | Date | Systems |", "| --- | --- | --- | --- | --- |"]
    entry_map: Dict[str, str] = {}
    for rfc in rfc_entries:
        systems = ", ".join(rfc.get("related_systems", [])) or "—"
        lines.append(f"| {rfc['id']} | {rfc['title']} | {rfc['status']} | {rfc['date']} | {systems} |")
        content = "\n".join([
            f"# {rfc['id']} — {rfc['title']}",
            "",
            f"**Status:** {rfc['status']} (date: {rfc['date']})",
            f"**Authors:** {', '.join(rfc.get('authors', [])) or '—'}",
            "",
            "## Summary",
            rfc.get("summary", ""),
            "",
            "## Proposal",
            rfc.get("proposal", ""),
            "",
            "## Concerns",
            rfc.get("concerns", ""),
            "",
            f"**Related Systems:** {', '.join(rfc.get('related_systems', [])) or '—'}",
        ])
        entry_map[rfc["id"]] = content + "\n"
    return "\n".join(lines) + "\n", entry_map


def generate_outputs(manifest: dict) -> Tuple[Dict[str, str], DocSections]:
    manifest = enrich_manifest(manifest)
    outputs: Dict[str, str] = {}
    outputs["todo.machine.md"] = render_program_section(manifest)
    outputs["data/tasks.board.json"] = render_tasks_board(manifest)
    outputs["reports/architecture-dashboard.json"] = render_dashboard(manifest)
    adr_index, adr_entries = render_adr_files(manifest)
    rfc_index, rfc_entries = render_rfc_files(manifest)
    doc_sections = DocSections(
        architecture_overview=render_architecture_overview(manifest),
        adr_index=adr_index,
        rfc_index=rfc_index,
        adr_entries=adr_entries,
        rfc_entries=rfc_entries,
    )
    return outputs, doc_sections


def generate_doc_sections(manifest: dict) -> DocSections:
    _, sections = generate_outputs(manifest)
    return sections


def generate_doc_sections_for(project_root: Path) -> DocSections:
    candidates = [
        project_root / "architecture" / "manifest.yaml",
        project_root / ".agentcontrol" / "architecture" / "manifest.yaml",
    ]
    for manifest_path in candidates:
        if manifest_path.exists():
            manifest = load_manifest_from_path(manifest_path)
            return generate_doc_sections(manifest)
    raise FileNotFoundError(
        "No architecture manifest found under 'architecture/manifest.yaml' or '.agentcontrol/architecture/manifest.yaml'",
    )


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

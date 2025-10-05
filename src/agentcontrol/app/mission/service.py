"""Mission twin builder for AgentControl."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agentcontrol.app.docs.service import DocsBridgeService
from agentcontrol.app.docs.operations import DocsCommandService
from agentcontrol.app.command_service import CommandService
from agentcontrol.domain.mcp import MCPConfigRepository
from agentcontrol.domain.project import ProjectId
from agentcontrol.settings import SETTINGS
from agentcontrol.app.runtime.service import RuntimeService
from agentcontrol.app.runtime.service import RuntimeService

MISSION_FILTERS = ("docs", "quality", "tasks", "timeline", "mcp")

TIMELINE_DOC_REFERENCES = {
    "docs": "docs/tutorials/automation_hooks.md",
    "quality": "docs/tutorials/perf_nightly.md",
    "mcp": "docs/tutorials/mcp_integration.md",
    "tasks": "architecture_plan.md",
    "timeline": "docs/tutorials/mission_control_walkthrough.md",
}


@dataclass(frozen=True)
class TwinBuildResult:
    twin: Dict[str, Any]
    path: Path


@dataclass(frozen=True)
class MissionExecResult:
    status: str
    playbook: Optional[Dict[str, Any]]
    action: Optional[Dict[str, Any]]
    twin: Dict[str, Any]
    message: Optional[str] = None


@dataclass(frozen=True)
class MissionPaletteEntry:
    """Interactive mission action descriptor."""

    id: str
    label: str
    command: str
    category: str
    type: str
    hotkey: Optional[str] = None
    summary: Optional[str] = None
    action: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "command": self.command,
            "category": self.category,
            "type": self.type,
        }
        if self.hotkey:
            data["hotkey"] = self.hotkey
        if self.summary:
            data["summary"] = self.summary
        if self.action:
            data["action"] = self.action
        return data


@dataclass(frozen=True)
class TimelineHint:
    text: str
    hint_id: str
    doc_path: Optional[str] = None


class MissionService:
    """Aggregates project telemetry into a mission twin."""

    def __init__(self) -> None:
        self._docs_service = DocsBridgeService()
        self._docs_command_service = DocsCommandService()
        self._command_service = CommandService(SETTINGS)
        self._runtime_service = RuntimeService()

    def build_twin(self, project_root: Path) -> Dict[str, Any]:
        project_root = project_root.resolve()
        docs_bridge = self._docs_service.diagnose(project_root)
        status_report = self._load_json(project_root / "reports" / "status.json")
        verify_report = self._load_json(project_root / "reports" / "verify.json")
        program_summary = self._program_summary(project_root, status_report)
        quality_summary = self._quality_summary(verify_report)
        timeline = self._timeline(project_root)
        mcp_summary = self._mcp_summary(project_root)
        playbooks = self._playbooks(project_root, docs_bridge, quality_summary, mcp_summary)
        drilldown = self._build_drilldown(docs_bridge, program_summary, quality_summary, mcp_summary, timeline)
        palette = self._palette(project_root, playbooks, program_summary, docs_bridge, quality_summary, mcp_summary)
        activity = self._mission_activity(project_root)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "docsBridge": docs_bridge,
            "program": program_summary,
            "quality": quality_summary,
            "playbooks": playbooks,
            "timeline": timeline,
            "mcp": mcp_summary,
            "filters": list(MISSION_FILTERS),
            "drilldown": drilldown,
            "palette": [entry.to_dict() for entry in palette],
            "activity": activity,
            "acknowledgements": self._acknowledgements(project_root),
            "perf": self._perf_overview(project_root),
        }

    def persist_twin(self, project_root: Path) -> TwinBuildResult:
        twin = self.build_twin(project_root)
        state_dir = self._state_dir(project_root)
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "twin.json"
        path.write_text(json.dumps(twin, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return TwinBuildResult(twin=twin, path=path)

    def persist_palette(self, project_root: Path, palette: List[MissionPaletteEntry] | List[Dict[str, Any]]) -> Path:
        state_dir = self._state_dir(project_root)
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "mission_palette.json"
        entries: List[Dict[str, Any]] = []
        for entry in palette:
            if isinstance(entry, MissionPaletteEntry):
                entries.append(entry.to_dict())
            else:
                entries.append(dict(entry))
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "entries": entries,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def execute_playbook_by_issue(self, project_root: Path, issue: str) -> MissionExecResult:
        project_root = project_root.resolve()
        twin = self.build_twin(project_root)
        playbooks: List[Dict[str, Any]] = twin.get("playbooks", []) or []
        selected = next((item for item in playbooks if item.get("issue") == issue), None)
        if selected is None:
            return MissionExecResult(
                status="noop",
                playbook=None,
                action=None,
                twin=twin,
                message=f"playbook '{issue}' not available",
            )
        return self._execute_playbook(project_root, selected, twin)

    def execute_action(self, project_root: Path, action: Dict[str, Any]) -> MissionExecResult:
        project_root = project_root.resolve()
        twin = self.build_twin(project_root)
        kind = action.get("kind")
        if kind == "playbook":
            issue = action.get("issue")
            if not issue:
                return MissionExecResult(status="error", playbook=None, action=None, twin=twin, message="missing playbook issue")
            playbooks: List[Dict[str, Any]] = twin.get("playbooks", []) or []
            selected = next((item for item in playbooks if item.get("issue") == issue), None)
            if selected is None:
                return MissionExecResult(status="noop", playbook=None, action=None, twin=twin, message=f"playbook '{issue}' not available")
            return self._execute_playbook(project_root, selected, twin)

        if kind == "mission_exec_top":
            return self.execute_top_playbook(project_root)

        if kind == "docs_sync":
            payload = self._docs_command_service.sync_sections(project_root, mode="repair")
            self._update_acknowledgement(project_root, "docs", status="success")
            return MissionExecResult(
                status="success",
                playbook=None,
                action={"type": "docs_sync", "payload": payload},
                twin=twin,
            )

        if kind == "auto_tests":
            project_id = ProjectId.from_existing(project_root)
            exit_code = self._command_service.run(project_id, "verify", [])
            status = "success" if exit_code == 0 else "warning"
            message = None if exit_code == 0 else "verify pipeline returned non-zero exit code"
            self._update_acknowledgement(project_root, "quality", status=status, message=message)
            return MissionExecResult(
                status=status,
                playbook=None,
                action={"type": "verify_pipeline", "exit_code": exit_code},
                twin=twin,
                message=message,
            )

        if kind == "mcp_status":
            status, action_payload, message = self._mcp_diagnostics(project_root)
            self._update_acknowledgement(project_root, "mcp", status=status, message=message)
            return MissionExecResult(
                status=status,
                playbook=None,
                action=action_payload,
                twin=twin,
                message=message,
            )

        if kind == "tasks_status":
            project_id = ProjectId.from_existing(project_root)
            exit_code = self._command_service.run(project_id, "status", [])
            status = "success" if exit_code == 0 else "warning"
            message = None if exit_code == 0 else "status pipeline returned non-zero exit code"
            self._update_acknowledgement(project_root, "tasks", status=status, message=message)
            return MissionExecResult(
                status=status,
                playbook=None,
                action={"type": "tasks_status", "exit_code": exit_code},
                twin=twin,
                message=message,
            )

        if kind == "runtime_refresh":
            manifest = self._runtime_service.build_manifest(project_root)
            self._update_acknowledgement(project_root, "runtime", status="success")
            return MissionExecResult(
                status="success",
                playbook=None,
                action={"type": "runtime_refresh", "path": str(manifest.path)},
                twin=twin,
            )

        return MissionExecResult(status="noop", playbook=None, action=None, twin=twin, message="unsupported action")

    def execute_top_playbook(self, project_root: Path) -> MissionExecResult:
        project_root = project_root.resolve()
        twin = self.build_twin(project_root)
        playbooks: List[Dict[str, Any]] = twin.get("playbooks", []) or []
        if not playbooks:
            return MissionExecResult(status="noop", playbook=None, action=None, twin=twin, message="no playbooks available")

        playbook = playbooks[0]
        return self._execute_playbook(project_root, playbook, twin)

    def _state_dir(self, project_root: Path) -> Path:
        return project_root.resolve() / ".agentcontrol" / "state"

    def _execute_playbook(
        self,
        project_root: Path,
        playbook: Dict[str, Any],
        twin: Dict[str, Any],
    ) -> MissionExecResult:
        category = playbook.get("category")
        try:
            if category == "docs":
                payload = self._docs_command_service.sync_sections(project_root, mode="repair")
                self._update_acknowledgement(project_root, "docs", status="success")
                return MissionExecResult(
                    status="success",
                    playbook=playbook,
                    action={"type": "docs_sync", "payload": payload},
                    twin=twin,
                )
            if category == "quality":
                project_id = ProjectId.from_existing(project_root)
                exit_code = self._command_service.run(project_id, "verify", [])
                status = "success" if exit_code == 0 else "warning"
                self._update_acknowledgement(
                    project_root,
                    "quality",
                    status=status,
                    message=None if exit_code == 0 else "verify pipeline returned non-zero exit code",
                )
                return MissionExecResult(
                    status=status,
                    playbook=playbook,
                    action={"type": "verify_pipeline", "exit_code": exit_code},
                    twin=twin,
                    message=None if exit_code == 0 else "verify pipeline returned non-zero exit code",
                )
            if category == "mcp":
                status, action_payload, message = self._mcp_diagnostics(project_root)
                self._update_acknowledgement(project_root, "mcp", status=status, message=message)
                return MissionExecResult(
                    status=status,
                    playbook=playbook,
                    action=action_payload,
                    twin=twin,
                    message=message,
                )
            if category == "tasks":
                project_id = ProjectId.from_existing(project_root)
                exit_code = self._command_service.run(project_id, "status", [])
                status = "success" if exit_code == 0 else "warning"
                self._update_acknowledgement(
                    project_root,
                    "tasks",
                    status=status,
                    message=None if exit_code == 0 else "status pipeline returned non-zero exit code",
                )
                return MissionExecResult(
                    status=status,
                    playbook=playbook,
                    action={"type": "tasks_status", "exit_code": exit_code},
                    twin=twin,
                    message=None if exit_code == 0 else "status pipeline returned non-zero exit code",
                )
            if category == "runtime":
                manifest = self._runtime_service.build_manifest(project_root)
                self._update_acknowledgement(project_root, "runtime", status="success")
                return MissionExecResult(
                    status="success",
                    playbook=playbook,
                    action={"type": "runtime_refresh", "path": str(manifest.path)},
                    twin=twin,
                )
        except Exception as exc:  # pragma: no cover - defensive path
            return MissionExecResult(status="error", playbook=playbook, action=None, twin=twin, message=str(exc))

        return MissionExecResult(
            status="noop",
            playbook=playbook,
            action=None,
            twin=twin,
            message="unsupported playbook category",
        )

    def _program_summary(
        self,
        project_root: Path,
        status_report: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if status_report is not None:
            return {
                "source": "status_report",
                "roadmap": status_report.get("roadmap", {}),
                "tasks": status_report.get("tasks", {}),
            }

        manifest_path = project_root / "architecture" / "manifest.yaml"
        if not manifest_path.exists():
            return {
                "source": "missing",
                "message": "Run architecture sync to generate status report.",
            }
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        tasks = raw.get("tasks", []) if isinstance(raw.get("tasks"), list) else []
        done = sum(1 for task in tasks if task.get("status") == "done")
        total = len(tasks)
        return {
            "source": "manifest",
            "program": raw.get("program", {}),
            "tasks": {
                "total": total,
                "done": done,
                "open": total - done,
            },
        }

    def _quality_summary(self, verify_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if verify_report is None:
            return {
                "verify": {
                    "available": False,
                    "message": "Run agentcall verify to refresh QA summary.",
                }
            }
        return {
            "verify": {
                "available": True,
                "status": verify_report.get("status"),
                "summary": verify_report.get("summary", {}),
            }
        }

    def _timeline(self, project_root: Path, *, limit: int = 50) -> List[Dict[str, Any]]:
        events_path = project_root / "journal" / "task_events.jsonl"
        if not events_path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = record.get("timestamp") or record.get("ts")
            event = record.get("event") or record.get("type")
            payload = record.get("payload") or record.get("data") or {}
            category = payload.get("category") or self._categorize_event(event, payload)
            hint = self._timeline_hint(category, payload)
            entry = {
                "timestamp": timestamp,
                "event": event,
                "category": category,
                "details": payload,
            }
            if hint:
                entry["hint"] = hint.text
                entry["hintId"] = hint.hint_id
                if hint.doc_path:
                    entry["docPath"] = hint.doc_path
            entries.append(entry)
        entries.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        return entries[:limit]

    def _categorize_event(self, event: str | None, payload: Dict[str, Any]) -> str:
        label = (event or "").lower()
        if "doc" in label or payload.get("section") == "docs":
            return "docs"
        if "verify" in label or payload.get("pipeline") == "verify":
            return "quality"
        if "mcp" in label:
            return "mcp"
        if any(key in label for key in ("task", "roadmap", "mission")):
            return "tasks"
        return payload.get("category", "general")

    def _mcp_summary(self, project_root: Path) -> Dict[str, Any]:
        repo = MCPConfigRepository(project_root)
        servers = repo.list()
        return {
            "count": len(servers),
            "servers": [server.to_dict() for server in servers],
        }

    def _build_drilldown(
        self,
        docs_bridge: Dict[str, Any],
        program: Dict[str, Any],
        quality: Dict[str, Any],
        mcp_summary: Dict[str, Any],
        timeline: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        summary = docs_bridge.get("summary", {}) if isinstance(docs_bridge, dict) else {}
        return {
            "docs": {
                "issues": docs_bridge.get("issues", []) if isinstance(docs_bridge, dict) else [],
                "sections": summary.get("sections", []),
            },
            "quality": quality.get("verify", {}),
            "tasks": program.get("tasks", {}),
            "mcp": mcp_summary,
            "timeline": timeline,
        }

    def _playbooks(
        self,
        project_root: Path,
        docs_bridge: Dict[str, Any],
        quality: Dict[str, Any],
        mcp_summary: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        suggestions: list[Dict[str, Any]] = []

        docs_issues = docs_bridge.get("issues") if isinstance(docs_bridge, dict) else []
        if docs_issues:
            priority = 100 + len(docs_issues) * 10
            suggestions.append(
                self._playbook_entry(
                    issue="docs_drift",
                    summary="Repair managed documentation sections",
                    command="agentcall docs sync",
                    priority=priority,
                    category="docs",
                    hint="Run `agentcall docs sync --json` to auto-heal managed regions",
                )
            )

        verify = quality.get("verify", {}) if isinstance(quality, dict) else {}
        if not verify.get("available"):
            suggestions.append(
                self._playbook_entry(
                    issue="verify_outdated",
                    summary="Run verification pipeline",
                    command="agentcall auto tests --apply",
                    priority=90,
                    category="quality",
                    hint="Trigger QA guardrail via `agentcall auto tests --apply`",
                )
            )
        elif verify.get("status") and str(verify.get("status")).lower() not in {"pass", "ok", "success"}:
            suggestions.append(
                self._playbook_entry(
                    issue="verify_attention",
                    summary="Investigate degraded verification status",
                    command="agentcall auto tests",
                    priority=75,
                    category="quality",
                    hint="Inspect `reports/verify.json` for failing gates",
                )
            )

        if mcp_summary.get("count", 0) == 0:
            suggestions.append(
                self._playbook_entry(
                    issue="mcp_servers_missing",
                    summary="Register mission-critical MCP servers",
                    command="agentcall mcp add --name <server> --endpoint <url>",
                    priority=60,
                    category="mcp",
                    hint="Expose tooling via `agentcall mcp add ...`",
                )
            )

        perf_playbook = self._perf_regression_playbook(project_root)
        if perf_playbook:
            suggestions.append(perf_playbook)

        suggestions.sort(key=lambda item: (-item.get("priority", 0), item.get("issue")))
        return suggestions

    def _palette(
        self,
        project_root: Path,
        playbooks: List[Dict[str, Any]],
        program_summary: Dict[str, Any],
        docs_bridge: Dict[str, Any] | Any,
        quality: Dict[str, Any] | Any,
        mcp_summary: Dict[str, Any] | Any,
    ) -> List[MissionPaletteEntry]:
        entries: List[MissionPaletteEntry] = []
        for idx, playbook in enumerate(playbooks[:9], start=1):
            issue = playbook.get("issue") or f"playbook-{idx}"
            label = playbook.get("summary") or playbook.get("command") or issue
            entries.append(
                MissionPaletteEntry(
                    id=f"playbook:{issue}",
                    label=label,
                    command=playbook.get("command") or "",
                    category=playbook.get("category", "playbook"),
                    type="playbook",
                    hotkey=str(idx),
                    summary=playbook.get("hint"),
                    action={"kind": "playbook", "issue": issue},
                )
            )

        entries.extend(
            [
                MissionPaletteEntry(
                    id="mission:exec",
                    label="Execute top playbook",
                    command="agentcall mission exec",
                    category="mission",
                    type="mission",
                    hotkey="e",
                    summary="Runs the highest-priority playbook",
                    action={"kind": "mission_exec_top"},
                ),
                MissionPaletteEntry(
                    id="docs:sync",
                    label="Docs sync (repair)",
                    command="agentcall docs sync --json",
                    category="docs",
                    type="automation",
                    hotkey="a",
                    summary="Repair managed regions via docs bridge",
                    action={"kind": "docs_sync"},
                ),
                MissionPaletteEntry(
                    id="quality:verify",
                    label="Run verify pipeline",
                    command="agentcall auto tests --apply",
                    category="quality",
                    type="automation",
                    hotkey="v",
                    summary="Execute QA guardrail",
                    action={"kind": "auto_tests"},
                ),
                MissionPaletteEntry(
                    id="mcp:status",
                    label="Inspect MCP registry",
                    command="agentcall mcp status --json",
                    category="mcp",
                    type="inspection",
                    hotkey="m",
                    summary="List configured MCP servers",
                    action={"kind": "mcp_status"},
                ),
            ]
        )

        tasks_meta = program_summary.get("tasks", {}) if isinstance(program_summary, dict) else {}
        open_tasks = tasks_meta.get("open")
        if open_tasks is None:
            counts = tasks_meta.get("counts") if isinstance(tasks_meta, dict) else {}
            open_tasks = counts.get("open") if isinstance(counts, dict) else None
        if open_tasks is None or open_tasks:
            entries.append(
                MissionPaletteEntry(
                    id="tasks:status",
                    label="Refresh status dashboard",
                    command="agentcall status",
                    category="tasks",
                    type="automation",
                    hotkey="t",
                    summary="Run status pipeline to resync tasks/todo",
                    action={"kind": "tasks_status"},
                )
            )

        if self._runtime_stale(project_root):
            entries.append(
                MissionPaletteEntry(
                    id="runtime:refresh",
                    label="Generate runtime manifest",
                    command="agentcall runtime status --json",
                    category="runtime",
                    type="automation",
                    hotkey="r",
                    summary="Rebuild .agentcontrol/runtime.json",
                    action={"kind": "runtime_refresh"},
                )
            )

        return entries

    def _playbook_entry(
        self,
        *,
        issue: str,
        summary: str,
        command: str,
        priority: int,
        category: str,
        hint: str,
    ) -> Dict[str, Any]:
        return {
            "issue": issue,
            "summary": summary,
            "command": command,
            "priority": priority,
            "category": category,
            "hint": hint,
        }

    def _timeline_hint(self, category: str, payload: Dict[str, Any]) -> Optional[TimelineHint]:
        remediation = payload.get("remediation") or payload.get("remediation_hint") or payload.get("hint")
        if remediation:
            return TimelineHint(text=str(remediation), hint_id="custom.remediation")

        if category == "docs":
            section = payload.get("section") or payload.get("marker")
            target = payload.get("path") or payload.get("target")
            label = f" `{section}`" if section else ""
            if section and all(ch.isalnum() or ch in {"_", "-"} for ch in str(section)):
                scope = f" --section {section}"
            else:
                scope = ""
            target_segment = f" (target: {target})" if target else ""
            text = (
                f"Docs drift{label}{target_segment}; run `agentcall docs sync{scope} --json` "
                "and review reports/automation/docs-diff.json"
            )
            hint_id = "docs.drift"
            if section:
                hint_id = f"docs.drift.{section}"
            return TimelineHint(text=text, hint_id=hint_id, doc_path=TIMELINE_DOC_REFERENCES["docs"])

        if category == "quality":
            status = str(payload.get("status") or payload.get("result") or "unknown").lower()
            if status in {"fail", "failed", "error", "warning", "degraded", "blocked"}:
                text = "QA degraded; run `agentcall auto tests --apply` and inspect reports/verify.json"
                hint_id = "quality.degraded"
            else:
                text = "QA update logged; refresh `agentcall mission summary --filter quality`"
                hint_id = "quality.update"
            return TimelineHint(text=text, hint_id=hint_id, doc_path=TIMELINE_DOC_REFERENCES["quality"])

        if category == "mcp":
            return TimelineHint(
                text="MCP registry change; run `agentcall mcp status --json` (see reports/automation/mcp-status.json)",
                hint_id="mcp.registry",
                doc_path=TIMELINE_DOC_REFERENCES["mcp"],
            )

        if category == "tasks":
            task_ref = payload.get("task") or payload.get("id") or payload.get("summary")
            label = f" `{task_ref}`" if task_ref else ""
            text = f"Task event{label}; sync architecture_plan.md & todo.md, then run `agentcall mission detail tasks --json`"
            return TimelineHint(text=text, hint_id="tasks.sync", doc_path=TIMELINE_DOC_REFERENCES["tasks"])

        if category == "timeline":
            return TimelineHint(
                text="Check `agentcall mission detail timeline --json` for expanded context",
                hint_id="timeline.inspect",
                doc_path=TIMELINE_DOC_REFERENCES["timeline"],
            )

        return None

    def _mission_activity(self, project_root: Path) -> Dict[str, Any]:
        log_path = project_root / "reports" / "automation" / "mission-actions.json"
        if not log_path.exists():
            return {"count": 0, "recent": []}
        try:
            entries = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                return {"count": 0, "recent": []}
        except json.JSONDecodeError:
            return {"count": 0, "recent": []}

        recent = entries[-5:]
        return {
            "count": len(entries),
            "recent": recent[::-1],
            "logPath": str(log_path),
        }

    def _acknowledgements(self, project_root: Path) -> Dict[str, Any]:
        ack_path = self._state_dir(project_root) / "mission_ack.json"
        if not ack_path.exists():
            return {}
        try:
            data = json.loads(ack_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        return {}

    def _update_acknowledgement(
        self,
        project_root: Path,
        category: str,
        *,
        status: str,
        message: Optional[str] = None,
    ) -> None:
        state_dir = self._state_dir(project_root)
        state_dir.mkdir(parents=True, exist_ok=True)
        ack_path = state_dir / "mission_ack.json"
        data = {}
        if ack_path.exists():
            try:
                raw = json.loads(ack_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = raw
            except json.JSONDecodeError:
                data = {}
        data[category] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "message": message,
        }
        ack_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _perf_overview(self, project_root: Path) -> Dict[str, Any]:
        diff_path = project_root / "reports" / "perf" / "history" / "diff.json"
        if not diff_path.exists():
            self._update_acknowledgement(project_root, "perf", status="success")
            return {"regressions": [], "diffPath": str(diff_path), "followup": self._load_perf_followup(project_root)}
        try:
            diff = json.loads(diff_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self._update_acknowledgement(project_root, "perf", status="warning", message="perf diff unreadable")
            return {"regressions": [], "diffPath": str(diff_path), "followup": self._load_perf_followup(project_root)}
        regressions = diff.get("regressions") or []
        if regressions:
            self._update_acknowledgement(
                project_root,
                "perf",
                status="warning",
                message=f"{len(regressions)} regressions open",
            )
        else:
            self._update_acknowledgement(project_root, "perf", status="success")
        return {
            "regressions": regressions,
            "diffPath": str(diff_path),
            "followup": self._load_perf_followup(project_root),
        }

    def _perf_regression_playbook(self, project_root: Path) -> Optional[Dict[str, Any]]:
        diff_path = project_root / "reports" / "perf" / "history" / "diff.json"
        if not diff_path.exists():
            return None
        try:
            diff = json.loads(diff_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        regressions = diff.get("regressions") or []
        if not regressions:
            return None
        return self._playbook_entry(
            issue="perf_regression",
            summary="Investigate docs performance regression",
            command="agentcall verify --json",
            priority=120,
            category="quality",
            hint="Review reports/perf/history/diff.json and rerun verify to validate perf fix",
        )

    def _load_perf_followup(self, project_root: Path) -> Dict[str, Any]:
        followup_path = project_root / "reports" / "automation" / "perf_followup.json"
        if not followup_path.exists():
            return {}
        try:
            payload = json.loads(followup_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload | {"path": str(followup_path)}
        except json.JSONDecodeError:
            return {"path": str(followup_path), "status": "unknown"}
        return {}

    def _runtime_stale(self, project_root: Path) -> bool:
        runtime_path = project_root / ".agentcontrol" / "runtime.json"
        if not runtime_path.exists():
            return True
        try:
            mtime = runtime_path.stat().st_mtime
        except OSError:
            return True
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(mtime, timezone.utc)
        return age.total_seconds() > 6 * 60 * 60

    def _mcp_diagnostics(self, project_root: Path) -> tuple[str, Dict[str, Any], Optional[str]]:
        repo = MCPConfigRepository(project_root)
        servers = [server.to_dict() for server in repo.list()]
        if not servers:
            return (
                "warning",
                {"type": "mcp_status", "servers": servers},
                "no MCP servers registered",
            )
        degraded = [server for server in servers if not server.get("endpoint")]
        status = "warning" if degraded else "success"
        message = None
        if degraded:
            missing_names = ", ".join(server.get("name", "unknown") for server in degraded)
            message = f"MCP servers missing endpoint configuration: {missing_names}"
        return status, {"type": "mcp_status", "servers": servers}, message

    @staticmethod
    def _load_json(path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

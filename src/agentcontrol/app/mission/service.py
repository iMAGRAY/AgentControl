"""Mission twin builder for AgentControl."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agentcontrol.app.docs.service import DocsBridgeService
from agentcontrol.domain.mcp import MCPConfigRepository

MISSION_FILTERS = ("docs", "quality", "tasks", "timeline", "mcp")


@dataclass(frozen=True)
class TwinBuildResult:
    twin: Dict[str, Any]
    path: Path


class MissionService:
    """Aggregates project telemetry into a mission twin."""

    def __init__(self) -> None:
        self._docs_service = DocsBridgeService()

    def build_twin(self, project_root: Path) -> Dict[str, Any]:
        project_root = project_root.resolve()
        docs_bridge = self._docs_service.diagnose(project_root)
        status_report = self._load_json(project_root / "reports" / "status.json")
        verify_report = self._load_json(project_root / "reports" / "verify.json")
        program_summary = self._program_summary(project_root, status_report)
        quality_summary = self._quality_summary(verify_report)
        timeline = self._timeline(project_root)
        mcp_summary = self._mcp_summary(project_root)
        playbooks = self._playbooks(docs_bridge, quality_summary, mcp_summary)
        drilldown = self._build_drilldown(docs_bridge, program_summary, quality_summary, mcp_summary, timeline)

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
        }

    def persist_twin(self, project_root: Path) -> TwinBuildResult:
        twin = self.build_twin(project_root)
        state_dir = self._state_dir(project_root)
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "twin.json"
        path.write_text(json.dumps(twin, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return TwinBuildResult(twin=twin, path=path)

    def _state_dir(self, project_root: Path) -> Path:
        return project_root.resolve() / ".agentcontrol" / "state"

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
            entries.append(
                {
                    "timestamp": timestamp,
                    "event": event,
                    "category": category,
                    "details": payload,
                }
            )
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

    def _playbooks(self, docs_bridge: Dict[str, Any], quality: Dict[str, Any], mcp_summary: Dict[str, Any]) -> list[Dict[str, Any]]:
        playbooks: list[Dict[str, Any]] = []
        if docs_bridge.get("issues"):
            playbooks.append(
                {
                    "issue": "docs_drift",
                    "summary": "Repair managed documentation sections",
                    "command": "agentcall auto docs --apply",
                }
            )
        verify = quality.get("verify", {})
        if not verify.get("available"):
            playbooks.append(
                {
                    "issue": "verify_outdated",
                    "summary": "Run verification pipeline",
                    "command": "agentcall auto tests --apply",
                }
            )
        if not mcp_summary.get("count"):
            playbooks.append(
                {
                    "issue": "mcp_servers_missing",
                    "summary": "Register mission-critical MCP servers",
                    "command": "agentcall mcp add --name demo --endpoint https://example.com",
                }
            )
        return playbooks

    @staticmethod
    def _load_json(path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

"""Mission assignment service with optimistic locking and quotas."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from agentcontrol.domain.project import ProjectId, ProjectNotInitialisedError

CONFIG_PATH = Path(".agentcontrol/config/mission_assign.yaml")
STATE_PATH = Path(".agentcontrol/state/assignments.json")


class MissionAssignmentError(RuntimeError):
    """Raised when assignment operations fail."""


@dataclass(frozen=True)
class Assignment:
    task_id: str
    agent_id: str
    status: str
    assigned_at: float
    metadata: Dict[str, str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "status": self.status,
            "assigned_at": self.assigned_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AgentQuota:
    agent_id: str
    label: str
    max_active: int
    tags: List[str]


class MissionAssignmentService:
    def __init__(self, project_root: Path) -> None:
        self._root = project_root.resolve()
        self._config_path = self._root / CONFIG_PATH
        self._state_path = self._root / STATE_PATH
        self._board_path = self._root / "data/tasks.board.json"

    def assign(self, task_id: str, agent_id: str) -> Dict[str, object]:
        board = self._load_board()
        if task_id not in board["tasks_map"]:
            raise MissionAssignmentError(f"task '{task_id}' not found in board")
        task_record = board["tasks_map"][task_id]
        if task_record.status == "done":
            raise MissionAssignmentError(f"task '{task_id}' already completed")

        quotas = self._load_config()
        quota = quotas.get(agent_id)
        if quota is None:
            raise MissionAssignmentError(f"agent '{agent_id}' not defined in mission_assign.yaml")

        state = self._load_state()
        checksum = board["checksum"]
        previous_checksum = state.get("board_checksum")
        if previous_checksum and previous_checksum != checksum:
            raise MissionAssignmentError("task board changed; rerun after refreshing state (optimistic lock)")

        assignments = state.setdefault("assignments", [])
        active_for_agent = [item for item in assignments if item["agent_id"] == agent_id and item["status"] == "assigned"]
        if len(active_for_agent) >= quota.max_active:
            raise MissionAssignmentError(f"agent '{agent_id}' reached max_active={quota.max_active}")

        now = time.time()
        assignment = {
            "task_id": task_id,
            "agent_id": agent_id,
            "status": "assigned",
            "assigned_at": now,
            "metadata": {
                "task_title": task_record.title,
            },
        }
        assignments.append(assignment)
        state["board_checksum"] = checksum
        self._write_state(state)
        return {
            "assignment": assignment,
            "board_checksum": checksum,
        }

    def update_status(self, task_id: str, status: str, *, agent_id: Optional[str] = None) -> Dict[str, object]:
        state = self._load_state()
        assignments = state.get("assignments", [])
        for assignment in assignments:
            if assignment.get("task_id") == task_id and (agent_id is None or assignment.get("agent_id") == agent_id):
                assignment["status"] = status
                assignment["completed_at"] = time.time()
                self._write_state(state)
                return assignment
        raise MissionAssignmentError(f"assignment for task '{task_id}' not found")

    def list_assignments(self) -> Dict[str, object]:
        state = self._load_state()
        assignments = state.get("assignments", [])
        board = self._load_board()
        return {
            "board_checksum": board["checksum"],
            "assignments": assignments,
        }

    def _load_config(self) -> Dict[str, AgentQuota]:
        if not self._config_path.exists():
            raise MissionAssignmentError(f"assignment config missing: {self._config_path}")
        try:
            payload = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:  # pragma: no cover
            raise MissionAssignmentError(f"assignment config invalid YAML: {exc}") from exc
        if not isinstance(payload, dict):
            raise MissionAssignmentError("assignment config must be a mapping")
        agents = payload.get("agents")
        if not isinstance(agents, list) or not agents:
            raise MissionAssignmentError("assignment config requires non-empty 'agents' list")
        quotas: Dict[str, AgentQuota] = {}
        for raw in agents:
            if not isinstance(raw, dict):
                raise MissionAssignmentError("agent entry must be a mapping")
            agent_id = str(raw.get("id", "")).strip()
            if not agent_id:
                raise MissionAssignmentError("agent entry missing 'id'")
            label = str(raw.get("name", agent_id))
            max_active = int(raw.get("max_active", 1) or 0)
            if max_active <= 0:
                raise MissionAssignmentError(f"agent '{agent_id}' must have positive max_active")
            tags_field = raw.get("tags", [])
            if isinstance(tags_field, list):
                tags = [str(tag).strip() for tag in tags_field if str(tag).strip()]
            else:
                tags = []
            quotas[agent_id] = AgentQuota(agent_id=agent_id, label=label, max_active=max_active, tags=tags)
        return quotas

    def _load_board(self) -> Dict[str, object]:
        if not self._board_path.exists():
            raise MissionAssignmentError(f"task board missing at {self._board_path}")
        try:
            payload = json.loads(self._board_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MissionAssignmentError(f"task board invalid JSON: {exc}") from exc
        tasks_raw = payload.get("tasks")
        if not isinstance(tasks_raw, list):
            raise MissionAssignmentError("task board missing 'tasks' list")
        tasks_map = {}
        for entry in tasks_raw:
            if isinstance(entry, dict) and "id" in entry:
                from agentcontrol.domain.tasks import TaskRecord

                tasks_map[entry["id"]] = TaskRecord(entry["id"], {k: v for k, v in entry.items() if k != "id"})
        checksum = sha256(self._board_path.read_bytes()).hexdigest()
        payload["tasks_map"] = tasks_map
        payload["checksum"] = checksum
        return payload

    def _load_state(self) -> Dict[str, object]:
        if not self._state_path.exists():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write_state(self, state: Dict[str, object]) -> None:
        path = self._state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = ["MissionAssignmentService", "MissionAssignmentError", "Assignment", "AgentQuota"]

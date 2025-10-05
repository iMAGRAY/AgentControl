"""Legacy migration utilities for AgentControl capsules."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import yaml

from agentcontrol.domain.project import ProjectId


@dataclass
class MigrationPlan:
    actions: List[dict]
    path: Path


class MigrationService:
    """Detects and migrates legacy `agentcontrol/` capsules to `.agentcontrol/`."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()

    def detect(self) -> MigrationPlan:
        actions: List[dict] = []
        legacy_docs = self._project_root / "agentcontrol" / "docs"
        legacy_config = self._project_root / "agentcontrol" / "config" / "docs.bridge.yaml"
        if legacy_docs.exists():
            actions.append({
                "action": "move_docs",
                "from": str(legacy_docs),
                "to": str(self._project_root / "docs"),
            })
        if legacy_config.exists():
            actions.append({
                "action": "move_config",
                "from": str(legacy_config),
                "to": str(self._project_root / ".agentcontrol/config/docs.bridge.yaml"),
            })
            actions.append({
                "action": "update_config_root",
                "path": str(self._project_root / ".agentcontrol/config/docs.bridge.yaml"),
                "value": "docs",
            })
        return MigrationPlan(actions=actions, path=self._project_root / ".agentcontrol" / "state" / "migration.json")

    def apply(self, plan: MigrationPlan) -> None:
        for action in plan.actions:
            kind = action["action"]
            if kind == "move_docs":
                self._move_tree(Path(action["from"]), Path(action["to"]))
            elif kind == "move_config":
                self._move_file(Path(action["from"]), Path(action["to"]))
            elif kind == "update_config_root":
                self._update_config_root(Path(action["path"]), action["value"])
        self._record(plan)

    def _move_tree(self, source: Path, target: Path) -> None:
        if not source.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(source), str(target))

    def _move_file(self, source: Path, target: Path) -> None:
        if not source.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))

    def _update_config_root(self, config_path: Path, root_value: str) -> None:
        if not config_path.exists():
            return
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        data["root"] = root_value
        config_path.write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True), encoding="utf-8")

    def _record(self, plan: MigrationPlan) -> None:
        plan.path.parent.mkdir(parents=True, exist_ok=True)
        counters = {"applied": len(plan.actions)}
        plan.path.write_text(json.dumps(counters, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def for_project(project_root: Path) -> "MigrationService":
        ProjectId.from_existing(project_root)  # ensure project exists
        return MigrationService(project_root)

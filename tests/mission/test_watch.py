from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

import pytest

from agentcontrol.app.mission.service import MissionExecResult, MissionPaletteEntry, TwinBuildResult
from agentcontrol.app.mission.watch import MissionWatcher, WatchRule, SLAEntry
from agentcontrol.domain.project import ProjectId


class FakeMissionService:
    def __init__(self, twin: dict) -> None:
        self.twin = twin
        self.executed: list[str] = []
        self.actions: list[dict] = []

    def persist_twin(self, project_root: Path) -> TwinBuildResult:
        path = project_root / ".agentcontrol" / "state" / "twin.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.twin, ensure_ascii=False, indent=2), encoding="utf-8")
        return TwinBuildResult(twin=self.twin, path=path)

    def execute_playbook_by_issue(self, project_root: Path, issue: str) -> MissionExecResult:
        self.executed.append(issue)
        return MissionExecResult(
            status="success",
            playbook={"issue": issue, "category": "automation"},
            action={"type": "playbook", "issue": issue},
            twin=self.twin,
        )

    def record_action(
        self,
        project_root: Path,
        *,
        action_id: str,
        label: str,
        action: dict | None,
        result: MissionExecResult,
        source: str | None = None,
        operation_id: str | None = None,
        tags: Iterable[str] | None = None,
        append_timeline: bool = False,
        timeline_event: str | None = None,
        timeline_payload: dict | None = None,
        **extra: dict,
    ) -> Path:
        entry = {
            "action_id": action_id,
            "label": label,
            "action": action,
            "result": result,
            "source": source,
            "operation_id": operation_id,
            "tags": list(tags) if tags else None,
        }
        self.actions.append(entry)
        if append_timeline:
            self.append_timeline_event(
                project_root,
                event=timeline_event or f"mission.action.{action_id}",
                payload=timeline_payload or {},
            )
        return project_root / "reports" / "automation" / "mission-actions.json"

    def append_timeline_event(
        self,
        project_root: Path,
        *,
        event: str,
        payload: dict,
        timestamp: str | None = None,
    ) -> Path:
        journal = project_root / "journal"
        journal.mkdir(parents=True, exist_ok=True)
        path = journal / "task_events.jsonl"
        record = {
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        if payload.get("category"):
            record["category"] = payload["category"]
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".agentcontrol" / "state").mkdir(parents=True, exist_ok=True)
    (root / "reports" / "automation").mkdir(parents=True, exist_ok=True)
    return root


def test_mission_watcher_triggers_playbook(project_root: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    twin = {
        "timeline": [
            {"timestamp": now, "event": "perf.regression"},
        ],
        "acknowledgements": {
            "docs": {"status": "success", "updated_at": now},
            "perf": {"status": "warning", "updated_at": now},
        },
    }
    service = FakeMissionService(twin)
    project_id = ProjectId.for_new_project(project_root)
    watcher = MissionWatcher(
        project_id,
        service,
        [WatchRule(id="perf_regression", event="perf.regression", playbook_issue="perf_regression")],
        [SLAEntry(id="perf_sla", acknowledgement="perf", max_minutes=0, severity="critical")],
    )

    report = watcher.run_once()

    assert service.executed == ["perf_regression"]
    watch_report = json.loads((project_root / "reports" / "automation" / "watch.json").read_text(encoding="utf-8"))
    assert watch_report["actions"][0]["rule"] == "perf_regression"
    assert watch_report["actions"][0]["actorId"] == "watcher:perf_regression"
    assert watch_report["actions"][0]["origin"] == "mission.watch"
    assert "outcome" in watch_report["actions"][0]
    assert "perf" in watch_report["actions"][0]["tags"]
    sla_report = json.loads((project_root / "reports" / "automation" / "sla.json").read_text(encoding="utf-8"))
    assert sla_report["breaches"][0]["id"] == "perf_sla"

    state = json.loads((project_root / ".agentcontrol" / "state" / "watch.json").read_text(encoding="utf-8"))
    assert "perf_regression" in state

    timeline_path = project_root / "journal" / "task_events.jsonl"
    assert timeline_path.exists()
    timeline_entry = json.loads(timeline_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert timeline_entry["event"].startswith("mission.watch")
    payload = timeline_entry["payload"]
    assert payload["actorId"] == "watcher:perf_regression"
    assert payload["origin"] == "mission.watch"
    assert payload["status"] == "success"
    assert "tags" in payload and "perf" in payload["tags"]


@pytest.mark.parametrize("order", ["ascending", "descending"])
def test_mission_watcher_uses_latest_event(order: str, project_root: Path) -> None:
    base = datetime.now(timezone.utc)
    older = (base - timedelta(minutes=5)).isoformat()
    newer = base.isoformat()

    def make_timeline(*timestamps: str) -> list[dict[str, str]]:
        entries = [{"timestamp": ts, "event": "perf.regression"} for ts in timestamps]
        if order == "descending":
            entries.reverse()
        return entries

    twin = {
        "timeline": make_timeline(older, newer),
        "acknowledgements": {},
    }
    service = FakeMissionService(twin)
    project_id = ProjectId.for_new_project(project_root)
    watcher = MissionWatcher(
        project_id,
        service,
        [WatchRule(id="perf_regression", event="perf.regression", playbook_issue="perf_regression")],
        [],
    )

    watcher.run_once()
    state_path = project_root / ".agentcontrol" / "state" / "watch.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["perf_regression"]["last_event_ts"] == newer
    assert service.executed == ["perf_regression"]

    newest = (base + timedelta(minutes=5)).isoformat()
    service.twin["timeline"] = make_timeline(older, newer, newest)

    watcher.run_once()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["perf_regression"]["last_event_ts"] == newest
    assert service.executed == ["perf_regression", "perf_regression"]



class FlakyMissionService(FakeMissionService):
    def __init__(self, twin: dict) -> None:
        super().__init__(twin)
        self._attempt = 0

    def execute_playbook_by_issue(self, project_root: Path, issue: str) -> MissionExecResult:
        self.executed.append(issue)
        self._attempt += 1
        if self._attempt < 2:
            return MissionExecResult(
                status="error",
                playbook={"issue": issue, "category": "automation"},
                action={"type": "playbook", "issue": issue},
                twin=self.twin,
                message="transient failure",
            )
        return MissionExecResult(
            status="success",
            playbook={"issue": issue, "category": "automation"},
            action={"type": "playbook", "issue": issue},
            twin=self.twin,
        )


class AlwaysFailMissionService(FakeMissionService):
    def execute_playbook_by_issue(self, project_root: Path, issue: str) -> MissionExecResult:
        self.executed.append(issue)
        return MissionExecResult(
            status="error",
            playbook={"issue": issue, "category": "automation"},
            action={"type": "playbook", "issue": issue},
            twin=self.twin,
            message="always failing",
        )


def test_mission_watcher_retries_on_failure(project_root: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    twin = {
        "timeline": [
            {"timestamp": now, "event": "docs.drift"},
        ],
        "acknowledgements": {},
    }
    service = FlakyMissionService(twin)
    project_id = ProjectId.for_new_project(project_root)
    watcher = MissionWatcher(
        project_id,
        service,
        [WatchRule(id="docs_drift", event="docs.drift", playbook_issue="docs_repair", max_retries=3)],
        [],
    )

    report1 = watcher.run_once()
    assert service.executed == ["docs_repair"]
    assert report1["actions"][0]["status"] == "error"
    report2 = watcher.run_once()
    assert service.executed == ["docs_repair", "docs_repair"]
    assert report2["actions"][0]["status"] == "success"


def test_mission_watcher_resets_attempts_for_new_event(project_root: Path) -> None:
    ts1 = datetime.now(timezone.utc).isoformat()
    twin = {
        "timeline": [
            {"timestamp": ts1, "event": "docs.drift"},
        ],
        "acknowledgements": {},
    }
    service = AlwaysFailMissionService(twin)
    project_id = ProjectId.for_new_project(project_root)
    watcher = MissionWatcher(
        project_id,
        service,
        [WatchRule(id="docs_drift", event="docs.drift", playbook_issue="docs_repair", max_retries=1)],
        [],
    )

    report1 = watcher.run_once()
    assert service.executed == ["docs_repair"]
    assert report1["actions"][0]["status"] == "error"

    ts2 = datetime.now(timezone.utc).isoformat()
    twin["timeline"] = [{"timestamp": ts2, "event": "docs.drift"}] + twin["timeline"]
    report2 = watcher.run_once()
    assert service.executed == ["docs_repair", "docs_repair"]
    assert report2["actions"][0]["status"] == "error"

    report3 = watcher.run_once()
    assert report3["actions"] == []
    assert service.executed == ["docs_repair", "docs_repair"]

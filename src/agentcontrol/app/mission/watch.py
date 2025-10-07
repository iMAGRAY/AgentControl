"""Automation watcher for mission timeline events and SLA enforcement."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import secrets

import yaml

from agentcontrol.app.mission.service import MissionService, MissionExecResult, TwinBuildResult
from agentcontrol.domain.project import ProjectId

STATE_FILENAME = "watch.json"
WATCH_REPORT_FILENAME = "reports/automation/watch.json"
SLA_REPORT_FILENAME = "reports/automation/sla.json"


@dataclass
class WatchRule:
    id: str
    event: str
    playbook_issue: str
    debounce_minutes: int = 0
    max_retries: int = 3


@dataclass
class SLAEntry:
    id: str
    acknowledgement: str
    max_minutes: int
    severity: str = "warning"


@dataclass
class WatchStateEntry:
    last_event_ts: Optional[str] = None
    last_trigger_ts: Optional[str] = None
    attempts: int = 0
    last_status: Optional[str] = None


class WatchState:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: Dict[str, WatchStateEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._entries = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
        entries: Dict[str, WatchStateEntry] = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if isinstance(value, dict):
                    entries[key] = WatchStateEntry(
                        last_event_ts=value.get("last_event_ts"),
                        last_trigger_ts=value.get("last_trigger_ts"),
                        attempts=int(value.get("attempts", 0)),
                        last_status=value.get("last_status"),
                    )
        self._entries = entries

    def save(self) -> None:
        payload = {
            key: {
                "last_event_ts": entry.last_event_ts,
                "last_trigger_ts": entry.last_trigger_ts,
                "attempts": entry.attempts,
                "last_status": entry.last_status,
            }
            for key, entry in self._entries.items()
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def entry(self, rule_id: str) -> WatchStateEntry:
        return self._entries.setdefault(rule_id, WatchStateEntry())

    def update(
        self,
        rule_id: str,
        event_ts: str,
        status: str,
        *,
        count_attempt: bool = True,
        mark_event: bool = True,
    ) -> None:
        entry = self.entry(rule_id)
        if mark_event:
            entry.last_event_ts = event_ts
        now_iso = datetime.now(timezone.utc).isoformat()
        if status == "success":
            entry.last_trigger_ts = now_iso
            entry.attempts = 0
        else:
            if count_attempt:
                entry.attempts += 1
        entry.last_status = status


@dataclass
class WatchActionResult:
    rule_id: str
    event_ts: str
    status: str
    playbook: Optional[str] = None
    message: Optional[str] = None
    actor_id: Optional[str] = None
    origin: Optional[str] = None
    tags: Optional[List[str]] = None
    outcome: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule_id,
            "event_ts": self.event_ts,
            "status": self.status,
            "playbook": self.playbook,
            "message": self.message,
            "actorId": self.actor_id,
            "origin": self.origin,
            "tags": self.tags,
            "outcome": self.outcome,
        }


@dataclass
class SLABreach:
    id: str
    acknowledgement: str
    status: str
    minutes_since_update: float
    severity: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "acknowledgement": self.acknowledgement,
            "status": self.status,
            "minutes_since_update": self.minutes_since_update,
            "severity": self.severity,
        }


class MissionWatcher:
    def __init__(
        self,
        project_id: ProjectId,
        service: MissionService,
        rules: Iterable[WatchRule],
        sla_rules: Iterable[SLAEntry],
    ) -> None:
        self._project_id = project_id
        self._service = service
        self._rules = list(rules)
        self._sla_rules = list(sla_rules)
        state_dir = self._state_dir(project_id.root)
        self._state = WatchState(state_dir / STATE_FILENAME)

    @staticmethod
    def _state_dir(project_root: Path) -> Path:
        return project_root / ".agentcontrol" / "state"

    def run_once(self) -> Dict[str, Any]:
        project_root = self._project_id.root
        twin_result: TwinBuildResult = self._service.persist_twin(project_root)
        twin = twin_result.twin
        timeline = twin.get("timeline", []) if isinstance(twin, dict) else []
        if not isinstance(timeline, list):
            timeline = []

        actions: List[WatchActionResult] = []
        for rule in self._rules:
            action = self._evaluate_rule(rule, timeline)
            if action is not None:
                actions.append(action)

        self._state.save()
        sla_breaches = self._evaluate_sla(twin)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "actions": [action.to_dict() for action in actions],
            "sla": [breach.to_dict() for breach in sla_breaches],
        }
        self._write_report(project_root, report)
        if sla_breaches:
            self._write_sla_report(project_root, sla_breaches)
        return report

    def _evaluate_rule(self, rule: WatchRule, timeline: List[Dict[str, Any]]) -> Optional[WatchActionResult]:
        if not timeline:
            return None
        latest_event: Optional[Dict[str, Any]] = None
        latest_event_dt: Optional[datetime] = None
        for entry in timeline:
            if entry.get("event") != rule.event:
                continue
            raw_ts = entry.get("timestamp")
            parsed_ts = _parse_datetime(raw_ts)
            if parsed_ts is None:
                parsed_ts = datetime.min.replace(tzinfo=timezone.utc)
            if latest_event_dt is None or parsed_ts > latest_event_dt:
                latest_event = entry
                latest_event_dt = parsed_ts
        if latest_event is None:
            return None
        event_ts = latest_event.get("timestamp") or datetime.now(timezone.utc).isoformat()
        state_entry = self._state.entry(rule.id)
        if state_entry.last_event_ts and state_entry.last_event_ts != event_ts:
            state_entry.attempts = 0
            state_entry.last_status = None
        if state_entry.last_event_ts == event_ts:
            allow_retry = (
                state_entry.last_status
                and state_entry.last_status != "success"
                and state_entry.attempts < rule.max_retries
            )
            if not allow_retry:
                return None
        if state_entry.last_trigger_ts and rule.debounce_minutes:
            last_trigger = _parse_datetime(state_entry.last_trigger_ts)
            if last_trigger and (datetime.now(timezone.utc) - last_trigger) < timedelta(minutes=rule.debounce_minutes):
                self._state.update(rule.id, event_ts, "debounce", count_attempt=False, mark_event=True)
                return None
        if state_entry.attempts >= rule.max_retries:
            self._state.update(rule.id, event_ts, "skipped", count_attempt=False, mark_event=True)
            return WatchActionResult(
                rule_id=rule.id,
                event_ts=event_ts,
                status="skipped",
                playbook=rule.playbook_issue,
                message="max retries reached",
            )
        project_root = self._project_id.root
        result: MissionExecResult = self._service.execute_playbook_by_issue(project_root, rule.playbook_issue)
        status = result.status
        message = result.message
        actor_id = f"watcher:{rule.id}"
        origin = "mission.watch"
        tags = self._infer_tags(rule, result)
        outcome = self._build_outcome(result)
        operation_id = secrets.token_hex(8)
        self._service.record_action(
            project_root,
            action_id=actor_id,
            label=f"Watcher {rule.event}",
            action={
                "kind": "watcher",
                "rule": rule.id,
                "event": rule.event,
                "playbook": rule.playbook_issue,
            },
            result=result,
            source=origin,
            origin=origin,
            actor_id=actor_id,
            tags=tags,
            operation_id=operation_id,
            append_timeline=True,
            timeline_event=f"mission.watch.{rule.id}",
            timeline_payload={
                "ruleId": rule.id,
                "watchEvent": rule.event,
                "playbookIssue": rule.playbook_issue,
                "status": status,
                "message": message,
                "tags": tags,
                "category": self._primary_tag(tags),
                "origin": origin,
                "actorId": actor_id,
                "outcome": outcome,
            },
        )
        self._state.update(rule.id, event_ts, status, mark_event=True)
        return WatchActionResult(
            rule_id=rule.id,
            event_ts=event_ts,
            status=status,
            playbook=rule.playbook_issue,
            message=message,
            actor_id=actor_id,
            origin=origin,
            tags=tags,
            outcome=outcome,
        )

    def _evaluate_sla(self, twin: Dict[str, Any]) -> List[SLABreach]:
        breaches: List[SLABreach] = []
        acknowledgements = twin.get("acknowledgements", {}) if isinstance(twin, dict) else {}
        if not isinstance(acknowledgements, dict):
            acknowledgements = {}
        now = datetime.now(timezone.utc)
        for entry in self._sla_rules:
            ack = acknowledgements.get(entry.acknowledgement)
            if not isinstance(ack, dict):
                continue
            status = ack.get("status", "unknown")
            updated_at = _parse_datetime(ack.get("updated_at"))
            if status == "success":
                continue
            minutes = None
            if updated_at:
                minutes = (now - updated_at).total_seconds() / 60
            else:
                minutes = entry.max_minutes + 1
            if minutes > entry.max_minutes:
                breaches.append(
                    SLABreach(
                        id=entry.id,
                        acknowledgement=entry.acknowledgement,
                        status=status,
                        minutes_since_update=minutes,
                        severity=entry.severity,
                    )
                )
        return breaches

    def _infer_tags(self, rule: WatchRule, result: MissionExecResult) -> List[str]:
        taxonomy = {"docs", "perf", "quality", "mcp", "runtime", "tasks"}
        tags: set[str] = set()
        tokens = [rule.event, rule.playbook_issue]
        playbook = result.playbook or {}
        action = result.action or {}
        tokens.append(playbook.get("category", ""))
        tokens.append(playbook.get("issue", ""))
        tokens.append(action.get("kind", ""))
        tokens.append(action.get("type", ""))
        for token in tokens:
            lower = (token or "").lower()
            for candidate in taxonomy:
                if candidate in lower:
                    tags.add(candidate)
        if not tags:
            tags.add("automation")
        return sorted(tags)

    def _primary_tag(self, tags: List[str]) -> str:
        for preferred in ("docs", "quality", "tasks", "mcp", "perf", "runtime"):
            if preferred in tags:
                return preferred
        return tags[0] if tags else "automation"

    def _build_outcome(self, result: MissionExecResult) -> Dict[str, Any]:
        outcome: Dict[str, Any] = {
            "status": result.status,
        }
        if result.message:
            outcome["message"] = result.message
        if result.action:
            outcome["action"] = result.action
        if result.playbook:
            outcome["playbook"] = result.playbook
        return outcome

    def _write_report(self, project_root: Path, report: Dict[str, Any]) -> None:
        path = project_root / WATCH_REPORT_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _write_sla_report(self, project_root: Path, breaches: List[SLABreach]) -> None:
        path = project_root / SLA_REPORT_FILENAME
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "breaches": [breach.to_dict() for breach in breaches],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_watch_rules(config_path: Path) -> List[WatchRule]:
    if not config_path.exists():
        raise FileNotFoundError(f"watch config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    events = data.get("events", []) if isinstance(data, dict) else []
    rules: List[WatchRule] = []
    for entry in events:
        if not isinstance(entry, dict):
            continue
        try:
            rule = WatchRule(
                id=str(entry["id"]),
                event=str(entry["event"]),
                playbook_issue=str(entry["playbook"]),
                debounce_minutes=int(entry.get("debounce_minutes", 0)),
                max_retries=int(entry.get("max_retries", 3)),
            )
        except KeyError as exc:
            raise ValueError(f"watch rule missing required field: {exc}") from exc
        rules.append(rule)
    return rules


def load_sla_rules(config_path: Path) -> List[SLAEntry]:
    if not config_path.exists():
        return []
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    entries = data.get("slas", []) if isinstance(data, dict) else []
    rules: List[SLAEntry] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            rule = SLAEntry(
                id=str(entry["id"]),
                acknowledgement=str(entry["acknowledgement"]),
                max_minutes=int(entry.get("max_minutes", 60)),
                severity=str(entry.get("severity", "warning")),
            )
        except KeyError as exc:
            raise ValueError(f"sla rule missing required field: {exc}") from exc
        rules.append(rule)
    return rules


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

from __future__ import annotations

import http.client
import json
from pathlib import Path

from agentcontrol.app.mission.service import MissionService
from agentcontrol.app.mission.web import load_or_create_session_token
from agentcontrol.settings import RuntimeSettings
from tests.mission._web_utils import shutdown_server, start_server


def _read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def test_playbook_post_records_action_and_telemetry(
    project: Path,
    runtime_settings: RuntimeSettings,
) -> None:
    token, _ = load_or_create_session_token(project)
    service = MissionService()
    twin = service.build_twin(project)
    issue = twin["playbooks"][0]["issue"]

    app, server, thread, port = start_server(project, token)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request(
            "POST",
            f"/playbooks/{issue}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert body["operationId"]
        assert body["status"] in {"success", "warning", "noop", "error"}
        assert body["remediationHint"]

        log_path = project / "reports" / "automation" / "mission-actions.json"
        entries = _read_log(log_path)
        assert any(
            entry.get("operationId") == body["operationId"] and entry.get("source") == "mission.web"
            for entry in entries
        )
        telemetry_log = runtime_settings.log_dir / "telemetry.jsonl"
        lines = telemetry_log.read_text(encoding="utf-8").splitlines()
        assert any("mission.dashboard.api" in line and body["operationId"] in line for line in lines)
    finally:
        shutdown_server(app, server, thread)


def test_playbook_post_requires_token(project: Path) -> None:
    token, _ = load_or_create_session_token(project)
    app, server, thread, port = start_server(project, token)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/playbooks/docs_drift")
        resp = conn.getresponse()
        assert resp.status == 401
    finally:
        shutdown_server(app, server, thread)


def test_playbook_post_is_idempotent_in_log(project: Path) -> None:
    token, _ = load_or_create_session_token(project)
    service = MissionService()
    twin = service.build_twin(project)
    issue = twin["playbooks"][0]["issue"]

    app, server, thread, port = start_server(project, token)
    try:
        operation_ids: list[str] = []
        for _ in range(2):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request(
                "POST",
                f"/playbooks/{issue}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            operation_ids.append(body["operationId"])
        log_path = project / "reports" / "automation" / "mission-actions.json"
        entries = _read_log(log_path)
        found = [
            entry
            for entry in entries
            if entry.get("source") == "mission.web" and entry.get("id", "").startswith("web:playbook:")
        ]
        assert len(found) >= 2
        assert all(op_id in {entry.get("operationId") for entry in found} for op_id in operation_ids)
    finally:
        shutdown_server(app, server, thread)

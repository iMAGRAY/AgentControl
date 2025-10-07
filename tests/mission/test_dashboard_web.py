from __future__ import annotations

import http.client
import json
from pathlib import Path

from agentcontrol.app.mission.service import MissionService
from agentcontrol.app.mission.web import load_or_create_session_token
from tests.mission._web_utils import shutdown_server, start_server


def test_dashboard_web_healthz(project: Path) -> None:
    token, _ = load_or_create_session_token(project)
    app, server, thread, port = start_server(project, token)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/healthz")
        resp = conn.getresponse()
        assert resp.status == 200
        payload = json.loads(resp.read().decode("utf-8"))
        assert payload == {"status": "ok"}
    finally:
        shutdown_server(app, server, thread)


def test_dashboard_web_sse_stream(project: Path) -> None:
    token, _ = load_or_create_session_token(project)
    app, server, thread, port = start_server(project, token)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", f"/sse/events?token={token}")
        resp = conn.getresponse()
        assert resp.status == 200
        line = resp.fp.readline().decode("utf-8").strip()
        while line == "":
            line = resp.fp.readline().decode("utf-8").strip()
        assert line.startswith("data: ")
        payload = json.loads(line[6:])
        assert "summary" in payload
        assert "timeline" in payload
        conn.close()
    finally:
        shutdown_server(app, server, thread)


def test_dashboard_web_playbook_endpoint(project: Path) -> None:
    service = MissionService()
    twin = service.build_twin(project)
    issue = twin["playbooks"][0]["issue"]
    token, _ = load_or_create_session_token(project)
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
        assert body["issue"] == issue
    finally:
        shutdown_server(app, server, thread)

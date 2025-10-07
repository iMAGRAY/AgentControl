"""HTTP server for mission dashboard web mode."""

from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from socketserver import ThreadingMixIn
from http.server import HTTPServer

from agentcontrol.app.mission.service import MissionService
from agentcontrol.settings import SETTINGS
from agentcontrol.utils.telemetry import record_structured_event

_SESSION_FILENAME = "session.json"
_HTML_TEMPLATE = """<!doctype html><html><head><meta charset='utf-8'><title>Mission Dashboard</title>
<style>
body { font-family: system-ui, sans-serif; margin: 2rem; background: #0c0d13; color: #fafafa; }
pre { background: #161821; padding: 1rem; border-radius: 8px; overflow-x: auto; max-height: 32rem; }
section { margin-bottom: 2rem; }
header { display:flex; justify-content: space-between; align-items: center; }
code { background: #1e2130; padding: 0.2rem 0.4rem; border-radius: 4px; }
.badge { display:inline-block; padding:0.2rem 0.6rem; border-radius:0.75rem; background:#3c40ff; color:#fff; font-size:0.75rem; }
.label { color:#7a85ff; text-transform:uppercase; font-size:0.75rem; letter-spacing:0.1rem; }
</style>
</head><body>
<header><h1>Mission Dashboard</h1><span class="badge">Web Beta</span></header>
<p>Streaming mission twin for <code>{project}</code>. Token required for API calls.</p>
<section>
  <h2>Streaming Summary</h2>
  <pre id="summary">Connecting…</pre>
</section>
<section>
  <h2>Recent Timeline</h2>
  <pre id="timeline">–</pre>
</section>
<section>
  <h2>Playbooks</h2>
  <pre id="playbooks">–</pre>
</section>
<section>
  <h2>How to trigger playbook</h2>
  <pre>curl -X POST \
  -H 'Authorization: Bearer {token}' \
  http://{host}:{port}/playbooks/<playbook-issue></pre>
</section>
<script>
const token = {token_json};
const source = new EventSource(`/sse/events?token=${token}`);
source.onmessage = (event) => {
  try {
    const payload = JSON.parse(event.data);
    document.getElementById('summary').textContent = JSON.stringify(payload.summary, null, 2);
    document.getElementById('timeline').textContent = JSON.stringify(payload.timeline.slice(0, 10), null, 2);
    document.getElementById('playbooks').textContent = JSON.stringify(payload.playbooks, null, 2);
  } catch (error) {
    console.error('Failed to parse event', error);
  }
};
source.onerror = () => {
  document.getElementById('summary').textContent = 'Connection lost. Retrying…';
};
</script>
</body></html>"""


def _state_dir(project_root: Path) -> Path:
    return project_root / ".agentcontrol" / "state"


def load_or_create_session_token(project_root: Path) -> tuple[str, Path]:
    state_dir = _state_dir(project_root)
    state_dir.mkdir(parents=True, exist_ok=True)
    session_path = state_dir / _SESSION_FILENAME
    if session_path.exists():
        try:
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            token = payload.get("token")
            if isinstance(token, str) and token:
                return token, session_path
        except json.JSONDecodeError:
            session_path.unlink(missing_ok=True)
    token = secrets.token_urlsafe(32)
    payload = {
        "token": token,
        "generated_at": time.time(),
    }
    session_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return token, session_path


@dataclass
class MissionDashboardWebConfig:
    project_root: Path
    filters: tuple[str, ...]
    timeline_limit: int
    interval: float
    token: str
    host: str
    port: int


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class MissionDashboardWebApp:
    """Embeds mission dashboard summary into a lightweight HTTP server."""

    def __init__(
        self,
        mission_service: MissionService,
        config: MissionDashboardWebConfig,
    ) -> None:
        self._mission_service = mission_service
        self._config = config
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    @property
    def config(self) -> MissionDashboardWebConfig:
        return self._config

    def shutdown(self) -> None:
        self._stop_event.set()

    def _build_payload(self) -> dict[str, object]:
        with self._lock:
            result = self._mission_service.persist_twin(self._config.project_root)
            summary = result.twin
        timeline = summary.get("timeline", []) if isinstance(summary, dict) else []
        playbooks = summary.get("playbooks", []) if isinstance(summary, dict) else []
        return {
            "summary": summary,
            "timeline": timeline[: self._config.timeline_limit],
            "playbooks": playbooks,
            "generatedAt": summary.get("generated_at") if isinstance(summary, dict) else None,
            "filters": list(self._config.filters),
        }

    def create_server(self) -> ThreadedHTTPServer:
        app = self
        config = self._config

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A003 - silence default logging
                return

            def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _require_auth(self) -> bool:
                token = self._extract_token()
                if token != config.token:
                    self.send_response(HTTPStatus.UNAUTHORIZED)
                    self.send_header("WWW-Authenticate", "Bearer")
                    self.end_headers()
                    return False
                return True

            def _extract_token(self) -> str | None:
                auth = self.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    return auth[7:]
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                tokens = params.get("token")
                if tokens:
                    return tokens[0]
                return None

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self._serve_index()
                    return
                if parsed.path == "/healthz":
                    self._write_json(HTTPStatus.OK, {"status": "ok"})
                    return
                if parsed.path == "/sse/events":
                    if not self._require_auth():
                        return
                    self._serve_sse()
                    return
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.startswith("/playbooks/"):
                    if not self._require_auth():
                        return
                    issue = parsed.path.split("/", maxsplit=2)[-1]
                    operation_id = secrets.token_hex(8)
                    with app._lock:
                        result = app._mission_service.execute_playbook_by_issue(config.project_root, issue)
                        category = result.playbook.get("category") if result.playbook else None
                        tags = [tag for tag in [category, "mission-web"] if tag]
                        actor_id = f"mission.web:{issue}"
                        outcome = {
                            "status": result.status,
                            "message": result.message,
                            "playbook": result.playbook,
                            "action": result.action,
                        }
                        app._mission_service.record_action(
                            config.project_root,
                            action_id=f"web:playbook:{issue}",
                            label=result.playbook.get("summary") if result.playbook else issue,
                            action={"kind": "playbook", "issue": issue},
                            result=result,
                            source="mission.web",
                            operation_id=operation_id,
                            actor_id=actor_id,
                            origin="mission.web",
                            tags=tags,
                            append_timeline=True,
                            timeline_event=f"mission.web.{issue}",
                            timeline_payload={
                                "category": category or "mission",
                                "playbookIssue": issue,
                                "status": result.status,
                                "message": result.message,
                                "tags": tags,
                                "actorId": actor_id,
                                "origin": "mission.web",
                                "outcome": outcome,
                            },
                        )
                        app._mission_service.persist_twin(config.project_root)

                    hint = None
                    if result.playbook:
                        hint = result.playbook.get("hint") or result.playbook.get("summary")
                    if result.message and not hint:
                        hint = result.message
                    response = {
                        "operationId": operation_id,
                        "status": result.status,
                        "issue": issue,
                        "playbook": result.playbook,
                        "action": result.action,
                        "remediationHint": hint,
                        "message": result.message,
                    }
                    telemetry_status = "success"
                    if result.status == "warning":
                        telemetry_status = "warning"
                    elif result.status == "error":
                        telemetry_status = "error"
                    record_structured_event(
                        SETTINGS,
                        "mission.dashboard.api",
                        status=telemetry_status,
                        component="mission",
                        payload={
                            "path": str(config.project_root),
                            "issue": issue,
                            "operation_id": operation_id,
                            "result_status": result.status,
                            "message": result.message,
                        },
                    )
                    self._write_json(HTTPStatus.OK, response)
                    return
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()

            def _serve_index(self) -> None:
                project_name = config.project_root.name or str(config.project_root)
                html = _HTML_TEMPLATE.format(
                    project=project_name,
                    token=config.token,
                    token_json=json.dumps(config.token),
                    host=config.host,
                    port=config.port,
                )
                data = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _serve_sse(self) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                try:
                    while not app._stop_event.is_set():
                        payload = app._build_payload()
                        data = json.dumps(payload, ensure_ascii=False)
                        message = f"data: {data}\n\n".encode("utf-8")
                        self.wfile.write(message)
                        self.wfile.flush()
                        for _ in range(int(max(config.interval, 0.5) * 10)):
                            if app._stop_event.is_set():
                                break
                            time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    return

        server = ThreadedHTTPServer((config.host, config.port), Handler)
        return server


__all__ = [
    "MissionDashboardWebApp",
    "MissionDashboardWebConfig",
    "load_or_create_session_token",
]

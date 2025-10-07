from __future__ import annotations

import threading
import time
from http.server import HTTPServer
from pathlib import Path
from typing import Tuple

from agentcontrol.app.mission.service import MissionService
from agentcontrol.app.mission.web import MissionDashboardWebApp, MissionDashboardWebConfig


def start_server(project: Path, token: str, *, interval: float = 0.5) -> Tuple[MissionDashboardWebApp, HTTPServer, threading.Thread, int]:
    service = MissionService()
    config = MissionDashboardWebConfig(
        project_root=project,
        filters=tuple("docs quality tasks timeline mcp".split()),
        timeline_limit=5,
        interval=interval,
        token=token,
        host="127.0.0.1",
        port=0,
    )
    app = MissionDashboardWebApp(service, config)
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    _, port = server.server_address
    return app, server, thread, port


def shutdown_server(app: MissionDashboardWebApp, server: HTTPServer, thread: threading.Thread) -> None:
    app.shutdown()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)

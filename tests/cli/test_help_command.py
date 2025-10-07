from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from agentcontrol.cli.main import _help_cmd
from agentcontrol.domain.project import ProjectCapsule, ProjectId, project_settings_hash


def _run_help(path: Path, *, as_json: bool = False) -> tuple[int, str]:
    namespace = type("Args", (), {})()
    namespace.path = str(path)
    namespace.json = as_json
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = _help_cmd(namespace)
    return exit_code, buffer.getvalue().strip()


def test_help_without_project(tmp_path: Path) -> None:
    exit_code, output = _run_help(tmp_path)
    assert exit_code == 0
    assert "капсула AgentControl не обнаружена" in output
    assert "agentcall quickstart" in output
    assert output.count("Quickstart") == 1


def test_help_with_project_context(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()

    project_id = ProjectId.for_new_project(project_root)
    capsule = ProjectCapsule(
        project_id=project_id,
        template_version="0.5.1",
        channel="stable",
        template_name="default",
        settings_hash=project_settings_hash("0.5.1", "stable", "default"),
    )
    capsule.store()

    config_dir = project_root / ".agentcontrol" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "watch.yaml").write_text(
        """
        events:
          - id: docs_drift
            event: "docs.drift"
            playbook: "docs_drift"
            debounce_minutes: 0
            max_retries: 3
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (config_dir / "sla.yaml").write_text(
        """
        slas:
          - id: docs_followup
            acknowledgement: "docs"
            max_minutes: 60
            severity: warning
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    state_dir = project_root / ".agentcontrol" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "watch.json").write_text(
        json.dumps(
            {
                "docs_drift": {
                    "last_event_ts": datetime.now(timezone.utc).isoformat(),
                    "last_trigger_ts": datetime.now(timezone.utc).isoformat(),
                    "attempts": 0,
                    "last_status": "success",
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "verify.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "steps": [
                    {"name": "template-integrity", "status": "ok", "severity": "critical", "exit_code": 0}
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code, text_output = _run_help(project_root)
    assert exit_code == 0
    assert "Проект: default@0.5.1" in text_output
    assert "Watch rules: 1" in text_output
    assert "agentcall mission watch --once --json" in text_output

    exit_code_json, json_output = _run_help(project_root, as_json=True)
    assert exit_code_json == 0
    payload = json.loads(json_output)
    assert payload["project"]["present"] is True
    assert payload["project"]["template"]["name"] == "default"
    assert payload["project"]["verify"]["status"] == "ok"
    assert payload["project"]["watch"]["rules"][0]["id"] == "docs_drift"
    assert payload["project"]["watch"]["sla"][0]["id"] == "docs_followup"

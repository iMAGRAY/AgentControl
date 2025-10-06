from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.adapters.bootstrap_profile.file_repository import FileBootstrapProfileRepository
from agentcontrol.app.bootstrap_profile.service import BootstrapProfileService
from agentcontrol.cli import main as cli_main
from agentcontrol.domain.project import ProjectId
from agentcontrol.settings import RuntimeSettings



def _load_json(output: str) -> dict[str, object]:
    stripped = output.strip()
    start = stripped.find('{')
    end = stripped.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise AssertionError('No JSON payload found in output')
    return json.loads(stripped[start:end + 1])


@pytest.fixture()
def runtime_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimeSettings:
    base = tmp_path / "runtime"
    home = base / "home"
    template_dir = base / "templates"
    state_dir = base / "state"
    log_dir = base / "logs"
    for directory in (home, template_dir, state_dir, log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    settings = RuntimeSettings(
        home_dir=home,
        template_dir=template_dir,
        state_dir=state_dir,
        log_dir=log_dir,
        cli_version=__version__,
    )
    monkeypatch.setattr(cli_main, "SETTINGS", settings, raising=False)
    cli_main._build_services()
    return settings


def test_doctor_requires_profile(tmp_path: Path, runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    project_path = tmp_path / "workspace"
    cli_main.main(["init", str(project_path)])

    exit_code = cli_main.main(["doctor", str(project_path), "--bootstrap", "--json"])
    assert exit_code == 1
    captured = capsys.readouterr()
    payload = _load_json(captured.out)
    assert payload["status"] == "fail"


def test_doctor_bootstrap_json_ok(tmp_path: Path, runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    project_path = tmp_path / "workspace"
    cli_main.main(["init", str(project_path)])

    service = BootstrapProfileService(FileBootstrapProfileRepository())
    project_id = ProjectId.for_new_project(project_path)
    answers = {
        "stack-primary": "Python",
        "stack-frameworks": "FastAPI",
        "cicd-provider": "GitHub Actions",
        "mcp-usage": "yes",
        "repo-scale": "single repo",
        "automation-goals": "verify",
        "notable-constraints": "",
    }
    service.capture(project_id, profile_id="python", answers=answers, operator="doctor-test")

    mcp_dir = project_path / ".agentcontrol" / "config" / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    (mcp_dir / "staging.json").write_text("{\"name\": \"staging\", \"endpoint\": \"https://mcp.example.com\"}", encoding="utf-8")

    exit_code = cli_main.main(["doctor", str(project_path), "--bootstrap", "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    payload = _load_json(captured.out)
    assert payload["status"] in {"ok", "warn"}
    checks = {check["id"]: check for check in payload["checks"]}
    assert checks["mcp-config"]["status"] == "ok"
    assert checks["python-version"]["status"] in {"ok", "warn"}

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.settings import RuntimeSettings


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
    cli_main._build_services()  # sync packaged templates into the temporary runtime
    return settings


def _answer_iterator() -> Iterator[str]:
    responses = [
        "Python",
        "FastAPI",
        "GitHub Actions",
        "no",
        "single repo",
        "automation first",
        "",
    ]
    for item in responses:
        yield item


def _extract_json(output: str) -> dict[str, object]:
    stripped = output.strip()
    start = stripped.find('{')
    end = stripped.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise AssertionError('No JSON payload found in output')
    return json.loads(stripped[start:end + 1])


def test_bootstrap_command_json(tmp_path: Path, runtime_settings: RuntimeSettings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    project_path = tmp_path / "workspace"
    cli_main.main(["init", str(project_path)])

    answers = _answer_iterator()
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    exit_code = cli_main.main(["bootstrap", str(project_path), "--profile", "python", "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    payload = _extract_json(captured.out)
    assert payload["profile"]["id"] == "python"
    assert payload["profile_path"].endswith(".agentcontrol/state/profile.json")
    assert Path(payload["profile_path"]).exists()
    assert payload["recommendations"]

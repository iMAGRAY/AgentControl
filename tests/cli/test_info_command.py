from __future__ import annotations

import json
from pathlib import Path

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
    cli_main._build_services()
    return settings


def _prepare_docs(project: Path) -> None:
    config = project / ".agentcontrol" / "config" / "docs.bridge.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "\n".join(
            [
                "version: 1",
                "root: docs",
                "sections:",
                "  architecture_overview:",
                "    mode: managed",
                "    target: architecture/overview.md",
                "    marker: agentcontrol-architecture-overview",
                "  adr_index:",
                "    mode: managed",
                "    target: adr/index.md",
                "    marker: agentcontrol-adr-index",
                "  rfc_index:",
                "    mode: managed",
                "    target: rfc/index.md",
                "    marker: agentcontrol-rfc-index",
                "  adr_entry:",
                "    mode: file",
                "    target_template: adr/{id}.md",
                "  rfc_entry:",
                "    mode: file",
                "    target_template: rfc/{id}.md",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    docs_root = project / "docs"
    (docs_root / "architecture").mkdir(parents=True, exist_ok=True)
    (docs_root / "adr").mkdir(parents=True, exist_ok=True)
    (docs_root / "rfc").mkdir(parents=True, exist_ok=True)
    (docs_root / "architecture" / "overview.md").write_text(
        "<!-- agentcontrol:start:agentcontrol-architecture-overview -->\nOverview\n<!-- agentcontrol:end:agentcontrol-architecture-overview -->\n",
        encoding="utf-8",
    )
    (docs_root / "adr" / "index.md").write_text(
        "<!-- agentcontrol:start:agentcontrol-adr-index -->\nADR Index\n<!-- agentcontrol:end:agentcontrol-adr-index -->\n",
        encoding="utf-8",
    )
    (docs_root / "rfc" / "index.md").write_text(
        "<!-- agentcontrol:start:agentcontrol-rfc-index -->\nRFC Index\n<!-- agentcontrol:end:agentcontrol-rfc-index -->\n",
        encoding="utf-8",
    )


@pytest.fixture()
def project(runtime_settings: RuntimeSettings, tmp_path: Path) -> Path:
    bootstrap, _ = cli_main._build_services()
    project_path = tmp_path / "workspace"
    project_path.mkdir(parents=True, exist_ok=True)
    cli_main._auto_bootstrap_project(bootstrap, project_path, "status")
    _prepare_docs(project_path)
    return project_path


def _load_telemetry(log_dir: Path) -> list[dict[str, object]]:
    log_file = log_dir / "telemetry.jsonl"
    if not log_file.exists():
        return []
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_info_without_project(runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["info", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == __version__
    assert "docs" in payload.get("features", {})
    events = _load_telemetry(runtime_settings.log_dir)
    statuses = [evt.get("status") for evt in events if evt.get("event") == "info.collect"]
    assert statuses.count("start") == 1
    assert statuses.count("success") == 1


def test_info_with_project(runtime_settings: RuntimeSettings, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["info", str(project), "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    mission = payload.get("mission")
    assert mission is not None
    assert mission.get("twinPath", "").endswith(".agentcontrol/state/twin.json")
    events = [evt for evt in _load_telemetry(runtime_settings.log_dir) if evt.get("event") == "info.collect"]
    assert events[-1].get("status") == "success"

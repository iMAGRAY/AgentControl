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


@pytest.fixture()
def project(runtime_settings: RuntimeSettings, tmp_path: Path) -> Path:
    bootstrap, _ = cli_main._build_services()
    project_path = tmp_path / "workspace"
    project_path.mkdir(parents=True, exist_ok=True)
    cli_main._auto_bootstrap_project(bootstrap, project_path, "status")
    return project_path


def _write_config(project_path: Path, *, valid: bool = True) -> Path:
    config = project_path / ".agentcontrol" / "config" / "docs.bridge.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    if valid:
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
    else:
        config.write_text("version: 1\nroot: docs\nsections: {}\n", encoding="utf-8")
    return config


def _load_events(settings: RuntimeSettings) -> list[dict[str, object]]:
    log_file = settings.log_dir / "telemetry.jsonl"
    if not log_file.exists():
        return []
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_docs_diagnose_warns_on_missing_root(project: Path, runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    _write_config(project)
    exit_code = cli_main.main(["docs", str(project), "diagnose", "--json"])
    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "warning"
    assert any(issue["code"] == "DOC_ROOT_MISSING" for issue in output["issues"])
    events = [evt for evt in _load_events(runtime_settings) if evt.get("event") == "docs.diagnose"]
    assert events[0].get("status") == "start"
    assert events[-1].get("status") in {"success", "warning"}


def test_docs_diagnose_invalid_config(project: Path, runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    _write_config(project, valid=False)
    exit_code = cli_main.main(["docs", str(project), "diagnose", "--json"])
    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error"
    assert output["issues"][0]["code"] == "DOC_BRIDGE_INVALID_CONFIG"
    events = [evt for evt in _load_events(runtime_settings) if evt.get("event") == "docs.diagnose"]
    assert events[-1].get("status") == "warning"


def test_docs_info_reports_capabilities(project: Path, runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    _write_config(project)
    docs_root = project / "docs"
    (docs_root / "architecture").mkdir(parents=True, exist_ok=True)
    (docs_root / "adr").mkdir(parents=True, exist_ok=True)
    (docs_root / "rfc").mkdir(parents=True, exist_ok=True)

    (docs_root / "architecture" / "overview.md").write_text(
        "\n".join(
            [
                "<!-- agentcontrol:start:agentcontrol-architecture-overview -->",
                "Overview",
                "<!-- agentcontrol:end:agentcontrol-architecture-overview -->",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs_root / "adr" / "index.md").write_text(
        "\n".join(
            [
                "<!-- agentcontrol:start:agentcontrol-adr-index -->",
                "ADR Index",
                "<!-- agentcontrol:end:agentcontrol-adr-index -->",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs_root / "rfc" / "index.md").write_text(
        "\n".join(
            [
                "<!-- agentcontrol:start:agentcontrol-rfc-index -->",
                "RFC Index",
                "<!-- agentcontrol:end:agentcontrol-rfc-index -->",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = cli_main.main(["docs", str(project), "info", "--json"])
    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ok"
    assert output["capabilities"]["managedRegions"] is True
    assert output["capabilities"]["atomicWrites"] is True
    assert output["capabilities"]["anchorInsertion"] is True
    events = [evt for evt in _load_events(runtime_settings) if evt.get("event") == "docs.info"]
    assert events[-1].get("status") == "success"


def test_docs_diff_repair_and_rollback(project: Path, runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    _write_config(project)
    docs_root = project / "docs"
    (docs_root / "architecture").mkdir(parents=True, exist_ok=True)
    overview = docs_root / "architecture" / "overview.md"
    overview.write_text("# Architecture Overview\n\nLegacy\n", encoding="utf-8")

    exit_code = cli_main.main(["docs", str(project), "diff", "--json"])
    assert exit_code == 1
    diff_payload = json.loads(capsys.readouterr().out)
    assert diff_payload["diff"]

    exit_code = cli_main.main(["docs", str(project), "repair", "--json"])
    assert exit_code == 0
    repair_payload = json.loads(capsys.readouterr().out)
    backup_path = Path(repair_payload["backup"])
    assert backup_path.exists()

    overview.write_text("# Architecture Overview\n\nDrift\n", encoding="utf-8")
    exit_code = cli_main.main(["docs", str(project), "diff", "--json"])
    assert exit_code == 1
    capsys.readouterr()

    exit_code = cli_main.main(["docs", str(project), "rollback", "--timestamp", backup_path.name, "--json"])
    assert exit_code == 0
    rollback_payload = json.loads(capsys.readouterr().out)
    assert rollback_payload["actions"]
    restored = overview.read_text(encoding="utf-8")
    assert "Drift" not in restored
    assert "Legacy" in restored
    events = [evt for evt in _load_events(runtime_settings) if evt.get("event") in {"docs.diff", "docs.repair", "docs.rollback"}]
    assert any(evt.get("status") == "start" for evt in events)


def test_docs_sync_repair_path(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_config(project)
    docs_root = project / "docs"
    (docs_root / "architecture").mkdir(parents=True, exist_ok=True)
    overview = docs_root / "architecture" / "overview.md"
    overview.write_text("# Architecture Overview\n\nLegacy\n", encoding="utf-8")

    exit_code = cli_main.main(["docs", str(project), "sync", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert "architecture_overview" in payload.get("sections", [])
    updated = overview.read_text(encoding="utf-8")
    assert "agentcontrol:start:agentcontrol-architecture-overview" in updated

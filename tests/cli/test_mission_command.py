from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.app.mission.service import MissionExecResult
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


@pytest.fixture()
def issue_project(runtime_settings: RuntimeSettings, tmp_path: Path) -> Path:
    bootstrap, _ = cli_main._build_services()
    project_path = tmp_path / "workspace_issue"
    project_path.mkdir(parents=True, exist_ok=True)
    cli_main._auto_bootstrap_project(bootstrap, project_path, "status")
    return project_path


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


def _load_events(settings: RuntimeSettings) -> list[dict[str, object]]:
    log_file = settings.log_dir / "telemetry.jsonl"
    if not log_file.exists():
        return []
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def _seed_timeline(project: Path) -> None:
    events_path = project / "journal" / "task_events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2025-10-05T00:00:00Z",
                        "event": "docs.updated",
                        "payload": {"category": "docs", "summary": "Updated overview"},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2025-10-05T00:05:00Z",
                        "event": "verify.run",
                        "payload": {"pipeline": "verify", "status": "pending"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _seed_mcp(project: Path) -> None:
    cfg_dir = project / ".agentcontrol" / "config" / "mcp"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "demo.yaml").write_text("name: demo\nendpoint: https://example.com\n", encoding="utf-8")


def test_mission_command_generates_twin(project: Path, runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    _prepare_docs(project)
    _seed_timeline(project)
    _seed_mcp(project)
    exit_code = cli_main.main(["mission", "summary", str(project), "--json"])
    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["docsBridge"]["status"] in {"ok", "warning"}
    assert output["quality"]["verify"]["available"] is False
    assert output["mcp"]["count"] == 1
    assert output["timeline"]
    first_timeline = output["timeline"][0]
    assert first_timeline.get("hint")
    assert first_timeline.get("hintId")
    doc_path = first_timeline.get("docPath")
    assert doc_path
    repo_root = Path(__file__).resolve().parents[2]
    assert (repo_root / doc_path).exists()
    first_timeline = output["timeline"][0]
    assert first_timeline.get("hint")
    assert first_timeline.get("hintId")
    assert output["filters"] == ["docs", "quality", "tasks", "timeline", "mcp"]
    assert {"docs", "quality", "tasks", "timeline", "mcp"}.issubset(output["drilldown"].keys())
    assert output["playbooks"]
    assert output["palette"]
    first_playbook = output["playbooks"][0]
    assert "priority" in first_playbook and "hint" in first_playbook
    twin_path = project / ".agentcontrol" / "state" / "twin.json"
    assert twin_path.exists()
    stored = json.loads(twin_path.read_text(encoding="utf-8"))
    assert stored["program"]["source"] in {"status_report", "manifest", "missing"}
    palette_path = project / ".agentcontrol" / "state" / "mission_palette.json"
    assert palette_path.exists()
    palette_payload = json.loads(palette_path.read_text(encoding="utf-8"))
    assert palette_payload["entries"]
    assert any(entry.get("hotkey") == "e" for entry in palette_payload["entries"])
    assert all("action" in entry for entry in palette_payload["entries"] if entry.get("type") == "playbook")
    events = [evt for evt in _load_events(runtime_settings) if evt.get("event") == "mission.summary"]
    assert events[-1].get("status") == "success"


def test_mission_playbook_suggested_for_docs(issue_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["mission", "summary", str(issue_project), "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    commands = [entry.get("command") for entry in payload.get("playbooks", [])]
    assert "agentcall docs sync" in commands


def test_mission_detail_timeline_json(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _seed_timeline(project)
    exit_code = cli_main.main([
        "mission",
        "detail",
        "timeline",
        str(project),
        "--json",
        "--timeline-limit",
        "1",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["section"] == "timeline"
    assert len(payload["detail"]) == 1
    assert payload["detail"][0].get("hint")
    assert payload["detail"][0].get("hintId")
    assert payload["detail"][0].get("docPath")
    assert payload["detail"][0].get("hintId")


def test_mission_summary_filter_limits_output(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _prepare_docs(project)
    exit_code = cli_main.main(["mission", "summary", str(project), "--filter", "docs"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "docs status" in output
    assert "verify status" not in output


def test_mission_exec_runs_docs_sync(
    project: Path,
    runtime_settings: RuntimeSettings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _prepare_docs(project)
    overview = project / 'docs' / 'architecture' / 'overview.md'
    overview.write_text('# Architecture Overview\n\nManual drift\n', encoding='utf-8')

    exit_code = cli_main.main(['mission', 'exec', str(project), '--json'])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['playbook']['issue'] == 'docs_drift'
    synced = overview.read_text(encoding='utf-8')
    assert 'agentcontrol:start:agentcontrol-architecture-overview' in synced

    events = [evt for evt in _load_events(runtime_settings) if evt.get('event') == 'mission.exec']
    assert events
    final = events[-1]
    assert final.get('status') == 'success'
    assert final.get('payload', {}).get('playbook') == 'docs_drift'


def test_mission_exec_with_issue(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _prepare_docs(project)
    overview = project / 'docs' / 'architecture' / 'overview.md'
    overview.write_text('# Architecture Overview\n\nManual drift\n', encoding='utf-8')

    exit_code = cli_main.main(['mission', 'exec', str(project), '--json', '--issue', 'docs_drift'])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['playbook']['issue'] == 'docs_drift'


def test_log_palette_action(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    entry = {
        "id": "docs:sync",
        "label": "Docs sync",
        "action": {"kind": "docs_sync"},
    }
    result = MissionExecResult(status="success", playbook=None, action={"type": "docs_sync"}, twin={}, message=None)
    cli_main._log_palette_action(project, entry, result)
    cli_main._log_palette_action(project, entry, result)
    log_path = project / "reports" / "automation" / "mission-actions.json"
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(payload) == 2
    assert payload[0]["status"] == "success"

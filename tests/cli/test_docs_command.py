from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
import yaml

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


def _write_manifest(project_path: Path) -> Path:
    manifest = {
        "version": "0.1.0",
        "updated_at": "2025-10-01T00:00:00Z",
        "program": {
            "meta": {
                "program": "v1",
                "program_id": "test",
                "name": "Docs Portal Test",
                "objectives": [],
            },
            "progress": {"progress_pct": 100, "health": "green"},
            "milestones": [],
        },
        "systems": [],
        "tasks": [],
        "big_tasks": [],
        "epics": [],
        "adr": [],
        "rfc": [],
    }
    manifest_path = project_path / "architecture" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


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


def test_docs_portal_generates_site(
    project: Path,
    runtime_settings: RuntimeSettings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(project)
    _write_config(project)
    tutorials = project / "docs" / "tutorials"
    tutorials.mkdir(parents=True, exist_ok=True)
    (tutorials / "mission.md").write_text(
        "# Mission Control Walkthrough\n\nЗапуск панели миссии и обзор возможностей.",
        encoding="utf-8",
    )
    example_root = project / "examples" / "portal"
    example_root.mkdir(parents=True, exist_ok=True)
    (example_root / "README.md").write_text(
        "# Sample Workflow\n\nЭтот пример демонстрирует nightly guard.",
        encoding="utf-8",
    )

    exit_code = cli_main.main(["docs", str(project), "portal", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    portal_dir = Path(payload["path"])
    assert portal_dir.exists()
    assert (portal_dir / "index.html").exists()
    assert (portal_dir / "assets" / "app.js").exists()
    index_content = (portal_dir / "index.html").read_text(encoding="utf-8")
    assert "AgentControl Docs Portal" in index_content
    assert payload["inventory"].get("tutorial", 0) >= 1
    assert payload["inventory"].get("example", 0) >= 1
    events = [evt for evt in _load_events(runtime_settings) if evt.get("event") == "docs.portal"]
    assert events and events[-1].get("status") in {"success", "warning"}


def test_docs_portal_respects_budget(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_manifest(project)
    _write_config(project)
    (project / "docs" / "tutorials").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "tutorials" / "short.md").write_text("# Short\n\nSummary.", encoding="utf-8")

    exit_code = cli_main.main(["docs", str(project), "portal", "--json", "--budget", "256"])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "DOCS_PORTAL_SIZE_BUDGET_EXCEEDED"


def test_docs_lint_knowledge_success(
    project: Path,
    runtime_settings: RuntimeSettings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(project)
    _write_config(project)

    tutorials_root = project / "docs" / "tutorials"
    tutorials_root.mkdir(parents=True, exist_ok=True)
    (tutorials_root / "index.md").write_text("- [Knowledge Base](getting_started.md)\n", encoding="utf-8")
    mission_root = project / "docs" / "mission"
    mission_root.mkdir(parents=True, exist_ok=True)
    (mission_root / "watchers.md").write_text(
        "# Mission Watch\n\nКомплексный обзор автоматизаций, правил и метрик Mission Watch.\n",
        encoding="utf-8",
    )
    (tutorials_root / "getting_started.md").write_text(
        "\n".join(
            [
                "# Getting Started",
                "",
                "Эта страница описывает полный процесс инициализации капсулы AgentControl, включая bootstrap, verify, аналитические отчёты и последующие операции.",
                "",
                "См. [Mission Watch](../mission/watchers.md) для подробностей об автоматизации и SLA.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    adr_root = project / "docs" / "adr"
    adr_root.mkdir(parents=True, exist_ok=True)
    (adr_root / "index.md").write_text("- [ADR-0001](ADR-0001.md)\n", encoding="utf-8")
    (adr_root / "ADR-0001.md").write_text(
        "# ADR-0001\n\nПодробное описание архитектурного решения и его последствий для сервисов и операторов.\n",
        encoding="utf-8",
    )
    rfc_root = project / "docs" / "rfc"
    rfc_root.mkdir(parents=True, exist_ok=True)
    (rfc_root / "index.md").write_text("", encoding="utf-8")

    exit_code = cli_main.main(["docs", str(project), "lint", "--knowledge", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    report_path = Path(payload["report_path"])
    assert report_path.exists()
    events = [evt for evt in _load_events(runtime_settings) if evt.get("event") == "docs.lint.knowledge"]
    if events:
        assert events[-1].get("status") in {"success", "warning"}


def test_docs_lint_knowledge_detects_issues(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_manifest(project)
    _write_config(project)

    tutorials_root = project / "docs" / "tutorials"
    tutorials_root.mkdir(parents=True, exist_ok=True)
    (tutorials_root / "README.md").write_text("# Tutorials\n\n- Overview\n", encoding="utf-8")
    (tutorials_root / "overview.md").write_text(
        "Содержание без заголовка и короткое описание.",
        encoding="utf-8",
    )

    exit_code = cli_main.main(["docs", str(project), "lint", "--knowledge", "--json"])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    codes = {issue["code"] for issue in payload["issues"]}
    assert "KNOWLEDGE_MISSING_TITLE" in codes
    assert "KNOWLEDGE_ORPHAN_TUTORIAL" in codes


def test_docs_lint_knowledge_detects_adr_orphan(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_manifest(project)
    _write_config(project)

    tutorials_root = project / "docs" / "tutorials"
    tutorials_root.mkdir(parents=True, exist_ok=True)
    (tutorials_root / "index.md").write_text("- [Guide](guide.md)\n", encoding="utf-8")
    (tutorials_root / "guide.md").write_text("# Guide\n\nПолное руководство по запуску.\n", encoding="utf-8")

    adr_root = project / "docs" / "adr"
    adr_root.mkdir(parents=True, exist_ok=True)
    (adr_root / "index.md").write_text("- [ADR-0001](ADR-0001.md)\n", encoding="utf-8")
    (adr_root / "ADR-0001.md").write_text("# ADR-0001\n\nОписание решения.\n", encoding="utf-8")
    (adr_root / "ADR-0002.md").write_text("# ADR-0002\n\nВторое решение.\n", encoding="utf-8")

    exit_code = cli_main.main(["docs", str(project), "lint", "--knowledge", "--json"])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    codes = {issue["code"] for issue in payload["issues"]}
    assert "KNOWLEDGE_ADR_ORPHAN" in codes


def test_docs_lint_knowledge_warns_insecure_link(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_manifest(project)
    _write_config(project)

    tutorials_root = project / "docs" / "tutorials"
    tutorials_root.mkdir(parents=True, exist_ok=True)
    (tutorials_root / "index.md").write_text("- [Guide](guide.md)\n", encoding="utf-8")
    (tutorials_root / "guide.md").write_text(
        "# Guide\n\nСм. [HTTP link](http://example.com) и продолжайте работу.\n",
        encoding="utf-8",
    )

    exit_code = cli_main.main(["docs", str(project), "lint", "--knowledge", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    codes = {issue["code"] for issue in payload["issues"]}
    assert "KNOWLEDGE_INSECURE_LINK" in codes


def test_docs_lint_knowledge_external_validation(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(project)
    _write_config(project)

    tutorials_root = project / "docs" / "tutorials"
    tutorials_root.mkdir(parents=True, exist_ok=True)
    (tutorials_root / "index.md").write_text("- [Guide](guide.md)\n", encoding="utf-8")
    (tutorials_root / "guide.md").write_text(
        "# Guide\n\nСм. [Service](https://status.example.com/api).\n",
        encoding="utf-8",
    )

    def fake_check(self, url: str, *, timeout: float) -> bool:
        return False

    monkeypatch.setattr("agentcontrol.app.docs.knowledge.KnowledgeLintService._check_external_link", fake_check)

    exit_code = cli_main.main(
        [
            "docs",
            str(project),
            "lint",
            "--knowledge",
            "--json",
            "--validate-external",
            "--link-timeout",
            "0.1",
        ]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    codes = {issue["code"] for issue in payload["issues"]}
    assert "KNOWLEDGE_EXTERNAL_UNREACHABLE" in codes


def test_docs_lint_knowledge_stale_detection(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_manifest(project)
    _write_config(project)

    tutorials_root = project / "docs" / "tutorials"
    tutorials_root.mkdir(parents=True, exist_ok=True)
    tutorial = tutorials_root / "history.md"
    tutorial.write_text("# History\n\nХронология изменений.\n", encoding="utf-8")
    stale_time = time.time() - 3600 * 48
    os.utime(tutorial, (stale_time, stale_time))

    exit_code = cli_main.main(
        ["docs", str(project), "lint", "--knowledge", "--json", "--max-age-hours", "24"]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert any(issue["code"] == "KNOWLEDGE_FILE_STALE" for issue in payload["issues"])

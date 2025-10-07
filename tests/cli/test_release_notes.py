from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.domain.project import ProjectCapsule, ProjectId, project_settings_hash
from agentcontrol.settings import RuntimeSettings


@pytest.fixture()
def runtime_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimeSettings:
    runtime = tmp_path / "runtime"
    home = runtime / "home"
    template_dir = runtime / "templates"
    state_dir = runtime / "state"
    log_dir = runtime / "logs"
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
    monkeypatch.setattr(cli_main, "maybe_auto_update", lambda *args, **kwargs: None, raising=False)
    cli_main._build_services()
    return settings


def _init_project(root: Path) -> None:
    project_id = ProjectId.for_new_project(root)
    capsule = ProjectCapsule(
        project_id=project_id,
        template_version="0.5.2",
        channel="stable",
        template_name="default",
        settings_hash=project_settings_hash("0.5.2", "stable", "default"),
        metadata={"created_with": __version__},
    )
    capsule.store()

    readme = root / "README.md"
    readme.write_text("# Sample Project\n\nInitial content.\n", encoding="utf-8")

    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "chore(init): bootstrap project"], cwd=root, check=True)

    readme.write_text("# Sample Project\n\nInitial content.\n\n## Getting Started\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "feat(docs): add getting started section"], cwd=root, check=True)

    changelog = root / "CHANGELOG.md"
    changelog.write_text("## Unreleased\n\n- Placeholder\n", encoding="utf-8")
    subprocess.run(["git", "add", "CHANGELOG.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "fix: add changelog placeholder"], cwd=root, check=True)


@pytest.mark.usefixtures("runtime_settings")
def test_release_notes_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _init_project(project_root)

    exit_code = cli_main.main(
        [
            "release",
            "notes",
            str(project_root),
            "--json",
            "--max-commits",
            "10",
        ]
    )
    assert exit_code == 0

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    summary = payload["summary"]
    assert summary["commit_count"] >= 3
    assert Path(payload["markdown"]).exists()
    assert payload["json"] is not None
    assert Path(payload["json"]).exists()

    markdown = Path(payload["markdown"]).read_text(encoding="utf-8")
    assert "# Release Notes" in markdown
    assert "Features" in markdown or "Other" in markdown

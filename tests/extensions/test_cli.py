from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.settings import RuntimeSettings


def _create_extension_source(base: Path, name: str) -> Path:
    root = base / name
    root.mkdir(parents=True, exist_ok=True)
    for subdir in ("playbooks", "hooks", "mcp"):
        (root / subdir).mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": "0.2.0",
        "description": f"Extension {name}",
        "entry_points": {"playbooks": [], "hooks": [], "mcp": []},
        "compatibility": {"cli": ">=0.5.1"},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def test_extension_init_list_publish(runtime_settings: RuntimeSettings, project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main([
        "extension",
        "--path",
        str(project_root),
        "init",
        "auto_docs",
    ])
    assert exit_code == 0
    manifest = json.loads((project_root / "extensions" / "auto_docs" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "auto_docs"
    capsys.readouterr()

    exit_code = cli_main.main([
        "extension",
        "--path",
        str(project_root),
        "list",
        "--json",
    ])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert any(entry["name"] == "auto_docs" for entry in data)

    exit_code = cli_main.main([
        "extension",
        "--path",
        str(project_root),
        "lint",
        "--json",
    ])
    assert exit_code == 0
    lint_payload = json.loads(capsys.readouterr().out)
    assert lint_payload["errors"] == []

    exit_code = cli_main.main([
        "extension",
        "--path",
        str(project_root),
        "publish",
        "--dry-run",
        "--json",
    ])
    assert exit_code == 0
    publish_payload = json.loads(capsys.readouterr().out)
    output = Path(publish_payload["path"])
    assert output.exists()
    aggregated = json.loads(output.read_text(encoding="utf-8"))
    assert aggregated["extensions"]

    exit_code = cli_main.main([
        "extension",
        "--path",
        str(project_root),
        "remove",
        "auto_docs",
    ])
    assert exit_code == 0
    capsys.readouterr()
    exit_code = cli_main.main([
        "extension",
        "--path",
        str(project_root),
        "list",
        "--json",
    ])
    assert exit_code == 0
    remaining = json.loads(capsys.readouterr().out)
    assert remaining == []


def test_extension_add_from_local_path(
    runtime_settings: RuntimeSettings,
    project_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = _create_extension_source(tmp_path, "external_ext")

    exit_code = cli_main.main(
        [
            "extension",
            "--path",
            str(project_root),
            "add",
            "external_ext",
            "--source",
            str(source_root),
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "external_ext"
    assert payload["source"] == str(source_root.resolve())
    installed_root = Path(payload["path"])
    assert installed_root.exists()
    manifest = json.loads((installed_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "external_ext"
    catalog = json.loads((project_root / "extensions" / "catalog.json").read_text(encoding="utf-8"))
    assert any(entry["source"] == payload["source"] for entry in catalog["extensions"])


def test_extension_add_from_git_repository(
    runtime_settings: RuntimeSettings,
    project_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    git_source = _create_extension_source(tmp_path, "git_ext")
    subprocess.run(["git", "init", "-b", "main"], check=True, cwd=git_source)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], check=True, cwd=git_source)
    subprocess.run(["git", "config", "user.name", "CI"], check=True, cwd=git_source)
    subprocess.run(["git", "add", "."], check=True, cwd=git_source)
    subprocess.run(["git", "commit", "-m", "initial"], check=True, cwd=git_source)

    exit_code = cli_main.main(
        [
            "extension",
            "--path",
            str(project_root),
            "add",
            "git_ext",
            "--git",
            str(git_source),
            "--ref",
            "main",
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "git_ext"
    assert payload["source"] == str(git_source)
    installed_root = Path(payload["path"])
    assert installed_root.exists()
    assert not (installed_root / ".git").exists()


def test_extension_add_invalid_source_rolls_back(
    runtime_settings: RuntimeSettings,
    project_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    broken_root = tmp_path / "broken_ext"
    broken_root.mkdir(parents=True, exist_ok=True)
    (broken_root / "hooks").mkdir(parents=True, exist_ok=True)

    exit_code = cli_main.main(
        [
            "extension",
            "--path",
            str(project_root),
            "add",
            "broken_ext",
            "--source",
            str(broken_root),
        ]
    )
    assert exit_code == 1
    capsys.readouterr()
    installed_root = project_root / "extensions" / "broken_ext"
    assert not installed_root.exists()
    catalog_path = project_root / "extensions" / "catalog.json"
    if catalog_path.exists():
        catalog_payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        assert all(entry["name"] != "broken_ext" for entry in catalog_payload.get("extensions", []))

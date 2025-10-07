from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol.cli import main as cli_main
from agentcontrol.settings import RuntimeSettings


def _manifest_path(project_root: Path, name: str) -> Path:
    return project_root / "extensions" / name / "manifest.json"


def test_extension_lint_detects_missing_required_fields(
    runtime_settings: RuntimeSettings,
    project_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli_main.main(
        [
            "extension",
            "--path",
            str(project_root),
            "init",
            "broken_ext",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    manifest_path = _manifest_path(project_root, "broken_ext")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("entry_points", None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    exit_code = cli_main.main(
        [
            "extension",
            "--path",
            str(project_root),
            "lint",
            "--json",
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 1
    assert any("'entry_points' is a required property" in message for message in payload["errors"])


def test_extension_lint_detects_invalid_version_and_compatibility(
    runtime_settings: RuntimeSettings,
    project_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli_main.main(
        [
            "extension",
            "--path",
            str(project_root),
            "init",
            "invalid_meta",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    manifest_path = _manifest_path(project_root, "invalid_meta")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = "not.a.version"
    manifest.setdefault("compatibility", {})["cli"] = ">=0.5"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    exit_code = cli_main.main(
        [
            "extension",
            "--path",
            str(project_root),
            "lint",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    combined_errors = " ".join(payload["errors"])
    assert "manifest invalid_meta schema violation at version" in combined_errors
    assert "manifest invalid_meta schema violation at compatibility.cli" in combined_errors

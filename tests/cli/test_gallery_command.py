from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
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


@pytest.mark.usefixtures("runtime_settings")
def test_gallery_list(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["gallery", "list", "--json"])
    assert exit_code == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert any(item["id"] == "python-minimal" for item in payload)


@pytest.mark.usefixtures("runtime_settings")
def test_gallery_fetch_archive(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dest_dir = tmp_path / "downloads"
    dest_dir.mkdir()
    exit_code = cli_main.main(
        [
            "gallery",
            "fetch",
            "python-minimal",
            "--dest",
            str(dest_dir),
            "--json",
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    archive_path = Path(payload["path"])
    assert archive_path.exists()
    assert archive_path.suffix == ".zip"
    assert payload["size_bytes"] < 30 * 1024 * 1024

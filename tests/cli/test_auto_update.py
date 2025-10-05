from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from agentcontrol.settings import RuntimeSettings
from agentcontrol.utils import updater


@pytest.fixture()
def runtime_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimeSettings:
    base = tmp_path / "runtime"
    home = base / "home"
    template_dir = base / "templates"
    state_dir = base / "state"
    log_dir = base / "logs"
    for directory in (home, template_dir, state_dir, log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(updater, "_is_dev_environment", lambda: False)
    monkeypatch.delenv("AGENTCONTROL_AUTO_UPDATE", raising=False)
    monkeypatch.delenv("AGENTCONTROL_DISABLE_AUTO_UPDATE", raising=False)
    monkeypatch.setenv("HOME", str(home))
    return RuntimeSettings(home_dir=home, template_dir=template_dir, state_dir=state_dir, log_dir=log_dir, cli_version="0.3.2")


def test_auto_update_triggers_when_newer_version(runtime_settings: RuntimeSettings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("AGENTCONTROL_AUTO_UPDATE", "1")
    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: "0.4.0")

    captured = {}

    def fake_update(mode: str) -> CompletedProcess[bytes]:
        captured["mode"] = mode
        return CompletedProcess(args=[mode], returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(updater, "_perform_update", fake_update)

    with pytest.raises(SystemExit) as exc_info:
        updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")
    assert exc_info.value.code == 0
    assert captured.get("mode") == "pip"
    state_path = runtime_settings.state_dir / updater.STATE_FILENAME
    assert state_path.exists()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["latest_version"] == "0.4.0"
    assert payload["status"] == "ok"
    stderr = capsys.readouterr().err
    assert "auto-updated" in stderr


def test_auto_update_respects_disable(runtime_settings: RuntimeSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTCONTROL_DISABLE_AUTO_UPDATE", "1")
    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: "0.4.0")

    def fail_update(mode: str) -> CompletedProcess[bytes]:  # pragma: no cover - should not execute
        raise AssertionError("update should not run")

    monkeypatch.setattr(updater, "_perform_update", fail_update)

    updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")

    state_path = runtime_settings.state_dir / updater.STATE_FILENAME
    assert not state_path.exists()


def test_auto_update_uses_cached_state(runtime_settings: RuntimeSettings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    state_path = runtime_settings.state_dir / updater.STATE_FILENAME
    state_path.write_text(
        json.dumps(
            {
                "last_checked": "2099-01-01T00:00:00+00:00",
                "latest_version": "0.3.2",
                "status": "ok",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: (_ for _ in ()).throw(AssertionError("fetch should not run")))

    def fail_update(mode: str) -> CompletedProcess[bytes]:  # pragma: no cover - should not execute
        raise AssertionError("update should not run")

    monkeypatch.setattr(updater, "_perform_update", fail_update)

    before = state_path.read_text(encoding="utf-8")
    updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")

    assert state_path.read_text(encoding="utf-8") == before
    captured = capsys.readouterr().err
    assert captured == ""


def test_auto_update_honours_mode_env(runtime_settings: RuntimeSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTCONTROL_AUTO_UPDATE_MODE", "pipx")
    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: "0.5.0")

    called = {}

    def fake_update(mode: str) -> CompletedProcess[bytes]:
        called["mode"] = mode
        return CompletedProcess(args=[mode], returncode=1, stdout=b"", stderr=b"")

    monkeypatch.setattr(updater, "_perform_update", fake_update)

    updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")

    assert called["mode"] == "pipx"




def test_auto_update_fetch_failure(runtime_settings: RuntimeSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: None)
    updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")
    state_path = runtime_settings.state_dir / updater.STATE_FILENAME
    assert state_path.exists()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["latest_version"] is None


def test_auto_update_skips_after_recent_failure(
    runtime_settings: RuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def failing_fetch() -> str | None:  # noqa: ANN202 - signature matches target
        calls["count"] += 1
        return None

    monkeypatch.setattr(updater, "_fetch_remote_version", failing_fetch)
    updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")

    assert calls["count"] == 1

    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: (_ for _ in ()).throw(AssertionError("should not run")))

    updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")


def test_auto_update_uses_local_cache(runtime_settings: RuntimeSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_dir = runtime_settings.state_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = cache_dir / "agentcontrol-0.4.0-py3-none-any.whl"
    wheel_path.write_bytes(b"")

    monkeypatch.setenv("AGENTCONTROL_AUTO_UPDATE_CACHE", str(cache_dir))
    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: None)

    captured: dict[str, str] = {}

    def fake_local_install(path: Path, mode: str) -> CompletedProcess[bytes]:
        captured["path"] = str(path)
        captured["mode"] = mode
        return CompletedProcess(args=[str(path)], returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(updater, "_install_local_package", fake_local_install)

    with pytest.raises(SystemExit) as exc_info:
        updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")

    assert exc_info.value.code == 0
    assert captured["path"].endswith("agentcontrol-0.4.0-py3-none-any.whl")
    assert captured["mode"] == "pip"
    state_path = runtime_settings.state_dir / updater.STATE_FILENAME
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["status"] == "local"
    assert payload["latest_version"] == "0.4.0"


def test_auto_update_uses_default_cache_directory(
    runtime_settings: RuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_home = runtime_settings.home_dir.parent / "default-home"
    default_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(default_home))
    monkeypatch.delenv("AGENTCONTROL_AUTO_UPDATE_CACHE", raising=False)
    cache_dir = default_home / ".agentcontrol" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = cache_dir / "agentcontrol-0.4.1-py3-none-any.whl"
    wheel_path.write_bytes(b"")

    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: None)

    captured: dict[str, str] = {}

    def fake_local_install(path: Path, mode: str) -> CompletedProcess[bytes]:
        captured["path"] = str(path)
        captured["mode"] = mode
        return CompletedProcess(args=[str(path)], returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(updater, "_install_local_package", fake_local_install)

    with pytest.raises(SystemExit) as exc_info:
        updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")

    assert exc_info.value.code == 0
    assert captured["path"].endswith("agentcontrol-0.4.1-py3-none-any.whl")
    assert captured["mode"] == "pip"

def test_auto_update_local_cache_failure(runtime_settings: RuntimeSettings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    cache_dir = runtime_settings.state_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = cache_dir / "agentcontrol-0.4.0-py3-none-any.whl"
    wheel_path.write_bytes(b"")

    monkeypatch.setenv("AGENTCONTROL_AUTO_UPDATE_CACHE", str(cache_dir))
    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: None)

    def failing_install(path: Path, mode: str) -> CompletedProcess[bytes]:
        return CompletedProcess(args=[str(path)], returncode=1, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(updater, "_install_local_package", failing_install)

    updater.maybe_auto_update(runtime_settings, "0.3.2", command="status")

    state_path = runtime_settings.state_dir / updater.STATE_FILENAME
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    captured_err = capsys.readouterr().err
    assert "local cache update failed" in captured_err

from __future__ import annotations

from pathlib import Path

import pytest

from agentcontrol.settings import RuntimeSettings
from agentcontrol.utils import updater


@pytest.fixture
def settings(tmp_path: Path) -> RuntimeSettings:
    home = tmp_path / "home"
    state = home / "state"
    template = home / "templates"
    logs = home / "logs"
    for directory in (home, state, template, logs):
        directory.mkdir(parents=True, exist_ok=True)
    return RuntimeSettings(home_dir=home, template_dir=template, state_dir=state, log_dir=logs)


def test_maybe_auto_update_noop_in_dev_environment(monkeypatch: pytest.MonkeyPatch, settings: RuntimeSettings) -> None:
    sentinel = {"fetch": False}

    monkeypatch.setenv("AGENTCONTROL_AUTO_UPDATE", "1")
    monkeypatch.setattr(updater, "_is_dev_environment", lambda: True)
    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: sentinel.__setitem__("fetch", True))

    updater.maybe_auto_update(settings, "0.5.1", command="status")

    assert sentinel["fetch"] is False


def test_maybe_auto_update_uses_cache_when_fetch_fails(
    monkeypatch: pytest.MonkeyPatch, settings: RuntimeSettings, tmp_path: Path
) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "agentcontrol-9.9.9-py3-none-any.whl").write_bytes(b"wheel")
    monkeypatch.setenv("AGENTCONTROL_AUTO_UPDATE_CACHE", str(cache_dir))
    monkeypatch.setenv("AGENTCONTROL_AUTO_UPDATE", "1")

    called = {"install": False}

    monkeypatch.setattr(updater, "_is_dev_environment", lambda: False)
    monkeypatch.setattr(updater, "_fetch_remote_version", lambda: None)
    monkeypatch.setattr(
        updater,
        "_select_cached_release",
        lambda *_: (cache_dir / "agentcontrol-9.9.9-py3-none-any.whl", updater.Version("9.9.9")),
    )
    monkeypatch.setattr(updater, "record_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(updater, "_install_from_cache", lambda *args, **kwargs: called.__setitem__("install", True))
    monkeypatch.setattr(updater, "_store_state", lambda *args, **kwargs: None)

    updater.maybe_auto_update(settings, "0.5.1", command="status")

    assert called["install"] is True


def test_select_cached_release_prefers_newer(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "agentcontrol-1.0.0-py3-none-any.whl").write_text("a", encoding="utf-8")
    (cache_dir / "agentcontrol-1.2.0-py3-none-any.whl").write_text("b", encoding="utf-8")
    (cache_dir / "agentcontrol-0.9.0.tar.gz").write_text("c", encoding="utf-8")

    selected = updater._select_cached_release(cache_dir, updater.Version("1.1.0"))

    assert selected is not None
    _, version = selected
    assert str(version) == "1.2.0"

from __future__ import annotations

from pathlib import Path

import pytest

from agentcontrol.plugins.loader import load_plugins
from agentcontrol.settings import RuntimeSettings


def _seed_entry_points(monkeypatch):
    from importlib import metadata

    class DummyEntryPoint(metadata.EntryPoint):  # type: ignore[misc]
        def load(self):  # pragma: no cover
            from tests.command.test_plugins_loader import DummyPlugin

            return DummyPlugin()

    def fake_entry_points():  # pragma: no cover
        return metadata.EntryPoints([
            DummyEntryPoint(name="dummy", value="tests.command.test_plugins_loader:DummyPlugin", group="agentcontrol.plugins"),
        ])

    monkeypatch.setattr(metadata, "entry_points", fake_entry_points)


class DummyPlugin:
    def register(self, registrar, context):  # pragma: no cover
        def builder(parser, ctx):
            def handler(args):
                return 0

            return handler

        registrar.add_subparser("dummy-cmd", "Dummy help", builder)


@pytest.fixture
def settings(tmp_path: Path) -> RuntimeSettings:
    dirs = {name: tmp_path / name for name in ("home", "templates", "state", "logs")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return RuntimeSettings(
        home_dir=dirs["home"],
        template_dir=dirs["templates"],
        state_dir=dirs["state"],
        log_dir=dirs["logs"],
        cli_version="0.2.0",
    )


def test_load_plugins(monkeypatch, settings):
    _seed_entry_points(monkeypatch)
    registry = load_plugins(settings)
    commands = dict(registry.items())
    assert "dummy-cmd" in commands

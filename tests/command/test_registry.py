from __future__ import annotations

from pathlib import Path

import pytest

from agentcontrol.app.command_service import CommandRegistry, CommandNotFoundError


def test_registry_loads(tmp_path: Path) -> None:
    config = tmp_path / "agentcall.yaml"
    config.write_text(
        """
        commands:
          verify:
            steps:
              - name: step1
                exec: ["echo", "hello"]
        """,
        encoding="utf-8",
    )
    registry = CommandRegistry.load_from_file(config)
    pipeline = registry.get("verify")
    assert pipeline.name == "verify"
    assert pipeline.steps[0].exec == ["echo", "hello"]


def test_registry_missing_command(tmp_path: Path) -> None:
    config = tmp_path / "agentcall.yaml"
    config.write_text("commands: {}\n", encoding="utf-8")
    registry = CommandRegistry.load_from_file(config)
    with pytest.raises(CommandNotFoundError):
        registry.get("unknown")

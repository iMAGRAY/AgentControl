"""Runtime settings for AgentControl global SDK."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentcontrol import __version__



@dataclass(frozen=True)
class RuntimeSettings:
    home_dir: Path
    template_dir: Path
    state_dir: Path
    log_dir: Path
    cli_version: str = __version__

    @property
    def project_registry_file(self) -> Path:
        return self.state_dir / "projects.json"


def _default_home_dir() -> Path:
    return Path.home() / ".agentcontrol"


def load_settings() -> RuntimeSettings:
    base = _default_home_dir()
    template_dir = base / "templates"
    state_dir = base / "state"
    log_dir = base / "logs"
    return RuntimeSettings(
        home_dir=base,
        template_dir=template_dir,
        state_dir=state_dir,
        log_dir=log_dir,
    )


SETTINGS = load_settings()

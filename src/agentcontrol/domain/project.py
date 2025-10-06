"""Domain model for project capsules."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


PROJECT_DESCRIPTOR = "agentcontrol.project.json"
PROJECT_DIR = ".agentcontrol"
COMMAND_DESCRIPTOR = "agentcall.yaml"


def _capsule_dir(root: Path) -> Path:
    return root / PROJECT_DIR


def _descriptor_candidates(root: Path) -> list[Path]:
    return [_capsule_dir(root) / PROJECT_DESCRIPTOR]


def command_descriptor_candidates(root: Path) -> list[Path]:
    return [_capsule_dir(root) / COMMAND_DESCRIPTOR]


class ProjectNotInitialisedError(RuntimeError):
    """Raised when a path is not recognised as an AgentControl project."""


@dataclass(frozen=True)
class ProjectId:
    """Identifier of a project capsule (its root path)."""

    root: Path

    @classmethod
    def for_new_project(cls, path: Path) -> "ProjectId":
        resolved = path.expanduser().resolve()
        return cls(root=resolved)

    @classmethod
    def from_existing(cls, path: Path) -> "ProjectId":
        resolved = path.expanduser().resolve()
        descriptor = _descriptor_candidates(resolved)[0]
        if descriptor.exists():
            return cls(root=resolved)
        raise ProjectNotInitialisedError(f"Path {resolved} is not an AgentControl project.")

    def descriptor_path(self) -> Path:
        return self.root / PROJECT_DIR / PROJECT_DESCRIPTOR

    def command_descriptor_path(self) -> Path:
        candidate = command_descriptor_candidates(self.root)[0]
        if candidate.exists():
            return candidate
        # default preferred location inside capsule
        return self.root / PROJECT_DIR / COMMAND_DESCRIPTOR


@dataclass
class ProjectCapsule:
    project_id: ProjectId
    template_version: str
    channel: str
    template_name: str
    settings_hash: str
    registry_version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def ensure_compatible(self, cli_version: str) -> None:
        if self.template_version.split(".")[0] != cli_version.split(".")[0]:
            raise RuntimeError(
                "CLI and template major versions differ: "
                f"cli={cli_version} template={self.template_version}."
            )

    def compute_descriptor_payload(self) -> dict[str, Any]:
        payload = {
            "template_version": self.template_version,
            "channel": self.channel,
            "template": self.template_name,
            "settings_hash": self.settings_hash,
            "registry_version": self.registry_version,
            "metadata": self.metadata,
        }
        payload["checksum"] = sha256(
            json.dumps({k: payload[k] for k in payload if k != "checksum"}, sort_keys=True).encode()
        ).hexdigest()
        return payload

    def store(self) -> None:
        descriptor_path = self.project_id.descriptor_path()
        descriptor_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor_path.write_text(
            json.dumps(self.compute_descriptor_payload(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, project_id: ProjectId) -> "ProjectCapsule":
        descriptor_path = project_id.descriptor_path()
        if not descriptor_path.exists():
            raise FileNotFoundError(descriptor_path)
        data = json.loads(descriptor_path.read_text("utf-8"))
        checksum = data.pop("checksum", "")
        expected = sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        if checksum != expected:
            raise RuntimeError(
                "Project descriptor checksum mismatch; file may be corrupted."
            )
        return cls(
            project_id=project_id,
            template_version=data["template_version"],
            channel=data.get("channel", "stable"),
            template_name=data.get("template", "default"),
            settings_hash=data["settings_hash"],
            registry_version=data.get("registry_version", 1),
            metadata=data.get("metadata", {}),
        )


def project_settings_hash(template_version: str, channel: str, template: str) -> str:
    return sha256(f"{template_version}:{channel}:{template}".encode()).hexdigest()

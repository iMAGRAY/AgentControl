"""Value objects for the documentation bridge bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional

from .constants import remediation_for


DEFAULT_VERSION = 1
DEFAULT_ROOT = Path("docs")
ALLOWED_MODES = {"managed", "file", "skip", "external"}
REQUIRED_SECTION_KEYS = {
    "architecture_overview",
    "adr_index",
    "rfc_index",
    "adr_entry",
    "rfc_entry",
}


@dataclass(frozen=True)
class InsertionPolicy:
    """Describes how to place managed regions when markers are absent."""

    kind: str  # "after_heading" | "before_marker"
    value: str

    def as_dict(self) -> Dict[str, str]:
        return {"type": self.kind, "value": self.value}


class DocsBridgeConfigError(ValueError):
    """Raised when documentation bridge configuration is invalid."""

    def __init__(self, message: str, *, code: str = "DOC_BRIDGE_INVALID_CONFIG", remediation: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.remediation = remediation if remediation is not None else remediation_for(code)


@dataclass(frozen=True)
class SectionConfig:
    """Immutable description of a bridge section."""

    mode: str
    target: Optional[str] = None
    target_template: Optional[str] = None
    marker: Optional[str] = None
    insertion: Optional[InsertionPolicy] = None
    adapter: Optional[str] = None
    options: Optional[Mapping[str, object]] = None

    def resolve_path(self, root: Path, identifier: Optional[str] = None) -> Path:
        """Resolve the absolute destination of the section."""

        if self.target:
            return (root / self.target).resolve()
        if self.target_template and identifier is not None:
            return (root / self.target_template.format(id=identifier)).resolve()
        raise DocsBridgeConfigError("SectionConfig requires target or target_template")


@dataclass(frozen=True)
class DocsBridgeConfig:
    """Aggregate value object describing the docs bridge layout."""

    version: int
    root: Path
    sections: Mapping[str, SectionConfig]

    @classmethod
    def from_dict(cls, data: Mapping[str, object], *, config_path: Path) -> "DocsBridgeConfig":
        """Build config from a raw mapping, validating invariants."""

        if not isinstance(data, Mapping):
            raise DocsBridgeConfigError(
                f"Configuration in {config_path} must be a mapping",
            )
        version = int(data.get("version", DEFAULT_VERSION))
        if version != DEFAULT_VERSION:
            raise DocsBridgeConfigError(
                f"Unsupported docs bridge config version {version} in {config_path}",
            )

        root_value = data.get("root", DEFAULT_ROOT.as_posix())
        if not isinstance(root_value, str):
            raise DocsBridgeConfigError(
                "docs bridge root must be a string",
            )

        raw_sections = data.get("sections", {})
        if not isinstance(raw_sections, Mapping):
            raise DocsBridgeConfigError("'sections' must be a mapping of section definitions")

        sections = _build_sections(raw_sections, config_path)
        return cls(version=version, root=Path(root_value), sections=sections)

    @classmethod
    def default(cls, root: str | Path = DEFAULT_ROOT) -> "DocsBridgeConfig":
        """Produce the default configuration for projects without overrides."""

        root_value = Path(root)
        data: Dict[str, object] = {
            "version": DEFAULT_VERSION,
            "root": root_value.as_posix(),
            "sections": {
                "architecture_overview": {
                    "mode": "managed",
                    "target": "architecture/overview.md",
                    "marker": "agentcontrol-architecture-overview",
                },
                "adr_index": {
                    "mode": "managed",
                    "target": "adr/index.md",
                    "marker": "agentcontrol-adr-index",
                },
                "rfc_index": {
                    "mode": "managed",
                    "target": "rfc/index.md",
                    "marker": "agentcontrol-rfc-index",
                },
                "adr_entry": {
                    "mode": "file",
                    "target_template": "adr/{id}.md",
                },
                "rfc_entry": {
                    "mode": "file",
                    "target_template": "rfc/{id}.md",
                },
            },
        }
        return cls.from_dict(data, config_path=Path("<default>"))

    def absolute_root(self, project_root: Path) -> Path:
        """Resolve the docs root relative to a project."""

        return self.root if self.root.is_absolute() else (project_root / self.root).resolve()

    def section(self, name: str) -> SectionConfig:
        try:
            return self.sections[name]
        except KeyError as exc:  # noqa: PERF203
            raise DocsBridgeConfigError(f"Unknown section '{name}' requested") from exc

    @property
    def architecture_overview(self) -> SectionConfig:
        return self.section("architecture_overview")

    @property
    def adr_index(self) -> SectionConfig:
        return self.section("adr_index")

    @property
    def rfc_index(self) -> SectionConfig:
        return self.section("rfc_index")

    @property
    def adr_entry(self) -> SectionConfig:
        return self.section("adr_entry")

    @property
    def rfc_entry(self) -> SectionConfig:
        return self.section("rfc_entry")

    def iter_sections(self) -> Iterable[tuple[str, SectionConfig]]:
        return self.sections.items()


def _build_sections(raw: Mapping[str, object], config_path: Path) -> Dict[str, SectionConfig]:
    missing = REQUIRED_SECTION_KEYS - set(raw.keys())
    if missing:
        raise DocsBridgeConfigError(
            f"Sections {sorted(missing)} missing in {config_path}",
        )

    sections: Dict[str, SectionConfig] = {}
    for name, definition in raw.items():
        if not isinstance(definition, Mapping):
            raise DocsBridgeConfigError(
                f"Section '{name}' in {config_path} must be a mapping",
            )
        mode = str(definition.get("mode") or _default_mode(name))
        if mode not in ALLOWED_MODES:
            raise DocsBridgeConfigError(
                f"Unsupported mode '{mode}' for section '{name}'",
            )
        target = definition.get("target")
        template = definition.get("target_template")
        marker = definition.get("marker")
        if mode != "skip" and mode != "external" and not target and not template:
            raise DocsBridgeConfigError(
                f"Section '{name}' must define 'target' or 'target_template'",
            )
        if mode == "external" and not definition.get("adapter"):
            raise DocsBridgeConfigError(f"Section '{name}' requires 'adapter' when mode is external")
        insertion = _parse_insertion(definition, name)
        sections[name] = SectionConfig(
            mode=mode,
            target=str(target) if isinstance(target, str) else target,
            target_template=str(template) if isinstance(template, str) else template,
            marker=str(marker) if isinstance(marker, str) else marker,
            insertion=insertion,
            adapter=str(definition.get("adapter")) if definition.get("adapter") else None,
            options=definition.get("options") if isinstance(definition.get("options"), Mapping) else None,
        )
    return sections


def _default_mode(name: str) -> str:
    if name in {
        "architecture_overview",
        "adr_index",
        "rfc_index",
    }:
        return "managed"
    return "file"


def _parse_insertion(definition: Mapping[str, object], section: str) -> Optional[InsertionPolicy]:
    insert_after = definition.get("insert_after_heading")
    insert_before = definition.get("insert_before_marker")
    if insert_after and insert_before:
        raise DocsBridgeConfigError(
            f"Section '{section}' cannot set both insert_after_heading and insert_before_marker",
        )
    if insert_after is not None:
        if not isinstance(insert_after, str) or not insert_after.strip():
            raise DocsBridgeConfigError(
                f"Section '{section}' insert_after_heading must be a non-empty string",
            )
        return InsertionPolicy(kind="after_heading", value=insert_after.strip())
    if insert_before is not None:
        if not isinstance(insert_before, str) or not insert_before.strip():
            raise DocsBridgeConfigError(
                f"Section '{section}' insert_before_marker must be a non-empty string",
            )
        return InsertionPolicy(kind="before_marker", value=insert_before.strip())
    return None

"""Documentation bridge façade combining domain primitives and adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml

from agentcontrol.domain.docs import SectionConfig

_CONFIG_CACHE: Dict[Path, tuple[int, int, DocsBridgeConfig]] = {}

from agentcontrol.domain.docs.aggregate import DocsBridgeAggregate, DocsBridgeContext
from agentcontrol.domain.docs.editor import ENGINE, RegionOperation, ensure_directory
from agentcontrol.domain.docs.value_objects import (
    DocsBridgeConfig,
    DocsBridgeConfigError,
    InsertionPolicy,
)

DEFAULT_CONFIG_RELATIVE = Path(".agentcontrol/config/docs.bridge.yaml")
LEGACY_CONFIG_RELATIVE = Path("agentcontrol/config/docs.bridge.yaml")


class DocsBridgeIOError(RuntimeError):
    """Raised when docs bridge IO operations fail."""


def load_docs_bridge_config(project_root: Path, path: Path | None = None) -> Tuple[DocsBridgeConfig, Path]:
    """Load configuration from disk, defaulting to the packaged template."""

    config_path = (path or (project_root / DEFAULT_CONFIG_RELATIVE)).resolve()
    if not config_path.exists() and path is None:
        legacy_path = (project_root / LEGACY_CONFIG_RELATIVE).resolve()
        if legacy_path.exists():
            config_path = legacy_path
    if config_path.exists():
        stat = config_path.stat()
        cached = _CONFIG_CACHE.get(config_path)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            config = cached[2]
        else:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            config = DocsBridgeConfig.from_dict(raw, config_path=config_path)
            _CONFIG_CACHE[config_path] = (stat.st_mtime_ns, stat.st_size, config)
    else:
        config = DocsBridgeConfig.default()
    return config, config_path


def default_docs_bridge_config(root: str | Path = "docs") -> DocsBridgeConfig:
    """Return default configuration value object."""

    return DocsBridgeConfig.default(root)


def inspect_bridge(
    project_root: Path,
    config: DocsBridgeConfig,
    *,
    config_path: Path,
    include_status: bool = False,
) -> Dict[str, object]:
    aggregate = _build_aggregate(project_root, config, config_path)
    return aggregate.inspect(include_status=include_status)


def diagnose_bridge(
    project_root: Path,
    config: DocsBridgeConfig,
    *,
    config_path: Path,
) -> Dict[str, object]:
    aggregate = _build_aggregate(project_root, config, config_path)
    return aggregate.diagnose()


def update_managed_region(
    file_path: Path,
    marker: str,
    content: Optional[str],
    *,
    insertion: Optional[InsertionPolicy] = None,
) -> bool:
    """Persist managed content, returning True when changes occurred."""

    result = ENGINE.apply(file_path, {marker: RegionOperation(content=content, insertion=insertion)})
    return result.changed


def read_managed_region(file_path: Path, marker: str) -> Optional[str]:
    """Read managed content if present."""

    return ENGINE.read(file_path, marker)


def write_file(path: Path, content: str) -> bool:
    """Write file only when content changes"""

    ensure_directory(path)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def ensure_config(path: Path) -> None:
    """Ensure configuration directory exists."""

    ensure_directory(path)


def _build_aggregate(project_root: Path, config: DocsBridgeConfig, config_path: Path) -> DocsBridgeAggregate:
    context = DocsBridgeContext(
        project_root=project_root.resolve(),
        config=config,
        config_path=config_path.resolve(),
    )
    return DocsBridgeAggregate(context)


__all__ = [
    "DocsBridgeConfig",
    "SectionConfig",
    "DocsBridgeConfigError",
    "DEFAULT_CONFIG_RELATIVE",
    "LEGACY_CONFIG_RELATIVE",
    "load_docs_bridge_config",
    "default_docs_bridge_config",
    "inspect_bridge",
    "diagnose_bridge",
    "update_managed_region",
    "read_managed_region",
    "write_file",
    "ensure_config",
]

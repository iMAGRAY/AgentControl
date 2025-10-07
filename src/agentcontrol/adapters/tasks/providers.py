"""Factory helpers for task providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from agentcontrol.ports.tasks.provider import TaskProvider, TaskProviderError

from .file_provider import FileTaskProvider
from .github_provider import GitHubIssuesProvider
from .jira_provider import JiraTaskProvider


@dataclass(frozen=True)
class ProviderBuildResult:
    provider: TaskProvider
    report_config: Dict[str, Any]


def build_provider_from_config(project_root: Path, config: Dict[str, Any]) -> ProviderBuildResult:
    if "type" not in config or not isinstance(config["type"], str):
        raise TaskProviderError("tasks.sync.config_invalid: missing provider type")
    provider_type = config["type"].strip().lower()

    raw_options = config.get("options", {})
    if not isinstance(raw_options, dict):
        raise TaskProviderError("tasks.sync.config_invalid: options must be object")
    options: Dict[str, Any] = dict(raw_options)

    _normalise_paths(project_root, options)
    _normalise_encryption(provider_type, options)

    if provider_type == "file":
        if "path" not in options:
            raise TaskProviderError(
                "tasks.sync.config_invalid: options.path required for file provider"
            )
        provider = FileTaskProvider(project_root, options)
    elif provider_type == "jira":
        provider = JiraTaskProvider(options)
    elif provider_type == "github":
        provider = GitHubIssuesProvider(options)
    else:
        raise TaskProviderError(f"tasks.sync.provider_not_supported: {provider_type}")

    report_config = {
        "type": config["type"],
        "options": _sanitise_options(options),
    }
    return ProviderBuildResult(provider=provider, report_config=report_config)


def _normalise_paths(project_root: Path, options: Dict[str, Any]) -> None:
    for key in ("path", "snapshot_path"):
        value = options.get(key)
        if not value:
            continue
        candidate = Path(str(value))
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        options[key] = str(candidate)


def _normalise_encryption(provider_type: str, options: Dict[str, Any]) -> None:
    encryption = options.get("encryption")
    snapshot_encryption = options.get("snapshot_encryption")

    if provider_type == "file":
        if encryption is not None and not isinstance(encryption, dict):
            raise TaskProviderError("tasks.sync.config_invalid: encryption must be object")
        if options.get("encrypted") and encryption is None:
            options["encryption"] = {"mode": "xor", "key": options.get("key"), "key_env": options.get("key_env")}
        options.pop("encrypted", None)
        options.pop("key", None)
        options.pop("key_env", None)
        return

    # remote providers
    if snapshot_encryption is not None and not isinstance(snapshot_encryption, dict):
        raise TaskProviderError("tasks.sync.config_invalid: snapshot_encryption must be object")
    if encryption and isinstance(encryption, dict):
        # allow using `encryption` for snapshot providers
        options.setdefault("snapshot_encryption", encryption)
    if options.get("snapshot_encrypted") and options.get("snapshot_encryption") is None:
        options["snapshot_encryption"] = {
            "mode": "xor",
            "key": options.get("snapshot_key"),
            "key_env": options.get("snapshot_key_env"),
        }
    options.pop("snapshot_encrypted", None)
    options.pop("snapshot_key", None)
    options.pop("snapshot_key_env", None)


def _sanitise_options(options: Dict[str, Any]) -> Dict[str, Any]:
    def _mask(value: Any) -> Any:
        if isinstance(value, dict):
            masked: Dict[str, Any] = {}
            for key, item in value.items():
                if key in {"key", "snapshot_key"} and item:
                    masked[key] = "***"
                else:
                    masked[key] = _mask(item)
            return masked
        if isinstance(value, list):
            return [_mask(item) for item in value]
        return value

    return _mask(options)


__all__ = ["ProviderBuildResult", "build_provider_from_config"]

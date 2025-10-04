"""Self-update utilities for AgentControl installations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packaging.version import Version, InvalidVersion

from agentcontrol.settings import RuntimeSettings
from agentcontrol.utils.telemetry import record_event

PYPI_URL = "https://pypi.org/pypi/agentcontrol/json"
STATE_FILENAME = "update.json"
CACHE_ENV = "AGENTCONTROL_AUTO_UPDATE_CACHE"
CHECK_INTERVAL = timedelta(hours=6)


@dataclass
class UpdateState:
    last_checked: datetime | None = None
    latest_version: str | None = None
    status: str | None = None

    @classmethod
    def from_file(cls, path: Path) -> "UpdateState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls()
        last_checked = None
        if ts := data.get("last_checked"):
            try:
                last_checked = datetime.fromisoformat(ts)
            except ValueError:
                last_checked = None
        return cls(
            last_checked=last_checked,
            latest_version=data.get("latest_version"),
            status=data.get("status"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "latest_version": self.latest_version,
            "status": self.status,
        }


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _falsy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"0", "false", "no", "off"}


def _is_dev_environment() -> bool:
    try:
        repo_root = Path(__file__).resolve().parents[3]
    except IndexError:
        return False
    if (repo_root / ".git").exists():
        if _truthy(os.environ.get("AGENTCONTROL_ALLOW_AUTO_UPDATE_IN_DEV")):
            return False
        return True
    return False


def _state_path(settings: RuntimeSettings) -> Path:
    return settings.state_dir / STATE_FILENAME


def _load_state(settings: RuntimeSettings) -> UpdateState:
    return UpdateState.from_file(_state_path(settings))


def _store_state(settings: RuntimeSettings, state: UpdateState) -> None:
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _fetch_remote_version() -> str | None:
    if _truthy(os.environ.get("AGENTCONTROL_FORCE_AUTO_UPDATE_FAILURE")):
        return None
    import urllib.request
    import urllib.error

    request = urllib.request.Request(PYPI_URL, headers={"User-Agent": "agentcontrol-updater"})
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):  # pragma: no cover - network failure
        return None
    releases = payload.get("releases", {})
    versions = [v for v, files in releases.items() if files]
    if not versions:
        return None
    try:
        return str(max((Version(v) for v in versions)))
    except InvalidVersion:
        return None


def _parse_version(value: str) -> Version | None:
    try:
        return Version(value)
    except InvalidVersion:
        return None


def _determine_update_mode() -> str:
    env = os.environ.get("AGENTCONTROL_AUTO_UPDATE_MODE", "pip")
    return env if env in {"pip", "pipx"} else "pip"


def _perform_update(mode: str) -> subprocess.CompletedProcess[bytes]:
    if mode == "pipx":
        command = ["pipx", "install", "agentcontrol", "--force"]
    else:
        command = [sys.executable, "-m", "pip", "install", "--upgrade", "agentcontrol"]
    return subprocess.run(command, capture_output=True)


def _install_local_package(path: Path, mode: str) -> subprocess.CompletedProcess[bytes]:
    if mode == "pipx":
        command = ["pipx", "install", str(path), "--force"]
    else:
        command = [sys.executable, "-m", "pip", "install", "--upgrade", str(path)]
    return subprocess.run(command, capture_output=True)


def _select_cached_release(cache_dir: Path | None, current: Version | None) -> tuple[Path, Version] | None:
    if cache_dir is None or not cache_dir.exists() or not cache_dir.is_dir():
        return None
    candidates: list[tuple[Version, Path]] = []
    for entry in cache_dir.iterdir():
        if not entry.is_file():
            continue
        version = _extract_version_from_filename(entry.name)
        if version is None:
            continue
        if current is not None and version < current:
            continue
        candidates.append((version, entry))
    if not candidates:
        return None
    version, path = max(candidates, key=lambda item: item[0])
    return path, version


def _extract_version_from_filename(filename: str) -> Version | None:
    # Wheel: agentcontrol-<version>-py3-none-any.whl
    if filename.startswith("agentcontrol-"):
        match = re.match(r"agentcontrol-([^-]+)", filename)
        if match:
            return _parse_version(match.group(1))
    return None


def maybe_auto_update(settings: RuntimeSettings, current_version: str, *, command: str | None = None, pipeline: str | None = None) -> None:
    if _is_dev_environment():
        return

    if _truthy(os.environ.get("AGENTCONTROL_DISABLE_AUTO_UPDATE")) or _falsy(os.environ.get("AGENTCONTROL_AUTO_UPDATE", "1")):
        return

    if command in {"self-update"}:
        return

    state = _load_state(settings)
    now = datetime.now(timezone.utc)
    remote_version: str | None = None

    use_cache = False
    if state.last_checked and now - state.last_checked < CHECK_INTERVAL:
        use_cache = True
        if state.status == "error":
            record_event(
                settings,
                "auto-update",
                {
                    "status": "recent_failure",
                    "command": command,
                    "pipeline": pipeline,
                },
            )
            return
        if state.latest_version:
            remote_version = state.latest_version

    if remote_version is None:
        remote_version = _fetch_remote_version()
        if remote_version is None:
            cache_dir_value = os.environ.get(CACHE_ENV)
            cache_dir = Path(cache_dir_value).expanduser() if cache_dir_value else None
            current_version_parsed = _parse_version(current_version)
            cached = _select_cached_release(cache_dir, current_version_parsed)
            if cached is None:
                state.last_checked = now
                state.latest_version = None
                state.status = "error"
                _store_state(settings, state)
                record_event(settings, "auto-update", {"status": "fetch_failed", "command": command, "pipeline": pipeline})
                return

            path, cached_version = cached
            mode = _determine_update_mode()
            record_event(
                settings,
                "auto-update",
                {
                    "status": "fallback_attempt",
                    "mode": mode,
                    "cache_path": str(path),
                    "current": current_version,
                    "cached": str(cached_version),
                    "command": command,
                    "pipeline": pipeline,
                },
            )
            result = _install_local_package(path, mode)
            status = "fallback_succeeded" if result.returncode == 0 else "fallback_failed"
            record_event(
                settings,
                "auto-update",
                {
                    "status": status,
                    "mode": mode,
                    "cache_path": str(path),
                    "exit_code": result.returncode,
                    "current": current_version,
                    "cached": str(cached_version),
                    "command": command,
                    "pipeline": pipeline,
                },
            )
            if result.returncode == 0:
                state.last_checked = now
                state.latest_version = str(cached_version)
                state.status = "local"
                _store_state(settings, state)
                sys.stderr.write("agentcall: auto-updated from local cache. Please re-run your command.\n")
                raise SystemExit(0)

            state.last_checked = now
            state.latest_version = None
            state.status = "error"
            _store_state(settings, state)
            sys.stderr.write(
                "agentcall: local cache update failed. Run `agentcall self-update --mode pipx` or `pip install --upgrade agentcontrol`.\n"
            )
            return
        state.last_checked = now
        state.latest_version = remote_version
        state.status = "ok"
        _store_state(settings, state)

    current = _parse_version(current_version)
    remote = _parse_version(remote_version)
    if current is None or remote is None:
        record_event(
            settings,
            "auto-update",
            {"status": "invalid_version", "current": current_version, "remote": remote_version},
        )
        return

    if remote <= current:
        if not use_cache:
            record_event(
                settings,
                "auto-update",
                {"status": "up_to_date", "current": current_version, "remote": remote_version},
            )
        return

    mode = _determine_update_mode()
    result = _perform_update(mode)
    status = "succeeded" if result.returncode == 0 else "failed"
    record_event(
        settings,
        "auto-update",
        {
            "status": status,
            "mode": mode,
            "exit_code": result.returncode,
            "current": current_version,
            "remote": remote_version,
            "command": command,
            "pipeline": pipeline,
        },
    )

    if result.returncode == 0:
        sys.stderr.write("agentcall: auto-updated to latest version. Please re-run your command.\n")
        raise SystemExit(0)

    sys.stderr.write(
        "agentcall: auto-update failed. Run `agentcall self-update --mode pipx` or `pip install --upgrade agentcontrol`.\n"
    )

"""Extension management services."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
import shutil
import subprocess
from typing import Any, Iterable
from uuid import uuid4

from agentcontrol.domain.project import ProjectId

from .schema import iter_schema_errors

CATALOG_FILENAME = "catalog.json"
DEFAULT_MANIFEST = {
    "name": "",
    "version": "0.1.0",
    "description": "Describe extension purpose.",
    "entry_points": {
        "playbooks": [],
        "hooks": [],
        "mcp": [],
    },
    "compatibility": {
        "cli": ">=0.5.1",
    },
}

EXTENSION_SUBDIRS = (
    "playbooks",
    "hooks",
    "mcp",
)


@dataclass
class CatalogEntry:
    name: str
    version: str
    path: str
    description: str
    source: str | None = None

    @classmethod
    def from_manifest(
        cls,
        root: Path,
        manifest: dict[str, Any],
        *,
        source: str | None = None,
    ) -> "CatalogEntry":
        return cls(
            name=manifest["name"],
            version=manifest["version"],
            path=str(root),
            description=manifest.get("description", ""),
            source=source,
        )


class Catalog:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: dict[str, CatalogEntry] = {}

    def load(self) -> None:
        if not self._path.exists():
            self._entries = {}
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._entries = {
            item["name"]: CatalogEntry(
                name=item["name"],
                version=item.get("version", "unknown"),
                path=item.get("path", ""),
                description=item.get("description", ""),
                source=item.get("source"),
            )
            for item in data.get("extensions", [])
        }

    def save(self) -> None:
        payload = {
            "extensions": [asdict(entry) for entry in sorted(self._entries.values(), key=lambda e: e.name)]
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def list_entries(self) -> Iterable[CatalogEntry]:
        return sorted(self._entries.values(), key=lambda e: e.name)

    def register(self, entry: CatalogEntry) -> None:
        self._entries[entry.name] = entry

    def remove(self, name: str) -> bool:
        return self._entries.pop(name, None) is not None

    def has(self, name: str) -> bool:
        return name in self._entries


class ExtensionService:
    def __init__(self, project_id: ProjectId) -> None:
        self._root = project_id.root
        self._extensions_dir = self._root / "extensions"
        self._extensions_dir.mkdir(parents=True, exist_ok=True)
        self._catalog_path = self._extensions_dir / CATALOG_FILENAME
        self._catalog = Catalog(self._catalog_path)
        self._catalog.load()

    @property
    def extensions_dir(self) -> Path:
        return self._extensions_dir

    def init(self, name: str, *, force: bool = False) -> Path:
        target = self._extensions_dir / name
        if target.exists():
            if not force:
                raise FileExistsError(f"Extension '{name}' already exists at {target}")
        target.mkdir(parents=True, exist_ok=True)
        for subdir in EXTENSION_SUBDIRS:
            (target / subdir).mkdir(parents=True, exist_ok=True)
        manifest_path = target / "manifest.json"
        manifest = json.loads(json.dumps(DEFAULT_MANIFEST))
        manifest["name"] = name
        manifest["description"] = f"{name} extension"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        readme = target / "README.md"
        if not readme.exists():
            readme.write_text(f"# Extension `{name}`\n\nDescribe goals and playbooks here.\n", encoding="utf-8")
        return target

    def add(
        self,
        name: str,
        *,
        source: Path | None = None,
        git_url: str | None = None,
        ref: str | None = None,
    ) -> CatalogEntry:
        if source and git_url:
            raise ValueError("--source and --git are mutually exclusive")

        target = self._extensions_dir / name
        source_path = Path(source).resolve() if source else None
        source_hint = git_url or (str(source_path) if source_path else None)

        if source or git_url:
            if target.exists():
                raise FileExistsError(f"Extension '{name}' already exists at {target}")
            staging = self._create_staging_dir(name)
            try:
                if git_url:
                    self._clone_git_repository(git_url, staging, ref=ref)
                else:
                    assert source_path is not None
                    self._copy_local_extension(source_path, staging)
                manifest = self._read_manifest(staging)
                if target.exists():
                    raise FileExistsError(f"Extension '{name}' already exists at {target}")
                staging.rename(target)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        else:
            if not target.exists():
                raise FileNotFoundError(f"Extension '{name}' not found under {self._extensions_dir}")
            manifest = self._read_manifest(target)

        manifest = self._read_manifest(target)
        entry = CatalogEntry.from_manifest(target, manifest, source=source_hint)
        self._catalog.register(entry)
        self._catalog.save()
        return entry

    def list(self) -> list[CatalogEntry]:
        return list(self._catalog.list_entries())

    def remove(self, name: str, *, purge: bool = False) -> bool:
        removed = self._catalog.remove(name)
        if removed:
            self._catalog.save()
            if purge:
                target = self._extensions_dir / name
                if target.exists():
                    shutil.rmtree(target)
        return removed

    def lint(self, name: str | None = None) -> dict[str, Any]:
        errors: list[str] = []
        targets: list[tuple[str, Path]]
        if name:
            targets = [(name, self._extensions_dir / name)]
        else:
            targets = [(p.name, p) for p in sorted(self._extensions_dir.iterdir()) if p.is_dir() and (p / "manifest.json").exists()]
        manifests: list[dict[str, Any]] = []
        for ext_name, root in targets:
            try:
                manifest = self._read_manifest(root)
            except FileNotFoundError:
                errors.append(f"extension {ext_name} is missing manifest.json")
                continue
            except ValueError as exc:
                errors.append(f"extension {ext_name} manifest invalid JSON: {exc}")
                continue
            manifest_errors = self._validate_manifest(ext_name, manifest)
            if manifest_errors:
                errors.extend(manifest_errors)
            manifests.append({"name": ext_name, "manifest": manifest})
        return {"errors": errors, "manifests": manifests}

    def publish(self, *, dry_run: bool = False) -> Path:
        entries = [asdict(entry) for entry in self._catalog.list_entries()]
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "extensions": entries,
        }
        reports_dir = self._root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        output = reports_dir / "extensions.json"
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output

    def _read_manifest(self, root: Path) -> dict[str, Any]:
        manifest_path = root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest.json not found in {root}")
        raw = manifest_path.read_text(encoding="utf-8")
        try:
            manifest = json.loads(raw)
        except JSONDecodeError as exc:
            raise ValueError(f"{exc.msg} (line {exc.lineno} column {exc.colno})") from exc
        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be a JSON object")
        return manifest

    def _validate_manifest(self, name: str, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for path, message in iter_schema_errors(manifest):
            location = path or "<root>"
            errors.append(f"manifest {name} schema violation at {location}: {message}")
        manifest_name = manifest.get("name")
        if isinstance(manifest_name, str) and manifest_name != name:
            errors.append(f"manifest name mismatch: directory={name} manifest={manifest_name}")
        return errors

    def _create_staging_dir(self, name: str) -> Path:
        staging = self._extensions_dir / f".{name}.staging-{uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        return staging

    def _copy_local_extension(self, source: Path, staging: Path) -> None:
        if not source.exists():
            raise FileNotFoundError(f"Source path {source} does not exist")
        if not source.is_dir():
            raise NotADirectoryError(f"Source path {source} must be a directory")
        shutil.copytree(source, staging, dirs_exist_ok=True)

    def _clone_git_repository(self, git_url: str, staging: Path, *, ref: str | None = None) -> None:
        clone_cmd = ["git", "clone", "--depth", "1"]
        if ref:
            clone_cmd += ["--branch", ref]
        clone_cmd += [git_url, str(staging)]
        try:
            subprocess.run(clone_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Failed to clone extension from {git_url}: {exc.stderr.decode().strip() or exc.stdout.decode().strip()}"
            ) from exc
        git_dir = staging / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir, ignore_errors=True)


def ensure_extensions_dir(project_id: ProjectId) -> Path:
    target = project_id.root / "extensions"
    target.mkdir(parents=True, exist_ok=True)
    (target / ".keep").touch()
    return target

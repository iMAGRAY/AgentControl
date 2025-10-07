"""Services for managing the AgentControl sample gallery."""

from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources as pkg_resources
from pathlib import Path
from typing import Iterator, List, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

GALLERY_RELATIVE_ROOT = Path("examples/gallery")
GALLERY_METADATA_FILENAME = "gallery.json"
MAX_PACKAGE_BYTES = 30 * 1024 * 1024  # 30 MiB
PACKAGE_RESOURCE_PACKAGE = "agentcontrol.resources.gallery"


class GalleryError(RuntimeError):
    """Raised when gallery metadata or export fails."""


@dataclass(frozen=True)
class GallerySample:
    sample_id: str
    name: str
    description: str
    tags: Sequence[str]
    source_relative: str
    origin: str  # "local" | "resource"
    estimated_size_kb: int


@dataclass(frozen=True)
class GalleryExportResult:
    sample: GallerySample
    output_path: Path
    size_bytes: int


class GalleryService:
    """Expose gallery metadata and export utilities."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._package_root = pkg_resources.files(PACKAGE_RESOURCE_PACKAGE)
        self._metadata_origin, self._metadata_payload = self._load_metadata()

    def list_samples(self) -> List[GallerySample]:
        samples: List[GallerySample] = []
        for entry in self._metadata_payload.get("samples", []):
            try:
                sample = self._sample_from_entry(entry)
            except GalleryError:
                continue
            samples.append(sample)
        return samples

    def export_sample(self, sample_id: str, destination: Path, *, archive: bool = True) -> GalleryExportResult:
        sample = self._resolve_sample(sample_id)

        if not archive:
            destination = destination.expanduser()
            if destination.exists():
                if destination.is_dir():
                    destination = destination / sample.sample_id
                else:
                    raise GalleryError(f"destination already exists: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with self._open_sample_dir(sample) as source_dir:
                shutil.copytree(source_dir, destination)
            size_bytes = _directory_size(destination)
            if size_bytes > MAX_PACKAGE_BYTES:
                raise GalleryError(f"copied directory exceeds 30 MiB ({size_bytes} bytes)")
            return GalleryExportResult(sample=sample, output_path=destination, size_bytes=size_bytes)

        destination = destination.expanduser()
        if destination.is_dir() or destination.suffix == "":
            destination = (destination / f"{sample.sample_id}").with_suffix(".zip")
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp_dir, self._open_sample_dir(sample) as source_dir:
            tmp_path = Path(tmp_dir) / f"{sample.sample_id}.zip"
            with ZipFile(tmp_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive_file:
                for candidate in sorted(source_dir.rglob("*")):
                    relative = candidate.relative_to(source_dir)
                    arcname = f"{sample.sample_id}/{relative.as_posix()}"
                    if candidate.is_dir():
                        continue
                    archive_file.write(candidate, arcname)
            size_bytes = tmp_path.stat().st_size
            if size_bytes > MAX_PACKAGE_BYTES:
                raise GalleryError(
                    f"archive exceeds maximum size (30 MiB). size={size_bytes} bytes, sample={sample.sample_id}"
                )
            shutil.move(str(tmp_path), destination)

        return GalleryExportResult(sample=sample, output_path=destination, size_bytes=size_bytes)

    def _resolve_sample(self, sample_id: str) -> GallerySample:
        for sample in self.list_samples():
            if sample.sample_id == sample_id:
                return sample
        raise GalleryError(f"sample '{sample_id}' not found")

    def _load_metadata(self) -> tuple[str, dict]:
        local_metadata = self._project_root / GALLERY_RELATIVE_ROOT / GALLERY_METADATA_FILENAME
        if local_metadata.exists():
            try:
                data = json.loads(local_metadata.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise GalleryError(f"gallery metadata invalid JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise GalleryError("gallery metadata must be a JSON object")
            return "local", data

        metadata_file = self._package_root / GALLERY_METADATA_FILENAME
        try:
            data = json.loads(metadata_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GalleryError(f"packaged gallery metadata invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise GalleryError("gallery metadata must be a JSON object")
        return "resource", data

    def _sample_from_entry(self, entry: dict) -> GallerySample:
        if not isinstance(entry, dict):
            raise GalleryError("gallery entry must be an object")
        sample_id = str(entry.get("id", "")).strip()
        if not sample_id:
            raise GalleryError("gallery entry missing 'id'")
        name = str(entry.get("name", "")).strip() or sample_id
        description = str(entry.get("description", "")).strip()
        tags_value = entry.get("tags", [])
        tags = [str(tag).strip() for tag in tags_value] if isinstance(tags_value, list) else []
        source_relative = str(entry.get("source", "")).strip()
        if not source_relative:
            raise GalleryError(f"gallery entry {sample_id} missing 'source'")
        estimated_size = int(entry.get("estimated_size_kb", 0) or 0)
        with self._open_sample_dir_raw(source_relative) as resolved:
            if not resolved.exists():
                raise GalleryError(f"gallery source '{source_relative}' missing")
        return GallerySample(
            sample_id=sample_id,
            name=name,
            description=description,
            tags=tags,
            source_relative=source_relative,
            origin=self._metadata_origin,
            estimated_size_kb=estimated_size,
        )

    @contextmanager
    def _open_sample_dir(self, sample: GallerySample) -> Iterator[Path]:
        with self._open_sample_dir_raw(sample.source_relative) as path:
            yield path

    @contextmanager
    def _open_sample_dir_raw(self, relative: str) -> Iterator[Path]:
        if self._metadata_origin == "local":
            source_path = (self._project_root / GALLERY_RELATIVE_ROOT / relative).resolve()
            if not source_path.exists():
                raise GalleryError(f"gallery source not found: {source_path}")
            yield source_path
            return
        traversable = self._package_root.joinpath(relative)
        if not traversable.exists():
            raise GalleryError(f"packaged gallery source not found: {relative}")
        with pkg_resources.as_file(traversable) as temp_path:
            yield Path(temp_path)


def _directory_size(root: Path) -> int:
    total = 0
    for candidate in root.rglob("*"):
        if candidate.is_file():
            total += candidate.stat().st_size
    return total


__all__ = ["GalleryService", "GallerySample", "GalleryExportResult", "GalleryError"]

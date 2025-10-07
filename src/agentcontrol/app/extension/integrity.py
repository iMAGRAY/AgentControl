"""Checksum and packaging integrity helpers for extension templates."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_EXTENSIONS_ROOT = DEFAULT_PROJECT_ROOT / "examples" / "extensions"
DEFAULT_SOURCES_FILE = DEFAULT_PROJECT_ROOT / "src/agentcontrol.egg-info/SOURCES.txt"
CHECKSUM_FILENAME = "extension.sha256"
BANNED_PACKAGING_PATTERNS: tuple[str, ...] = (".test_place",)


@dataclass
class ExtensionChecksumReport:
    name: str
    path: Path
    checksum_path: Path | None
    expected: str | None
    actual: str
    status: str

    def to_dict(self, project_root: Path) -> dict[str, str | None]:
        def _relative_or_str(value: Path | None) -> str | None:
            if value is None:
                return None
            try:
                return value.relative_to(project_root).as_posix()
            except ValueError:
                return str(value)

        return {
            "name": self.name,
            "path": _relative_or_str(self.path),
            "checksum": _relative_or_str(self.checksum_path),
            "expected": self.expected,
            "actual": self.actual,
            "status": self.status,
        }


@dataclass
class ExtensionIntegritySummary:
    status: str
    extensions: list[ExtensionChecksumReport]
    packaging_issues: list[str]

    def to_dict(self, project_root: Path) -> dict[str, object]:
        return {
            "status": self.status,
            "extensions": [report.to_dict(project_root) for report in self.extensions],
            "packaging_issues": self.packaging_issues,
        }


def iter_extension_dirs(root: Path) -> Iterable[Path]:
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and (entry / "manifest.json").exists():
            yield entry


def compute_checksum(extension_dir: Path) -> str:
    digest = sha256()
    for candidate in sorted(extension_dir.rglob("*")):
        if not candidate.is_file() or candidate.name == CHECKSUM_FILENAME:
            continue
        digest.update(candidate.relative_to(extension_dir).as_posix().encode("utf-8"))
        digest.update(candidate.read_bytes())
    return digest.hexdigest()


def _load_expected(checksum_path: Path) -> str:
    return checksum_path.read_text(encoding="utf-8").strip()


def _collect_packaging_issues(
    *,
    sources_file: Path | None,
    project_root: Path,
    expected_paths: Iterable[Path],
    banned_patterns: Sequence[str],
) -> list[str]:
    if sources_file is None:
        return []
    if not sources_file.exists():
        return [f"sources file missing: {sources_file}"]

    normalized_lines = [line.strip().replace("\\", "/") for line in sources_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    issues: list[str] = []
    for pattern in banned_patterns:
        for line in normalized_lines:
            if pattern in line:
                issues.append(f"banned path '{line}' present (pattern '{pattern}')")
    normalized_set = set(normalized_lines)
    for target in expected_paths:
        try:
            relative = target.relative_to(project_root).as_posix()
        except ValueError:
            # Skip verification for paths outside the project root (test fixtures).
            continue
        if relative not in normalized_set:
            issues.append(f"missing from SOURCES.txt: {relative}")
    return issues


def verify_extensions(
    *,
    root: Path = DEFAULT_EXTENSIONS_ROOT,
    sources_file: Path | None = DEFAULT_SOURCES_FILE,
    project_root: Path | None = None,
    banned_patterns: Sequence[str] = BANNED_PACKAGING_PATTERNS,
) -> ExtensionIntegritySummary:
    if project_root is None:
        project_root = DEFAULT_PROJECT_ROOT

    reports: list[ExtensionChecksumReport] = []
    expected_paths: list[Path] = []
    for extension_dir in iter_extension_dirs(root):
        checksum_path = extension_dir / CHECKSUM_FILENAME
        actual = compute_checksum(extension_dir)
        if checksum_path.exists():
            expected = _load_expected(checksum_path)
            status = "ok" if expected == actual else "mismatch"
            expected_paths.append(checksum_path)
        else:
            expected = None
            status = "missing"
        reports.append(
            ExtensionChecksumReport(
                name=extension_dir.name,
                path=extension_dir.resolve(),
                checksum_path=checksum_path.resolve() if checksum_path.exists() else None,
                expected=expected,
                actual=actual,
                status=status,
            )
        )

    packaging_issues = _collect_packaging_issues(
        sources_file=sources_file,
        project_root=project_root,
        expected_paths=expected_paths,
        banned_patterns=banned_patterns,
    )

    has_checksum_issues = any(report.status != "ok" for report in reports)
    status = "ok" if not has_checksum_issues and not packaging_issues else "error"
    return ExtensionIntegritySummary(status=status, extensions=reports, packaging_issues=packaging_issues)


__all__ = [
    "ExtensionChecksumReport",
    "ExtensionIntegritySummary",
    "verify_extensions",
    "compute_checksum",
    "iter_extension_dirs",
    "DEFAULT_EXTENSIONS_ROOT",
    "DEFAULT_SOURCES_FILE",
    "DEFAULT_PROJECT_ROOT",
    "BANNED_PACKAGING_PATTERNS",
    "CHECKSUM_FILENAME",
]

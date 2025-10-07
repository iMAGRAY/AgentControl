"""Knowledge coverage lint service."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from agentcontrol.app.docs.utils import extract_summary, iso_mtime, safe_relpath, utc_now_iso

DEFAULT_REPORT_PATH = Path("reports/docs_coverage.json")
TUTORIAL_SUMMARY_MIN_LENGTH = 80
COLLECTION_SUMMARY_MIN_LENGTH = 40
DEFAULT_EXTERNAL_TIMEOUT = 5.0
_LINK_PATTERN = re.compile(r"\[[^\]]*]\(([^)]+)\)")


@dataclass
class KnowledgeIssue:
    code: str
    path: str
    message: str
    severity: str  # "warning" | "error"

    def as_dict(self) -> dict:
        return asdict(self)


class KnowledgeLintService:
    """Analyse knowledge assets (tutorials/ADR/RFC) and report coverage issues."""

    def __init__(self, *, tutorial_summary_min_length: int = TUTORIAL_SUMMARY_MIN_LENGTH) -> None:
        self._tutorial_summary_min_length = tutorial_summary_min_length

    def lint(
        self,
        project_root: Path,
        *,
        output_path: Optional[Path] = None,
        max_age_hours: Optional[float] = None,
        validate_external: bool = False,
        external_timeout: float = DEFAULT_EXTERNAL_TIMEOUT,
    ) -> Dict[str, object]:
        project_root = project_root.resolve()
        docs_root = project_root / "docs"
        tutorials_root = docs_root / "tutorials"
        if not tutorials_root.exists():
            raise FileNotFoundError(f"{tutorials_root} not found")

        issues: List[KnowledgeIssue] = []
        files_meta: List[Tuple[Path, datetime]] = []

        (
            tutorials_stats,
            tutorial_index,
            tutorial_issues,
            tutorial_files,
            external_targets,
        ) = self._lint_tutorials(project_root, tutorials_root)
        issues.extend(tutorial_issues)
        files_meta.extend(tutorial_files)

        adr_stats, adr_index, adr_issues, adr_files, adr_external = self._lint_collection(
            project_root,
            docs_root / "adr",
            collection_name="adr",
            issue_prefix="KNOWLEDGE_ADR",
            summary_min_length=COLLECTION_SUMMARY_MIN_LENGTH,
        )
        issues.extend(adr_issues)
        files_meta.extend(adr_files)
        external_targets.update(adr_external)

        rfc_stats, rfc_index, rfc_issues, rfc_files, rfc_external = self._lint_collection(
            project_root,
            docs_root / "rfc",
            collection_name="rfc",
            issue_prefix="KNOWLEDGE_RFC",
            summary_min_length=COLLECTION_SUMMARY_MIN_LENGTH,
        )
        issues.extend(rfc_issues)
        files_meta.extend(rfc_files)
        external_targets.update(rfc_external)

        if max_age_hours is not None and max_age_hours >= 0:
            now = datetime.now(timezone.utc)
            threshold = timedelta(hours=max_age_hours)
            stale_cutoff = now - threshold
            for path, mtime in files_meta:
                if mtime < stale_cutoff:
                    age_hours = (now - mtime).total_seconds() / 3600
                    issues.append(
                        KnowledgeIssue(
                            code="KNOWLEDGE_FILE_STALE",
                            path=safe_relpath(path, project_root),
                            message=f"Knowledge file stale ({age_hours:.1f}h > {max_age_hours}h)",
                            severity="error",
                        )
                    )

        validated_external_links = 0
        if validate_external and external_targets:
            for link, origin_path in sorted(external_targets.items()):
                validated_external_links += 1
                if not self._check_external_link(link, timeout=external_timeout):
                    issues.append(
                        KnowledgeIssue(
                            code="KNOWLEDGE_EXTERNAL_UNREACHABLE",
                            path=origin_path,
                            message=f"External link unreachable: {link}",
                            severity="error",
                        )
                    )

        error_count = sum(1 for issue in issues if issue.severity == "error")
        warning_count = sum(1 for issue in issues if issue.severity == "warning")
        status = "error" if error_count else ("warning" if warning_count else "ok")

        report = {
            "generated_at": utc_now_iso(),
            "project_root": str(project_root),
            "tutorials": tutorials_stats,
            "index": tutorial_index,
            "collections": {
                "tutorials": tutorials_stats | {"index": tutorial_index},
                "adr": adr_stats | {"index": adr_index},
                "rfc": rfc_stats | {"index": rfc_index},
            },
            "validated_external_links": validated_external_links if validate_external else 0,
            "issues": [issue.as_dict() for issue in issues],
            "status": status,
        }

        destination = output_path or DEFAULT_REPORT_PATH
        if not destination.is_absolute():
            destination = project_root / destination
        report["report_path"] = str(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report

    # ------------------------------------------------------------------
    # Tutorials
    # ------------------------------------------------------------------

    def _lint_tutorials(
        self,
        project_root: Path,
        tutorials_root: Path,
    ) -> Tuple[Dict[str, object], Dict[str, object], List[KnowledgeIssue], List[Tuple[Path, datetime]]]:
        tutorials = self._discover_markdown(tutorials_root)
        issues: List[KnowledgeIssue] = []
        files_meta: List[Tuple[Path, datetime]] = []
        checked_links = 0
        external_links = 0
        insecure_links = 0
        with_title = 0
        with_summary = 0
        external_targets: dict[str, str] = {}

        for tutorial in tutorials:
            text = tutorial.read_text(encoding="utf-8")
            rel_path = safe_relpath(tutorial, project_root)
            files_meta.append((tutorial, datetime.fromtimestamp(tutorial.stat().st_mtime, tz=timezone.utc)))

            if self._has_heading(text):
                with_title += 1
            else:
                issues.append(
                    KnowledgeIssue(
                        code="KNOWLEDGE_MISSING_TITLE",
                        path=rel_path,
                        message="Top-level heading (# ...) not found",
                        severity="error",
                    )
                )

            summary = extract_summary(text)
            if len(summary.strip()) >= self._tutorial_summary_min_length:
                with_summary += 1
            else:
                issues.append(
                    KnowledgeIssue(
                        code="KNOWLEDGE_SHORT_SUMMARY",
                        path=rel_path,
                        message=f"First paragraph shorter than {self._tutorial_summary_min_length} characters",
                        severity="warning",
                    )
                )

            for target in self._iter_local_links(text):
                normalised = self._normalise_target(target)
                if not normalised:
                    continue
                checked_links += 1
                if not self._link_exists(project_root, tutorial, normalised):
                    issues.append(
                        KnowledgeIssue(
                            code="KNOWLEDGE_BROKEN_LINK",
                            path=rel_path,
                            message=f"Broken link: {target}",
                            severity="error",
                        )
                    )

            for link in self._iter_external_links(text):
                external_links += 1
                if link.startswith("http://"):
                    insecure_links += 1
                    issues.append(
                        KnowledgeIssue(
                            code="KNOWLEDGE_INSECURE_LINK",
                            path=rel_path,
                            message=f"Insecure external link uses HTTP: {link}",
                            severity="warning",
                        )
                    )
                external_targets.setdefault(link, rel_path)

        index_report, index_issues = self._lint_index(
            root=tutorials_root,
            entries=tutorials,
            project_root=project_root,
            orphan_code="KNOWLEDGE_ORPHAN_TUTORIAL",
        )
        issues.extend(index_issues)

        stats = {
            "count": len(tutorials),
            "with_title": with_title,
            "with_summary": with_summary,
            "checked_links": checked_links,
            "checked_external_links": external_links,
            "insecure_links": insecure_links,
            "latest_modified_at": iso_mtime(max(tutorials, key=lambda p: p.stat().st_mtime)) if tutorials else None,
        }
        return stats, index_report, issues, files_meta, external_targets

    # ------------------------------------------------------------------
    # Generic collections (ADR/RFC)
    # ------------------------------------------------------------------

    def _lint_collection(
        self,
        project_root: Path,
        collection_root: Path,
        *,
        collection_name: str,
        issue_prefix: str,
        summary_min_length: int,
    ) -> Tuple[
        Dict[str, object],
        Dict[str, object],
        List[KnowledgeIssue],
        List[Tuple[Path, datetime]],
        dict[str, str],
    ]:
        if not collection_root.exists():
            return (
                {"count": 0, "with_title": 0, "with_summary": 0, "latest_modified_at": None},
                {"path": None, "listed": 0, "expected": 0},
                [],
                [],
                {},
            )

        entries = self._discover_markdown(collection_root)
        issues: List[KnowledgeIssue] = []
        files_meta: List[Tuple[Path, datetime]] = []
        with_title = 0
        with_summary = 0
        external_targets: dict[str, str] = {}

        for entry in entries:
            text = entry.read_text(encoding="utf-8")
            rel_path = safe_relpath(entry, project_root)
            files_meta.append((entry, datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)))

            if self._has_heading(text):
                with_title += 1
            else:
                issues.append(
                    KnowledgeIssue(
                        code=f"{issue_prefix}_MISSING_TITLE",
                        path=rel_path,
                        message=f"{collection_name.upper()} entry missing leading heading",
                        severity="error",
                    )
                )

            summary = extract_summary(text, limit=summary_min_length)
            if len(summary.strip()) >= summary_min_length:
                with_summary += 1
            else:
                issues.append(
                    KnowledgeIssue(
                        code=f"{issue_prefix}_SHORT_SUMMARY",
                        path=rel_path,
                        message=f"{collection_name.upper()} summary shorter than {summary_min_length} characters",
                        severity="warning",
                    )
                )

            for link in self._iter_external_links(text):
                external_targets.setdefault(link, rel_path)

        index_report, index_issues = self._lint_index(
            root=collection_root,
            entries=entries,
            project_root=project_root,
            orphan_code=f"{issue_prefix}_ORPHAN",
        )
        issues.extend(index_issues)

        stats = {
            "count": len(entries),
            "with_title": with_title,
            "with_summary": with_summary,
            "latest_modified_at": iso_mtime(max(entries, key=lambda p: p.stat().st_mtime)) if entries else None,
        }
        return stats, index_report, issues, files_meta, external_targets

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _discover_markdown(self, root: Path) -> List[Path]:
        entries: List[Path] = []
        for path in sorted(root.rglob("*.md")):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name in {"index.md", "readme.md"}:
                continue
            entries.append(path)
        return entries

    def _has_heading(self, text: str) -> bool:
        for idx, line in enumerate(text.splitlines()):
            if idx > 120:
                break
            if line.strip().startswith("# "):
                return True
        return False

    def _iter_local_links(self, text: str) -> Iterable[str]:
        for match in _LINK_PATTERN.finditer(text):
            target = match.group(1).strip()
            if not target:
                continue
            if any(target.startswith(prefix) for prefix in ("http://", "https://", "mailto:", "#", "data:")):
                continue
            if "://" in target:
                continue
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            yield target

    def _iter_external_links(self, text: str) -> Iterable[str]:
        for match in _LINK_PATTERN.finditer(text):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://")):
                yield target

    def _normalise_target(self, target: str) -> str | None:
        clean = target
        if "#" in clean:
            clean = clean.split("#", 1)[0]
        if "?" in clean:
            clean = clean.split("?", 1)[0]
        clean = clean.strip()
        return clean or None

    def _link_exists(self, project_root: Path, current_file: Path, target: str) -> bool:
        if target.startswith("/"):
            candidate = project_root / target.lstrip("/")
        else:
            candidate = (current_file.parent / target).resolve()
        return candidate.exists()

    def _lint_index(
        self,
        *,
        root: Path,
        entries: List[Path],
        project_root: Path,
        orphan_code: str,
    ) -> Tuple[Dict[str, object], List[KnowledgeIssue]]:
        candidates = [
            root / "index.md",
            root / "README.md",
        ]
        index_path = next((path for path in candidates if path.exists()), None)
        if index_path is None:
            return {"path": None, "listed": 0, "expected": len(entries)}, []

        text = index_path.read_text(encoding="utf-8")
        listed = 0
        issues: List[KnowledgeIssue] = []
        rel_index = safe_relpath(index_path, project_root)
        for entry in entries:
            rel_from_root = entry.relative_to(root).as_posix()
            rel_with_docs = safe_relpath(entry, project_root)
            slug = rel_from_root.replace(".md", "")
            if (
                rel_from_root in text
                or rel_with_docs in text
                or slug in text
                or entry.stem in text
            ):
                listed += 1
                continue
            issues.append(
                KnowledgeIssue(
                    code=orphan_code,
                    path=safe_relpath(entry, project_root),
                    message=f"Entry not referenced in {rel_index}",
                    severity="error",
                )
            )
        return {"path": rel_index, "listed": listed, "expected": len(entries)}, issues


    def _check_external_link(self, url: str, *, timeout: float) -> bool:
        import urllib.error
        import urllib.request

        request = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310
                return True
        except urllib.error.HTTPError as exc:
            if exc.code in {405, 501}:
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout):  # noqa: S310
                        return True
                except Exception:  # noqa: BLE001
                    return False
            return False
        except Exception:  # noqa: BLE001
            return False


__all__ = ["KnowledgeLintService", "KnowledgeIssue", "DEFAULT_REPORT_PATH"]

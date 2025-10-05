"""Aggregate responsible for documentation bridge operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .constants import remediation_for
from .editor import ENGINE, ManagedRegionCorruptionError, RegionOperation
from .events import DocsBridgeIssue, ManagedRegionChange
from .value_objects import DocsBridgeConfig, InsertionPolicy, SectionConfig


@dataclass(frozen=True)
class DocsBridgeContext:
    """Value object tying a configuration to a project root."""

    project_root: Path
    config: DocsBridgeConfig
    config_path: Path

    def absolute_root(self) -> Path:
        return self.config.absolute_root(self.project_root)


class DocsBridgeAggregate:
    """Aggregate applying docs bridge policies to project documentation."""

    def __init__(self, context: DocsBridgeContext) -> None:
        self._context = context
        self._region_cache: Dict[tuple[Path, str], tuple[int, Optional[str]]] = {}

    @property
    def config(self) -> DocsBridgeConfig:
        return self._context.config

    @property
    def project_root(self) -> Path:
        return self._context.project_root

    @property
    def config_path(self) -> Path:
        return self._context.config_path

    def inspect(self, *, include_status: bool = False) -> Dict[str, object]:
        root_base = self._context.absolute_root()
        summary_sections: List[Dict[str, object]] = []
        if include_status:
            sections, _ = self._collect_section_status(root_base)
            summary_sections = sections
        else:
            for name, spec in self.config.iter_sections():
                summary_sections.append(self._section_summary(root_base, name, spec))
        return {
            "configPath": str(self.config_path),
            "root": self._rel_to_project(root_base),
            "rootExists": root_base.exists(),
            "sections": summary_sections,
        }

    def diagnose(self) -> Dict[str, object]:
        root_base = self._context.absolute_root()
        sections, issues = self._collect_section_status(root_base)
        if not root_base.exists():
            issues.insert(
                0,
                DocsBridgeIssue(
                    severity="warning",
                    code="DOC_ROOT_MISSING",
                    message=f"Documentation root {root_base} does not exist",
                    section=None,
                    remediation=remediation_for("DOC_ROOT_MISSING"),
                ),
            )
        status = self._derive_overall_status(issues)
        return {
            "summary": {
                "configPath": str(self.config_path),
                "root": self._rel_to_project(root_base),
                "rootExists": root_base.exists(),
                "sections": sections,
            },
            "issues": [issue.__dict__ for issue in issues],
            "status": status,
        }

    # ------------------------------------------------------------------
    # Managed region primitives
    # ------------------------------------------------------------------

    def update_managed_region(
        self,
        file_path: Path,
        marker: str,
        content: Optional[str],
        *,
        insertion: Optional[InsertionPolicy] = None,
    ) -> ManagedRegionChange:
        resolved = file_path.resolve()
        self._region_cache.pop((resolved, marker), None)
        result = ENGINE.apply(file_path, {marker: RegionOperation(content=content, insertion=insertion)})
        return result.changes[0] if result.changes else ManagedRegionChange(
            section="unknown",
            marker=marker,
            changed=False,
            path=file_path.as_posix(),
        )

    def read_managed_region(self, file_path: Path, marker: str) -> Optional[str]:
        resolved = file_path.resolve()
        cache_key = (resolved, marker)
        try:
            stat = resolved.stat()
        except FileNotFoundError:
            self._region_cache.pop(cache_key, None)
            return None
        cached = self._region_cache.get(cache_key)
        if cached and cached[0] == stat.st_mtime_ns:
            return cached[1]
        try:
            region = ENGINE.read(resolved, marker)
        except ManagedRegionCorruptionError:
            self._region_cache.pop(cache_key, None)
            raise
        self._region_cache[cache_key] = (stat.st_mtime_ns, region)
        return region

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_section_status(
        self,
        root_base: Path,
    ) -> Tuple[List[Dict[str, object]], List[DocsBridgeIssue]]:
        sections: List[Dict[str, object]] = []
        issues: List[DocsBridgeIssue] = []
        for name, spec in self.config.iter_sections():
            entry = self._section_summary(root_base, name, spec)
            status = "skipped" if spec.mode == "skip" else "ok"
            if spec.mode == "managed" and spec.target:
                marker = spec.marker or f"agentcontrol-{name}"
                abs_path = spec.resolve_path(root_base)
                entry["target"] = self._rel_to_project(abs_path)
                if not abs_path.exists():
                    status = "missing_file"
                    issues.append(
                        DocsBridgeIssue(
                            severity="warning",
                            code="DOC_SECTION_MISSING_FILE",
                            message=f"Managed section '{name}' target {abs_path} is missing",
                            section=name,
                            remediation=remediation_for("DOC_SECTION_MISSING_FILE"),
                        ),
                    )
                else:
                    try:
                        region = self.read_managed_region(abs_path, marker)
                    except ManagedRegionCorruptionError as exc:
                        status = "corrupted"
                        issues.append(
                            DocsBridgeIssue(
                                severity="error",
                                code="DOC_SECTION_MARKER_CORRUPTED",
                                message=str(exc),
                                section=name,
                                remediation=remediation_for("DOC_SECTION_MARKER_CORRUPTED"),
                            ),
                        )
                    else:
                        if region is None:
                            status = "missing_marker"
                            issues.append(
                                DocsBridgeIssue(
                                    severity="warning",
                                    code="DOC_SECTION_MISSING_MARKER",
                                    message=f"Managed section '{name}' missing markers in {abs_path}",
                                    section=name,
                                    remediation=remediation_for("DOC_SECTION_MISSING_MARKER"),
                                ),
                            )
            elif spec.mode == "file":
                if spec.target:
                    abs_path = spec.resolve_path(root_base)
                    entry["target"] = self._rel_to_project(abs_path)
                    if not abs_path.exists():
                        status = "missing_file"
                        issues.append(
                            DocsBridgeIssue(
                                severity="warning",
                                code="DOC_SECTION_MISSING_FILE",
                                message=f"Section '{name}' target {abs_path} is missing",
                                section=name,
                                remediation=remediation_for("DOC_SECTION_MISSING_FILE"),
                            ),
                        )
                elif spec.target_template:
                    directory = (root_base / spec.target_template.format(id="example")).parent
                    entry["directory"] = self._rel_to_project(directory)
                    if not directory.exists():
                        status = "missing_directory"
                        issues.append(
                            DocsBridgeIssue(
                                severity="info",
                                code="DOC_SECTION_MISSING_DIRECTORY",
                                message=f"Directory {directory} for section '{name}' does not exist",
                                section=name,
                                remediation=remediation_for("DOC_SECTION_MISSING_DIRECTORY"),
                            ),
                        )
            elif spec.mode == "external":
                status = "external"
            entry["status"] = status
            sections.append(entry)
        return sections, issues

    def _section_summary(self, root_base: Path, name: str, spec: SectionConfig) -> Dict[str, object]:
        entry: Dict[str, object] = {"name": name, "mode": spec.mode}
        if spec.target:
            abs_path = spec.resolve_path(root_base)
            entry["target"] = self._rel_to_project(abs_path)
        if spec.marker:
            entry["marker"] = spec.marker
        if spec.target_template:
            entry["targetTemplate"] = spec.target_template
            directory = (root_base / spec.target_template.format(id="example")).parent
            entry["directory"] = self._rel_to_project(directory)
        if spec.insertion:
            entry["insertion"] = spec.insertion.as_dict()
        return entry

    def _rel_to_project(self, path: Path) -> str:
        project_root = self.project_root.resolve()
        try:
            return path.resolve().relative_to(project_root).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    @staticmethod
    def _derive_overall_status(issues: Iterable[DocsBridgeIssue]) -> str:
        severities = {issue.severity for issue in issues}
        if "error" in severities:
            return "error"
        if "warning" in severities:
            return "warning"
        return "ok"

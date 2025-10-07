"""Utilities for generating release notes from git history and telemetry."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from agentcontrol.domain.project import ProjectId


_TYPE_SECTIONS: Mapping[str, str] = {
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "refactor": "Refactorings",
    "docs": "Documentation",
    "test": "Testing",
    "build": "Build",
    "ci": "CI",
    "style": "Style",
    "chore": "Maintenance",
}


class ReleaseNotesError(RuntimeError):
    """Raised when release notes cannot be produced."""


@dataclass(frozen=True)
class ReleaseCommit:
    sha: str
    summary: str
    body: str
    author: str
    date: str
    type: str
    scope: str | None

    @property
    def short_sha(self) -> str:
        return self.sha[:8]


@dataclass
class ReleaseNotesResult:
    markdown_path: Path
    json_path: Path | None
    commits: List[ReleaseCommit]
    summary: Dict[str, Any]


class ReleaseNotesGenerator:
    """Generate release notes by analysing git history and auxiliary artefacts."""

    def __init__(self, project_id: ProjectId) -> None:
        self._project_id = project_id
        self._root = project_id.root

    def generate(
        self,
        *,
        from_ref: str | None = None,
        to_ref: str = "HEAD",
        max_commits: int | None = None,
        output_path: Path | None = None,
        json_output: bool = False,
    ) -> ReleaseNotesResult:
        commits = self._collect_commits(from_ref=from_ref, to_ref=to_ref, max_commits=max_commits)
        if not commits:
            raise ReleaseNotesError("no commits found for selected range")

        verify_summary = self._load_verify_summary()
        generated_at = _utc_now_iso()
        contributors = sorted({commit.author for commit in commits})
        summary = {
            "generated_at": generated_at,
            "from_ref": from_ref,
            "to_ref": to_ref,
            "commit_count": len(commits),
            "contributors": contributors,
            "sections": self._summarise_sections(commits),
            "verify": verify_summary,
        }

        markdown_path = output_path or (self._root / "reports" / "release_notes.md")
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown = self._render_markdown(summary, commits)
        markdown_path.write_text(markdown, encoding="utf-8")

        json_path: Path | None = None
        if json_output:
            json_path = markdown_path.with_suffix(".json")
            json_path.write_text(json.dumps(summary | {"commits": [commit.__dict__ for commit in commits]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return ReleaseNotesResult(markdown_path=markdown_path, json_path=json_path, commits=commits, summary=summary)

    def _collect_commits(
        self,
        *,
        from_ref: str | None,
        to_ref: str,
        max_commits: int | None,
    ) -> List[ReleaseCommit]:
        range_spec: Sequence[str]
        if from_ref:
            range_spec = [f"{from_ref}..{to_ref}"]
        else:
            range_spec = [to_ref]

        log_cmd = [
            "git",
            "log",
            *range_spec,
            "--pretty=format:%H\x1f%an\x1f%ad\x1f%s\x1f%b",
            "--date=iso-strict",
        ]
        if max_commits is not None:
            log_cmd.extend(["--max-count", str(max_commits)])
        try:
            result = subprocess.run(
                log_cmd,
                cwd=self._root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:  # pragma: no cover - system interaction
            raise ReleaseNotesError(f"failed to read git history: {exc}") from exc

        commits: List[ReleaseCommit] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\x1f")
            if len(parts) < 5:
                continue
            sha, author, date, summary, body = parts[0:5]
            commit_type, scope, subject = _parse_conventional_summary(summary)
            commits.append(
                ReleaseCommit(
                    sha=sha,
                    author=author,
                    date=date,
                    summary=subject,
                    body=body.strip(),
                    type=commit_type,
                    scope=scope,
                )
            )
        return commits

    def _load_verify_summary(self) -> Dict[str, Any] | None:
        verify_path = self._root / "reports" / "verify.json"
        if not verify_path.exists():
            return None
        try:
            payload = json.loads(verify_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        summary = {
            "generated_at": payload.get("generated_at"),
            "exit_code": payload.get("exit_code"),
        }
        steps = payload.get("steps")
        if isinstance(steps, list):
            failing = [
                {"name": step.get("name"), "status": step.get("status")}
                for step in steps
                if isinstance(step, dict) and step.get("status") != "ok"
            ]
            if failing:
                summary["failing_steps"] = failing
        return summary

    def _summarise_sections(self, commits: Iterable[ReleaseCommit]) -> Dict[str, Any]:
        totals: Dict[str, Dict[str, Any]] = {}
        for commit in commits:
            section = _TYPE_SECTIONS.get(commit.type, "Other")
            bucket = totals.setdefault(section, {"count": 0, "types": {}})
            bucket["count"] += 1
            bucket["types"][commit.type] = bucket["types"].get(commit.type, 0) + 1
        return {name: {"count": data["count"], "types": data["types"]} for name, data in sorted(totals.items())}

    def _render_markdown(self, summary: Dict[str, Any], commits: Sequence[ReleaseCommit]) -> str:
        lines: List[str] = []
        lines.append("# Release Notes")
        lines.append("")
        lines.append(f"Generated at {summary['generated_at']}")
        from_ref = summary.get("from_ref")
        to_ref = summary.get("to_ref")
        if from_ref:
            lines.append(f"Range: `{from_ref}` → `{to_ref}`")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- Commits: {summary['commit_count']}")
        contributors: Sequence[str] = summary.get("contributors", [])
        if contributors:
            joined = ", ".join(contributors)
            lines.append(f"- Contributors ({len(contributors)}): {joined}")
        sections = summary.get("sections", {})
        if sections:
            lines.append("- Types:")
            for section_name, data in sections.items():
                lines.append(f"  - {section_name}: {data['count']}")
        lines.append("")

        for section_name in sections.keys():
            section_commits = [commit for commit in commits if _TYPE_SECTIONS.get(commit.type, "Other") == section_name]
            if not section_commits:
                continue
            lines.append(f"## {section_name}")
            lines.append("")
            for commit in section_commits:
                scope_display = f"{commit.scope} — " if commit.scope else ""
                lines.append(f"- {scope_display}{commit.summary} (`{commit.short_sha}`)")
            lines.append("")

        other_commits = [commit for commit in commits if _TYPE_SECTIONS.get(commit.type, "Other") == "Other"]
        if other_commits:
            lines.append("## Other")
            lines.append("")
            for commit in other_commits:
                scope_display = f"{commit.scope} — " if commit.scope else ""
                lines.append(f"- {scope_display}{commit.summary} (`{commit.short_sha}`)")
            lines.append("")

        verify_summary = summary.get("verify")
        if isinstance(verify_summary, dict):
            lines.append("## Quality Gate")
            lines.append("")
            lines.append(f"- generated_at: {verify_summary.get('generated_at')}")
            lines.append(f"- exit_code: {verify_summary.get('exit_code')}")
            failing = verify_summary.get("failing_steps") or []
            if failing:
                lines.append("- failing_steps:")
                for step in failing:
                    lines.append(f"  - {step.get('name')}: {step.get('status')}")
            else:
                lines.append("- failing_steps: none")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


def _parse_conventional_summary(summary: str) -> tuple[str, str | None, str]:
    text = summary.strip()
    if ":" not in text:
        return "other", None, text
    prefix, subject = text.split(":", 1)
    subject = subject.strip()
    if "(" in prefix and ")" in prefix:
        type_part, scope_part = prefix.split("(", 1)
        scope = scope_part.rstrip(")")
        commit_type = type_part.strip().lower()
        return (commit_type or "other", scope or None, subject)
    commit_type = prefix.strip().lower()
    return (commit_type or "other", None, subject)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = ["ReleaseNotesGenerator", "ReleaseNotesResult", "ReleaseNotesError", "ReleaseCommit"]

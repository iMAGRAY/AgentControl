"""Application service orchestrating bootstrap profile capture."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from agentcontrol.domain.bootstrap import (
    BootstrapAnswer,
    BootstrapProfileAggregate,
    BootstrapProfileDefinition,
    BootstrapProfileSnapshot,
    BootstrapQuestion,
    BootstrapRequirements,
)
from agentcontrol.domain.project import PROJECT_DIR, ProjectId
from agentcontrol.ports.bootstrap_profile_repository import BootstrapProfileRepository
from agentcontrol.resources import load_profile_payloads


QUESTION_STACK = "stack-primary"
QUESTION_FRAMEWORKS = "stack-frameworks"
QUESTION_CICD = "cicd-provider"
QUESTION_MCP = "mcp-usage"
QUESTION_REPO_SCALE = "repo-scale"
QUESTION_AUTOMATION = "automation-goals"
QUESTION_NOTES = "notable-constraints"


@dataclass(frozen=True)
class CaptureResult:
    snapshot: BootstrapProfileSnapshot
    recommendations: List[dict[str, object]]


@dataclass(frozen=True)
class DoctorCheck:
    check_id: str
    status: str
    message: str
    details: Dict[str, object]


@dataclass(frozen=True)
class DoctorReport:
    status: str
    checks: List[DoctorCheck]
    snapshot: BootstrapProfileSnapshot | None


class BootstrapProfileService:
    """Provides high-level operations for the bootstrap wizard."""

    def __init__(self, repository: BootstrapProfileRepository) -> None:
        self._repository = repository
        self._profiles = {definition.profile_id: definition for definition in self._load_definitions()}
        self._questions = self._build_questions()

    def list_profiles(self) -> Sequence[BootstrapProfileDefinition]:
        return sorted(self._profiles.values(), key=lambda item: item.name.lower())

    def get_profile(self, profile_id: str) -> BootstrapProfileDefinition:
        if profile_id not in self._profiles:
            raise KeyError(profile_id)
        return self._profiles[profile_id]

    def list_questions(self) -> Sequence[BootstrapQuestion]:
        return list(self._questions)

    def capture(
        self,
        project_id: ProjectId,
        profile_id: str,
        answers: Mapping[str, str],
        *,
        operator: str,
    ) -> CaptureResult:
        definition = self.get_profile(profile_id)
        answer_entities = [
            BootstrapAnswer(
                question_id=question.question_id,
                value=self._normalise_answer(question.question_id, answers.get(question.question_id, "")),
                metadata={"source": "wizard"},
            )
            for question in self._questions
        ]
        recommendations = self._build_recommendations(definition, answer_entities)
        metadata = {
            "operator": operator,
            "questions": {
                question.question_id: {"prompt": question.prompt, "category": question.category}
                for question in self._questions
            },
            "recommendations": recommendations,
        }
        aggregate = BootstrapProfileAggregate(definition, self._questions)
        snapshot, _event = aggregate.capture(answer_entities, metadata=metadata)
        self._repository.save(project_id, snapshot)
        return CaptureResult(snapshot=snapshot, recommendations=recommendations)

    def load(self, project_id: ProjectId) -> BootstrapProfileSnapshot | None:
        return self._repository.load(project_id)

    def diagnose(self, project_id: ProjectId) -> DoctorReport:
        snapshot = self.load(project_id)
        if snapshot is None:
            check = DoctorCheck(
                check_id="profile-captured",
                status="fail",
                message="Bootstrap profile missing. Run `agentcall bootstrap` first.",
                details={"profile_path": str(project_id.root / PROJECT_DIR / "state" / "profile.json")},
            )
            return DoctorReport(status="fail", checks=[check], snapshot=None)

        checks: list[DoctorCheck] = []
        checks.append(self._check_python(snapshot.profile))
        checks.append(self._check_profile_drift(snapshot.profile))
        checks.append(self._check_mcp(project_id, snapshot))
        overall = self._summarise_status(checks)
        return DoctorReport(status=overall, checks=checks, snapshot=snapshot)

    def _load_definitions(self) -> Iterable[BootstrapProfileDefinition]:
        definitions: list[BootstrapProfileDefinition] = []
        for payload in load_profile_payloads():
            requirements_payload = payload.get("requirements", {}) if isinstance(payload, dict) else {}
            requirements = BootstrapRequirements(
                python_min_version=str(requirements_payload.get("python_min_version", "3.10")),
                recommended_cicd=list(requirements_payload.get("recommended_cicd", [])),
                mcp_required=bool(requirements_payload.get("mcp_required", False)),
                repo_scale=str(requirements_payload.get("repo_scale", "single")),
                automation_focus=str(requirements_payload.get("automation_focus", "verify-first")),
                notes=str(requirements_payload.get("notes", "")),
            )
            definitions.append(
                BootstrapProfileDefinition(
                    profile_id=str(payload.get("id", "custom")),
                    version=str(payload.get("version", "1.0")),
                    name=str(payload.get("name", "Custom Profile")),
                    description=str(payload.get("description", "")),
                    requirements=requirements,
                )
            )
        return definitions

    def _build_questions(self) -> Sequence[BootstrapQuestion]:
        return (
            BootstrapQuestion(QUESTION_STACK, "Primary runtime stack (e.g. Python, Node, JVM)", "stack"),
            BootstrapQuestion(QUESTION_FRAMEWORKS, "Key frameworks or libraries that must be supported", "stack"),
            BootstrapQuestion(QUESTION_CICD, "Which CI/CD platform do you rely on today?", "cicd"),
            BootstrapQuestion(QUESTION_MCP, "Do you operate Model Context Protocol (MCP) servers?", "mcp"),
            BootstrapQuestion(QUESTION_REPO_SCALE, "How many repositories make up this delivery surface?", "scale"),
            BootstrapQuestion(QUESTION_AUTOMATION, "What outcomes must automation deliver first?", "automation"),
            BootstrapQuestion(QUESTION_NOTES, "Any constraints, compliance needs, or manual runbooks to preserve?", "notes"),
        )

    def _normalise_answer(self, question_id: str, value: str) -> str:
        value = (value or "").strip()
        if not value:
            if question_id == QUESTION_NOTES:
                return "none"
            raise ValueError(f"Answer required for {question_id}")
        if question_id == QUESTION_REPO_SCALE:
            # reduce to canonical tokens: single, multi, meta
            lowered = value.lower()
            if "meta" in lowered:
                return "meta"
            if re.search(r"multi|mono", lowered):
                return "multi"
            return "single"
        if question_id == QUESTION_MCP:
            lowered = value.lower()
            if lowered in {"y", "yes", "true", "1"}:
                return "yes"
            if lowered in {"n", "no", "false", "0"}:
                return "no"
            return lowered
        return value

    def _check_python(self, profile: BootstrapProfileDefinition) -> DoctorCheck:
        required = profile.requirements.python_min_version
        required_tuple = self._parse_version(required)
        current_tuple = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
        ok = current_tuple >= required_tuple
        status = "ok" if ok else "fail"
        message = (
            f"Python {self._format_version(current_tuple)} detected; requires ≥ {required}."
            if ok
            else f"Python {self._format_version(current_tuple)} below required ≥ {required}."
        )
        return DoctorCheck(
            check_id="python-version",
            status=status,
            message=message,
            details={
                "current": self._format_version(current_tuple),
                "required": required,
            },
        )

    def _check_profile_drift(self, profile: BootstrapProfileDefinition) -> DoctorCheck:
        reference = self._profiles.get(profile.profile_id)
        if reference is None:
            return DoctorCheck(
                check_id="profile-reference",
                status="warn",
                message="Profile id not shipped with current CLI; consider recapturing bootstrap profile.",
                details={"profile_id": profile.profile_id, "captured_version": profile.version},
            )
        if reference.version != profile.version:
            return DoctorCheck(
                check_id="profile-version",
                status="warn",
                message=(
                    f"Profile version drifted (captured {profile.version}, current {reference.version})."
                    " Run `agentcall bootstrap` to refresh."
                ),
                details={
                    "profile_id": profile.profile_id,
                    "captured_version": profile.version,
                    "current_version": reference.version,
                },
            )
        return DoctorCheck(
            check_id="profile-version",
            status="ok",
            message="Bootstrap profile matches packaged defaults.",
            details={
                "profile_id": profile.profile_id,
                "captured_version": profile.version,
                "current_version": reference.version,
            },
        )

    def _check_mcp(self, project_id: ProjectId, snapshot: BootstrapProfileSnapshot) -> DoctorCheck:
        answers_map = self._answers_map(snapshot.answers)
        uses_mcp = answers_map.get(QUESTION_MCP, "no") in {"yes", "true", "y"}
        required = snapshot.profile.requirements.mcp_required or uses_mcp
        config_dir = project_id.root / PROJECT_DIR / "config" / "mcp"
        registered = sorted([entry.name for entry in config_dir.glob("*.json")]) if config_dir.exists() else []
        if required:
            if registered:
                return DoctorCheck(
                    check_id="mcp-config",
                    status="ok",
                    message=f"{len(registered)} MCP server(s) configured.",
                    details={"path": str(config_dir), "servers": registered},
                )
            return DoctorCheck(
                check_id="mcp-config",
                status="fail",
                message="MCP expected but no servers configured. Register via `agentcall mcp add`.",
                details={"path": str(config_dir), "servers": registered},
            )
        if registered:
            return DoctorCheck(
                check_id="mcp-config",
                status="info",
                message=f"MCP optional; {len(registered)} server(s) configured.",
                details={"path": str(config_dir), "servers": registered},
            )
        return DoctorCheck(
            check_id="mcp-config",
            status="info",
            message="MCP optional for this profile.",
            details={"path": str(config_dir), "servers": registered},
        )

    def _summarise_status(self, checks: Sequence[DoctorCheck]) -> str:
        statuses = {check.status for check in checks}
        if "fail" in statuses:
            return "fail"
        if "warn" in statuses:
            return "warn"
        return "ok"

    def _answers_map(self, answers: Sequence[BootstrapAnswer]) -> Dict[str, str]:
        return {answer.question_id: answer.value for answer in answers}

    def _parse_version(self, value: str) -> tuple[int, int, int]:
        parts = [int(part) for part in re.split(r"[.]+", value) if part.isdigit()]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def _format_version(self, value: tuple[int, int, int]) -> str:
        return ".".join(str(part) for part in value)

    def _build_recommendations(
        self,
        definition: BootstrapProfileDefinition,
        answers: Sequence[BootstrapAnswer],
    ) -> List[dict[str, object]]:
        answers_map = {answer.question_id: answer.value for answer in answers}
        recs: list[dict[str, object]] = []
        cicd = answers_map.get(QUESTION_CICD, "")
        if cicd:
            if not any(cicd.lower().startswith(item.lower()) for item in definition.requirements.recommended_cicd):
                recs.append(
                    {
                        "id": "cicd-alignment",
                        "status": "suggestion",
                        "message": (
                            "CI/CD platform differs from curated defaults; ensure verify pipeline maps to "
                            f"{', '.join(definition.requirements.recommended_cicd)}"
                        ),
                    }
                )
            else:
                recs.append(
                    {
                        "id": "cicd-alignment",
                        "status": "ok",
                        "message": "CI/CD platform matches recommended defaults.",
                    }
                )
        mcp_answer = answers_map.get(QUESTION_MCP, "no")
        if definition.requirements.mcp_required and mcp_answer not in {"yes", "y", "true"}:
            recs.append(
                {
                    "id": "mcp-required",
                    "status": "action",
                    "message": "Profile expects MCP connectivity; register servers via agentcall mcp add before verify.",
                }
            )
        elif not definition.requirements.mcp_required and mcp_answer in {"yes", "y", "true"}:
            recs.append(
                {
                    "id": "mcp-optional",
                    "status": "info",
                    "message": "MCP usage optional for this profile; ensure automation env exposes credentials securely.",
                }
            )
        repo_scale = answers_map.get(QUESTION_REPO_SCALE, "single")
        if repo_scale != definition.requirements.repo_scale:
            recs.append(
                {
                    "id": "repo-scale",
                    "status": "warn",
                    "message": (
                        "Repository scale differs from profile defaults; adjust workspace descriptors or choose another profile."
                    ),
                }
            )
        automation = answers_map.get(QUESTION_AUTOMATION, "")
        if automation:
            recs.append(
                {
                    "id": "automation-focus",
                    "status": "info",
                    "message": f"Primary automation goal captured: {automation}",
                }
            )
        notes = answers_map.get(QUESTION_NOTES, "")
        if notes:
            recs.append(
                {
                    "id": "notes",
                    "status": "info",
                    "message": notes,
                }
            )
        return recs


__all__ = ["BootstrapProfileService", "CaptureResult", "DoctorCheck", "DoctorReport"]

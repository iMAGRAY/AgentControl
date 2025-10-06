"""Filesystem-backed storage for bootstrap profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

from agentcontrol.domain.bootstrap import BootstrapProfileSnapshot
from agentcontrol.domain.project import PROJECT_DIR, ProjectId
from agentcontrol.ports.bootstrap_profile_repository import BootstrapProfileRepository


class FileBootstrapProfileRepository(BootstrapProfileRepository):
    """Persist profile snapshot and derived summary into the project capsule."""

    def save(self, project_id: ProjectId, snapshot: BootstrapProfileSnapshot) -> None:
        state_path = self._profile_path(project_id)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = snapshot.as_dict()
        state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

        summary_path = self._summary_path(project_id)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_payload = self._build_summary(snapshot)
        summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True), encoding="utf-8")

    def load(self, project_id: ProjectId) -> BootstrapProfileSnapshot | None:
        state_path = self._profile_path(project_id)
        if not state_path.exists():
            return None
        data = json.loads(state_path.read_text("utf-8"))
        from agentcontrol.domain.bootstrap import (
            BootstrapAnswer,
            BootstrapProfileDefinition,
            BootstrapProfileSnapshot,
            BootstrapRequirements,
        )

        profile_data = data.get("profile") or {}
        requirements_data = profile_data.get("requirements") or {}
        requirements = BootstrapRequirements(
            python_min_version=requirements_data.get("python_min_version", "3.10"),
            recommended_cicd=list(requirements_data.get("recommended_cicd", [])),
            mcp_required=bool(requirements_data.get("mcp_required", False)),
            repo_scale=requirements_data.get("repo_scale", "single"),
            automation_focus=requirements_data.get("automation_focus", "verify-first"),
            notes=requirements_data.get("notes", ""),
        )
        profile = BootstrapProfileDefinition(
            profile_id=profile_data.get("id", "custom"),
            version=profile_data.get("version", "1.0"),
            name=profile_data.get("name", "Custom Profile"),
            description=profile_data.get("description", ""),
            requirements=requirements,
        )
        answers = [
            BootstrapAnswer(
                question_id=answer.get("question_id", "unknown"),
                value=answer.get("value", ""),
                metadata=answer.get("metadata", {}),
            )
            for answer in data.get("answers", [])
        ]
        snapshot = BootstrapProfileSnapshot(
            profile=profile,
            answers=answers,
            captured_at=data.get("captured_at", ""),
            metadata=data.get("metadata", {}),
        )
        return snapshot

    def _profile_path(self, project_id: ProjectId) -> Path:
        return project_id.root / PROJECT_DIR / "state" / "profile.json"

    def _summary_path(self, project_id: ProjectId) -> Path:
        return project_id.root / "reports" / "bootstrap_summary.json"

    def _build_summary(self, snapshot: BootstrapProfileSnapshot) -> Dict[str, Any]:
        questions_meta = snapshot.metadata.get("questions", {}) if isinstance(snapshot.metadata, dict) else {}
        recommendations: Iterable[dict[str, Any]] = snapshot.metadata.get("recommendations", []) if isinstance(snapshot.metadata, dict) else []
        operator = snapshot.metadata.get("operator") if isinstance(snapshot.metadata, dict) else None
        answers_payload = []
        for answer in snapshot.answers:
            meta = questions_meta.get(answer.question_id, {})
            answers_payload.append(
                {
                    "question_id": answer.question_id,
                    "prompt": meta.get("prompt", ""),
                    "category": meta.get("category", ""),
                    "value": answer.value,
                    "metadata": answer.metadata,
                }
            )
        return {
            "profile": snapshot.profile.as_dict(),
            "captured_at": snapshot.captured_at,
            "operator": operator,
            "answers": answers_payload,
            "recommendations": list(recommendations),
        }


__all__ = ["FileBootstrapProfileRepository"]

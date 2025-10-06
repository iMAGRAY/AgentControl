"""Value objects for bootstrap profile capture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class BootstrapQuestion:
    """Defines a wizard prompt that must be answered."""

    question_id: str
    prompt: str
    category: str

    def __post_init__(self) -> None:
        if not self.question_id or not self.question_id.strip():
            raise ValueError("question_id must be a non-empty string")
        if not self.prompt or not self.prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        object.__setattr__(self, "question_id", self.question_id.strip())
        object.__setattr__(self, "prompt", self.prompt.strip())
        object.__setattr__(self, "category", self.category.strip() or "general")


@dataclass(frozen=True)
class BootstrapAnswer:
    """Immutable recording of a single answer provided by the operator."""

    question_id: str
    value: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.question_id or not self.question_id.strip():
            raise ValueError("question_id must be provided")
        if not self.value or not self.value.strip():
            raise ValueError("value must be provided")
        object.__setattr__(self, "question_id", self.question_id.strip())
        object.__setattr__(self, "value", self.value.strip())
        object.__setattr__(self, "metadata", dict(self.metadata))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "value": self.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class BootstrapRequirements:
    """Represents minimum environment expectations for a profile."""

    python_min_version: str
    recommended_cicd: List[str]
    mcp_required: bool
    repo_scale: str
    automation_focus: str
    notes: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "python_min_version", self.python_min_version.strip())
        object.__setattr__(self, "recommended_cicd", [item.strip() for item in self.recommended_cicd])
        object.__setattr__(self, "repo_scale", self.repo_scale.strip())
        object.__setattr__(self, "automation_focus", self.automation_focus.strip())
        object.__setattr__(self, "notes", self.notes.strip())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "python_min_version": self.python_min_version,
            "recommended_cicd": list(self.recommended_cicd),
            "mcp_required": self.mcp_required,
            "repo_scale": self.repo_scale,
            "automation_focus": self.automation_focus,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class BootstrapProfileDefinition:
    """Defines a reusable default bootstrap profile."""

    profile_id: str
    version: str
    name: str
    description: str
    requirements: BootstrapRequirements

    def __post_init__(self) -> None:
        for field_name in ("profile_id", "version", "name", "description"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"{field_name} must be provided")
            object.__setattr__(self, field_name, value.strip())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.profile_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "requirements": self.requirements.as_dict(),
        }


@dataclass(frozen=True)
class BootstrapProfileSnapshot:
    """Stable snapshot persisted to disk after wizard completion."""

    profile: BootstrapProfileDefinition
    answers: List[BootstrapAnswer]
    captured_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "answers", list(self.answers))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile.as_dict(),
            "answers": [answer.as_dict() for answer in self.answers],
            "captured_at": self.captured_at,
            "metadata": dict(self.metadata),
        }


def ensure_required_answers(
    questions: Iterable[BootstrapQuestion],
    answers: Iterable[BootstrapAnswer],
) -> None:
    """Raise if required question ids are missing or extra answers exist."""

    question_ids = {q.question_id for q in questions}
    answer_ids = [a.question_id for a in answers]
    missing = question_ids.difference(answer_ids)
    if missing:
        raise ValueError(f"Missing answers for: {sorted(missing)}")
    extra = set(answer_ids).difference(question_ids)
    if extra:
        raise ValueError(f"Unexpected answers provided: {sorted(extra)}")

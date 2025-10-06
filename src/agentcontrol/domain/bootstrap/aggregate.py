"""Aggregate orchestrating bootstrap profile capture."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Tuple

from .events import BootstrapProfileCaptured
from .value_objects import (
    BootstrapAnswer,
    BootstrapProfileDefinition,
    BootstrapProfileSnapshot,
    BootstrapQuestion,
    ensure_required_answers,
)


class BootstrapProfileAggregate:
    """Ensures bootstrap answers satisfy invariants before persistence."""

    def __init__(
        self,
        profile: BootstrapProfileDefinition,
        questions: Iterable[BootstrapQuestion],
    ) -> None:
        question_list = list(questions)
        if not question_list:
            raise ValueError("Bootstrap profile aggregate requires at least one question")
        self._profile = profile
        self._questions = {question.question_id: question for question in question_list}

    @property
    def profile(self) -> BootstrapProfileDefinition:
        return self._profile

    @property
    def questions(self) -> List[BootstrapQuestion]:
        return list(self._questions.values())

    def capture(
        self,
        answers: Iterable[BootstrapAnswer],
        *,
        metadata: dict[str, object] | None = None,
        captured_at: datetime | None = None,
    ) -> Tuple[BootstrapProfileSnapshot, BootstrapProfileCaptured]:
        answers_list = list(answers)
        ensure_required_answers(self._questions.values(), answers_list)
        timestamp = captured_at or datetime.now(timezone.utc)
        snapshot = BootstrapProfileSnapshot(
            profile=self._profile,
            answers=answers_list,
            captured_at=timestamp.isoformat(),
            metadata=dict(metadata or {}),
        )
        event = BootstrapProfileCaptured(snapshot=snapshot)
        return snapshot, event


__all__ = ["BootstrapProfileAggregate"]

from __future__ import annotations

import json
from pathlib import Path

from agentcontrol.adapters.bootstrap_profile.file_repository import FileBootstrapProfileRepository
from agentcontrol.app.bootstrap_profile.service import BootstrapProfileService
from agentcontrol.domain.project import ProjectId


def _prepare_answers(service: BootstrapProfileService) -> dict[str, str]:
    seed = {
        "stack-primary": "Python",
        "stack-frameworks": "FastAPI",
        "cicd-provider": "GitHub Actions",
        "mcp-usage": "no",
        "repo-scale": "single repo",
        "automation-goals": "autopilot verify",
        "notable-constraints": "",
    }
    answers: dict[str, str] = {}
    for question in service.list_questions():
        answers[question.question_id] = seed[question.question_id]
    return answers


def test_capture_persists_profile(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / ".agentcontrol").mkdir(parents=True)
    service = BootstrapProfileService(FileBootstrapProfileRepository())
    project_id = ProjectId.for_new_project(project_root)

    result = service.capture(
        project_id,
        profile_id="python",
        answers=_prepare_answers(service),
        operator="tester",
    )

    profile_path = project_root / ".agentcontrol" / "state" / "profile.json"
    summary_path = project_root / "reports" / "bootstrap_summary.json"
    assert profile_path.exists()
    assert summary_path.exists()

    payload = json.loads(profile_path.read_text("utf-8"))
    assert payload["profile"]["id"] == "python"
    assert payload["metadata"]["operator"] == "tester"

    summary = json.loads(summary_path.read_text("utf-8"))
    assert summary["profile"]["id"] == "python"
    assert any(rec["status"] for rec in summary["recommendations"])
    assert result.recommendations

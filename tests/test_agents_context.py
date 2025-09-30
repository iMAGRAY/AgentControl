from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.agents.context import generate_context


def test_generate_context_without_task():
    context = generate_context(task_id="", role="Architect", agent="codex", top_k=2)
    assert "Progress Snapshot" in context
    assert "## Roadmap Phase Progress" in context
    assert len(context.splitlines()) > 10

from __future__ import annotations

import subprocess
from pathlib import Path


def test_roadmap_status_compact_outputs_table() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "roadmap-status.sh"
    result = subprocess.run(
        ["bash", str(script), "compact"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = result.stdout
    assert "Program" in stdout
    assert stdout.count("+") >= 4
    assert "Phases" in stdout

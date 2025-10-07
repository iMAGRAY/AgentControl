from __future__ import annotations

import subprocess
from pathlib import Path

from agentcontrol import __version__

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-legacy-pipelines.py"


def run_script(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SCRIPT, "--root", str(root)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_check_legacy_passes(tmp_path: Path) -> None:
    result = run_script(tmp_path)
    assert result.returncode == 0
    assert "No legacy" in result.stdout


def test_check_legacy_fails_when_directory_exists(tmp_path: Path) -> None:
    (tmp_path / "agentcontrol").mkdir()
    result = run_script(tmp_path)
    assert result.returncode == 1
    assert "legacy pipelines" in result.stderr

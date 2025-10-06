from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _copy_template(template: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(template, destination)


def test_automation_hooks_extend_verify_commands(tmp_path: Path) -> None:
    template_root = Path("src/agentcontrol/templates/0.5.1/default/.agentcontrol")
    project_root = tmp_path / ".agentcontrol"
    _copy_template(template_root, project_root)

    script = """
    set -Eeuo pipefail
    source scripts/lib/common.sh
    sdk::load_commands
    sdk::load_commands
    for cmd in "${SDK_VERIFY_COMMANDS[@]}"; do
      printf '%s\n' "$cmd"
    done
    """
    result = subprocess.run(
        ["bash", "-lc", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    if result.returncode != 0:
        raise AssertionError(f"stderr={result.stderr}\nstdout={result.stdout}")

    commands = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    reports_dir = project_root / "reports" / "automation"
    assert reports_dir.is_dir()

    expected = {
        f'agentcall docs diff --json > "{reports_dir / "docs-diff.json"}" || agentcall docs adopt --json > "{reports_dir / "docs-diff.json"}"',
        f'agentcall mission summary --json --timeline-limit 20 > "{reports_dir / "mission-summary.json"}"',
        f'agentcall mcp status --json > "{reports_dir / "mcp-status.json"}" || true',
    }
    for hook in expected:
        assert commands.count(hook) == 1

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check-make-alignment.py"

EXPECTED = (
    ("init", "init.sh"),
    ("dev", "dev.sh"),
    ("verify", "verify.sh"),
    ("fix", "fix.sh"),
    ("review", "review.sh"),
    ("ship", "ship.sh"),
    ("doctor", "doctor.sh"),
    ("status", "status.sh"),
)


def run_checker(root: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--root", str(root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_alignment_passes(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    lines = ["SDK_RUNNER := ./scripts", ""]
    for target, script in EXPECTED:
        lines.append(f"{target}:")
        lines.append(f'\t"${{SDK_RUNNER}}/{script}"')
        lines.append("")
    makefile.write_text("\n".join(lines), encoding="utf-8")

    process = run_checker(tmp_path)
    assert process.returncode == 0
    assert b"Makefile alignment ok" in process.stdout


def test_alignment_reports_missing_target(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        "\n".join(
            [
                "SDK_RUNNER := ./scripts",
                "",
                "init:",
                "\t${SDK_RUNNER}/init.sh",
            ]
        ),
        encoding="utf-8",
    )
    process = run_checker(tmp_path)
    assert process.returncode == 1
    assert b"missing target" in process.stderr

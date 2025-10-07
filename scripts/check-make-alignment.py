#!/usr/bin/env python3
"""Validate that Makefile targets stay aligned with SDK CLI pipelines."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

EXPECTED_TARGETS: Dict[str, str] = {
    "init": "init.sh",
    "dev": "dev.sh",
    "verify": "verify.sh",
    "fix": "fix.sh",
    "review": "review.sh",
    "ship": "ship.sh",
    "doctor": "doctor.sh",
    "status": "status.sh",
}


def _parse_makefile(makefile: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    lines = makefile.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":") and " " not in stripped[:-1]:
            target = stripped[:-1]
            if index + 1 >= len(lines):
                continue
            recipe = lines[index + 1]
            if not recipe.startswith("\t"):
                continue
            command = recipe.strip()
            if command.startswith('"') and command.endswith('"'):
                command = command[1:-1]
            if command.startswith("${SDK_RUNNER}/"):
                mapping[target] = command[len("${SDK_RUNNER}/"):]
    return mapping


def _validate(mapping: Dict[str, str]) -> List[str]:
    errors: List[str] = []
    for target, script in EXPECTED_TARGETS.items():
        if target not in mapping:
            expected = f"${{SDK_RUNNER}}/{script}"
            errors.append(f"missing target '{target}' calling {expected}")
            continue
        actual = mapping[target]
        if actual != script:
            expected = f"${{SDK_RUNNER}}/{script}"
            found = f"${{SDK_RUNNER}}/{actual}"
            errors.append(f"target '{target}' should call {expected} but calls {found}")
    for target in sorted(mapping):
        if target not in EXPECTED_TARGETS:
            errors.append(f"unexpected Makefile target '{target}' detected for SDK pipelines")
    return errors


def check_makefile(root: Path) -> List[str]:
    makefile = root / "Makefile"
    if not makefile.exists():
        return [f"Makefile not found under {root}"]
    mapping = _parse_makefile(makefile)
    return _validate(mapping)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = check_makefile(args.root)
    if errors:
        for error in errors:
            print(f"make-alignment: {error}", file=sys.stderr)
        return 1
    print("Makefile alignment ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

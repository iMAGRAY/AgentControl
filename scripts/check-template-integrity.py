#!/usr/bin/env python3
"""Validate packaged template checksums for the AgentControl SDK."""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Iterable

DEFAULT_REL = Path("src/agentcontrol/templates")


def compute_checksum(target: Path) -> str:
    digest = sha256()
    for path in sorted(target.rglob("*")):
        if path.name == "template.sha256" or not path.is_file():
            continue
        digest.update(path.relative_to(target).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def iter_checksum_files(templates_root: Path) -> Iterable[Path]:
    yield from templates_root.rglob("template.sha256")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    templates_root = (args.root / DEFAULT_REL).resolve()
    if not templates_root.exists():
        payload = {"status": "skip", "reason": f"templates root not found: {templates_root}"}
        if args.json:
            json.dump(payload, sys.stdout)
            sys.stdout.write("\n")
        return 0

    mismatches = []
    reports = []
    for checksum_path in iter_checksum_files(templates_root):
        template_dir = checksum_path.parent
        expected = checksum_path.read_text(encoding="utf-8").strip()
        actual = compute_checksum(template_dir)
        status = "ok" if actual == expected else "mismatch"
        reports.append(
            {
                "template": str(template_dir.relative_to(templates_root)),
                "checksum_file": str(checksum_path.relative_to(templates_root)),
                "expected": expected,
                "actual": actual,
                "status": status,
            }
        )
        if status != "ok":
            mismatches.append(checksum_path)

    payload = {"status": "ok" if not mismatches else "error", "templates": reports}
    if args.json:
        json.dump(payload, sys.stdout)
        sys.stdout.write("\n")
    else:
        for report in reports:
            marker = "✓" if report["status"] == "ok" else "✗"
            print(f"{marker} {report['template']}: {report['actual']}")
        if mismatches:
            print("Template checksum mismatch detected", file=sys.stderr)

    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

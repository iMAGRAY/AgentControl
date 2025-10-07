#!/usr/bin/env python3
"""Validate packaged extension templates and packaging hygiene."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agentcontrol.app.extension.integrity import (
    DEFAULT_EXTENSIONS_ROOT,
    DEFAULT_PROJECT_ROOT,
    DEFAULT_SOURCES_FILE,
    BANNED_PACKAGING_PATTERNS,
    verify_extensions,
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extensions-root", type=Path, default=DEFAULT_EXTENSIONS_ROOT, help="Path to extensions directory")
    parser.add_argument("--sources-file", type=Path, default=DEFAULT_SOURCES_FILE, help="Path to SOURCES.txt for packaging checks")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT, help="Project root for relative reporting")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    summary = verify_extensions(
        root=args.extensions_root,
        sources_file=args.sources_file,
        project_root=args.project_root,
        banned_patterns=BANNED_PACKAGING_PATTERNS,
    )

    if args.json:
        json.dump(summary.to_dict(args.project_root), sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        for report in summary.extensions:
            marker = "✓" if report.status == "ok" else "✗"
            rel = report.to_dict(args.project_root)["path"]
            print(f"{marker} {report.name}: {report.actual} ({rel})")
        if summary.packaging_issues:
            print("Packaging issues:")
            for issue in summary.packaging_issues:
                print(f"  - {issue}")
        print(f"Status: {summary.status}")

    return 0 if summary.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

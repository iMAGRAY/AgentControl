#!/usr/bin/env python3
"""Ensure mission timeline hint documentation references exist."""

from __future__ import annotations

import sys
from pathlib import Path

from agentcontrol.app.mission.service import TIMELINE_DOC_REFERENCES


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    missing: list[str] = []
    for doc_path in sorted(set(TIMELINE_DOC_REFERENCES.values())):
        if not (repo_root / doc_path).exists():
            missing.append(doc_path)
    if missing:
        for path in missing:
            print(f"missing timeline hint doc: {path}")
        return 1
    print("timeline hint docs verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())

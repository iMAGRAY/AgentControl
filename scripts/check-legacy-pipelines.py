#!/usr/bin/env python3
"""Fail when legacy `agentcontrol/` pipelines are still present."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def has_legacy_capsule(root: Path) -> bool:
    legacy_dir = root / "agentcontrol"
    return legacy_dir.exists()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root

    if has_legacy_capsule(root):
        print(
            "legacy pipelines detected: remove or migrate './agentcontrol/' to '.agentcontrol/'",
            file=sys.stderr,
        )
        return 1
    print("No legacy pipelines detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

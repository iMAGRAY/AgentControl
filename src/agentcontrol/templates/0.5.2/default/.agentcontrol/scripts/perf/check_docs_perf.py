#!/usr/bin/env python3
"""Validate docs benchmark results against latency thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check docs benchmark thresholds")
    parser.add_argument("--report", type=Path, required=True, help="Path to benchmark JSON report")
    parser.add_argument("--threshold", type=float, default=60000.0, help="Allowed p95 in milliseconds")
    args = parser.parse_args()

    if not args.report.exists():
        print(f"perf report missing: {args.report}")
        return 1

    data = json.loads(args.report.read_text(encoding="utf-8"))
    operations = data.get("operations", {})
    violations: list[str] = []
    for name, payload in operations.items():
        p95 = payload.get("p95_ms")
        if p95 is None:
            continue
        if p95 > args.threshold:
            violations.append(f"{name} p95={p95:.1f}ms")
    if violations:
        print("; ".join(violations))
        return 1
    print("docs benchmark within threshold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

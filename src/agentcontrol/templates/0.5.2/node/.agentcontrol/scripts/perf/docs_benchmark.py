#!/usr/bin/env python3
"""Benchmark managed documentation operations on large datasets."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agentcontrol.app.docs.operations import DocsCommandService
from agentcontrol.app.docs.service import DocsBridgeService

BASE_SECTIONS = {
    "architecture_overview": {
        "mode": "managed",
        "target": "architecture/overview.md",
        "marker": "agentcontrol-architecture-overview",
    },
    "adr_index": {
        "mode": "managed",
        "target": "adr/index.md",
        "marker": "agentcontrol-adr-index",
    },
    "rfc_index": {
        "mode": "managed",
        "target": "rfc/index.md",
        "marker": "agentcontrol-rfc-index",
    },
    "adr_entry": {
        "mode": "file",
        "target_template": "adr/{id}.md",
    },
    "rfc_entry": {
        "mode": "file",
        "target_template": "rfc/{id}.md",
    },
}

BASE_FILES = {
    "architecture/overview.md": "<!-- agentcontrol:start:agentcontrol-architecture-overview -->\nOverview\n<!-- agentcontrol:end:agentcontrol-architecture-overview -->\n",
    "adr/index.md": "<!-- agentcontrol:start:agentcontrol-adr-index -->\nADR Index\n<!-- agentcontrol:end:agentcontrol-adr-index -->\n",
    "rfc/index.md": "<!-- agentcontrol:start:agentcontrol-rfc-index -->\nRFC Index\n<!-- agentcontrol:end:agentcontrol-rfc-index -->\n",
}



def _build_project(root: Path, sections: int) -> None:
    capsule = root / ".agentcontrol"
    config_dir = capsule / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    config_sections: Dict[str, Dict[str, Any]] = dict(BASE_SECTIONS)
    for rel_path, content in BASE_FILES.items():
        target_path = docs_dir / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")

    for idx in range(sections):
        name = f"bench_section_{idx}"
        marker = f"benchmark-marker-{idx}"
        target_rel = f"bench/{name}.md"
        target_path = docs_dir / target_rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            f"<!-- agentcontrol:start:{marker} -->\nSeed {idx}\n<!-- agentcontrol:end:{marker} -->\n",
            encoding="utf-8",
        )
        config_sections[name] = {
            "mode": "managed",
            "target": target_rel,
            "marker": marker,
        }

    config = {
        "version": 1,
        "root": "docs",
        "sections": config_sections,
    }
    yaml.safe_dump(config, (config_dir / "docs.bridge.yaml").open("w", encoding="utf-8"), sort_keys=True)


def _percentiles(samples: List[float]) -> Dict[str, float]:
    if not samples:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    sorted_samples = sorted(samples)
    return {
        "p50": statistics.quantiles(sorted_samples, n=100)[49],
        "p95": statistics.quantiles(sorted_samples, n=100)[94],
        "p99": statistics.quantiles(sorted_samples + [sorted_samples[-1]] * max(0, 100 - len(sorted_samples)), n=100)[98],
    }


def _run_operation(operation: str, project: Path, command_service: DocsCommandService, bridge_service: DocsBridgeService) -> float:
    start = time.perf_counter()
    if operation == "diagnose":
        bridge_service.diagnose(project)
    elif operation == "list":
        command_service.list_sections(project)
    else:
        raise ValueError(f"Unsupported operation {operation}")
    return (time.perf_counter() - start) * 1000


def benchmark(sections: int, trials: int) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agentcontrol-bench-") as workspace:
        project = Path(workspace)
        _build_project(project, sections)
        bridge_service = DocsBridgeService()
        command_service = DocsCommandService()

        results: Dict[str, List[float]] = {"diagnose": [], "list": []}
        for _ in range(trials):
            for op in results.keys():
                duration = _run_operation(op, project, command_service, bridge_service)
                results[op].append(duration)

    operations: Dict[str, Any] = {}
    for op, samples in results.items():
        percentiles = _percentiles(samples)
        operations[op] = {
            "durations_ms": samples,
            "p50_ms": percentiles["p50"],
            "p95_ms": percentiles["p95"],
            "p99_ms": percentiles["p99"],
        }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
        "trials": trials,
        "operations": operations,
    }


def write_report(payload: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark docs bridge operations")
    parser.add_argument("--sections", type=int, default=1200, help="Number of managed sections to generate")
    parser.add_argument("--trials", type=int, default=9, help="Number of measurement trials")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/perf/docs_benchmark.json"),
        help="Where to persist benchmark results",
    )
    args = parser.parse_args()

    payload = benchmark(args.sections, args.trials)
    write_report(payload, args.report)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

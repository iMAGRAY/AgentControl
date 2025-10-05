from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _write_report(path: Path, value: float) -> None:
    payload = {
        "generatedAt": "2025-10-05T00:00:00Z",
        "sections": 1000,
        "trials": 5,
        "operations": {
            "diagnose": {"p95_ms": value, "p50_ms": value, "p99_ms": value},
            "list": {"p95_ms": value, "p50_ms": value, "p99_ms": value},
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_perf_history_regression_detection(tmp_path: Path) -> None:
    history_dir = tmp_path / "history"
    report_path = tmp_path / "baseline.json"
    _write_report(report_path, 1000.0)

    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "perf" / "compare_history.py"

    baseline = subprocess.run(
        [
            "python3",
            str(script),
            "--report",
            str(report_path),
            "--history-dir",
            str(history_dir),
            "--update-history",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert baseline.returncode == 0

    regression_report = tmp_path / "regression.json"
    _write_report(regression_report, 1300.0)
    journal_dir = tmp_path / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    regression = subprocess.run(
        [
            "python3",
            str(script),
            "--report",
            str(regression_report),
            "--history-dir",
            str(history_dir),
            "--max-regression-pct",
            "10",
            "--max-regression-ms",
            "100",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert regression.returncode == 1
    diff_path = history_dir / "diff.json"
    diff = json.loads(diff_path.read_text(encoding="utf-8"))
    assert diff["regressions"]
    op = diff["regressions"][0]
    assert op["operation"] == "diagnose"
    assert op["regression"] is True
    events_path = tmp_path / "journal" / "task_events.jsonl"
    assert events_path.exists()
    entries = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(entry.get("event") == "perf.regression" for entry in entries)
    followup = tmp_path / "reports" / "automation" / "perf_followup.json"
    assert followup.exists()
    followup_payload = json.loads(followup.read_text(encoding="utf-8"))
    assert followup_payload["regressions"]


def test_perf_history_keep_trim(tmp_path: Path) -> None:
    history_dir = tmp_path / "history"
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "perf" / "compare_history.py"
    values = [1000.0, 900.0, 800.0]
    for idx, value in enumerate(values):
        report = tmp_path / f"run_{idx}.json"
        _write_report(report, value)
        result = subprocess.run(
            [
                "python3",
                str(script),
                "--report",
                str(report),
                "--history-dir",
                str(history_dir),
                "--update-history",
                "--keep",
                "2",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert result.returncode == 0

    history_file = history_dir / "docs_benchmark_history.jsonl"
    lines = [line for line in history_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2

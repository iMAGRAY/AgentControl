from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

from scripts import progress


def make_manifest() -> dict:
    return {
        "version": "0.1.0",
        "updated_at": "2025-01-01T00:00:00Z",
        "program": {
            "meta": {
                "program": "v1",
                "program_id": "test-program",
                "name": "Test",
                "objectives": [],
                "kpis": {},
                "owners": ["tester"],
                "policies": {"task_min_points": 5},
                "teach": True,
                "updated_at": "2025-01-01T00:00:00Z",
            },
            "progress": {"health": "green", "progress_pct": 0, "phase_progress": {}},
            "milestones": [
                {"id": "m_q1", "title": "Q1", "due": "2025-02-01T00:00:00Z", "status": "planned"}
            ],
        },
        "epics": [
            {
                "id": "epic-1",
                "title": "Epic",
                "type": "epic",
                "status": "in_progress",
                "priority": "P0",
                "size_points": 8,
                "scope_paths": [],
                "spec": "",
                "budgets": {},
                "risks": [],
                "dependencies": [],
                "docs_updates": [],
                "artifacts": [],
                "tests_required": [],
                "verify_commands": [],
                "audit": {"created_at": "2025-01-01T00:00:00Z", "created_by": "tester"},
            }
        ],
        "big_tasks": [
            {
                "id": "big-1",
                "title": "Big",
                "type": "feature",
                "status": "in_progress",
                "priority": "P0",
                "size_points": 8,
                "parent_epic": "epic-1",
                "scope_paths": [],
                "spec": "",
                "budgets": {},
                "risks": [],
                "dependencies": [],
                "docs_updates": [],
                "artifacts": [],
                "tests_required": [],
                "verify_commands": [],
                "audit": {"created_at": "2025-01-01T00:00:00Z", "created_by": "tester"},
            }
        ],
        "tasks": [
            {
                "id": "TASK-1",
                "title": "T1",
                "big_task": "big-1",
                "system": "sys",
                "roadmap_phase": "m_q1",
                "status": "done",
                "priority": "P0",
                "owner": "tester",
                "size_points": 5,
            },
            {
                "id": "TASK-2",
                "title": "T2",
                "big_task": "big-1",
                "system": "sys",
                "roadmap_phase": "m_q1",
                "status": "done",
                "priority": "P0",
                "owner": "tester",
                "size_points": 3,
            },
        ],
    }


def make_todo() -> str:
    return """## Program
```yaml
program: v1
program_id: test-program
name: Test
objectives: []
kpis: {}
owners: [tester]
policies:
  task_min_points: 5
teach: true
updated_at: '2025-01-01T00:00:00Z'
health: green
progress_pct: 0
phase_progress:
  Q1: 0
milestones:
- id: m_q1
  title: Q1
  due: '2025-02-01T00:00:00Z'
  status: planned
```

## Epics
```yaml
- id: epic-1
  title: Epic
  type: epic
  status: in_progress
  priority: P0
  size_points: 8
  scope_paths: []
  spec: ''
  budgets: {}
  risks: []
  dependencies: []
  docs_updates: []
  artifacts: []
  big_tasks_planned:
  - big-1
  progress_pct: 0
  health: green
  tests_required: []
  verify_commands: []
  audit:
    created_at: '2025-01-01T00:00:00Z'
    created_by: tester
```

## Big Tasks
```yaml
- id: big-1
  title: Big
  type: feature
  status: in_progress
  priority: P0
  size_points: 8
  parent_epic: epic-1
  scope_paths: []
  spec: ''
  budgets: {}
  risks: []
  dependencies: []
  progress_pct: 0
  health: green
  acceptance: []
  tests_required: []
  verify_commands: []
  docs_updates: []
  artifacts: []
  audit:
    created_at: '2025-01-01T00:00:00Z'
    created_by: tester
```
"""


def test_progress_updates_manifest_and_todo(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path
    (root / "architecture").mkdir()
    (root / "reports").mkdir()
    manifest_path = root / "architecture" / "manifest.yaml"
    todo_path = root / "todo.machine.md"

    manifest_path.write_text(yaml.dump(make_manifest(), sort_keys=False, allow_unicode=True), encoding="utf-8")
    todo_path.write_text(make_todo(), encoding="utf-8")

    monkeypatch.setattr(progress, "ROOT", root)
    monkeypatch.setattr(progress, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(progress, "TODO_PATH", todo_path)

    progress.run(dry_run=False)

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["program"]["progress"]["progress_pct"] == 100
    assert manifest["program"]["milestones"][0]["status"] == "done"
    assert manifest["updated_at"].endswith("Z")
    assert manifest["updated_at"] != "2025-01-01T00:00:00Z"

    todo = todo_path.read_text(encoding="utf-8")
    assert "progress_pct: 100" in todo
    assert "status: done" in todo

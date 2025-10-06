#!/usr/bin/env python3
"""Generate a compact agent digest for the AgentControl SDK repo."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentcontrol import __version__
CAPSULE_STATE = ROOT / ".agentcontrol" / "state"
FALLBACK_STATE = ROOT / "state"

def resolve_state_dir() -> Path:
    if CAPSULE_STATE.exists():
        return CAPSULE_STATE
    if CAPSULE_STATE.parent.exists():
        return CAPSULE_STATE
    return FALLBACK_STATE


def resolve_digest_path() -> Path:
    state_dir = resolve_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "agent_digest.json"
MAX_ITEMS = 5
MAX_LENGTH = 4096  # bytes


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}
    except yaml.YAMLError:
        return {}


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except json.JSONDecodeError:
        return {}


def health_summary(agent_cfg: Dict[str, Any]) -> Dict[str, Any]:
    health = agent_cfg.get("HEALTH") or {}
    return {
        "status": health.get("status"),
        "progress_pct": health.get("progress_pct"),
        "risks": (health.get("risks") or [])[:MAX_ITEMS],
        "next": (health.get("next") or [])[:MAX_ITEMS],
    }


def open_tasks(agent_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks = agent_cfg.get("TASKS") or []
    if not isinstance(tasks, list):
        return []
    result: List[Dict[str, Any]] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status == "done":
            continue
        result.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": status,
                "priority": item.get("priority"),
            }
        )
    return result[:MAX_ITEMS]


def summarize_verify(report: Dict[str, Any]) -> Dict[str, Any]:
    steps = report.get("steps") or []
    failing: List[Dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("status") != "ok":
            failing.append({
                "name": step.get("name"),
                "status": step.get("status"),
                "severity": step.get("severity"),
            })
    return {
        "exit_code": report.get("exit_code"),
        "generated_at": report.get("generated_at"),
        "failing": failing[:MAX_ITEMS],
    }


def summarize_status(report: Dict[str, Any]) -> Dict[str, Any]:
    roadmap = report.get("roadmap") or {}
    program = roadmap.get("program") or {}
    return {
        "health": program.get("health"),
        "progress_pct": program.get("progress_pct"),
    }


def build_digest() -> Dict[str, Any]:
    agents = load_yaml(ROOT / "AGENTS.md")
    verify_report = load_json(ROOT / "reports" / "verify.json")
    status_report = load_json(ROOT / "reports" / "status.json")
    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sdk_version": __version__,
        "health": health_summary(agents),
        "tasks": open_tasks(agents),
        "verify": summarize_verify(verify_report),
        "roadmap": summarize_status(status_report),
    }
    return digest


def main() -> int:
    digest = build_digest()
    payload = json.dumps(digest, ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_LENGTH:
        # Drop tasks first, then risks if still large
        digest["tasks"] = []
        digest.setdefault("health", {}).update({"risks": [], "next": []})
        payload = json.dumps(digest, ensure_ascii=False, separators=(",", ":"))
        if len(payload.encode("utf-8")) > MAX_LENGTH:
            digest = {"generated_at": digest["generated_at"], "sdk_version": __version__}
            payload = json.dumps(digest, ensure_ascii=False, separators=(",", ":"))

    digest_path = resolve_digest_path()
    digest_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

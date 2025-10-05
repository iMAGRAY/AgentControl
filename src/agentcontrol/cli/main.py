#!/usr/bin/env python3
"""Entry point for the agentcall CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import select
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

from agentcontrol.app.bootstrap_service import BootstrapService
from agentcontrol.app.command_service import CommandService
from agentcontrol.app.docs import DocsBridgeService, DocsBridgeServiceError, DocsCommandService
from agentcontrol.app.mission.service import MissionService, MissionExecResult
from agentcontrol.app.mcp.manager import MCPManager
from agentcontrol.app.runtime.service import RuntimeService
from agentcontrol.app.info import InfoService
from agentcontrol.app.migration.service import MigrationService
from agentcontrol.app.sandbox.service import SandboxService
from agentcontrol.domain.project import PROJECT_DESCRIPTOR, PROJECT_DIR, ProjectId, ProjectNotInitialisedError
from agentcontrol.adapters.fs_template_repo import FSTemplateRepository
from agentcontrol.settings import SETTINGS
from agentcontrol.domain.mcp import MCPServerConfig
from agentcontrol.utils.telemetry import clear as telemetry_clear
from agentcontrol.utils.telemetry import iter_events as telemetry_iter
from agentcontrol.utils.telemetry import record_event, record_structured_event, summarize as telemetry_summarize
from agentcontrol.runtime import stream_events
from agentcontrol.plugins import PluginContext
from agentcontrol import __version__

MISSION_FILTER_CHOICES = ("docs", "quality", "tasks", "timeline", "mcp")
from agentcontrol.plugins.loader import load_plugins
from agentcontrol.utils.updater import maybe_auto_update


def _truthy_env(var: str) -> bool:
    return os.environ.get(var, "").strip().lower() in {"1", "true", "yes", "on"}


def _default_project_path(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg).expanduser().resolve()
    return Path(os.getcwd())


def _state_directory_for(project_path: Path) -> Path:
    digest = hashlib.sha256(str(project_path).encode("utf-8")).hexdigest()[:16]
    return SETTINGS.state_dir / digest


def _build_services() -> tuple[BootstrapService, CommandService]:
    template_repo = FSTemplateRepository(SETTINGS.template_dir)
    bootstrap = BootstrapService(template_repo, SETTINGS)
    command_service = CommandService(SETTINGS)
    bootstrap.ensure_bootstrap_prerequisites()
    _sync_packaged_templates()
    return bootstrap, command_service


def _sync_packaged_templates() -> None:
    package_root = Path(__file__).resolve().parents[1]
    source_base = package_root / "templates"
    source_version_dir = source_base / SETTINGS.cli_version
    if not source_version_dir.exists():
        candidates = [p for p in source_base.iterdir() if p.is_dir()]
        if not candidates:
            return
        source_version_dir = sorted(candidates)[-1]

    target_version_dir = SETTINGS.template_dir / "stable" / SETTINGS.cli_version
    if target_version_dir.exists():
        shutil.rmtree(target_version_dir)
    shutil.copytree(source_version_dir, target_version_dir, dirs_exist_ok=True)

    for entry in target_version_dir.iterdir():
        if entry.is_dir():
            checksum = _compute_template_checksum(entry)
            (entry / "template.sha256").write_text(f"{checksum}\n", encoding="utf-8")


def _compute_template_checksum(target: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(target.rglob("*")):
        if path.is_file() and path.name != "template.sha256":
            digest.update(path.relative_to(target).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _print_project_hint(project_path: Path, command: str) -> None:
    print(f"Path {project_path} does not contain an AgentControl project.", file=sys.stderr)
    print("This directory is not an AgentControl project.", file=sys.stderr)
    print('Run `agentcall init [--template ...]` here, or pass the project path explicitly.', file=sys.stderr)
    print('Example: `agentcall status /path/to/project`', file=sys.stderr)
    print('Auto-initialisation runs automatically unless you set `AGENTCONTROL_NO_AUTO_INIT=1`. Use `AGENTCONTROL_AUTO_INIT=0` to opt out explicitly.', file=sys.stderr)
    record_event(SETTINGS, 'error.project_missing', {'command': command, 'cwd': str(project_path)})


def _auto_bootstrap_project(bootstrap: BootstrapService, project_path: Path, command: str) -> ProjectId | None:
    if _truthy_env('AGENTCONTROL_NO_AUTO_INIT'):
        record_event(SETTINGS, 'autobootstrap.disabled', {'command': command, 'cwd': str(project_path)})
        return None

    env_value = os.environ.get('AGENTCONTROL_AUTO_INIT')
    auto_enabled = True if env_value is None or env_value.strip() == '' else _truthy_env('AGENTCONTROL_AUTO_INIT')
    if not auto_enabled:
        return None
    capsule_dir = project_path / PROJECT_DIR
    descriptor = capsule_dir / PROJECT_DESCRIPTOR
    if descriptor.exists():
        return ProjectId.from_existing(project_path)
    if capsule_dir.exists() and any(capsule_dir.iterdir()):
        return None
    channel = os.environ.get('AGENTCONTROL_DEFAULT_CHANNEL', 'stable')
    template = os.environ.get('AGENTCONTROL_DEFAULT_TEMPLATE', 'default')
    print(f"agentcall: auto-initialising capsule in {capsule_dir} using {template}@{channel}")
    project_id = ProjectId.for_new_project(project_path)
    try:
        bootstrap.bootstrap(project_id, channel, template=template, force=False)
    except Exception as exc:  # noqa: BLE001
        print(f"agentcall: auto initialisation failed: {exc}", file=sys.stderr)
        record_event(SETTINGS, 'autobootstrap.fail', {'command': command, 'cwd': str(project_path), 'error': str(exc)})
        return None
    try:
        confirmed = ProjectId.from_existing(project_path)
    except ProjectNotInitialisedError:
        record_event(SETTINGS, 'autobootstrap.missing_descriptor', {'command': command, 'cwd': str(project_path)})
        return None
    record_event(SETTINGS, 'autobootstrap.ok', {'command': command, 'cwd': str(project_path), 'template': template, 'channel': channel})
    print('agentcall: capsule ready — continuing command execution')
    return confirmed


def _resolve_project_id(bootstrap: BootstrapService, project_path: Path, command: str, *, allow_auto: bool) -> ProjectId | None:
    try:
        return ProjectId.from_existing(project_path)
    except ProjectNotInitialisedError:
        if allow_auto:
            project_id = _auto_bootstrap_project(bootstrap, project_path, command)
            if project_id is not None:
                return project_id
        _print_project_hint(project_path, command)
        return None


def _bootstrap_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(args.path)
    project_id = ProjectId.for_new_project(project_path)
    bootstrap.bootstrap(
        project_id,
        args.channel,
        template=args.template,
        force=args.force,
    )
    record_event(
        SETTINGS,
        "init",
        {"channel": args.channel, "template": args.template, "force": args.force},
    )
    print(f"Project initialised at {project_path}")
    return 0


def _upgrade_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(args.path)
    project_id = _resolve_project_id(bootstrap, project_path, 'upgrade', allow_auto=False)
    if project_id is None:
        return 1

    bootstrap.upgrade(project_id, args.channel, template=args.template)
    record_event(
        SETTINGS,
        "upgrade",
        {"channel": args.channel, "template": args.template or "(existing)"},
    )
    print(f"Project upgraded at {project_path}")
    return 0


def _run_pipeline(command: str, args: argparse.Namespace) -> int:
    bootstrap, command_service = _build_services()
    project_path = _default_project_path(args.path)
    project_id = _resolve_project_id(bootstrap, project_path, command, allow_auto=True)
    if project_id is None:
        return 1

    extra = getattr(args, "extra", []) or []
    exit_code = command_service.run(project_id, command, list(extra))
    record_event(SETTINGS, "run", {"command": command, "exit_code": exit_code})
    return exit_code


def _run_cmd(args: argparse.Namespace) -> int:
    return _run_pipeline(args.command_name, args)


def _list_cmd(args: argparse.Namespace) -> int:
    from agentcontrol.app.command_service import CommandRegistry

    bootstrap, _ = _build_services()
    project_path = _default_project_path(args.path)
    project_id = _resolve_project_id(bootstrap, project_path, 'commands', allow_auto=True)
    if project_id is None:
        return 1
    registry = CommandRegistry.load_from_file(project_id.command_descriptor_path())
    for name in registry.list_commands():
        print(name)
    return 0


def _cleanup_cmd(args: argparse.Namespace) -> int:
    project_path = _default_project_path(args.path)
    state_dir = _state_directory_for(project_path)
    if state_dir.exists():
        import shutil

        shutil.rmtree(state_dir)
        print(f"Removed state directory {state_dir}")
    else:
        print("No state directory found.")
    return 0


def _templates_cmd(args: argparse.Namespace) -> int:
    _sync_packaged_templates()
    channel_dir = SETTINGS.template_dir / args.channel
    templates = []
    if channel_dir.exists():
        for version_dir in sorted(p for p in channel_dir.iterdir() if p.is_dir()):
            for entry in sorted(p for p in version_dir.iterdir() if p.is_dir()):
                templates.append((entry.name, version_dir.name))
    if not templates:
        print("No templates installed", file=sys.stderr)
        return 1
    seen = set()
    def version_key(item):
        name, version = item
        try:
            parts = tuple(int(p) for p in version.split('.'))
        except ValueError:
            parts = (0,)
        return parts

    for name, version in sorted(templates, key=version_key, reverse=True):
        if name in seen:
            continue
        seen.add(name)
        print(f"{name} (version {version})")
    record_event(SETTINGS, "templates", {"count": len(seen), "channel": args.channel})
    return 0


def _telemetry_cmd(args: argparse.Namespace) -> int:
    if args.telemetry_command == "report":
        events = list(telemetry_iter(SETTINGS))
        summary = telemetry_summarize(events)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    if args.telemetry_command == "clear":
        telemetry_clear(SETTINGS)
        print("Telemetry log cleared")
        return 0
    if args.telemetry_command == "tail":
        from collections import deque

        limit = args.limit
        dq = deque(maxlen=limit)
        for evt in telemetry_iter(SETTINGS):
            dq.append(evt)
        for evt in dq:
            print(json.dumps(evt, ensure_ascii=False))
        return 0
    print("Unsupported telemetry command", file=sys.stderr)
    return 2


def _self_update_cmd(args: argparse.Namespace) -> int:
    mode = args.mode
    if mode == "print":
        print(
            "Run one of:\n"
            "  pipx install agentcontrol --force\n"
            f"  {sys.executable} -m pip install --upgrade agentcontrol",
            file=sys.stdout,
        )
        record_event(SETTINGS, "self-update", {"mode": "print"})
        return 0

    if mode == "pipx":
        command = ["pipx", "install", "agentcontrol", "--force"]
    else:
        command = [sys.executable, "-m", "pip", "install", "--upgrade", "agentcontrol"]

    result = subprocess.run(command)
    record_event(SETTINGS, "self-update", {"mode": mode, "exit_code": result.returncode})
    return result.returncode


def _plugins_cmd(args: argparse.Namespace) -> int:
    action = args.plugins_command
    if action == "list":
        eps = metadata.entry_points().select(group="agentcontrol.plugins")
        if not eps:
            print("No plugins registered")
            record_event(SETTINGS, "plugins.list", {"count": 0})
            return 0
        sorted_eps = sorted(eps, key=lambda e: e.name)
        for ep in sorted_eps:
            dist = getattr(ep, "dist", None)
            dist_name = dist.name if dist else "unknown"
            print(f"{ep.name}\t{ep.value}\t[{dist_name}]")
        record_event(SETTINGS, "plugins.list", {"count": len(sorted_eps)})
        return 0

    if action == "install":
        package = args.package
        if args.mode == "pipx":
            command = ["pipx", "install", package]
        else:
            command = [sys.executable, "-m", "pip", "install", package]
        code = subprocess.run(command).returncode
        record_event(SETTINGS, "plugins.install", {"package": package, "mode": args.mode, "exit_code": code})
        return code

    if action == "remove":
        package = args.package
        if args.mode == "pipx":
            command = ["pipx", "uninstall", package]
        else:
            command = [sys.executable, "-m", "pip", "uninstall", package]
        code = subprocess.run(command).returncode
        record_event(SETTINGS, "plugins.remove", {"package": package, "mode": args.mode, "exit_code": code})
        return code

    if action == "info":
        name = args.name
        eps = metadata.entry_points().select(group="agentcontrol.plugins")
        for ep in eps:
            if ep.name == name:
                dist = getattr(ep, "dist", None)
                print(f"Name: {ep.name}")
                print(f"Target: {ep.value}")
                if dist is not None:
                    print(f"Distribution: {dist.name} {dist.version}")
                    if dist.metadata:
                        summary = dist.metadata.get("Summary")
                        if summary:
                            print(f"Summary: {summary}")
                record_event(SETTINGS, "plugins.info", {"plugin": name, "found": True})
                return 0
        print(f"Plugin {name} not found", file=sys.stderr)
        record_event(SETTINGS, "plugins.info", {"plugin": name, "found": False})
        return 1

    print("Unsupported plugin command", file=sys.stderr)
    return 2


def _docs_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "docs", allow_auto=True)
    if project_id is None:
        return 1

    bridge_service = DocsBridgeService()
    command_service = DocsCommandService()
    command = args.docs_command
    as_json = getattr(args, "json", False)
    event_context = {"command": command, "path": str(project_path)}
    record_structured_event(
        SETTINGS,
        f"docs.{command}",
        status="start",
        component="docs",
        payload=event_context,
    )
    start = time.perf_counter()

    try:
        if command == "diagnose":
            payload = bridge_service.diagnose(project_path)
            exit_code = 0 if payload.get("status") != "error" else 1
            _emit_docs_result(payload, as_json, exit_code, command)
        elif command == "info":
            try:
                payload = bridge_service.info(project_path)
                exit_code = 0
            except DocsBridgeServiceError as exc:
                payload = {
                    "status": "error",
                    "issues": [
                        {
                            "severity": "error",
                            "code": exc.code,
                            "message": exc.message,
                            "remediation": exc.remediation,
                        }
                    ],
                }
                exit_code = 1
            _emit_docs_result(payload, as_json, exit_code, command)
        elif command == "list":
            payload = command_service.list_sections(project_path)
            if as_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                _print_docs_list(payload)
            exit_code = 0
        elif command == "diff":
            sections = getattr(args, "sections", None)
            payload = command_service.diff_sections(project_path, sections=sections)
            if as_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                _print_docs_diff(payload)
            exit_code = 0 if all(item["status"] == "match" for item in payload["diff"]) else 1
        elif command == "repair":
            sections = getattr(args, "sections", None)
            entries = getattr(args, "entries", None)
            payload = command_service.repair_sections(project_path, sections=sections, entries=entries)
            if as_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                _print_docs_actions("repair", payload)
            exit_code = 0
        elif command == "adopt":
            sections = getattr(args, "sections", None)
            entries = getattr(args, "entries", None)
            payload = command_service.adopt_sections(project_path, sections=sections, entries=entries)
            if as_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                _print_docs_actions("adopt", payload)
            exit_code = 0
        elif command == "rollback":
            sections = getattr(args, "sections", None)
            entries = getattr(args, "entries", None)
            payload = command_service.rollback_sections(
                project_path,
                timestamp=args.timestamp,
                sections=sections,
                entries=entries,
            )
            if as_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                _print_docs_actions("rollback", payload)
            exit_code = 0
        elif command == "sync":
            sections = getattr(args, "sections", None)
            entries = getattr(args, "entries", None)
            mode = getattr(args, "mode", "repair")
            payload = command_service.sync_sections(
                project_path,
                mode=mode,
                sections=sections,
                entries=entries,
            )
            if as_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                _print_docs_sync(payload)
            exit_code = 0 if payload.get("status") == "ok" else 1
        else:
            record_structured_event(
                SETTINGS,
                f"docs.{command}",
                status="error",
                level="error",
                component="docs",
                payload=event_context | {"message": "unsupported"},
            )
            print("Unsupported docs command", file=sys.stderr)
            return 2
    except DocsBridgeServiceError as exc:
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            f"docs.{command}",
            status="error",
            level="error",
            component="docs",
            duration_ms=duration,
            payload=event_context | {"code": exc.code, "message": exc.message},
        )
        print(f"docs {command} failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - propagate unexpected issues
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            f"docs.{command}",
            status="error",
            level="error",
            component="docs",
            duration_ms=duration,
            payload=event_context | {"error": str(exc)},
        )
        raise

    duration = (time.perf_counter() - start) * 1000
    status_label = "success" if exit_code == 0 else "warning"
    level = "info" if exit_code == 0 else "warn"
    record_structured_event(
        SETTINGS,
        f"docs.{command}",
        status=status_label,
        level=level,
        component="docs",
        duration_ms=duration,
        payload=event_context | {"exit_code": exit_code},
    )
    return exit_code


def _emit_docs_result(payload: dict, as_json: bool, exit_code: int, command: str) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_docs_summary(payload, command)
    return exit_code


def _print_docs_summary(payload: dict, command: str) -> None:
    status = payload.get("status", "ok")
    print(f"docs {command}: status={status}")
    issues = payload.get("issues", [])
    if issues:
        print("issues:")
        for item in issues:
            code = item.get("code")
            message = item.get("message")
            remediation = item.get("remediation")
            print(f"  - {code}: {message}")
            if remediation:
                print(f"    remediation: {remediation}")
    if command == "info" and status != "error":
        capabilities = payload.get("capabilities", {})
        print("capabilities:")
        for key, value in capabilities.items():
            print(f"  - {key}: {value}")


def _print_docs_list(payload: dict) -> None:
    print(f"docs list @ {payload.get('generatedAt')}")
    for section in payload.get("sections", []):
        status = section.get("status", "unknown")
        name = section.get("name")
        marker = section.get("marker")
        target = section.get("target") or section.get("directory")
        print(f"  - {name}: status={status} target={target}")
        if marker:
            print(f"      marker={marker}")


def _print_docs_diff(payload: dict) -> None:
    print(f"docs diff @ {payload.get('generatedAt')}")
    for entry in payload.get("diff", []):
        name = entry.get("name")
        status = entry.get("status")
        path = entry.get("path")
        print(f"  - {name}: {status} ({path})")
        if status == "differs":
            print(f"      expectedHash={entry.get('expectedHash')} actualHash={entry.get('actualHash')}")
        if entry.get("error"):
            print(f"      error={entry['error']}")


def _print_docs_actions(operation: str, payload: dict) -> None:
    print(f"docs {operation} @ {payload.get('generatedAt')}")
    backup = payload.get("backup")
    if backup:
        print(f"  backup: {backup}")
    for action in payload.get("actions", []):
        name = action.get("name")
        path = action.get("path")
        action_type = action.get("action")
        print(f"  - {name}: {action_type} ({path})")


def _print_docs_sync(payload: dict) -> None:
    print(f"docs sync ({payload.get('mode')}) @ {payload.get('generatedAt')}")
    processed = payload.get("sections") or []
    if processed:
        print(f"  processed: {', '.join(processed)}")
    else:
        print("  processed: none (already in sync)")
    for step in payload.get("steps", []):
        label = step.get("step")
        if label == "diff-after":
            issues = [entry for entry in step.get("diff", []) if entry.get("status") != "match"]
            print(f"  {label}: {len(issues)} issues remaining")
        elif label in {"repair", "adopt"} and step.get("payload"):
            actions = step["payload"].get("actions", [])
            print(f"  {label}: {len(actions)} actions")
        elif step.get("skipped"):
            print(f"  {label}: skipped")


def _print_mission_exec(result: MissionExecResult, *, as_json: bool) -> None:
    if as_json:
        payload = {
            "status": result.status,
            "playbook": result.playbook,
            "action": result.action,
            "message": result.message,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"mission exec: status={result.status}")
    if result.playbook:
        display = result.playbook.get("issue")
        priority = result.playbook.get("priority")
        if priority is not None:
            display = f"[{priority}] {display}"
        print(f"  playbook: {display}")
        if result.playbook.get("hint"):
            print(f"    hint: {result.playbook['hint']}")
    else:
        print("  playbook: none")
    if result.action:
        action_type = result.action.get("type")
        print(f"  action: {action_type}")
        payload = result.action.get("payload")
        if isinstance(payload, dict) and payload.get("status"):
            print(f"    payload status: {payload.get('status')}")
        if action_type == "verify_pipeline":
            print(f"    exit_code: {result.action.get('exit_code')}")
    if result.message:
        print(f"  note: {result.message}")
    print()


def _info_cmd(args: argparse.Namespace) -> int:
    service = InfoService()
    path_arg = getattr(args, "path", None)
    project_path = _default_project_path(path_arg) if path_arg else None
    event_context = {"path": str(project_path) if project_path else None}
    record_structured_event(
        SETTINGS,
        "info.collect",
        status="start",
        component="info",
        payload=event_context,
    )
    start = time.perf_counter()
    try:
        payload = service.collect(project_path).data
    except Exception as exc:  # pragma: no cover - unexpected failure path
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            "info.collect",
            status="error",
            level="error",
            component="info",
            duration_ms=duration,
            payload=event_context | {"error": str(exc)},
        )
        print(f"info command failed: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_info_summary(payload)

    duration = (time.perf_counter() - start) * 1000
    record_structured_event(
        SETTINGS,
        "info.collect",
        status="success",
        component="info",
        duration_ms=duration,
        payload=event_context | {"features": list(payload.get("features", {}).keys())},
    )
    return 0


def _print_info_summary(payload: dict[str, Any]) -> None:
    version = payload.get("version", "unknown")
    print(f"agentcall version: {version}")
    features = payload.get("features", {})
    if features:
        print("features:")
        for name, meta in features.items():
            print(f"  - {name}:")
            if isinstance(meta, dict):
                for key, value in meta.items():
                    print(f"      {key}: {value}")
            else:
                print(f"      {meta}")
    mission_snapshot = payload.get("mission")
    if mission_snapshot:
        print("mission snapshot available")
        twin_path = mission_snapshot.get("twinPath")
        if twin_path:
            print(f"  twin: {twin_path}")


def _clear_terminal() -> None:
    print("\033[2J\033[H", end="")


def _log_palette_action(project_path: Path, entry: dict[str, Any], result: MissionExecResult) -> None:
    report_dir = project_path / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_path = report_dir / "mission-actions.json"
    log_data: list[dict[str, Any]] = []
    if log_path.exists():
        try:
            log_data = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(log_data, list):
                log_data = []
        except json.JSONDecodeError:
            log_data = []
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "id": entry.get("id"),
        "label": entry.get("label"),
        "action": entry.get("action"),
        "status": result.status,
        "message": result.message,
    }
    if result.action:
        log_entry["resultAction"] = result.action
    if result.playbook:
        log_entry["playbook"] = result.playbook
    log_data.append(log_entry)
    log_path.write_text(json.dumps(log_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _update_mission_dashboard(project_path: Path, analytics: dict[str, Any]) -> None:
    report_dir = project_path / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = report_dir / "architecture-dashboard.json"
    data: dict[str, Any]
    if dashboard_path.exists():
        try:
            data = json.loads(dashboard_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    data.setdefault("mission", {})
    data["mission"] = analytics | {"updated_at": datetime.now(timezone.utc).isoformat()}
    dashboard_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _render_mission_dashboard(
    payload: dict[str, Any],
    twin_path: Path,
    *,
    filters: Iterable[str] | None = None,
    timeline_limit: int = 5,
    interactive: bool = True,
    title: str | None = None,
    palette: Iterable[dict[str, Any]] | None = None,
) -> None:
    active_filters = {item.lower() for item in (filters or MISSION_FILTER_CHOICES)}
    header_label = title or "Mission Control"
    generated = payload.get("generated_at")
    if generated:
        header_label = f"{header_label} — generated {generated}"
    print(header_label)
    print("=" * len(header_label))
    print(f"twin file: {twin_path}")

    if "docs" in active_filters:
        docs = payload.get("docsBridge", {})
        docs_status = docs.get("status", "unknown")
        issues = docs.get("issues", [])
        print(f"docs status: {docs_status} (issues: {len(issues)})")
        if issues:
            for issue in issues[:3]:
                code = issue.get("code", "?")
                message = issue.get("message", "")
                print(f"  - {code}: {message}")
        summary = docs.get("summary", {}) if isinstance(docs, dict) else {}
        sections = summary.get("sections", []) if isinstance(summary, dict) else []
        degraded_sections = [section for section in sections if section.get("status") not in {"ok", "external"}]
        if degraded_sections:
            print("  sections:")
            for section in degraded_sections[:5]:
                print(f"    - {section.get('name')}: {section.get('status')}")

    program = payload.get("program", {})
    roadmap = program.get("roadmap", {}) if isinstance(program, dict) else {}
    if "tasks" in active_filters:
        program_meta = roadmap.get("program", {}) if isinstance(roadmap, dict) else {}
        progress = program_meta.get("progress_pct")
        health = program_meta.get("health")
        if progress is not None:
            print(f"program progress: {progress}% (health: {health})")
        phase_progress = roadmap.get("phase_progress", {}) if isinstance(roadmap, dict) else {}
        if phase_progress:
            leading = sorted(phase_progress.items(), key=lambda item: item[0])[:3]
            phase_display = ", ".join(f"{name}: {value}%" for name, value in leading)
            print(f"phase progress: {phase_display}")
        tasks = roadmap.get("tasks", {}) if isinstance(roadmap, dict) else {}
        counts = tasks.get("counts") or program.get("tasks", {}).get("counts") if isinstance(program, dict) else {}
        if counts:
            total = sum(counts.values())
            done = counts.get("done", 0)
            print(f"tasks done: {done}/{total}")

    if "quality" in active_filters:
        verify = payload.get("quality", {}).get("verify", {})
        if verify:
            status = verify.get("status")
            available = verify.get("available")
            state = status or ("available" if available else "unavailable")
            print(f"verify status: {state}")
            summary = verify.get("summary")
            if isinstance(summary, dict) and summary:
                for name, value in list(summary.items())[:3]:
                    print(f"  {name}: {value}")

    if "mcp" in active_filters:
        mcp = payload.get("mcp", {})
        count = mcp.get("count", 0)
        print(f"mcp servers: {count}")
        servers = mcp.get("servers") or []
        for server in servers[:3]:
            name = server.get("name")
            endpoint = server.get("endpoint")
            print(f"  - {name}: {endpoint}")

    if "timeline" in active_filters:
        timeline = payload.get("timeline") or []
        if timeline:
            print("timeline:")
            for entry in timeline[:timeline_limit]:
                timestamp = entry.get("timestamp") or "unknown"
                category = entry.get("category", "general")
                event = entry.get("event") or entry.get("details", {}).get("event") or "-"
                print(f"  - [{timestamp}] ({category}) {event}")
                hint = entry.get("hint")
                if hint:
                    print(f"      hint: {hint}")

    playbooks = payload.get("playbooks") or []
    if playbooks:
        print("playbooks:")
        for playbook in playbooks[:3]:
            priority = playbook.get("priority")
            label = f"[{priority}] " if priority is not None else ""
            print(f"  - {label}{playbook.get('issue')}: {playbook.get('command')}")
            if playbook.get("summary"):
                print(f"      {playbook['summary']}")
            if playbook.get("hint"):
                print(f"      hint: {playbook['hint']}")

    activity = payload.get("activity") or {}
    recent_actions = activity.get("recent") or []
    if recent_actions:
        print("recent mission actions:")
        for action in recent_actions[:5]:
            label = action.get("label") or action.get("id")
            status = action.get("status")
            timestamp = action.get("timestamp")
            print(f"  - [{timestamp}] {label} → {status}")

    acknowledgements = payload.get("acknowledgements") or {}
    if acknowledgements:
        print("acknowledgements:")
        for category, meta in acknowledgements.items():
            status = meta.get("status")
            updated = meta.get("updated_at")
            message = meta.get("message")
            note = f" ({message})" if message else ""
            print(f"  - {category}: {status}@{updated}{note}")

    perf = payload.get("perf") or {}
    regressions = perf.get("regressions") or []
    if perf:
        print(f"perf regressions: {len(regressions)}")
        for reg in regressions[:3]:
            operation = reg.get("operation")
            delta = reg.get("delta_ms")
            print(f"  - {operation}: Δ {delta} ms")
        diff_path = perf.get("diffPath")
        if diff_path:
            print(f"  diff: {diff_path}")

    if interactive:
        if palette:
            hotkeys = []
            for entry in palette:
                hotkey = entry.get("hotkey")
                label = entry.get("label") or entry.get("command")
                if hotkey and label:
                    hotkeys.append(f"{hotkey}:{label}")
            if hotkeys:
                print("\nPalette hotkeys: " + " | ".join(hotkeys))
        print("Press Ctrl+C or 'q' to exit, 'r' to refresh now")


def _print_mission_analytics(payload: dict[str, Any]) -> None:
    activity = payload.get("activity") or {}
    perf = payload.get("perf") or {}
    acknowledgements = payload.get("acknowledgements") or {}

    print("Mission Analytics")
    print("=================")
    print(f"activity count: {activity.get('count', 0)}")
    recent = activity.get("recent") or []
    if recent:
        print("recent actions:")
        for entry in recent[:5]:
            timestamp = entry.get("timestamp")
            label = entry.get("label") or entry.get("id")
            status = entry.get("status")
            print(f"  - [{timestamp}] {label} → {status}")
    print()

    if acknowledgements:
        print("acknowledgements:")
        for category, meta in acknowledgements.items():
            status = meta.get("status")
            updated_at = meta.get("updated_at")
            message = meta.get("message")
            note = f" ({message})" if message else ""
            print(f"  - {category}: {status} @ {updated_at}{note}")
        print()

    regressions = perf.get("regressions") or []
    print(f"open perf regressions: {len(regressions)}")
    if regressions:
        for reg in regressions[:5]:
            operation = reg.get("operation")
            delta = reg.get("delta_ms")
            print(f"  - {operation}: Δ {delta} ms")
    diff_path = perf.get("diffPath")
    if diff_path:
        print(f"diff file: {diff_path}")
    print()


def _mission_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "mission", allow_auto=True)
    if project_id is None:
        return 1

    service = MissionService()
    command = getattr(args, "mission_command", "summary")
    try:
        filters = _normalize_filters(getattr(args, "filters", None))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    timeline_limit = getattr(args, "timeline_limit", 5)

    event_context: dict[str, Any] = {"command": command, "path": str(project_path)}
    if filters:
        event_context["filters"] = filters
    if hasattr(args, "timeline_limit"):
        event_context["timeline_limit"] = getattr(args, "timeline_limit")
    if command == "detail":
        event_context["section"] = getattr(args, "section")

    record_structured_event(
        SETTINGS,
        f"mission.{command}",
        status="start",
        component="mission",
        payload=event_context,
    )
    start = time.perf_counter()

    if command == "summary":
        result = service.persist_twin(project_path)
        payload = result.twin
        if payload.get("palette"):
            service.persist_palette(project_path, payload.get("palette"))
        as_json = getattr(args, "json", False)
        if as_json:
            summary_payload = dict(payload)
            if filters:
                summary_payload = {**payload, "filtersApplied": filters}
            print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
        else:
            _print_mission_summary(payload, result.path, filters=filters or None, timeline_limit=timeline_limit)
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            "mission.summary",
            status="success",
            component="mission",
            duration_ms=duration,
            payload=event_context | {"twin": str(result.path)},
        )
        return 0

    if command == "ui":
        interval = getattr(args, "interval", 2.0)
        return _mission_ui(service, project_path, interval, filters, timeline_limit)

    if command == "detail":
        section = getattr(args, "section")
        result = service.persist_twin(project_path)
        payload = result.twin
        drilldown = payload.get("drilldown", {}) if isinstance(payload, dict) else {}
        detail_payload = drilldown.get(section, {})
        if section == "timeline":
            detail_payload = payload.get("timeline", [])[:timeline_limit]
        if getattr(args, "json", False):
            print(json.dumps({"section": section, "detail": detail_payload}, ensure_ascii=False, indent=2))
        else:
            _print_mission_detail(section, detail_payload, timeline_limit=timeline_limit)
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            "mission.detail",
            status="success",
            component="mission",
            duration_ms=duration,
            payload=event_context | {"section": section},
        )
        return 0

    duration = (time.perf_counter() - start) * 1000
    record_structured_event(
        SETTINGS,
        f"mission.{command}",
        status="error",
        level="error",
        component="mission",
        duration_ms=duration,
        payload=event_context | {"message": "unsupported"},
    )
    print("Unsupported mission command", file=sys.stderr)
    return 2


def _mission_exec_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "mission", allow_auto=True)
    if project_id is None:
        return 1

    service = MissionService()
    event_context = {"path": str(project_path)}
    record_structured_event(
        SETTINGS,
        "mission.exec",
        status="start",
        component="mission",
        payload=event_context,
    )
    issue = getattr(args, "issue", None)
    if issue:
        event_context["issue"] = issue
    start = time.perf_counter()
    if issue:
        result = service.execute_playbook_by_issue(project_path, issue)
    else:
        result = service.execute_top_playbook(project_path)
    duration = (time.perf_counter() - start) * 1000
    telemetry_status = "success"
    if result.status == "error":
        telemetry_status = "error"
    elif result.status == "warning":
        telemetry_status = "warning"

    payload: dict[str, Any] = {
        "playbook": result.playbook.get("issue") if result.playbook else issue,
        "category": result.playbook.get("category") if result.playbook else None,
        "action": result.action.get("type") if result.action else None,
    }
    if result.action and result.action.get("type") == "verify_pipeline":
        payload["exit_code"] = result.action.get("exit_code")
    if result.message:
        payload["message"] = result.message

    record_structured_event(
        SETTINGS,
        "mission.exec",
        status=telemetry_status,
        component="mission",
        duration_ms=duration,
        payload=event_context | payload,
    )

    _print_mission_exec(result, as_json=getattr(args, "json", False))
    log_entry = {
        "id": f"playbook:{payload.get('playbook') or issue or 'unknown'}",
        "label": payload.get("playbook") or issue or "mission exec",
        "action": {"kind": "playbook" if result.playbook else "mission_exec_top", "issue": payload.get("playbook") or issue},
    }
    _log_palette_action(project_path, log_entry, result)
    return 0 if result.status in {"success", "noop"} else 1


def _mission_analytics_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "mission", allow_auto=True)
    if project_id is None:
        return 1

    service = MissionService()
    record_structured_event(
        SETTINGS,
        "mission.analytics",
        status="start",
        component="mission",
        payload={"path": str(project_path)},
    )
    start = time.perf_counter()
    result = service.persist_twin(project_path)
    payload = result.twin
    duration = (time.perf_counter() - start) * 1000

    if getattr(args, "json", False):
        summary = {
            "activity": payload.get("activity", {}),
            "acknowledgements": payload.get("acknowledgements", {}),
            "perf": payload.get("perf", {}),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_mission_analytics(payload)

    _update_mission_dashboard(project_path, {
        "activity": payload.get("activity", {}),
        "acknowledgements": payload.get("acknowledgements", {}),
        "perf": payload.get("perf", {}),
    })

    record_structured_event(
        SETTINGS,
        "mission.analytics",
        status="success",
        component="mission",
        duration_ms=duration,
        payload={"path": str(project_path)},
    )
    return 0


def _mcp_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "mcp", allow_auto=True)
    if project_id is None:
        return 1

    manager = MCPManager.for_project(project_path)
    command = getattr(args, "mcp_command")
    event_context = {"command": command, "path": str(project_path)}
    record_structured_event(
        SETTINGS,
        f"mcp.{command}",
        status="start",
        component="mcp",
        payload=event_context,
    )
    start = time.perf_counter()

    try:
        if command == "add":
            metadata = _parse_metadata(getattr(args, "meta", None))
            config = MCPServerConfig(
                name=args.name,
                endpoint=args.endpoint,
                description=getattr(args, "description", None),
                metadata=metadata,
            )
            manager.add(config, overwrite=getattr(args, "force", False))
            if getattr(args, "json", False):
                print(json.dumps({"status": "ok", "server": config.to_dict()}, ensure_ascii=False, indent=2))
            else:
                print(f"mcp add: registered {config.name} -> {config.endpoint}")
            exit_code = 0
        elif command == "remove":
            removed = manager.remove(args.name)
            exit_code = 0 if removed else 1
            message = "removed" if removed else "not found"
            if getattr(args, "json", False):
                print(json.dumps({"status": message, "name": args.name}, ensure_ascii=False, indent=2))
            else:
                print(f"mcp remove: {args.name} {message}")
        elif command == "status":
            servers = manager.list()
            if getattr(args, "json", False):
                print(json.dumps({"servers": [srv.to_dict() for srv in servers]}, ensure_ascii=False, indent=2))
            else:
                if not servers:
                    print("mcp status: no servers registered")
                else:
                    print("mcp status:")
                    for server in servers:
                        print(f"  - {server.name}: {server.endpoint}")
                        if server.description:
                            print(f"      description: {server.description}")
            exit_code = 0
        else:
            duration = (time.perf_counter() - start) * 1000
            record_structured_event(
                SETTINGS,
                f"mcp.{command}",
                status="error",
                level="error",
                component="mcp",
                duration_ms=duration,
                payload=event_context | {"message": "unsupported"},
            )
            print("Unsupported mcp command", file=sys.stderr)
            return 2
    except ValueError as exc:
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            f"mcp.{command}",
            status="error",
            level="error",
            component="mcp",
            duration_ms=duration,
            payload=event_context | {"error": str(exc)},
        )
        print(f"mcp {command} failed: {exc}", file=sys.stderr)
        return 1

    duration = (time.perf_counter() - start) * 1000
    record_structured_event(
        SETTINGS,
        f"mcp.{command}",
        status="success",
        component="mcp",
        duration_ms=duration,
        payload=event_context | {"exit_code": exit_code},
    )
    return exit_code


def _sandbox_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "sandbox", allow_auto=True)
    if project_id is None:
        return 1

    service = SandboxService(FSTemplateRepository(SETTINGS.template_dir), SETTINGS)
    command = getattr(args, "sandbox_command")
    event_context = {"command": command, "path": str(project_path)}
    record_structured_event(
        SETTINGS,
        f"sandbox.{command}",
        status="start",
        component="sandbox",
        payload=event_context,
    )
    start = time.perf_counter()

    try:
        if command == "start":
            metadata = _parse_metadata(getattr(args, "meta", None))
            descriptor = service.start(
                project_path,
                template=getattr(args, "template", None),
                metadata=metadata,
                minimal=getattr(args, "minimal", False),
            )
            payload = descriptor.to_dict()
            if getattr(args, "json", False):
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"sandbox start: {descriptor.sandbox_id}")
                print(f"  workspace: {descriptor.path}")
                if metadata:
                    print("  metadata:")
                    for key, value in metadata.items():
                        print(f"    {key}: {value}")
                print(f"next steps: cd {descriptor.path}")
            exit_code = 0
        elif command == "list":
            entries = [item.to_dict() for item in service.list(project_path)]
            if getattr(args, "json", False):
                print(json.dumps({"sandboxes": entries}, ensure_ascii=False, indent=2))
            else:
                if not entries:
                    print("sandbox list: no sandboxes provisioned")
                else:
                    print("sandbox list:")
                    for item in entries:
                        print(f"  - {item['sandbox_id']} @ {item['path']} ({item['template']})")
            exit_code = 0
        elif command == "purge":
            sandbox_id = getattr(args, "sandbox_id", None)
            purge_all = getattr(args, "all", False)
            if sandbox_id and purge_all:
                raise SandboxServiceError("Specify either --id or --all, not both")
            if not sandbox_id and not purge_all:
                raise SandboxServiceError("Use --id <sandbox> or --all to purge")
            removed = service.purge(project_path, sandbox_id=None if purge_all else sandbox_id)
            payload = [item.to_dict() for item in removed if item is not None]
            if getattr(args, "json", False):
                print(json.dumps({"removed": payload}, ensure_ascii=False, indent=2))
            else:
                if not payload:
                    print("sandbox purge: nothing removed")
                else:
                    print("sandbox purge removed:")
                    for item in payload:
                        print(f"  - {item['sandbox_id']} @ {item['path']}")
            exit_code = 0
        else:
            duration = (time.perf_counter() - start) * 1000
            record_structured_event(
                SETTINGS,
                f"sandbox.{command}",
                status="error",
                level="error",
                component="sandbox",
                duration_ms=duration,
                payload=event_context | {"message": "unsupported"},
            )
            print("Unsupported sandbox command", file=sys.stderr)
            return 2
    except SandboxServiceError as exc:
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            f"sandbox.{command}",
            status="error",
            level="error",
            component="sandbox",
            duration_ms=duration,
            payload=event_context | {"error": str(exc)},
        )
        print(f"sandbox {command} failed: {exc}", file=sys.stderr)
        return 1

    duration = (time.perf_counter() - start) * 1000
    record_structured_event(
        SETTINGS,
        f"sandbox.{command}",
        status="success",
        component="sandbox",
        duration_ms=duration,
        payload=event_context | {"exit_code": exit_code},
    )
    return exit_code




def _parse_metadata(items: Iterable[str] | None) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if not items:
        return metadata
    for entry in items:
        if "=" not in entry:
            raise ValueError(f"Metadata entry '{entry}' must be in key=value format")
        key, value = entry.split("=", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _normalize_filters(items: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    if not items:
        return normalized
    for item in items:
        key = item.lower().strip()
        if key not in MISSION_FILTER_CHOICES:
            raise ValueError(f"Unsupported filter '{item}'. Expected one of {', '.join(MISSION_FILTER_CHOICES)}")
        if key not in normalized:
            normalized.append(key)
    return normalized


def _print_runtime_manifest(payload: dict[str, Any], path: Path) -> None:
    print(f"runtime manifest: {path}")
    print(f"  version: {payload.get('version')}")
    print(f"  generated_at: {payload.get('generated_at')}")
    commands = payload.get("commands", [])
    print(f"  commands ({len(commands)}): {', '.join(commands)}")
    telemetry = payload.get("telemetry", {})
    if telemetry:
        print(f"  telemetry log: {telemetry.get('log')}")
        print(f"  telemetry schema: {telemetry.get('schema')}")


def _runtime_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "runtime", allow_auto=True)
    if project_id is None:
        return 1

    service = RuntimeService()
    command = getattr(args, "runtime_command")
    event_context = {"command": command, "path": str(project_path)}
    record_structured_event(
        SETTINGS,
        f"runtime.{command}",
        status="start",
        component="runtime",
        payload=event_context,
    )
    start = time.perf_counter()

    if command == "status":
        manifest = service.build_manifest(project_path)
        if getattr(args, "json", False):
            print(json.dumps(manifest.data, ensure_ascii=False, indent=2))
        else:
            _print_runtime_manifest(manifest.data, manifest.path)
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            "runtime.status",
            status="success",
            component="runtime",
            duration_ms=duration,
            payload=event_context | {"manifest": str(manifest.path)},
        )
        return 0

    if command == "events":
        follow = getattr(args, "follow", False)
        limit = getattr(args, "limit", 0)
        emitted = 0
        try:
            for event in stream_events(SETTINGS.log_dir, follow=follow, poll_interval=getattr(args, "poll", 0.5)):
                print(json.dumps(event, ensure_ascii=False))
                emitted += 1
                if limit and emitted >= limit:
                    break
        except KeyboardInterrupt:
            pass
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            "runtime.events",
            status="success",
            component="runtime",
            duration_ms=duration,
            payload=event_context | {"follow": follow, "emitted": emitted},
        )
        return 0

    duration = (time.perf_counter() - start) * 1000
    record_structured_event(
        SETTINGS,
        f"runtime.{command}",
        status="error",
        level="error",
        component="runtime",
        duration_ms=duration,
        payload=event_context | {"message": "unsupported"},
    )
    print("Unsupported runtime command", file=sys.stderr)
    return 2


def _auto_cmd(args: argparse.Namespace) -> int:
    bootstrap, command_service = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "auto", allow_auto=True)
    if project_id is None:
        return 1

    command = getattr(args, "auto_command")
    apply_changes = getattr(args, "apply", False)
    dry_run = not apply_changes
    event_context = {"command": command, "path": str(project_path)}
    record_structured_event(
        SETTINGS,
        f"auto.{command}",
        status="start",
        component="automation",
        payload=event_context | {"apply": apply_changes},
    )
    start = time.perf_counter()

    docs_command_service = DocsCommandService()

    if command == "docs":
        return _auto_docs(args, project_path, dry_run, docs_command_service, event_context, start)
    if command == "tests":
        return _auto_tests(args, project_path, dry_run, event_context, start)
    if command == "release":
        return _auto_release(args, project_path, dry_run, event_context, start)

    duration = (time.perf_counter() - start) * 1000
    record_structured_event(
        SETTINGS,
        f"auto.{command}",
        status="error",
        level="error",
        component="automation",
        duration_ms=duration,
        payload=event_context | {"message": "unsupported"},
    )
    print("Unsupported auto command", file=sys.stderr)
    return 2


def _migrate_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "migrate", allow_auto=True)
    if project_id is None:
        return 1

    service = MigrationService.for_project(project_path)
    plan = service.detect()
    as_json = getattr(args, "json", False)
    apply_changes = getattr(args, "apply", False)
    event_context = {"path": str(project_path), "apply": apply_changes}
    record_structured_event(
        SETTINGS,
        "migration.plan",
        status="start",
        component="migration",
        payload=event_context | {"actions": len(plan.actions)},
    )
    if not apply_changes or not plan.actions:
        record_structured_event(
            SETTINGS,
            "migration.plan",
            status="success",
            component="migration",
            payload=event_context | {"actions": len(plan.actions)},
        )
        if as_json:
            print(json.dumps({"plan": plan.actions}, ensure_ascii=False, indent=2))
        else:
            if plan.actions:
                print("migration plan:")
                for action in plan.actions:
                    print(f"  - {action}")
            else:
                print("migration: no legacy artefacts detected")
        return 0

    service.apply(plan)
    record_structured_event(
        SETTINGS,
        "migration.apply",
        status="success",
        component="migration",
        payload=event_context | {"actions": len(plan.actions)},
    )
    if as_json:
        print(json.dumps({"plan": plan.actions, "result": {"status": "ok", "actions": len(plan.actions)}}, ensure_ascii=False, indent=2))
    else:
        print("migration applied:")
        for action in plan.actions:
            print(f"  - {action}")
    return 0


def _auto_docs(
    args: argparse.Namespace,
    project_path: Path,
    dry_run: bool,
    command_service: DocsCommandService,
    event_context: dict[str, Any],
    start: float,
) -> int:
    bridge_service = DocsBridgeService()
    diagnosis = bridge_service.diagnose(project_path)
    issues = diagnosis.get("issues", [])
    sections = getattr(args, "sections", None)
    entries = getattr(args, "entries", None)
    plan = ["docs diagnose", "docs repair" if not dry_run else "(dry-run) docs repair"]

    if dry_run:
        print("automation plan (docs):")
        for step in plan:
            print(f"  - {step}")
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            "auto.docs",
            status="success",
            component="automation",
            duration_ms=duration,
            payload=event_context | {"dry_run": True, "issues": len(issues)},
        )
        return 0

    if issues:
        payload = command_service.repair_sections(project_path, sections=sections, entries=entries)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("automation docs: no issues detected, nothing to repair")

    duration = (time.perf_counter() - start) * 1000
    record_structured_event(
        SETTINGS,
        "auto.docs",
        status="success",
        component="automation",
        duration_ms=duration,
        payload=event_context | {"dry_run": False, "issues": len(issues)},
    )
    return 0


def _auto_tests(
    args: argparse.Namespace,
    project_path: Path,
    dry_run: bool,
    event_context: dict[str, Any],
    start: float,
) -> int:
    plan = ["verify pipeline"]
    if dry_run:
        print("automation plan (tests):")
        for step in plan:
            print(f"  - {step}")
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            "auto.tests",
            status="success",
            component="automation",
            duration_ms=duration,
            payload=event_context | {"dry_run": True},
        )
        return 0

    ns = argparse.Namespace(command_name="verify", path=str(project_path), extra=[])
    exit_code = _run_pipeline("verify", ns)
    duration = (time.perf_counter() - start) * 1000
    status = "success" if exit_code == 0 else "error"
    level = "info" if exit_code == 0 else "error"
    record_structured_event(
        SETTINGS,
        "auto.tests",
        status=status,
        level=level,
        component="automation",
        duration_ms=duration,
        payload=event_context | {"dry_run": False, "exit_code": exit_code},
    )
    return exit_code


def _auto_release(
    args: argparse.Namespace,
    project_path: Path,
    dry_run: bool,
    event_context: dict[str, Any],
    start: float,
) -> int:
    plan = ["review pipeline", "ship pipeline"]
    if dry_run:
        print("automation plan (release):")
        for step in plan:
            print(f"  - {step}")
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            "auto.release",
            status="success",
            component="automation",
            duration_ms=duration,
            payload=event_context | {"dry_run": True},
        )
        return 0

    for pipeline in ("review", "ship"):
        ns = argparse.Namespace(command_name=pipeline, path=str(project_path), extra=[])
        exit_code = _run_pipeline(pipeline, ns)
        if exit_code != 0:
            duration = (time.perf_counter() - start) * 1000
            record_structured_event(
                SETTINGS,
                "auto.release",
                status="error",
                level="error",
                component="automation",
                duration_ms=duration,
                payload=event_context | {"pipeline": pipeline, "exit_code": exit_code},
            )
            return exit_code

    duration = (time.perf_counter() - start) * 1000
    record_structured_event(
        SETTINGS,
        "auto.release",
        status="success",
        component="automation",
        duration_ms=duration,
        payload=event_context | {"dry_run": False},
    )
    return 0


def _mission_ui(
    service: MissionService,
    project_path: Path,
    interval: float,
    filters: list[str],
    timeline_limit: int,
) -> int:
    display_filters = filters or []
    interactive = sys.stdin.isatty()
    try:
        while True:
            cycle_start = time.perf_counter()
            result = service.persist_twin(project_path)
            payload = result.twin
            palette_entries = payload.get("palette") or []
            service.persist_palette(project_path, palette_entries)
            _clear_terminal()
            _render_mission_dashboard(
                payload,
                result.path,
                filters=display_filters or None,
                timeline_limit=timeline_limit,
                interactive=True,
                palette=palette_entries,
            )
            docs_status = payload.get("docsBridge", {}).get("status", "unknown")
            duration_ms = (time.perf_counter() - cycle_start) * 1000
            record_structured_event(
                SETTINGS,
                "mission.ui.refresh",
                status="success",
                component="mission",
                duration_ms=duration_ms,
                payload={
                    "path": str(project_path),
                    "docs_status": docs_status,
                    "filters": display_filters,
                    "timeline_limit": timeline_limit,
                },
            )
            if not interactive:
                remaining = max(interval - (time.perf_counter() - cycle_start), 0.2)
                time.sleep(remaining)
                continue

            action = _await_mission_palette_action(interval, cycle_start, palette_entries)
            if action is None:
                continue
            if action == "exit":
                record_structured_event(
                    SETTINGS,
                    "mission.ui",
                    component="mission",
                    status="stopped",
                    payload={"path": str(project_path), "filters": display_filters},
                )
                return 0
            if action == "refresh":
                continue

            entry = _resolve_palette_action(action, palette_entries)
            if entry is None:
                continue
            result_exec = service.execute_action(project_path, entry.get("action", {}))
            _print_mission_exec(result_exec, as_json=False)
            record_structured_event(
                SETTINGS,
                "mission.ui.action",
                status=result_exec.status,
                component="mission",
                payload={
                    "path": str(project_path),
                    "action_id": entry.get("id"),
                    "action_type": (entry.get("action") or {}).get("kind"),
                },
            )
            _log_palette_action(project_path, entry, result_exec)
            time.sleep(1.0)
    except KeyboardInterrupt:
        record_structured_event(
            SETTINGS,
            "mission.ui",
            component="mission",
            status="stopped",
            payload={"path": str(project_path), "filters": display_filters},
        )
        return 0


def _await_mission_palette_action(interval: float, cycle_start: float, entries: list[dict[str, Any]]) -> str | None:
    remaining = interval - (time.perf_counter() - cycle_start)
    if remaining <= 0:
        return None
    try:
        import select  # type: ignore

        while True:
            remaining = interval - (time.perf_counter() - cycle_start)
            if remaining <= 0:
                return None
            readable, _, _ = select.select([sys.stdin], [], [], max(remaining, 0.1))
            if not readable:
                return None
            raw = sys.stdin.readline().strip()
            if not raw:
                return None
            normalized = raw.lower()
            if normalized in {"q", "quit"}:
                return "exit"
            if normalized in {"r", "refresh"}:
                return "refresh"
            return normalized
    except (ImportError, OSError):  # pragma: no cover - fallback path
        time.sleep(remaining)
        return None


def _resolve_palette_action(action_key: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    key = action_key.lower().strip()
    mapping: dict[str, dict[str, Any]] = {}
    for entry in entries:
        hotkey = entry.get("hotkey")
        if hotkey:
            mapping[str(hotkey).lower()] = entry
        entry_id = entry.get("id")
        if entry_id:
            mapping[str(entry_id).lower()] = entry
        command = entry.get("command")
        if command:
            mapping[str(command).lower()] = entry
    return mapping.get(key)


def _print_mission_summary(
    payload: dict[str, Any],
    path: Path,
    *,
    filters: Iterable[str] | None = None,
    timeline_limit: int = 5,
) -> None:
    _render_mission_dashboard(
        payload,
        path,
        filters=filters,
        timeline_limit=timeline_limit,
        interactive=False,
        title="Mission Summary",
        palette=payload.get("palette"),
    )
    print()


def _print_mission_detail(section: str, payload: Any, *, timeline_limit: int = 10) -> None:
    section = section.lower()
    print(f"mission detail — {section}")
    print("-" * (18 + len(section)))
    if section == "docs":
        issues = payload.get('issues', []) if isinstance(payload, dict) else []
        sections = payload.get('sections', []) if isinstance(payload, dict) else []
        print(f"issues: {len(issues)}")
        for issue in issues[:5]:
            code = issue.get('code', '?')
            message = issue.get('message', '')
            print(f"  - {code}: {message}")
        if sections:
            print('sections:')
            for entry in sections[:10]:
                print(f"  - {entry.get('name')}: {entry.get('status')}")
        return
    if section == "quality":
        if not isinstance(payload, dict):
            print('no quality data available')
            return
        status = payload.get('status')
        summary = payload.get('summary', {})
        print(f"verify status: {status}")
        for name, value in list(summary.items())[:10]:
            print(f"  {name}: {value}")
        return
    if section == "tasks":
        counts = payload.get('counts', {}) if isinstance(payload, dict) else {}
        if counts:
            print('task counts:')
            for name, value in counts.items():
                print(f"  {name}: {value}")
        else:
            print('no task metrics available')
        return
    if section == "mcp":
        if not isinstance(payload, dict):
            print('no mcp data available')
            return
        servers = payload.get('servers', [])
        if not servers:
            print('no MCP servers registered')
            return
        for server in servers:
            print(f"  - {server.get('name')}: {server.get('endpoint')}")
        return
    if section == "timeline":
        events = payload if isinstance(payload, list) else []
        if not events:
            print('no timeline events recorded')
            return
        for entry in events[:timeline_limit]:
            timestamp = entry.get('timestamp') or 'unknown'
            category = entry.get('category', 'general')
            event = entry.get('event') or entry.get('details', {}).get('event') or '-'
            print(f"  - [{timestamp}] ({category}) {event}")
            hint = entry.get('hint')
            if hint:
                print(f"      hint: {hint}")
        return
    print('no detail available for requested section')
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentcall", description="AgentControl SDK CLI")
    parser.add_argument('--version', action='version', version=f'agentcall {__version__}')

    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="Bootstrap a new project capsule")
    init_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    init_cmd.add_argument("--channel", default="stable")
    init_cmd.add_argument("--template", default="default", help="Template name (default)")
    init_cmd.add_argument("--force", action="store_true")
    init_cmd.set_defaults(func=_bootstrap_cmd)

    upgrade_cmd = sub.add_parser("upgrade", help="Upgrade existing project to current template")
    upgrade_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    upgrade_cmd.add_argument("--channel", default="stable")
    upgrade_cmd.add_argument("--template", default=None, help="Override template name")
    upgrade_cmd.set_defaults(func=_upgrade_cmd)

    list_cmd = sub.add_parser("commands", help="List available project commands")
    list_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    list_cmd.set_defaults(func=_list_cmd)

    cleanup_cmd = sub.add_parser("cleanup", help="Remove cached state for a project")
    cleanup_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    cleanup_cmd.set_defaults(func=_cleanup_cmd)

    templates_cmd = sub.add_parser("templates", help="List available templates")
    templates_cmd.add_argument("--channel", default="stable")
    templates_cmd.set_defaults(func=_templates_cmd)

    telemetry_cmd = sub.add_parser("telemetry", help="Inspect local telemetry logs")
    telemetry_sub = telemetry_cmd.add_subparsers(dest="telemetry_command", required=True)

    telemetry_report = telemetry_sub.add_parser("report", help="Print aggregated telemetry stats")
    telemetry_report.set_defaults(func=_telemetry_cmd)

    telemetry_clear = telemetry_sub.add_parser("clear", help="Remove telemetry log file")
    telemetry_clear.set_defaults(func=_telemetry_cmd)

    telemetry_tail = telemetry_sub.add_parser("tail", help="Print last N telemetry events")
    telemetry_tail.add_argument("--limit", type=int, default=20)
    telemetry_tail.set_defaults(func=_telemetry_cmd)

    self_update_cmd = sub.add_parser("self-update", help="Update the agentcontrol installation")
    self_update_cmd.add_argument(
        "--mode",
        choices=["print", "pip", "pipx"],
        default="print",
        help="How to perform the update (default: print instructions)",
    )
    self_update_cmd.set_defaults(func=_self_update_cmd)

    plugins_cmd = sub.add_parser("plugins", help="Manage agentcall plugins")
    plugins_cmd.set_defaults(func=_plugins_cmd)
    plugins_sub = plugins_cmd.add_subparsers(dest="plugins_command", required=True)

    plugins_list = plugins_sub.add_parser("list", help="List discovered plugins")
    plugins_list.set_defaults(plugins_command="list")

    plugins_info = plugins_sub.add_parser("info", help="Show plugin metadata")
    plugins_info.add_argument("name")
    plugins_info.set_defaults(plugins_command="info")

    plugins_install = plugins_sub.add_parser("install", help="Install plugin package")
    plugins_install.add_argument("package")
    plugins_install.add_argument("--mode", choices=["pip", "pipx"], default="pip")
    plugins_install.set_defaults(plugins_command="install")

    plugins_remove = plugins_sub.add_parser("remove", help="Uninstall plugin package")
    plugins_remove.add_argument("package")
    plugins_remove.add_argument("--mode", choices=["pip", "pipx"], default="pip")
    plugins_remove.set_defaults(plugins_command="remove")

    docs_cmd = sub.add_parser("docs", help="Inspect documentation bridge state")
    docs_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    docs_sub = docs_cmd.add_subparsers(dest="docs_command", required=True)

    docs_diagnose = docs_sub.add_parser("diagnose", help="Validate docs bridge configuration")
    docs_diagnose.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_diagnose.set_defaults(func=_docs_cmd, docs_command="diagnose")

    docs_info = docs_sub.add_parser("info", help="Describe docs bridge capabilities")
    docs_info.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_info.set_defaults(func=_docs_cmd, docs_command="info")

    docs_list = docs_sub.add_parser("list", help="List managed documentation sections")
    docs_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_list.set_defaults(func=_docs_cmd, docs_command="list")

    docs_diff = docs_sub.add_parser("diff", help="Show drift between expected and actual docs")
    docs_diff.add_argument("--section", dest="sections", action="append", help="Filter by section name")
    docs_diff.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_diff.set_defaults(func=_docs_cmd, docs_command="diff")

    docs_repair = docs_sub.add_parser("repair", help="Restore managed sections to expected content")
    docs_repair.add_argument("--section", dest="sections", action="append", help="Filter by section name")
    docs_repair.add_argument("--entry", dest="entries", action="append", help="Filter entries (adr/rfc ids)")
    docs_repair.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_repair.set_defaults(func=_docs_cmd, docs_command="repair")

    docs_adopt = docs_sub.add_parser("adopt", help="Adopt current docs as managed baseline")
    docs_adopt.add_argument("--section", dest="sections", action="append", help="Filter by section name")
    docs_adopt.add_argument("--entry", dest="entries", action="append", help="Filter entries (adr/rfc ids)")
    docs_adopt.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_adopt.set_defaults(func=_docs_cmd, docs_command="adopt")

    docs_rollback = docs_sub.add_parser("rollback", help="Restore documentation from backup")
    docs_rollback.add_argument("--timestamp", required=True, help="Backup timestamp returned by repair")
    docs_rollback.add_argument("--section", dest="sections", action="append", help="Filter by section name")
    docs_rollback.add_argument("--entry", dest="entries", action="append", help="Filter entries (adr/rfc ids)")
    docs_rollback.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_rollback.set_defaults(func=_docs_cmd, docs_command="rollback")

    docs_sync = docs_sub.add_parser("sync", help="Auto repair/adopt managed sections")
    docs_sync.add_argument("--mode", choices=["repair", "adopt"], default="repair", help="Sync mode (default: repair)")
    docs_sync.add_argument("--section", dest="sections", action="append", help="Filter by section name")
    docs_sync.add_argument("--entry", dest="entries", action="append", help="Filter entries (adr/rfc ids)")
    docs_sync.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_sync.set_defaults(func=_docs_cmd, docs_command="sync")

    info_cmd = sub.add_parser("info", help="Display AgentControl capabilities")
    info_cmd.add_argument("path", nargs="?", help="Project path (optional)")
    info_cmd.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    info_cmd.set_defaults(func=_info_cmd)

    mcp_cmd = sub.add_parser("mcp", help="Manage MCP server registrations")
    mcp_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    mcp_sub = mcp_cmd.add_subparsers(dest="mcp_command", required=True)

    mcp_add = mcp_sub.add_parser("add", help="Register a new MCP server")
    mcp_add.add_argument("--name", required=True)
    mcp_add.add_argument("--endpoint", required=True)
    mcp_add.add_argument("--description")
    mcp_add.add_argument("--meta", action="append", help="Additional metadata as key=value pairs")
    mcp_add.add_argument("--force", action="store_true", help="Overwrite existing server with the same name")
    mcp_add.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    mcp_add.set_defaults(func=_mcp_cmd, mcp_command="add")

    mcp_remove = mcp_sub.add_parser("remove", help="Remove a registered MCP server")
    mcp_remove.add_argument("--name", required=True)
    mcp_remove.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    mcp_remove.set_defaults(func=_mcp_cmd, mcp_command="remove")

    mcp_status = mcp_sub.add_parser("status", help="List registered MCP servers")
    mcp_status.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    mcp_status.set_defaults(func=_mcp_cmd, mcp_command="status")

    sandbox_cmd = sub.add_parser("sandbox", help="Manage disposable sandbox workspaces")
    sandbox_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    sandbox_sub = sandbox_cmd.add_subparsers(dest="sandbox_command", required=True)

    sandbox_start = sandbox_sub.add_parser("start", help="Provision a fresh sandbox capsule")
    sandbox_start.add_argument("--template", default=None, help="Template name (default: sandbox)")
    sandbox_start.add_argument("--minimal", action="store_true", help="Trim heavy sample assets")
    sandbox_start.add_argument("--meta", action="append", help="Attach metadata as key=value")
    sandbox_start.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    sandbox_start.set_defaults(func=_sandbox_cmd, sandbox_command="start")

    sandbox_list = sandbox_sub.add_parser("list", help="List existing sandboxes")
    sandbox_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    sandbox_list.set_defaults(func=_sandbox_cmd, sandbox_command="list")

    sandbox_purge = sandbox_sub.add_parser("purge", help="Remove sandbox workspaces")
    sandbox_purge.add_argument("--id", dest="sandbox_id", help="Sandbox identifier")
    sandbox_purge.add_argument("--all", action="store_true", help="Remove all sandboxes")
    sandbox_purge.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    sandbox_purge.set_defaults(func=_sandbox_cmd, sandbox_command="purge")

    runtime_cmd = sub.add_parser("runtime", help="Runtime metadata and events")
    runtime_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    runtime_sub = runtime_cmd.add_subparsers(dest="runtime_command", required=True)

    runtime_status = runtime_sub.add_parser("status", help="Generate runtime manifest")
    runtime_status.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    runtime_status.set_defaults(func=_runtime_cmd, runtime_command="status")

    runtime_events = runtime_sub.add_parser("events", help="Stream telemetry events")
    runtime_events.add_argument("--follow", action="store_true", help="Keep streaming new events")
    runtime_events.add_argument("--limit", type=int, default=0, help="Stop after N events (0 = unlimited)")
    runtime_events.add_argument("--poll", type=float, default=0.5, help="Polling interval when following (seconds)")
    runtime_events.set_defaults(func=_runtime_cmd, runtime_command="events")

    auto_cmd = sub.add_parser("auto", help="Automation playbooks")
    auto_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    auto_sub = auto_cmd.add_subparsers(dest="auto_command", required=True)

    auto_docs = auto_sub.add_parser("docs", help="Repair documentation drift")
    auto_docs.add_argument("--apply", action="store_true", help="Execute repair actions")
    auto_docs.add_argument("--section", dest="sections", action="append", help="Limit to specific section names")
    auto_docs.add_argument("--entry", dest="entries", action="append", help="Limit to specific entries")
    auto_docs.set_defaults(func=_auto_cmd, auto_command="docs")

    auto_tests = auto_sub.add_parser("tests", help="Run verification pipeline")
    auto_tests.add_argument("--apply", action="store_true", help="Execute verify pipeline")
    auto_tests.set_defaults(func=_auto_cmd, auto_command="tests")

    auto_release = auto_sub.add_parser("release", help="Execute review+ship pipelines")
    auto_release.add_argument("--apply", action="store_true", help="Execute pipelines")
    auto_release.set_defaults(func=_auto_cmd, auto_command="release")

    migrate_cmd = sub.add_parser("migrate", help="Migrate legacy capsules to the new layout")
    migrate_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    migrate_cmd.add_argument("--apply", action="store_true", help="Execute the migration actions")
    migrate_cmd.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    migrate_cmd.set_defaults(func=_migrate_cmd)

    mission_cmd = sub.add_parser("mission", help="Mission control commands")
    mission_cmd.set_defaults(func=_mission_cmd, mission_command="summary")
    mission_sub = mission_cmd.add_subparsers(dest="mission_command")

    mission_summary = mission_sub.add_parser("summary", help="Generate mission twin summary")
    mission_summary.add_argument("path", nargs="?", help="Project path (default: current directory)")
    mission_summary.add_argument("--json", action="store_true", help="Emit machine-readable JSON twin")
    mission_summary.add_argument("--filter", dest="filters", action="append", choices=MISSION_FILTER_CHOICES, help="Filter sections to display")
    mission_summary.add_argument("--timeline-limit", type=int, default=5, help="Number of timeline events to display")
    mission_summary.set_defaults(func=_mission_cmd, mission_command="summary")

    mission_ui = mission_sub.add_parser("ui", help="Stream mission dashboard updates")
    mission_ui.add_argument("path", nargs="?", help="Project path (default: current directory)")
    mission_ui.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds (default: 2)")
    mission_ui.add_argument("--filter", dest="filters", action="append", choices=MISSION_FILTER_CHOICES, help="Filter sections to display")
    mission_ui.add_argument("--timeline-limit", type=int, default=10, help="Number of timeline events per refresh")
    mission_ui.set_defaults(func=_mission_cmd, mission_command="ui")

    mission_exec = mission_sub.add_parser("exec", help="Execute highest-priority playbook")
    mission_exec.add_argument("path", nargs="?", help="Project path (default: current directory)")
    mission_exec.add_argument("--json", action="store_true", help="Emit machine-readable JSON result")
    mission_exec.add_argument("--issue", help="Specific playbook issue to execute", dest="issue")
    mission_exec.set_defaults(func=_mission_exec_cmd)

    mission_detail = mission_sub.add_parser("detail", help="Inspect detailed mission section")
    mission_detail.add_argument("section", choices=MISSION_FILTER_CHOICES, help="Section to inspect")
    mission_detail.add_argument("path", nargs="?", help="Project path (default: current directory)")
    mission_detail.add_argument("--json", action="store_true", help="Emit machine-readable detail output")
    mission_detail.add_argument("--timeline-limit", type=int, default=10, help="Number of timeline events to display")
    mission_detail.set_defaults(func=_mission_cmd, mission_command="detail")

    mission_analytics = mission_sub.add_parser("analytics", help="Show mission analytics summary")
    mission_analytics.add_argument("path", nargs="?", help="Project path (default: current directory)")
    mission_analytics.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    mission_analytics.set_defaults(func=_mission_analytics_cmd)

    def make_pipeline(name: str, help_text: str) -> None:
        pipeline_cmd = sub.add_parser(name, help=help_text)
        pipeline_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
        pipeline_cmd.add_argument("extra", nargs=argparse.REMAINDER, help="Extra arguments passed to underlying steps")
        pipeline_cmd.set_defaults(func=_run_cmd, command_name=name)

    make_pipeline("verify", "Run the QA verification pipeline")
    make_pipeline("fix", "Run autofix pipeline")
    make_pipeline("review", "Run review pipeline")
    make_pipeline("ship", "Run release pipeline")
    make_pipeline("status", "Render project status")
    make_pipeline("agents", "Agent management commands")
    make_pipeline("doctor", "Environment diagnostics")

    # Generic run entrypoint for custom commands
    run_cmd = sub.add_parser("run", help="Run arbitrary registered command")
    run_cmd.add_argument("command_name")
    run_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    run_cmd.add_argument("extra", nargs=argparse.REMAINDER)
    run_cmd.set_defaults(func=_run_cmd)

    registry = load_plugins(SETTINGS)
    context = PluginContext(settings=SETTINGS)
    for name, entry in registry.items():
        plugin_parser = sub.add_parser(name, help=entry.help)
        handler = entry.builder(plugin_parser, context)

        def _plugin_dispatch(ns: argparse.Namespace, plugin_handler=handler) -> int:
            return plugin_handler(ns)

        plugin_parser.set_defaults(func=_plugin_dispatch)

    return parser


def _preprocess_argv(argv: list[str]) -> list[str]:
    """Normalize argv to preserve backward-compatible shorthands."""

    if not argv:
        return argv
    if argv[0] != "mission":
        return argv
    mission_subcommands = {"summary", "ui", "detail", "exec", "analytics"}
    if len(argv) >= 2:
        candidate = argv[1]
        if not candidate.startswith("-") and candidate not in mission_subcommands:
            return ["mission", "summary", *argv[1:]]
    if len(argv) == 1:
        return ["mission", "summary"]
    return argv


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        raw_args = sys.argv[1:]
        processed_args = _preprocess_argv(raw_args)
        args = parser.parse_args(processed_args)
    else:
        processed_args = _preprocess_argv(argv)
        args = parser.parse_args(processed_args)
    command = getattr(args, "command", None)
    pipeline = getattr(args, "command_name", None)
    maybe_auto_update(SETTINGS, __version__, command=command, pipeline=pipeline)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

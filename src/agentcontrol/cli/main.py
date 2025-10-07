#!/usr/bin/env python3
"""Entry point for the agentcall CLI."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import shutil
import select
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, Iterable
from textwrap import dedent
import textwrap

from agentcontrol.adapters.bootstrap_profile.file_repository import FileBootstrapProfileRepository
from agentcontrol.app.bootstrap_profile.service import BootstrapProfileService
from agentcontrol.app.bootstrap_service import BootstrapService, UpgradeReport
from agentcontrol.app.command_service import CommandService
from agentcontrol.app.docs import (
    DEFAULT_EXTERNAL_TIMEOUT,
    DEFAULT_REPORT_PATH,
    DocsBridgeService,
    DocsBridgeServiceError,
    DocsCommandService,
    DocsPortalGenerator,
    DocsPortalError,
    KnowledgeLintService,
    PORTAL_DEFAULT_BUDGET,
)
from agentcontrol.app.mission.service import MissionService, MissionExecResult
from agentcontrol.app.mission.dashboard import (
    MissionDashboardRenderer,
    run_dashboard_curses,
    write_snapshot,
    terminal_width,
)
from agentcontrol.app.mission.web import (
    MissionDashboardWebApp,
    MissionDashboardWebConfig,
    load_or_create_session_token,
)
from agentcontrol.app.mission.watch import (
    MissionWatcher,
    load_watch_rules,
    load_sla_rules,
)
from agentcontrol.app.mcp.manager import MCPManager
from agentcontrol.app.runtime.service import RuntimeService
from agentcontrol.app.info import InfoService
from agentcontrol.app.migration.service import MigrationService
from agentcontrol.app.sandbox.service import SandboxService
from agentcontrol.app.extension.service import ExtensionService
from agentcontrol.app.release_notes import ReleaseNotesError, ReleaseNotesGenerator
from agentcontrol.app.gallery.service import GalleryError, GalleryService
from agentcontrol.app.tasks import TaskSyncError, TaskSyncResult, TaskSyncService
from agentcontrol.domain.project import (
    PROJECT_DESCRIPTOR,
    PROJECT_DIR,
    ProjectCapsule,
    ProjectId,
    ProjectNotInitialisedError,
)
from agentcontrol.domain.tasks import TaskSyncOp
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


HELP_OVERVIEW = dedent(
    """
    Quick start:
      - Install the CLI once: pipx install agentcontrol
      - Inside a repository: agentcall quickstart --template default [PATH]

    Core pipelines:
      - agentcall setup      - prepare .agentcontrol/, environments, and tools
      - agentcall verify     - run the quality gate (fmt/tests/security/perf/docs)
      - agentcall mission ... - mission dashboard and automated playbooks

    Anti-patterns:
      - Do not run agentcall inside the SDK source tree itself
      - Do not edit .agentcontrol/ manually; use quickstart or upgrade
      - Do not skip verify before ship; the release gate blocks on failures
    """
)


def _truthy_env(var: str) -> bool:
    return os.environ.get(var, "").strip().lower() in {"1", "true", "yes", "on"}


def _default_project_path(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg).expanduser().resolve()
    return Path(os.getcwd())


def _state_directory_for(project_path: Path) -> Path:
    digest = hashlib.sha256(str(project_path).encode("utf-8")).hexdigest()[:16]
    return SETTINGS.state_dir / digest


def _collect_help_context(project_path: Path) -> dict[str, Any]:
    resolved = project_path.expanduser().resolve()
    context: dict[str, Any] = {
        "version": __version__,
        "cwd": str(resolved),
        "sdk_repo": _is_sdk_source_tree(resolved),
        "project": {"present": False},
        "recommendations": [],
        "docs": [
            "docs/getting_started.md",
            "docs/mission/watchers.md",
            "docs/tutorials/mission_control_walkthrough.md",
            "docs/tutorials/extensions.md",
        ],
        "environment": [
            "AGENTCONTROL_NO_AUTO_INIT=1 — отключает авто-bootstrap",
            "AGENTCONTROL_DISABLE_AUTO_UPDATE=1 — запрещает автообновления",
            "AGENTCONTROL_AUTO_UPDATE_CACHE=<dir> — офлайн-кэш обновлений",
        ],
        "warnings": [],
    }

    recommendations: list[str] = context["recommendations"]

    try:
        project_id = ProjectId.from_existing(resolved)
    except ProjectNotInitialisedError:
        recommendations.extend(
            [
                "agentcall quickstart --template default",
                "agentcall verify",
                "agentcall help --path <project> (после инициализации)",
            ]
        )
        return context

    capsule = ProjectCapsule.load(project_id)
    project_context: dict[str, Any] = {
        "present": True,
        "path": str(project_id.root),
        "template": {
            "name": capsule.template_name,
            "version": capsule.template_version,
            "channel": capsule.channel,
        },
    }

    verify_path = project_id.root / "reports" / "verify.json"
    verify_summary: dict[str, Any]
    if verify_path.exists():
        try:
            payload = json.loads(verify_path.read_text(encoding="utf-8"))
            steps = payload.get("steps", [])
            failed = [step["name"] for step in steps if step.get("status") == "fail"]
            warnings = [
                step["name"]
                for step in steps
                if step.get("severity") == "warning" or step.get("status") == "warning"
            ]
            if failed:
                status = "fail"
            elif warnings:
                status = "warn"
            else:
                status = "ok"
            verify_summary = {
                "status": status,
                "generated_at": payload.get("generated_at"),
                "step_count": len(steps),
                "failed_steps": failed,
                "warning_steps": warnings,
            }
        except (json.JSONDecodeError, OSError):
            verify_summary = {"status": "error", "generated_at": None, "step_count": 0}
    else:
        verify_summary = {"status": "missing", "generated_at": None, "step_count": 0}
    project_context["verify"] = verify_summary

    watch_config = project_id.root / PROJECT_DIR / "config" / "watch.yaml"
    watch_state_path = project_id.root / PROJECT_DIR / "state" / "watch.json"
    sla_config = project_id.root / PROJECT_DIR / "config" / "sla.yaml"

    watch_summary: dict[str, Any] = {
        "config_path": str(watch_config.relative_to(project_id.root)) if watch_config.exists() else None,
        "state_path": str(watch_state_path.relative_to(project_id.root)) if watch_state_path.exists() else None,
        "rules": [],
        "sla": [],
        "last_event": None,
        "errors": [],
    }

    if watch_config.exists():
        try:
            rules = load_watch_rules(watch_config)
            watch_summary["rules"] = [
                {
                    "id": rule.id,
                    "event": rule.event,
                    "playbook": rule.playbook_issue,
                    "debounce_minutes": rule.debounce_minutes,
                    "max_retries": rule.max_retries,
                }
                for rule in rules
            ]
        except ValueError as exc:
            watch_summary["errors"].append(str(exc))
    else:
        watch_summary["errors"].append("watch.yaml missing")

    if sla_config.exists():
        try:
            entries = load_sla_rules(sla_config)
            watch_summary["sla"] = [
                {
                    "id": entry.id,
                    "acknowledgement": entry.acknowledgement,
                    "max_minutes": entry.max_minutes,
                    "severity": entry.severity,
                }
                for entry in entries
            ]
        except ValueError as exc:
            watch_summary["errors"].append(str(exc))

    if watch_state_path.exists():
        try:
            state_payload = json.loads(watch_state_path.read_text(encoding="utf-8"))
            entries: list[dict[str, Any]] = []
            for rule_id, value in (state_payload or {}).items():
                if isinstance(value, dict):
                    entries.append(
                        {
                            "rule": rule_id,
                            "last_event_ts": value.get("last_event_ts"),
                            "last_status": value.get("last_status"),
                            "attempts": value.get("attempts"),
                        }
                    )
            watch_summary["state"] = entries
            if entries:
                def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
                    ts = item.get("last_event_ts")
                    return (0 if ts else 1, ts or "")

                latest = sorted(entries, key=_sort_key, reverse=True)[0]
                watch_summary["last_event"] = latest
        except (json.JSONDecodeError, OSError):
            watch_summary["errors"].append("watch.json unreadable")

    project_context["watch"] = watch_summary

    recommendations.extend(
        [
            "agentcall mission dashboard --no-curses",
            "agentcall mission watch --once --json" if watch_summary["rules"] else "agentcall mission watch --once --json (создайте watch.yaml)",
        ]
    )

    if verify_summary["status"] != "ok":
        recommendations.insert(0, "agentcall verify")
    else:
        recommendations.insert(0, "agentcall verify (актуализируйте перед ship)")

    project_context["recommendations"] = recommendations
    context["project"] = project_context
    return context


def _format_lines(context: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    def _wrap(text: str, *, indent: int = 0, bullet: str | None = None) -> None:
        prefix = " " * indent
        if bullet is not None:
            initial = prefix + bullet
            subsequent = " " * (indent + len(bullet))
        else:
            initial = prefix
            subsequent = prefix
        wrapped = textwrap.wrap(
            text,
            width=80,
            initial_indent=initial,
            subsequent_indent=subsequent,
        )
        if not wrapped:
            lines.append(initial.rstrip())
        else:
            lines.extend(wrapped)

    lines.append(f"AgentControl CLI {context['version']} — contextual help")
    lines.append(f"Working dir: {context['cwd']}")
    if context.get("sdk_repo"):
        _wrap(
            "Внимание: вы внутри репозитория SDK. Используйте scripts/test-place.sh для отладки шаблонов.",
            indent=0,
        )

    project = context.get("project", {})
    lines.append("")
    if not project.get("present"):
        lines.append("На этой директории капсула AgentControl не обнаружена.")
        lines.append("Quickstart:")
        for idx, cmd in enumerate(context.get("recommendations", []), start=1):
            _wrap(cmd, indent=2, bullet=f"{idx}. ")
    else:
        template = project.get("template", {})
        _wrap(
            f"Проект: {template.get('name', '?')}@{template.get('version', '?')} (канал {template.get('channel', '?')})",
            indent=0,
        )
        verify = project.get("verify", {})
        _wrap(
            f"Verify: статус {verify.get('status', 'unknown')} (steps={verify.get('step_count', 0)}, generated_at={verify.get('generated_at') or '—'})",
            indent=0,
        )
        watch = project.get("watch", {})
        rule_count = len(watch.get("rules", []))
        config_path = watch.get("config_path") or "нет watch.yaml"
        _wrap(
            f"Watch rules: {rule_count} (config: {config_path})",
            indent=0,
        )
        for note in watch.get("errors", []):
            _wrap(f"Watch note: {note}", indent=0)
        if watch.get("last_event"):
            last = watch["last_event"]
            _wrap(
                f"Последний триггер: {last.get('rule')} → {last.get('last_status')} @ {last.get('last_event_ts') or '—'}",
                indent=0,
            )
        if watch.get("sla"):
            _wrap(
                f"SLA правил: {len(watch['sla'])} (config: .agentcontrol/config/sla.yaml)",
                indent=0,
            )
        lines.append("Рекомендованные шаги:")
        for idx, cmd in enumerate(project.get("recommendations", []), start=1):
            _wrap(cmd, indent=2, bullet=f"{idx}. ")

    if context.get("docs"):
        lines.append("")
        lines.append("Документация:")
        for doc in context["docs"]:
            _wrap(doc, indent=2, bullet="- ")

    if context.get("environment"):
        lines.append("")
        lines.append("Переменные среды:")
        for env in context["environment"]:
            _wrap(env, indent=2, bullet="- ")

    return lines


def _help_cmd(args: argparse.Namespace) -> int:
    project_path = _default_project_path(getattr(args, "path", None))
    context = _collect_help_context(project_path)
    if getattr(args, "json", False):
        print(json.dumps(context, ensure_ascii=False, indent=2))
        return 0
    lines = _format_lines(context)
    print("\n".join(lines))
    return 0


def _is_sdk_source_tree(path: Path) -> bool:
    """Return True when running inside the AgentControl SDK source tree.

    The AgentControl project hosts its own templates under ``src/agentcontrol``
    and declares the project metadata in ``pyproject.toml``. Scanning the
    current directory and its parents for both conditions lets us short-circuit
    the auto-bootstrap logic for every sub-path inside the SDK repository while
    keeping behaviour unchanged for installed CLI users.
    """

    resolved = path.resolve()
    candidates: Iterable[Path] = (resolved,) + tuple(resolved.parents)
    for candidate in candidates:
        if not (candidate / "src" / "agentcontrol").is_dir():
            continue
        pyproject = candidate / "pyproject.toml"
        if not pyproject.exists():
            continue
        try:
            content = pyproject.read_text(encoding="utf-8")
        except OSError:
            continue
        if "name = \"agentcontrol\"" in content or "name = 'agentcontrol'" in content:
            return True
    return False


def _build_services() -> tuple[BootstrapService, CommandService]:
    template_repo = FSTemplateRepository(SETTINGS.template_dir)
    bootstrap = BootstrapService(template_repo, SETTINGS)
    command_service = CommandService(SETTINGS)
    bootstrap.ensure_bootstrap_prerequisites()
    _sync_packaged_templates()
    return bootstrap, command_service


def _build_profile_service() -> BootstrapProfileService:
    repository = FileBootstrapProfileRepository()
    return BootstrapProfileService(repository)


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
    # Skip auto-init when running inside the AgentControl SDK source tree.
    if _is_sdk_source_tree(project_path):
        record_event(
            SETTINGS,
            'autobootstrap.skip_sdk_repo',
            {'command': command, 'cwd': str(project_path)},
        )
        return None

    capsule_dir = project_path / PROJECT_DIR
    descriptor = capsule_dir / PROJECT_DESCRIPTOR
    if descriptor.exists():
        return ProjectId.from_existing(project_path)
    if capsule_dir.exists() and any(capsule_dir.iterdir()):
        return None
    channel = os.environ.get('AGENTCONTROL_DEFAULT_CHANNEL', 'stable')
    template = os.environ.get('AGENTCONTROL_DEFAULT_TEMPLATE', 'default')
    print(
        f"agentcall: auto-initialising capsule in {capsule_dir} using {template}@{channel}",
        file=sys.stderr,
    )
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
    print('agentcall: capsule ready — continuing command execution', file=sys.stderr)
    return confirmed


def _resolve_project_id(bootstrap: BootstrapService, project_path: Path, command: str, *, allow_auto: bool) -> ProjectId | None:
    try:
        return ProjectId.from_existing(project_path)
    except ProjectNotInitialisedError:
        legacy_descriptor = project_path / "agentcontrol" / PROJECT_DESCRIPTOR
        if legacy_descriptor.exists() and command == "upgrade":
            return ProjectId.for_new_project(project_path)
        if allow_auto:
            project_id = _auto_bootstrap_project(bootstrap, project_path, command)
            if project_id is not None:
                return project_id
        _print_project_hint(project_path, command)
        return None


def _determine_operator() -> str:
    operator = os.environ.get("AGENTCONTROL_OPERATOR")
    if operator:
        return operator.strip()
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "unknown"


def _prompt_profile_selection(profiles, *, selected_id: str | None = None):
    definitions = list(profiles)
    if not definitions:
        raise RuntimeError("No bootstrap profiles available")
    if selected_id:
        for definition in definitions:
            if definition.profile_id == selected_id:
                return definition
        available = ", ".join(definition.profile_id for definition in definitions)
        raise KeyError(f"Unknown profile id '{selected_id}'. Available: {available}")
    print("Available bootstrap profiles:")
    for index, definition in enumerate(definitions, start=1):
        req = definition.requirements
        cicd = ", ".join(req.recommended_cicd) or "—"
        print(f"  {index}. {definition.name} [{definition.profile_id}] — Python ≥ {req.python_min_version}; CI/CD: {cicd}")
        print(f"     {definition.description}")
    while True:
        choice = input("Select profile [1]: ").strip()
        if not choice:
            return definitions[0]
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(definitions):
                return definitions[index - 1]
        print(f"Enter a value between 1 and {len(definitions)}.")


def _prompt_question(question) -> str:
    while True:
        print(question.prompt)
        response = input("> ").strip()
        if response:
            return response
        if getattr(question, "category", "") == "notes":
            return ""
        print("This answer is required.")


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

def _print_quickstart_summary(project_path: Path, summary: list[tuple[str, int]]) -> None:
    print(f"Project ready: {project_path}")
    if not summary:
        print("  - setup/verify skipped by flags")
        return
    for name, code in summary:
        status = "ok" if code == 0 else f"exit {code}"
        print(f"  - {name}: {status}")


def _quickstart_cmd(args: argparse.Namespace) -> int:
    bootstrap, command_service = _build_services()
    project_path = _default_project_path(args.path)
    project_id = ProjectId.for_new_project(project_path)

    try:
        bootstrap.bootstrap(
            project_id,
            args.channel,
            template=args.template,
            force=args.force,
        )
    except RuntimeError as exc:
        print(f"quickstart failed: {exc}", file=sys.stderr)
        return 1

    project_id = ProjectId.from_existing(project_path)
    summary: list[tuple[str, int]] = []

    if not args.no_setup:
        exit_setup = command_service.run(project_id, "setup", [])
        summary.append(("setup", exit_setup))
        if exit_setup != 0 and not args.force:
            _print_quickstart_summary(project_path, summary)
            return exit_setup

    if not args.no_verify:
        exit_verify = command_service.run(project_id, "verify", args.verify_args or [])
        summary.append(("verify", exit_verify))
        if exit_verify != 0 and not args.force:
            _print_quickstart_summary(project_path, summary)
            return exit_verify

    _print_quickstart_summary(project_path, summary)
    return 0 if all(code == 0 for _, code in summary) else 1


def _bootstrap_profile_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "bootstrap", allow_auto=True)
    if project_id is None:
        return 1

    service = _build_profile_service()
    try:
        profile = _prompt_profile_selection(service.list_profiles(), selected_id=getattr(args, "profile", None))
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"bootstrap wizard unavailable: {exc}", file=sys.stderr)
        return 1

    print(f"Selected profile: {profile.name} [{profile.profile_id}]")

    answers: dict[str, str] = {}
    try:
        for question in service.list_questions():
            answers[question.question_id] = _prompt_question(question)
    except KeyboardInterrupt:  # pragma: no cover - interactive interruption
        print("\nBootstrap wizard cancelled.")
        return 1

    operator = _determine_operator()
    try:
        result = service.capture(project_id, profile.profile_id, answers, operator=operator)
    except ValueError as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 1

    profile_path = project_id.root / PROJECT_DIR / "state" / "profile.json"
    summary_path = project_id.root / "reports" / "bootstrap_summary.json"
    payload = result.snapshot.as_dict()
    payload.update(
        {
            "profile_path": str(profile_path),
            "summary_path": str(summary_path),
            "recommendations": result.recommendations,
        }
    )
    record_event(
        SETTINGS,
        "bootstrap.profile",
        {
            "project": str(project_id.root),
            "profile": profile.profile_id,
            "operator": operator,
        },
    )
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print(f"Bootstrap profile '{profile.name}' captured for {project_id.root}")
        print(f"Profile stored at {profile_path}")
        print(f"Summary stored at {summary_path}")
        if result.recommendations:
            print("Recommendations:")
            for recommendation in result.recommendations:
                status = recommendation.get("status", "info")
                message = recommendation.get("message", "")
                print(f"  [{status}] {message}")
    return 0


def _print_upgrade_report(report: UpgradeReport, *, as_json: bool, project_path: Path) -> None:
    if as_json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
        return

    legacy = report.legacy_migration
    if legacy.performed:
        print(f"Legacy capsule migrated to {legacy.new_path}")
        if legacy.backup_path:
            print(f"Backup stored at {legacy.backup_path}")
    elif legacy.reason:
        print(f"Legacy migration skipped: {legacy.reason}")

    if report.actions:
        print("Actions:")
        for action in report.actions:
            print(f"  - {action}")

    if report.dry_run:
        print(f"Dry run only — no changes applied in {project_path}")


def _upgrade_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(args.path)
    project_id = _resolve_project_id(bootstrap, project_path, 'upgrade', allow_auto=False)
    if project_id is None:
        return 1

    try:
        report = bootstrap.upgrade(
            project_id,
            args.channel,
            template=args.template,
            legacy_migrate=not getattr(args, "skip_legacy_migrate", False),
            dry_run=getattr(args, "dry_run", False),
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _print_upgrade_report(report, as_json=getattr(args, "json", False), project_path=project_path)

    if report.dry_run:
        return 0

    record_event(
        SETTINGS,
        "upgrade",
        {
            "channel": args.channel,
            "template": (args.template or report.template_name or "(existing)"),
            "template_version": report.template_version,
        },
    )
    print(f"Project upgraded at {project_path}")
    return 0


def _parse_provider_option_value(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _assign_provider_option(options: Dict[str, Any], key: str, value: Any) -> None:
    parts = [segment.strip() for segment in key.split(".") if segment.strip()]
    if not parts:
        raise ValueError("provider option key must be non-empty")
    target: Dict[str, Any] = options
    for part in parts[:-1]:
        current = target.get(part)
        if current is None:
            current = {}
            target[part] = current
        elif not isinstance(current, dict):
            raise ValueError(f"provider option '{part}' already set as a non-object value")
        target = current
    target[parts[-1]] = value


def _resolve_provider_input(raw: str, project_path: Path) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("input path must not be empty")
    expanded = Path(value).expanduser()
    if expanded.is_absolute():
        return str(expanded)
    return value


def _build_inline_provider_config(
    provider_type: str,
    args: argparse.Namespace,
    project_path: Path,
) -> Dict[str, Any]:
    provider = provider_type.strip()
    if not provider:
        raise ValueError("provider type must not be empty")
    options: Dict[str, Any] = {}
    inline_input = getattr(args, "provider_input", None)
    if inline_input:
        key = "path" if provider.lower() == "file" else "snapshot_path"
        resolved = _resolve_provider_input(inline_input, project_path)
        _assign_provider_option(options, key, resolved)
    for raw_option in getattr(args, "provider_option", []) or []:
        if "=" not in raw_option:
            raise ValueError(
                f"invalid provider option '{raw_option}': expected key=value"
            )
        opt_key, opt_value = raw_option.split("=", 1)
        opt_key = opt_key.strip()
        if not opt_key:
            raise ValueError("provider option key must not be empty")
        parsed_value = _parse_provider_option_value(opt_value)
        _assign_provider_option(options, opt_key, parsed_value)
    return {"type": provider, "options": options}


def _tasks_sync_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "tasks.sync", allow_auto=True)
    if project_id is None:
        return 1

    service = TaskSyncService(project_id)

    def _resolve_path(raw: str | None) -> Path | None:
        if raw is None:
            return None
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate
        return (project_path / candidate).resolve()

    provider_arg = getattr(args, "provider", None)
    provider_options = list(getattr(args, "provider_option", []) or [])
    if provider_arg is None and provider_options:
        print("--provider-option requires --provider", file=sys.stderr)
        return 1
    if provider_arg is None and getattr(args, "provider_input", None):
        print("--input requires --provider", file=sys.stderr)
        return 1

    inline_config: Dict[str, Any] | None = None
    config_path: Path | None = None
    if provider_arg is not None:
        try:
            inline_config = _build_inline_provider_config(provider_arg, args, project_path)
        except ValueError as exc:
            print(f"tasks.sync.config_invalid: {exc}", file=sys.stderr)
            return 1
    else:
        config_path = _resolve_path(getattr(args, "config", None))

    try:
        result = service.sync(
            config_path=config_path,
            provider=inline_config,
            apply=getattr(args, "apply", False),
            output_path=_resolve_path(getattr(args, "output", None)),
        )
    except TaskSyncError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _print_task_sync_result(
        result,
        as_json=getattr(args, "json", False),
        project_root=project_path,
    )

    summary = result.plan.summary()
    status = "applied" if result.applied else "dry-run"
    provider_type = (result.provider_config or {}).get("type")
    record_structured_event(
        SETTINGS,
        "tasks.sync",
        status=status,
        component="tasks",
        payload={
            "create": summary["create"],
            "update": summary["update"],
            "close": summary["close"],
            "unchanged": summary["unchanged"],
            "report_path": str(result.report_path),
            "applied": result.applied,
            "provider_type": provider_type,
        },
    )
    return 0


def _print_task_sync_result(
    result: TaskSyncResult,
    *,
    as_json: bool,
    project_root: Path,
) -> None:
    if as_json:
        payload = result.to_dict(project_root=project_root)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    summary = result.plan.summary()
    provider_type = (result.provider_config or {}).get("type")
    print(
        "Tasks sync: create={create} update={update} close={close} unchanged={unchanged}".format(
            **summary
        )
    )
    if provider_type:
        print(f"Provider: {provider_type}")
    if result.plan.actions:
        print("Plan:")
        for action in result.plan.actions:
            if action.op == TaskSyncOp.CREATE and action.task is not None:
                print(
                    f"  + create {action.task.id}: {action.task.title} [{action.task.status}]"
                )
            elif action.op == TaskSyncOp.UPDATE and action.task_id:
                changes = action.changes or {}
                changes_repr = ", ".join(
                    f"{field}={change['from']}→{change['to']}" for field, change in changes.items()
                )
                print(f"  ~ update {action.task_id}: {changes_repr}")
            elif action.op == TaskSyncOp.CLOSE and action.task_id:
                reason = action.reason or "provider_removed"
                print(f"  - close {action.task_id}: {reason}")
    else:
        print("Plan: no changes detected")

    if result.applied:
        print(f"Board updated at {result.board_path}")
    else:
        print("Dry-run only; use --apply to persist changes")
    print(f"Report stored at {result.report_path}")


def _gallery_cmd(args: argparse.Namespace) -> int:
    project_path = _default_project_path(getattr(args, "path", None))
    command = getattr(args, "gallery_command", "list")
    as_json = bool(getattr(args, "json", False))
    service = GalleryService(project_path)

    if command == "list":
        try:
            samples = service.list_samples()
        except GalleryError as exc:
            print(f"gallery error: {exc}", file=sys.stderr)
            return 1
        payload = [
            {
                "id": sample.sample_id,
                "name": sample.name,
                "description": sample.description,
                "tags": list(sample.tags),
                "estimated_size_kb": sample.estimated_size_kb,
                "origin": sample.origin,
            }
            for sample in samples
        ]
        record_event(SETTINGS, "gallery.list", {"count": len(payload)})
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if not payload:
                print("No gallery samples available")
            else:
                for item in payload:
                    tags = ", ".join(item["tags"]) if item["tags"] else "-"
                    print(f"{item['id']}\t{item['name']} [{tags}] ~{item['estimated_size_kb']} KiB")
                    if item["description"]:
                        print(f"  {item['description']}")
        return 0

    if command == "fetch":
        sample_id = getattr(args, "sample_id")
        dest_arg = getattr(args, "dest", None)
        destination = Path(dest_arg).expanduser() if dest_arg else Path.cwd()
        as_directory = bool(getattr(args, "directory", False))
        try:
            result = service.export_sample(sample_id, destination, archive=not as_directory)
        except GalleryError as exc:
            print(f"gallery error: {exc}", file=sys.stderr)
            return 1
        payload = {
            "id": result.sample.sample_id,
            "path": str(result.output_path),
            "size_bytes": result.size_bytes,
            "archive": not as_directory,
        }
        record_event(SETTINGS, "gallery.fetch", payload | {"dest": dest_arg})
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            mode = "archive" if payload["archive"] else "directory"
            print(f"Fetched {result.sample.sample_id} -> {result.output_path} ({mode}, {result.size_bytes} bytes)")
        return 0

    print("Unsupported gallery command", file=sys.stderr)
    return 2


def _release_notes_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "release.notes", allow_auto=True)
    if project_id is None:
        return 1

    generator = ReleaseNotesGenerator(project_id)
    from_ref = getattr(args, "from_ref", None)
    to_ref = getattr(args, "to_ref", "HEAD")
    max_commits = getattr(args, "max_commits", None)
    output_override = getattr(args, "output", None)
    json_requested = bool(getattr(args, "json", False))

    output_path: Path | None = None
    if output_override:
        candidate = Path(output_override).expanduser()
        if not candidate.is_absolute():
            candidate = (project_path / candidate).resolve()
        output_path = candidate

    try:
        result = generator.generate(
            from_ref=from_ref,
            to_ref=to_ref,
            max_commits=max_commits,
            output_path=output_path,
            json_output=json_requested,
        )
    except ReleaseNotesError as exc:
        print(f"release notes error: {exc}", file=sys.stderr)
        return 1

    payload = {
        "markdown": str(result.markdown_path),
        "json": str(result.json_path) if result.json_path else None,
        "summary": result.summary,
    }
    if json_requested:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Release notes saved to {payload['markdown']}")
        if payload["json"]:
            print(f"JSON summary saved to {payload['json']}")
        print(f"Commits analysed: {payload['summary']['commit_count']}")
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


def _doctor_cmd(args: argparse.Namespace) -> int:
    if getattr(args, "bootstrap", False):
        return _doctor_bootstrap_cmd(args)
    return _run_pipeline("doctor", args)


def _doctor_bootstrap_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "doctor", allow_auto=True)
    if project_id is None:
        return 1

    service = _build_profile_service()
    report = service.diagnose(project_id)
    checks_payload = [
        {
            "id": check.check_id,
            "status": check.status,
            "message": check.message,
            "details": check.details,
        }
        for check in report.checks
    ]
    payload: dict[str, object] = {
        "status": report.status,
        "checks": checks_payload,
        "profile_path": str(project_id.root / PROJECT_DIR / "state" / "profile.json"),
        "summary_path": str(project_id.root / "reports" / "bootstrap_summary.json"),
    }
    if report.snapshot is not None:
        payload["profile"] = report.snapshot.profile.as_dict()
        payload["captured_at"] = report.snapshot.captured_at

    record_structured_event(
        SETTINGS,
        "doctor.bootstrap",
        payload=payload,
        status=report.status,
        component="doctor",
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print(f"Bootstrap readiness: {report.status}")
        for check in checks_payload:
            print(f"  - [{check['status']}] {check['id']}: {check['message']}")
    return 0 if report.status != "fail" else 1


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


def _extension_service(args: argparse.Namespace, command: str) -> tuple[ProjectId | None, ExtensionService | None]:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, f"extension.{command}", allow_auto=True)
    if project_id is None:
        return None, None
    return project_id, ExtensionService(project_id)


def _extension_init_cmd(args: argparse.Namespace) -> int:
    project_id, service = _extension_service(args, "init")
    if service is None or project_id is None:
        return 1

    try:
        service.init(args.name, force=args.force)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    entry = service.add(args.name)
    record_event(
        SETTINGS,
        "extension.init",
        {"project": str(project_id.root), "name": entry.name, "version": entry.version},
    )
    print(f"Extension scaffolded at {entry.path}")
    print("Registered in catalog")
    return 0


def _extension_add_cmd(args: argparse.Namespace) -> int:
    project_id, service = _extension_service(args, "add")
    if service is None or project_id is None:
        return 1

    try:
        source_path = Path(args.source).expanduser().resolve() if getattr(args, "source", None) else None
        entry = service.add(
            args.name,
            source=source_path,
            git_url=getattr(args, "git", None),
            ref=getattr(args, "ref", None),
        )
    except (FileNotFoundError, FileExistsError, NotADirectoryError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    payload = {
        "project": str(project_id.root),
        "name": entry.name,
        "version": entry.version,
        "source": entry.source,
        "path": entry.path,
    }
    record_event(SETTINGS, "extension.add", payload)
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Extension '{entry.name}' registered at {entry.path}")
    return 0


def _extension_list_cmd(args: argparse.Namespace) -> int:
    project_id, service = _extension_service(args, "list")
    if service is None or project_id is None:
        return 1

    entries = service.list()
    if args.json:
        payload = [asdict(entry) for entry in entries]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not entries:
            print("No extensions registered")
        else:
            for entry in entries:
                hint = f" [source: {entry.source}]" if entry.source else ""
                print(f"- {entry.name} {entry.version} :: {entry.description}{hint}")
    return 0


def _extension_remove_cmd(args: argparse.Namespace) -> int:
    project_id, service = _extension_service(args, "remove")
    if service is None or project_id is None:
        return 1
    removed = service.remove(args.name, purge=getattr(args, "purge", False))
    if removed:
        payload = {
            "project": str(project_id.root),
            "name": args.name,
            "purged": bool(getattr(args, "purge", False)),
        }
        record_event(SETTINGS, "extension.remove", payload)
        if getattr(args, "json", False):
            print(json.dumps({"removed": True, **payload}, ensure_ascii=False, indent=2))
        else:
            suffix = " and purged" if payload["purged"] else ""
            print(f"Extension '{args.name}' removed from catalog{suffix}")
        return 0
    error_payload = {"project": str(project_id.root), "name": args.name}
    if getattr(args, "json", False):
        print(json.dumps({"removed": False, **error_payload}, ensure_ascii=False, indent=2))
    else:
        print(f"Extension '{args.name}' not found", file=sys.stderr)
    return 1


def _extension_lint_cmd(args: argparse.Namespace) -> int:
    project_id, service = _extension_service(args, "lint")
    if service is None or project_id is None:
        return 1
    result = service.lint(name=args.name)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        errors = result["errors"]
        if errors:
            print("Lint issues:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("No issues detected")
    record_event(
        SETTINGS,
        "extension.lint",
        {
            "project": str(project_id.root),
            "name": args.name,
            "errors": len(result["errors"]),
        },
    )
    return 0 if not result["errors"] else 1


def _extension_publish_cmd(args: argparse.Namespace) -> int:
    project_id, service = _extension_service(args, "publish")
    if service is None or project_id is None:
        return 1
    output = service.publish(dry_run=args.dry_run)
    payload = {"project": str(project_id.root), "dry_run": args.dry_run, "path": str(output)}
    record_event(SETTINGS, "extension.publish", payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        flag = "(dry-run)" if args.dry_run else ""
        print(f"Extensions catalog exported to {output} {flag}".strip())
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
        recent = getattr(args, "recent", 0)
        if recent and recent > 0:
            from collections import deque

            window = deque(maxlen=recent)
            for evt in telemetry_iter(SETTINGS):
                window.append(evt)
            events = list(window)
        else:
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
    command = args.docs_command
    if command in {"lint", "portal"}:
        try:
            project_id = ProjectId.from_existing(project_path)
        except ProjectNotInitialisedError:
            project_id = None
    else:
        project_id = _resolve_project_id(bootstrap, project_path, "docs", allow_auto=True)
        if project_id is None:
            return 1
    project_root = project_id.root if project_id is not None else project_path.resolve()
    bridge_service = DocsBridgeService()
    command_service = DocsCommandService()
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
        elif command == "lint":
            if not getattr(args, "knowledge", False):
                print("docs lint: specify --knowledge to run knowledge coverage lint", file=sys.stderr)
                event_context.update({"error": "missing_target"})
                exit_code = 2
            else:
                lint_service = KnowledgeLintService()
                output_override = getattr(args, "output", None)
                output_path = Path(output_override).expanduser() if output_override else None
                max_age_hours = getattr(args, "max_age_hours", None)
                if max_age_hours is not None:
                    event_context["max_age_hours"] = max_age_hours
                validate_external = getattr(args, "validate_external", False)
                link_timeout = getattr(args, "link_timeout", None)
                if validate_external:
                    event_context["validate_external"] = True
                if link_timeout is not None:
                    event_context["link_timeout"] = link_timeout
                try:
                    report = lint_service.lint(
                        project_root,
                        output_path=output_path,
                        max_age_hours=max_age_hours,
                        validate_external=validate_external,
                        external_timeout=link_timeout or DEFAULT_EXTERNAL_TIMEOUT,
                    )
                except FileNotFoundError as exc:
                    payload = {
                        "status": "error",
                        "error": {
                            "code": "KNOWLEDGE_ROOT_MISSING",
                            "message": str(exc),
                        },
                    }
                    if as_json:
                        print(json.dumps(payload, ensure_ascii=False, indent=2))
                    else:
                        print(f"docs lint knowledge error: {exc}", file=sys.stderr)
                    event_context.update({"error_code": "KNOWLEDGE_ROOT_MISSING"})
                    exit_code = 1
                else:
                    issues = report.get("issues", [])
                    errors = sum(1 for issue in issues if issue.get("severity") == "error")
                    warnings = sum(1 for issue in issues if issue.get("severity") == "warning")
                    event_context.update(
                        {
                            "output": report.get("report_path"),
                            "issues": {"error": errors, "warning": warnings},
                        }
                    )
                    if as_json:
                        print(json.dumps(report, ensure_ascii=False, indent=2))
                    else:
                        print(
                            f"knowledge lint status={report.get('status')} "
                            f"errors={errors} warnings={warnings} -> {report.get('report_path')}"
                        )
                        if errors or warnings:
                            for issue in issues[:10]:
                                print(
                                    f"  [{issue.get('severity')}] {issue.get('code')}: "
                                    f"{issue.get('path')} — {issue.get('message')}"
                                )
                            if len(issues) > 10:
                                print(f"  ... {len(issues) - 10} more issues")
                    exit_code = 1 if report.get("status") == "error" else 0
        elif command == "portal":
            generator = DocsPortalGenerator(command_service)
            output_override = getattr(args, "output", None)
            budget_override = getattr(args, "budget", None)
            budget_limit = int(budget_override) if budget_override is not None else None
            default_output = (project_root / "reports/docs/portal").resolve()
            event_context.update(
                {
                    "output": str(Path(output_override).expanduser().resolve()) if output_override else str(default_output),
                    "budget": budget_limit if budget_limit is not None else PORTAL_DEFAULT_BUDGET,
                }
            )
            try:
                result = generator.generate(
                    project_root,
                    output_dir=Path(output_override).expanduser() if output_override else None,
                    budget=budget_limit,
                    force=getattr(args, "force", False),
                )
            except DocsPortalError as exc:
                payload = {
                    "status": "error",
                    "error": {
                        "code": exc.code,
                        "message": str(exc),
                        "remediation": exc.remediation,
                    },
                }
                if as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"docs portal error: {exc.code}: {exc}", file=sys.stderr)
                    if exc.remediation:
                        print(f"  remediation: {exc.remediation}", file=sys.stderr)
                event_context.update({"error_code": exc.code})
                exit_code = 1
            else:
                response = {
                    "status": "ok",
                    "path": str(result.output_path),
                    "files": result.file_count,
                    "size_bytes": result.total_size_bytes,
                    "generated_at": result.generated_at,
                    "inventory": result.inventory_counts,
                }
                if as_json:
                    print(json.dumps(response, ensure_ascii=False, indent=2))
                else:
                    print(
                        f"docs portal generated at {response['path']} "
                        f"({response['files']} files, {response['size_bytes']} bytes)",
                    )
                event_context.update({"files": result.file_count, "size_bytes": result.total_size_bytes})
                exit_code = 0
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


def _log_palette_action(
    project_path: Path,
    entry: dict[str, Any],
    result: MissionExecResult,
    *,
    service: MissionService | None = None,
    operation_id: str | None = None,
    source: str = "cli",
) -> None:
    svc = service or MissionService()
    action_id = entry.get("id") or entry.get("label") or "mission-action"
    label = entry.get("label") or action_id
    actor_id = entry.get("actorId") or action_id
    category = entry.get("category") or (entry.get("action") or {}).get("kind")
    raw_tags = entry.get("tags") or []
    if category:
        raw_tags = [category, *raw_tags]
    tags = [tag for tag in dict.fromkeys(raw_tags) if isinstance(tag, str) and tag]
    timeline_event = f"{source}.{action_id}".replace(":", ".").replace(" ", "_")
    svc.record_action(
        project_path,
        action_id=action_id,
        label=label,
        action=entry.get("action"),
        result=result,
        source=source,
        operation_id=operation_id,
        actor_id=actor_id,
        origin=source,
        tags=tags,
        append_timeline=True,
        timeline_event=timeline_event,
        timeline_payload={
            "category": category or (tags[0] if tags else "mission"),
            "label": label,
            "action": entry.get("action"),
            "palette": {
                key: entry[key]
                for key in ("id", "label", "category", "type")
                if key in entry
            },
        },
    )


def _update_mission_dashboard(project_path: Path, analytics: dict[str, Any]) -> None:
    report_dir = project_path / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = report_dir / "architecture-dashboard.json"
    activity_path = report_dir / "mission-activity.json"
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
    mission_payload = dict(analytics)
    mission_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("mission", {})
    data["mission"] = mission_payload
    dashboard_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    activity_snapshot = {
        "generated_at": mission_payload["updated_at"],
        "activity": mission_payload.get("activity", {}),
        "filters": mission_payload.get("activityFilters", {}),
    }
    activity_path.write_text(json.dumps(activity_snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        board = payload.get("tasks") or {}
        open_count = board.get("open", 0)
        board_tasks = board.get("tasks") or []
        print(f"perf follow-up tasks open: {open_count}")
        for task in [task for task in board_tasks if task.get("status") == "open"][:3]:
            print(f"  - {task.get('id')}: {task.get('recommended_action')}")

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
        followup = perf.get("followup") or {}
        if followup:
            status = followup.get("status")
            recommended = followup.get("recommended_action")
            print(f"  followup: {status}")
            if recommended:
                print(f"    action: {recommended}")
        tasks = perf.get("tasks") or []
        if tasks:
            print("  open tasks:")
            for task in tasks:
                if task.get("status") == "open":
                    print(f"    - {task.get('id')} → {task.get('recommended_action')}")


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
    board = payload.get("tasks") or {}

    print("Mission Analytics")
    print("=================")
    print(f"activity count: {activity.get('count', 0)}")
    sources = activity.get("sources") or {}
    if sources:
        print("by source:")
        for name, count in sorted(sources.items(), key=lambda item: item[0]):
            print(f"  - {name}: {count}")
    actors = activity.get("actors") or {}
    if actors:
        print("top actors:")
        for name, count in sorted(actors.items(), key=lambda item: item[1], reverse=True)[:5]:
            print(f"  - {name}: {count}")
    tags = activity.get("tags") or {}
    if tags:
        print("tag summary:")
        for name, count in sorted(tags.items(), key=lambda item: item[1], reverse=True)[:5]:
            print(f"  - {name}: {count}")
    last_op = activity.get("lastOperationId")
    if last_op:
        print(f"last operation: {last_op} @ {activity.get('lastTimestamp')}")
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
    followup = perf.get("followup") or {}
    if followup:
        status = followup.get("status")
        recommended = followup.get("recommended_action")
        print(f"followup status: {status}")
        if recommended:
            print(f"recommended action: {recommended}")
    tasks = board.get("tasks") or []
    if tasks:
        print(f"open follow-up tasks: {sum(1 for task in tasks if task.get('status') == 'open')}")
        for task in tasks[:5]:
            label = task.get("id")
            status = task.get("status")
            action = task.get("recommended_action")
            print(f"  - {label}: {status} ({action})")
    tasks = perf.get("tasks") or []
    if tasks:
        open_tasks = [task for task in tasks if task.get("status") == "open"]
        print(f"open perf tasks: {len(open_tasks)}")
        for task in open_tasks[:5]:
            print(f"  - {task.get('id')}: {task.get('recommended_action')}")
    print()


def _summarize_activity_entries(entries: list[dict[str, Any]], log_path: str | Path) -> dict[str, Any]:
    sources: dict[str, int] = {}
    actors: dict[str, int] = {}
    tags: dict[str, int] = {}
    last_operation_id: str | None = None
    last_timestamp: str | None = None
    for entry in entries:
        source = entry.get("source") or entry.get("origin")
        if isinstance(source, str) and source:
            sources[source] = sources.get(source, 0) + 1
        actor = entry.get("actorId")
        if isinstance(actor, str) and actor:
            actors[actor] = actors.get(actor, 0) + 1
        entry_tags = entry.get("tags") if isinstance(entry.get("tags"), list) else []
        for tag in entry_tags:
            if isinstance(tag, str) and tag:
                tags[tag] = tags.get(tag, 0) + 1
        op_id = entry.get("operationId")
        if isinstance(op_id, str) and op_id:
            last_operation_id = op_id
        ts = entry.get("timestamp")
        if isinstance(ts, str):
            last_timestamp = ts
    recent = entries[-5:]
    return {
        "count": len(entries),
        "recent": recent[::-1],
        "logPath": str(log_path),
        "sources": sources,
        "actors": actors,
        "tags": tags,
        "lastOperationId": last_operation_id,
        "lastTimestamp": last_timestamp,
    }


def _filter_activity_payload(
    activity: dict[str, Any] | None,
    *,
    sources: list[str] | None,
    actors: list[str] | None,
    tags: list[str] | None,
) -> dict[str, Any] | None:
    if not activity or not (sources or actors or tags):
        return activity
    log_path = activity.get("logPath")
    if not log_path:
        return activity
    try:
        entries = json.loads(Path(log_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return activity

    def _match(entry: dict[str, Any]) -> bool:
        if sources:
            source = entry.get("source") or entry.get("origin")
            if source not in sources:
                return False
        if actors:
            actor = entry.get("actorId")
            if actor not in actors:
                return False
        if tags:
            entry_tags = entry.get("tags") if isinstance(entry.get("tags"), list) else []
            if not any(tag in entry_tags for tag in tags):
                return False
        return True

    filtered = [entry for entry in entries if _match(entry)]
    return _summarize_activity_entries(filtered, log_path)


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

    if command == "dashboard":
        filters_tuple = tuple(filters) if filters else tuple(MISSION_FILTER_CHOICES)
        if getattr(args, "serve", False):
            host = getattr(args, "bind", "127.0.0.1")
            port = int(getattr(args, "port", 8765) or 0)
            interval = max(float(getattr(args, "interval", 5.0)), 0.5)
            provided_token = getattr(args, "token", None)
            if provided_token:
                token = provided_token
                session_path = None
            else:
                token, session_path = load_or_create_session_token(project_path)
            config = MissionDashboardWebConfig(
                project_root=project_path,
                filters=filters_tuple,
                timeline_limit=timeline_limit,
                interval=interval,
                token=token,
                host=host,
                port=port,
            )
            app = MissionDashboardWebApp(service, config)
            server = app.create_server()
            actual_host, actual_port = server.server_address
            print(f"Mission dashboard web server listening on http://{actual_host}:{actual_port}/")
            print(f"Authorization token: {token}")
            if session_path:
                print(f"Session token saved in {session_path}")
            print("Endpoints: / (UI), /healthz, /sse/events, POST /playbooks/<issue>")
            print("Press Ctrl+C to stop.")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("Stopping mission dashboard web server")
            finally:
                app.shutdown()
                server.shutdown()
                server.server_close()
            duration = (time.perf_counter() - start) * 1000
            record_structured_event(
                SETTINGS,
                "mission.dashboard",
                status="success",
                component="mission",
                duration_ms=duration,
                payload=event_context | {
                    "mode": "web",
                    "bind": actual_host,
                    "port": actual_port,
                    "interval": interval,
                },
            )
            return 0

        result = service.persist_twin(project_path)
        payload = result.twin
        renderer = MissionDashboardRenderer(payload, filters, timeline_limit)
        snapshot_path = getattr(args, "snapshot", None)
        if snapshot_path:
            path = Path(snapshot_path).expanduser().resolve()
            write_snapshot(renderer, path)
            print(f"Mission dashboard snapshot written to {path}")
            duration = (time.perf_counter() - start) * 1000
            record_structured_event(
                SETTINGS,
                "mission.dashboard",
                status="success",
                component="mission",
                duration_ms=duration,
                payload=event_context | {"snapshot": str(path)},
            )
            return 0
        use_curses = getattr(args, "no_curses", False) is False and sys.stdout.isatty()
        width = terminal_width()
        if use_curses:
            exit_code = run_dashboard_curses(service, project_path, renderer, filters, timeline_limit)
            duration = (time.perf_counter() - start) * 1000
            record_structured_event(
                SETTINGS,
                "mission.dashboard",
                status="success",
                component="mission",
                duration_ms=duration,
                payload=event_context | {"mode": "curses"},
            )
            return exit_code
        print(renderer.render_text(width=width))
        duration = (time.perf_counter() - start) * 1000
        record_structured_event(
            SETTINGS,
            "mission.dashboard",
            status="success",
            component="mission",
            duration_ms=duration,
            payload=event_context | {"mode": "static"},
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
        "category": result.playbook.get("category") if result.playbook else None,
    }
    _log_palette_action(project_path, log_entry, result, service=service, source="mission.exec")
    return 0 if result.status in {"success", "noop"} else 1


def _mission_watch_cmd(args: argparse.Namespace) -> int:
    bootstrap, _ = _build_services()
    project_path = _default_project_path(getattr(args, "path", None))
    project_id = _resolve_project_id(bootstrap, project_path, "mission", allow_auto=True)
    if project_id is None:
        return 1

    config_path = project_id.root / PROJECT_DIR / "config" / "watch.yaml"
    sla_path = project_id.root / PROJECT_DIR / "config" / "sla.yaml"
    try:
        rules = load_watch_rules(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        sla_rules = load_sla_rules(sla_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not rules and not sla_rules:
        print("No watch rules or SLA entries configured", file=sys.stderr)
        return 1

    watcher = MissionWatcher(project_id, MissionService(), rules, sla_rules)
    interval = getattr(args, "interval", 60.0)
    iterations = getattr(args, "max_iterations", 0)
    if getattr(args, "once", False):
        iterations = 1
    executed = 0

    try:
        while True:
            start = time.perf_counter()
            report = watcher.run_once()
            duration = (time.perf_counter() - start) * 1000
            record_structured_event(
                SETTINGS,
                "mission.watch",
                status="success",
                component="mission",
                duration_ms=duration,
                payload={
                    "path": str(project_id.root),
                    "actions": len(report["actions"]),
                    "sla_breaches": len(report["sla"]),
                },
            )
            for breach in report["sla"]:
                record_structured_event(
                    SETTINGS,
                    "sla.breach",
                    status=breach.get("severity", "warning"),
                    component="mission",
                    payload=breach | {"path": str(project_id.root)},
                )
            if getattr(args, "json", False):
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                if report["actions"]:
                    print("Triggered actions:")
                    for action in report["actions"]:
                        print(
                            f"  - {action['rule']} -> {action['status']} (event {action['event_ts']})"
                        )
                if report["sla"]:
                    print("SLA breaches:")
                    for breach in report["sla"]:
                        print(
                            f"  - {breach['acknowledgement']} status={breach['status']} age={breach['minutes_since_update']:.1f}m"
                        )
            executed += 1
            if iterations and executed >= iterations:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("mission watch interrupted")
    return 0


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

    sources_filter = getattr(args, "sources", None)
    actors_filter = getattr(args, "actors", None)
    tags_filter = getattr(args, "tags", None)

    activity = payload.get("activity") or {}
    filtered_activity = _filter_activity_payload(activity, sources=sources_filter, actors=actors_filter, tags=tags_filter)
    if filtered_activity is None:
        filtered_activity = activity

    analytics_payload = dict(payload)
    analytics_payload["activity"] = filtered_activity
    filters_meta: dict[str, Any] | None = None
    if sources_filter or actors_filter or tags_filter:
        filters_meta = {}
        if sources_filter:
            filters_meta["sources"] = sources_filter
        if actors_filter:
            filters_meta["actors"] = actors_filter
        if tags_filter:
            filters_meta["tags"] = tags_filter

    if getattr(args, "json", False):
        summary = {
            "activity": filtered_activity,
            "acknowledgements": analytics_payload.get("acknowledgements", {}),
            "perf": analytics_payload.get("perf", {}),
            "tasks": analytics_payload.get("tasks", {}),
        }
        if filters_meta:
            summary["filters"] = filters_meta
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_mission_analytics(analytics_payload)

    dashboard_payload = {
        "activity": filtered_activity,
        "acknowledgements": analytics_payload.get("acknowledgements", {}),
        "perf": analytics_payload.get("perf", {}),
        "tasks": analytics_payload.get("tasks", {}),
    }
    if filters_meta:
        dashboard_payload["activityFilters"] = filters_meta

    _update_mission_dashboard(project_path, dashboard_payload)

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
            _log_palette_action(project_path, entry, result_exec, service=service, source="mission.ui")
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
    parser = argparse.ArgumentParser(
        prog="agentcall",
        description=HELP_OVERVIEW,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('--version', action='version', version=f'agentcall {__version__}')

    sub = parser.add_subparsers(dest="command", required=True)

    help_cmd = sub.add_parser(
        "help",
        help="Показать контекстную справку по проекту",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Contextual guidance for AgentControl projects",
    )
    help_cmd.add_argument("--path", nargs="?", help="Проект (по умолчанию: текущая директория)")
    help_cmd.add_argument("--json", action="store_true", help="Вывести справку в формате JSON")
    help_cmd.set_defaults(func=_help_cmd)

    quickstart_cmd = sub.add_parser("quickstart", help="Bootstrap project and run setup/verify")
    quickstart_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    quickstart_cmd.add_argument("--channel", default="stable", help="Template channel (default: stable)")
    quickstart_cmd.add_argument("--template", default="default", help="Template name (default: default)")
    quickstart_cmd.add_argument("--force", action="store_true", help="Recreate capsule if it already exists")
    quickstart_cmd.add_argument("--no-setup", action="store_true", help="Skip setup pipeline")
    quickstart_cmd.add_argument("--no-verify", action="store_true", help="Skip verify pipeline")
    quickstart_cmd.add_argument("--verify-arg", dest="verify_args", action="append", default=[], help="Forward extra arguments to verify")
    quickstart_cmd.set_defaults(func=_quickstart_cmd)

    init_cmd = sub.add_parser("init", help="Bootstrap a new project capsule")
    init_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    init_cmd.add_argument("--channel", default="stable")
    init_cmd.add_argument("--template", default="default", help="Template name (default)")
    init_cmd.add_argument("--force", action="store_true")
    init_cmd.set_defaults(func=_bootstrap_cmd)

    bootstrap_profile_cmd = sub.add_parser("bootstrap", help="Run bootstrap onboarding wizard")
    bootstrap_profile_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    bootstrap_profile_cmd.add_argument("--profile", help="Pre-select a default profile by id")
    bootstrap_profile_cmd.add_argument("--json", action="store_true", help="Emit machine-readable summary output")
    bootstrap_profile_cmd.set_defaults(func=_bootstrap_profile_cmd)

    upgrade_cmd = sub.add_parser("upgrade", help="Upgrade existing project to current template")
    upgrade_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    upgrade_cmd.add_argument("--channel", default="stable")
    upgrade_cmd.add_argument("--template", default=None, help="Override template name")
    upgrade_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview legacy migration and template upgrade without applying changes",
    )
    upgrade_cmd.add_argument(
        "--skip-legacy-migrate",
        action="store_true",
        help="Skip automatic migration of legacy agentcontrol/ capsules",
    )
    upgrade_cmd.add_argument("--json", action="store_true", help="Emit machine-readable report")
    upgrade_cmd.set_defaults(func=_upgrade_cmd)

    tasks_cmd = sub.add_parser(
        "tasks",
        help="Task board operations",
        description="Synchronise data/tasks.board.json against external providers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tasks_sub = tasks_cmd.add_subparsers(dest="tasks_command", required=True)

    tasks_sync_cmd = tasks_sub.add_parser(
        "sync",
        help="Diff local board against configured provider",
    )
    tasks_sync_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    provider_group = tasks_sync_cmd.add_mutually_exclusive_group()
    provider_group.add_argument(
        "--config",
        help="Provider config path (default: config/tasks.provider.json)",
    )
    provider_group.add_argument(
        "--provider",
        help="Inline provider type (file/jira/github)",
    )
    tasks_sync_cmd.add_argument(
        "--input",
        dest="provider_input",
        help="Inline provider snapshot/input path (used with --provider)",
    )
    tasks_sync_cmd.add_argument(
        "--provider-option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set inline provider option (repeatable, dot notation supported)",
    )
    tasks_sync_cmd.add_argument(
        "--output",
        help="Override report path (default: reports/tasks_sync.json)",
    )
    tasks_sync_cmd.add_argument(
        "--apply",
        action="store_true",
        help="Apply detected changes to data/tasks.board.json",
    )
    tasks_sync_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit plan as JSON",
    )
    tasks_sync_cmd.set_defaults(func=_tasks_sync_cmd)

    extension_help = dedent(
        """
        Lifecycle commands for project extensions.

        Quickstart recipes:
          1. agentcall extension init docs_sync
          2. agentcall extension add docs_sync --source extensions/docs_sync
          3. agentcall extension publish --json

        Outputs:
          - --json emits structured catalog entries for add/list/remove/publish.
        """
    )
    extension_epilog = dedent(
        """
        Avoid:
          - Running inside the SDK repository (use scripts/test-place.sh instead).
          - Mixing --source and --git flags in a single add command.
          - Registering scaffolds before manifest.json passes lint.

        Docs:
          - docs/tutorials/extensions.md
        """
    )
    extension_cmd = sub.add_parser(
        "extension",
        help="Manage project extensions",
        description=extension_help,
        epilog=extension_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    extension_cmd.add_argument("--path", dest="path", default=None, help="Project path (default: current directory)")
    extension_sub = extension_cmd.add_subparsers(dest="extension_command", required=True)

    extension_init = extension_sub.add_parser("init", help="Scaffold a new extension")
    extension_init.add_argument("name")
    extension_init.add_argument("--force", action="store_true", help="Overwrite existing extension scaffold")
    extension_init.set_defaults(func=_extension_init_cmd)

    extension_add = extension_sub.add_parser("add", help="Register an existing extension in the catalog")
    extension_add.add_argument("name")
    extension_add.add_argument("--source", help="Local path to copy the extension from")
    extension_add.add_argument("--git", dest="git", help="Git repository URL to clone the extension from")
    extension_add.add_argument("--ref", dest="ref", help="Git reference/branch to checkout when cloning")
    extension_add.add_argument("--json", action="store_true", help="Emit machine-readable JSON result")
    extension_add.set_defaults(func=_extension_add_cmd)

    extension_list = extension_sub.add_parser("list", help="List registered extensions")
    extension_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    extension_list.set_defaults(func=_extension_list_cmd)

    extension_remove = extension_sub.add_parser("remove", help="Remove an extension from the catalog")
    extension_remove.add_argument("name")
    extension_remove.add_argument("--purge", action="store_true", help="Delete extension files after removal")
    extension_remove.add_argument("--json", action="store_true", help="Emit machine-readable JSON result")
    extension_remove.set_defaults(func=_extension_remove_cmd)

    extension_lint = extension_sub.add_parser("lint", help="Validate extension manifests")
    extension_lint.add_argument("--name", default=None, help="Validate a specific extension only")
    extension_lint.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    extension_lint.set_defaults(func=_extension_lint_cmd)

    extension_publish = extension_sub.add_parser("publish", help="Export extension catalog")
    extension_publish.add_argument("--dry-run", action="store_true", help="Mark the export as dry run")
    extension_publish.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    extension_publish.set_defaults(func=_extension_publish_cmd)

    gallery_cmd = sub.add_parser("gallery", help="Sample gallery utilities")
    gallery_cmd.add_argument("--path", dest="path", help="Project path (default: current directory)")
    gallery_sub = gallery_cmd.add_subparsers(dest="gallery_command", required=True)

    gallery_list = gallery_sub.add_parser("list", help="List available gallery samples")
    gallery_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    gallery_list.set_defaults(func=_gallery_cmd, gallery_command="list")

    gallery_fetch = gallery_sub.add_parser("fetch", help="Download a gallery sample as archive or directory")
    gallery_fetch.add_argument("sample_id", help="Identifier of the gallery sample")
    gallery_fetch.add_argument("--dest", help="Destination directory or archive path (default: current directory)")
    gallery_fetch.add_argument("--directory", action="store_true", help="Copy as directory instead of ZIP archive")
    gallery_fetch.add_argument("--json", action="store_true", help="Emit machine-readable JSON result")
    gallery_fetch.set_defaults(func=_gallery_cmd, gallery_command="fetch")

    release_cmd = sub.add_parser("release", help="Release management utilities")
    release_sub = release_cmd.add_subparsers(dest="release_command", required=True)

    release_notes = release_sub.add_parser("notes", help="Generate release notes from git history")
    release_notes.add_argument("path", nargs="?", help="Project path (default: current directory)")
    release_notes.add_argument("--from-ref", help="Lower bound git reference (exclusive)")
    release_notes.add_argument("--to-ref", default="HEAD", help="Upper bound git reference (default: HEAD)")
    release_notes.add_argument("--max-commits", type=int, help="Limit number of commits analysed")
    release_notes.add_argument(
        "--output",
        help="Markdown output path (default: reports/release_notes.md)",
    )
    release_notes.add_argument(
        "--json",
        action="store_true",
        help="Emit metadata as JSON (also writes reports/release_notes.json)",
    )
    release_notes.set_defaults(func=_release_notes_cmd)

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
    telemetry_report.add_argument(
        "--recent",
        type=int,
        default=0,
        help="Limit aggregation to the last N telemetry events",
    )
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

    docs_lint = docs_sub.add_parser("lint", help="Run documentation lint checks")
    docs_lint.add_argument("--knowledge", action="store_true", help="Run knowledge coverage lint")
    docs_lint.add_argument("--output", help="Override report output path")
    docs_lint.add_argument(
        "--max-age-hours",
        type=float,
        dest="max_age_hours",
        help="Fail when knowledge files are older than the specified number of hours",
    )
    docs_lint.add_argument(
        "--validate-external",
        action="store_true",
        help="Validate external HTTP(S) links",
    )
    docs_lint.add_argument(
        "--link-timeout",
        type=float,
        dest="link_timeout",
        help="Timeout for external link validation (seconds)",
    )
    docs_lint.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_lint.set_defaults(func=_docs_cmd, docs_command="lint")

    docs_portal = docs_sub.add_parser("portal", help="Generate static documentation portal")
    docs_portal.add_argument("--output", help="Output directory (default: reports/docs/portal)")
    docs_portal.add_argument("--force", action="store_true", help="Overwrite output directory if it exists")
    docs_portal.add_argument("--budget", type=int, help="Size budget in bytes (default: 1048576)")
    docs_portal.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    docs_portal.set_defaults(func=_docs_cmd, docs_command="portal")

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

    mission_dashboard = mission_sub.add_parser("dashboard", help="Interactive mission dashboard (TUI)")
    mission_dashboard.add_argument("path", nargs="?", help="Project path (default: current directory)")
    mission_dashboard.add_argument("--filter", dest="filters", action="append", choices=MISSION_FILTER_CHOICES, help="Filter sections to display")
    mission_dashboard.add_argument("--timeline-limit", type=int, default=10, help="Number of timeline events to display")
    mission_dashboard.add_argument("--snapshot", help="Write HTML snapshot to the given path")
    mission_dashboard.add_argument("--no-curses", action="store_true", help="Disable curses UI and print static output")
    mission_dashboard.add_argument("--serve", action="store_true", help="Start lightweight web server instead of TUI")
    mission_dashboard.add_argument("--bind", default="127.0.0.1", help="Bind address for --serve (default: 127.0.0.1)")
    mission_dashboard.add_argument("--port", type=int, default=8765, help="Bind port for --serve (default: 8765, 0 for random)")
    mission_dashboard.add_argument("--token", help="Override auth token for --serve (default: session.json token)")
    mission_dashboard.add_argument("--interval", type=float, default=5.0, help="Seconds between SSE updates in --serve mode")
    mission_dashboard.set_defaults(func=_mission_cmd, mission_command="dashboard")

    mission_watch = mission_sub.add_parser("watch", help="Automate playbooks based on mission events")
    mission_watch.add_argument("path", nargs="?", help="Project path (default: current directory)")
    mission_watch.add_argument("--interval", type=float, default=60.0, help="Polling interval in seconds (default: 60)")
    mission_watch.add_argument("--max-iterations", type=int, default=0, help="Stop after N iterations (0 = run until interrupted)")
    mission_watch.add_argument("--once", action="store_true", help="Run a single iteration and exit")
    mission_watch.add_argument("--json", action="store_true", help="Emit machine-readable JSON per iteration")
    mission_watch.set_defaults(func=_mission_watch_cmd)

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
    mission_analytics.add_argument("--source", dest="sources", action="append", help="Filter activity by source/origin")
    mission_analytics.add_argument("--actor", dest="actors", action="append", help="Filter activity by actorId")
    mission_analytics.add_argument("--tag", dest="tags", action="append", help="Filter activity by tag")
    mission_analytics.set_defaults(func=_mission_analytics_cmd)

    doctor_cmd = sub.add_parser("doctor", help="Environment diagnostics")
    doctor_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
    doctor_cmd.add_argument("--bootstrap", action="store_true", help="Run bootstrap readiness checks")
    doctor_cmd.add_argument("--json", action="store_true", help="Emit machine-readable output")
    doctor_cmd.add_argument(
        "extra",
        nargs="*",
        help="Extra arguments passed to the project doctor pipeline when --bootstrap is not used",
    )
    doctor_cmd.set_defaults(func=_doctor_cmd, command_name="doctor")

    def make_pipeline(name: str, help_text: str) -> None:
        pipeline_cmd = sub.add_parser(name, help=help_text)
        pipeline_cmd.add_argument("path", nargs="?", help="Project path (default: current directory)")
        pipeline_cmd.add_argument("extra", nargs=argparse.REMAINDER, help="Extra arguments passed to underlying steps")
        pipeline_cmd.set_defaults(func=_run_cmd, command_name=name)

    make_pipeline("setup", "Run environment setup pipeline")
    make_pipeline("dev", "Run development workflow pipeline")
    make_pipeline("verify", "Run the QA verification pipeline")
    make_pipeline("fix", "Run autofix pipeline")
    make_pipeline("review", "Run review pipeline")
    make_pipeline("ship", "Run release pipeline")
    make_pipeline("status", "Render project status")
    make_pipeline("progress", "Render roadmap and progress dashboards")
    make_pipeline("roadmap", "Render roadmap status overview")
    make_pipeline("agents", "Agent management commands")

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
    mission_subcommands = {"summary", "ui", "detail", "exec", "analytics", "dashboard", "watch"}
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

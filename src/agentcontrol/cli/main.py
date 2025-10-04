#!/usr/bin/env python3
"""Entry point for the agentcall CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from agentcontrol.app.bootstrap_service import BootstrapService
from agentcontrol.app.command_service import CommandService
from agentcontrol.domain.project import PROJECT_DESCRIPTOR, PROJECT_DIR, ProjectId, ProjectNotInitialisedError
from agentcontrol.adapters.fs_template_repo import FSTemplateRepository
from agentcontrol.settings import SETTINGS
from agentcontrol.utils.telemetry import clear as telemetry_clear
from agentcontrol.utils.telemetry import iter_events as telemetry_iter
from agentcontrol.utils.telemetry import record_event, summarize as telemetry_summarize
from agentcontrol.plugins import PluginContext
from agentcontrol import __version__
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
    print(f"Path {project_path} does not contain an AgentControl capsule.", file=sys.stderr)
    print('Run `agentcall init [--template ...]` here, or pass the project path explicitly.', file=sys.stderr)
    print('Example: `agentcall status /path/to/project`', file=sys.stderr)
    print('Auto-initialisation is disabled by default. Set `AGENTCONTROL_AUTO_INIT=1` to enable it explicitly, or `AGENTCONTROL_NO_AUTO_INIT=1` to force-disable in wrappers.', file=sys.stderr)
    record_event(SETTINGS, 'error.project_missing', {'command': command, 'cwd': str(project_path)})


def _auto_bootstrap_project(bootstrap: BootstrapService, project_path: Path, command: str) -> ProjectId | None:
    if _truthy_env('AGENTCONTROL_NO_AUTO_INIT'):
        record_event(SETTINGS, 'autobootstrap.disabled', {'command': command, 'cwd': str(project_path)})
        return None

    auto_enabled = _truthy_env('AGENTCONTROL_AUTO_INIT')
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
    make_pipeline("heart", "Memory Heart operations")
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", None)
    pipeline = getattr(args, "command_name", None)
    maybe_auto_update(SETTINGS, __version__, command=command, pipeline=pipeline)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

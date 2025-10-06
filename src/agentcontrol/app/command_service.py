"""Command orchestration for agentcall."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from agentcontrol.domain.project import PROJECT_DIR, ProjectCapsule, ProjectId
from agentcontrol.settings import RuntimeSettings
from agentcontrol.utils.telemetry import record_event


class CommandNotFoundError(RuntimeError):
    pass


@dataclass
class CommandStep:
    name: str
    exec: List[str]


@dataclass
class CommandPipeline:
    name: str
    steps: List[CommandStep]


class CommandRegistry:
    def __init__(self, pipelines: dict[str, CommandPipeline]) -> None:
        self._pipelines = pipelines

    @classmethod
    def load_from_file(cls, path: Path) -> "CommandRegistry":
        import yaml  # lazy import to keep import cost low

        if not path.exists():
            raise FileNotFoundError(f"Command descriptor missing: {path}")
        data = yaml.safe_load(path.read_text("utf-8")) or {}
        pipelines: dict[str, CommandPipeline] = {}
        commands = data.get("commands", {})
        if not isinstance(commands, dict):
            raise ValueError("Invalid agentcall.yaml structure: commands is not a mapping")
        for name, payload in commands.items():
            steps_raw = payload.get("steps", []) if isinstance(payload, dict) else []
            steps: list[CommandStep] = []
            for idx, step in enumerate(steps_raw):
                if not isinstance(step, dict):
                    raise ValueError(f"Command {name} step #{idx} must be a mapping")
                exec_cmd = step.get("exec")
                if not isinstance(exec_cmd, list) or not all(isinstance(arg, str) for arg in exec_cmd):
                    raise ValueError(f"Command {name} step #{idx} exec must be a list of strings")
                step_name = step.get("name", f"{name}-step{idx}")
                steps.append(CommandStep(step_name, exec_cmd))
            pipelines[name] = CommandPipeline(name=name, steps=steps)
        return cls(pipelines)

    def get(self, name: str) -> CommandPipeline:
        if name not in self._pipelines:
            raise CommandNotFoundError(f"Command {name} not registered")
        pipeline = self._pipelines[name]
        if not pipeline.steps:
            raise RuntimeError(f"Command {name} has no steps defined")
        return pipeline

    def list_commands(self) -> Iterable[str]:
        return sorted(self._pipelines)


class CommandService:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings

    def run(self, project_id: ProjectId, command: str, extra_args: list[str]) -> int:
        capsule = ProjectCapsule.load(project_id)
        capsule.ensure_compatible(self._settings.cli_version)
        descriptor_path = project_id.command_descriptor_path()
        registry = CommandRegistry.load_from_file(descriptor_path)
        pipeline = registry.get(command)
        state_dir = self._resolve_state_dir(project_id)
        state_dir.mkdir(parents=True, exist_ok=True)
        env = self._build_env(project_id, state_dir, capsule.template_name)
        exit_code = 0
        for index, step in enumerate(pipeline.steps):
            args = step.exec
            if index == 0 and extra_args:
                args = args + extra_args
            try:
                result = subprocess.run(args, cwd=project_id.root, env=env)
            except FileNotFoundError as exc:
                missing = args[0] if args else "<unknown>"
                raise RuntimeError(
                    "Command pipeline step executable missing: "
                    f"command={pipeline.name} step={step.name} executable={missing}. "
                    "Run `agentcall upgrade` to refresh the capsule or update agentcall.yaml."
                ) from exc
            exit_code = result.returncode
            if exit_code != 0:
                break
        record_event(
            self._settings,
            "pipeline",
            {
                "command": command,
                "project": str(project_id.root),
                "template": capsule.template_name,
                "exit_code": exit_code,
            },
        )
        return exit_code

    def _resolve_state_dir(self, project_id: ProjectId) -> Path:
        import hashlib

        digest = hashlib.sha256(str(project_id.root).encode("utf-8")).hexdigest()[:16]
        return self._settings.state_dir / digest

    def _build_env(self, project_id: ProjectId, state_dir: Path, template: str) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("AGENTCONTROL_HOME", str(self._settings.home_dir))
        env["AGENTCONTROL_PROJECT_ROOT"] = str(project_id.root)
        env["AGENTCONTROL_STATE"] = str(state_dir)
        env["AGENTCONTROL_TEMPLATE"] = template
        capsule_paths = [str(project_id.root / PROJECT_DIR)]
        pythonpath = env.get("PYTHONPATH")
        capsule_pythonpath = os.pathsep.join(capsule_paths)
        if pythonpath:
            env["PYTHONPATH"] = f"{capsule_pythonpath}{os.pathsep}{pythonpath}"
        else:
            env["PYTHONPATH"] = capsule_pythonpath
        env.setdefault("PYTHONUNBUFFERED", "1")
        return env

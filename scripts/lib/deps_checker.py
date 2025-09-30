#!/usr/bin/env python3
"""Проверка окружения и зависимостей для GPT-5 Codex SDK."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str
    details: str
    fix: str


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd: list[str]) -> tuple[bool, str]:
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, text=True)
        return True, out.stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover - depends on env
        return False, str(exc)


def detect_python_packages() -> Iterable[CheckResult]:
    for pkg in ("pytest", "diff_cover", "reviewdog", "detect_secrets"):
        try:
            __import__(pkg.replace("-", "_"))
            status, details = "ok", "installed"
        except ImportError:
            status, details = "missing", ""
        fix = f"pip install {pkg}" if pkg != "reviewdog" else "GO111MODULE=on go install github.com/reviewdog/reviewdog/cmd/reviewdog@latest"
        yield CheckResult(name=f"python:{pkg}", status=status, details=details, fix=fix)


def detect_tools() -> Iterable[CheckResult]:
    commands = {
        "git": "apt install git",
        "make": "apt install make",
        "bash": "already required",
        "shellcheck": "apt install shellcheck",
        "diff-cover": "pip install diff-cover",
        "detect-secrets": "pip install detect-secrets",
    }
    for cmd, fix in commands.items():
        if which(cmd):
            status, details = "ok", shutil.which(cmd) or ""
        else:
            status, details = "missing", ""
        yield CheckResult(name=f"tool:{cmd}", status=status, details=details, fix=fix)


def detect_stack_configs(root: Path) -> Iterable[CheckResult]:
    entries = {
        "package.json": "npm install",
        "yarn.lock": "yarn install",
        "pnpm-lock.yaml": "pnpm install",
        "Pipfile": "pipenv install --dev",
        "poetry.lock": "poetry install",
        "go.mod": "go mod download",
        "Cargo.toml": "cargo fetch",
        "pom.xml": "mvn -B verify",
        "build.gradle": "./gradlew check",
        "build.gradle.kts": "./gradlew check",
        "requirements.txt": "pip install -r requirements.txt",
    }
    for rel, tip in entries.items():
        if (root / rel).exists():
            yield CheckResult(name=f"stack:{rel}", status="detected", details=tip, fix=tip)


def collect(root: Path) -> dict:
    results = [
        *detect_tools(),
        *detect_python_packages(),
        *detect_stack_configs(root),
    ]
    summary = {
        "generated_at": Path("/").stat().st_mtime,
        "root": str(root),
        "results": [asdict(r) for r in results],
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    root = Path(argv[0]).resolve() if argv else Path.cwd()
    report = collect(root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

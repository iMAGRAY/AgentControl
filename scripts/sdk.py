#!/usr/bin/env python3
"""AgentControl SDK helper CLI.

Commands:
  publish  – build distributions, upload to PyPI, then update local installation.
  local    – build distributions and update local installation only.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD_ENV = ROOT / ".sdk-build-env"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, text=True)


def env_python() -> Path:
    if os.name == "nt":
        return BUILD_ENV / "Scripts" / "python.exe"
    return BUILD_ENV / "bin" / "python"


def ensure_build_env() -> Path:
    python_path = env_python()
    if not python_path.exists():
        BUILD_ENV.mkdir(parents=True, exist_ok=True)
        run([sys.executable, "-m", "venv", str(BUILD_ENV)])
        run([str(python_path), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([str(python_path), "-m", "pip", "install", "build", "twine"])
    return python_path


def build_dist() -> tuple[list[Path], Path]:
    python_path = ensure_build_env()
    shutil.rmtree(DIST, ignore_errors=True)
    run([str(python_path), "-m", "build"])
    wheels = sorted(DIST.glob("*.whl"), key=lambda p: p.stat().st_mtime)
    if not wheels:
        raise SystemExit("build produced no wheel artifacts")
    return wheels, python_path


def install_local(wheel: Path, *, force: bool) -> None:
    if shutil.which("pipx"):
        cmd = ["pipx", "install", str(wheel)]
        if force:
            cmd.append("--force")
        run(cmd)
    elif shutil.which("pip"):
        cmd = [sys.executable, "-m", "pip", "install", str(wheel)]
        if force:
            cmd.append("--upgrade")
        run(cmd)
    else:
        raise SystemExit("neither pipx nor pip available for local installation")


def publish_and_update(force: bool) -> None:
    wheels, python_path = build_dist()
    artifacts = [str(p) for p in sorted(DIST.iterdir())]
    run([str(python_path), "-m", "twine", "upload", *artifacts])
    install_local(wheels[-1], force=force)


def local_update(force: bool) -> None:
    wheels, _ = build_dist()
    install_local(wheels[-1], force=force)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentControl SDK helper")
    sub = parser.add_subparsers(dest="command", required=True)

    publish = sub.add_parser("publish", help="Build, upload to PyPI, then update local installation")
    publish.add_argument("--force", action="store_true", help="Force reinstall local wheel")

    local = sub.add_parser("local", help="Build and update local installation only")
    local.add_argument("--force", action="store_true", help="Force reinstall local wheel")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "publish":
        publish_and_update(force=args.force)
    elif args.command == "local":
        local_update(force=args.force)
    else:
        parser.error("Unknown command")


if __name__ == "__main__":
    main()

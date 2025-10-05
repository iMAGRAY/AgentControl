#!/usr/bin/env python3
"""Manage offline auto-update cache for AgentControl."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_CACHE = Path.home() / ".agentcontrol" / "cache"


def resolve_cache_dir(dest: str | None) -> Path:
    candidate = dest or os.environ.get("AGENTCONTROL_AUTO_UPDATE_CACHE") or DEFAULT_CACHE
    path = Path(candidate).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def cmd_download(version: str, cache_dir: Path) -> None:
    command = [sys.executable, "-m", "pip", "download", f"agentcontrol=={version}", "--no-deps", "-d", str(cache_dir)]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print("pip download failed", file=sys.stderr)
        sys.exit(result.returncode)
    wheels = list(cache_dir.glob(f"agentcontrol-{version}-*.whl"))
    if not wheels:
        print("No wheel downloaded; ensure the package/version exists.", file=sys.stderr)
        sys.exit(1)
    print(f"Downloaded {wheels[0].name} to {cache_dir}")


def cmd_add(source: Path, cache_dir: Path) -> None:
    if not source.exists() or not source.is_file():
        print(f"Source file {source} not found", file=sys.stderr)
        sys.exit(1)
    target = cache_dir / source.name
    shutil.copy2(source, target)
    print(f"Cached {target}")


def cmd_list(cache_dir: Path, output_json: bool) -> None:
    artifacts = sorted(cache_dir.glob("agentcontrol-*-py3-none-any.whl"))
    if output_json:
        payload = {
            "cache_dir": str(cache_dir),
            "artifacts": [
                {
                    "name": art.name,
                    "path": str(art),
                    "size": art.stat().st_size,
                }
                for art in artifacts
            ],
        }
        print(json.dumps(payload, indent=2))
        return
    if not artifacts:
        print("No cached wheels found.")
        return
    print(f"Cache directory: {cache_dir}")
    for art in artifacts:
        size_kib = art.stat().st_size / 1024
        print(f"- {art.name} ({size_kib:.1f} KiB)")


def cmd_verify(cache_dir: Path) -> None:
    wheels = list(cache_dir.glob("agentcontrol-*-py3-none-any.whl"))
    if not wheels:
        print("No wheel to verify.")
        return
    for path in wheels:
        if not path.is_file():
            print(f"Skipping non-file entry {path}")
            continue
        print(f"Verified {path.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage AgentControl offline update cache")
    parser.add_argument("--dest", help="Override cache directory (default: env or ~/.agentcontrol/cache)")
    sub = parser.add_subparsers(dest="command", required=True)

    download = sub.add_parser("download", help="Download wheel for specific version from PyPI")
    download.add_argument("version", help="Version to download (e.g. 0.3.2)")

    add = sub.add_parser("add", help="Copy an existing wheel into the cache")
    add.add_argument("path", help="Path to wheel file")

    lst = sub.add_parser("list", help="List cached wheels")
    lst.add_argument("--json", action="store_true", dest="as_json")

    sub.add_parser("verify", help="Validate cached wheels exist")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cache_dir = resolve_cache_dir(args.dest)

    if args.command == "download":
        cmd_download(args.version, cache_dir)
        return 0
    if args.command == "add":
        cmd_add(Path(args.path).expanduser().resolve(), cache_dir)
        return 0
    if args.command == "list":
        cmd_list(cache_dir, args.as_json)
        return 0
    if args.command == "verify":
        cmd_verify(cache_dir)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

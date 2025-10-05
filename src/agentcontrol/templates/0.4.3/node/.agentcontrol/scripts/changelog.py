#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import textwrap
from pathlib import Path

from agentcontrol import __version__


def append_entry(message: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    header = f"## {__version__} — {now}"
    entry = textwrap.dedent(f"""
    {header}
    {message.strip()}
    """).strip()
    if path.exists():
        content = path.read_text(encoding="utf-8")
        path.write_text(entry + "\n\n" + content, encoding="utf-8")
    else:
        path.write_text(entry + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Append release notes entry")
    parser.add_argument("message", help="Release notes body")
    parser.add_argument("--file", default="docs/changes.md")
    args = parser.parse_args()

    append_entry(args.message, Path(args.file))
    print(f"Appended changelog entry for version {__version__} to {args.file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

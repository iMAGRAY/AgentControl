#!/usr/bin/env python3
"""Realness и secrets-сканирование изменённых строк.

Используется в make verify / make review для сигнализации о заглушках и
секретах без жёсткой блокировки.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


REALNESS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("not_implemented", re.compile(r"NotImplemented")),
    ("not_implemented_error", re.compile(r"raise\s+NotImplementedError")),
    ("stub_keyword", re.compile(r"\bstub\b", re.IGNORECASE)),
    ("fake_keyword", re.compile(r"\bfake\b", re.IGNORECASE)),
    ("mock_keyword", re.compile(r"\bmock\b", re.IGNORECASE)),
    ("plain_pass", re.compile(r"^\s*pass\s*(#.*)?$")),
)

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "aws_secret_key",
        re.compile(r"(?i)aws(.{0,20})?(secret|access).{0,20}['\"]?[A-Za-z0-9/+=]{40}"),
    ),
    (
        "generic_token",
        re.compile(r"(?i)(api|secret|token|key)[^\r\n]{0,8}['\"]?[A-Za-z0-9]{20,}"),
    ),
    (
        "private_key",
        re.compile(r"-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----"),
    ),
)

TARGET_PREFIXES = ("src/", "app/", "services/", "lib/")


@dataclass(slots=True)
class Finding:
    kind: str
    file: str
    line: int
    snippet: str
    pattern: str


def run(cmd: Sequence[str]) -> str:
    result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command {' '.join(cmd)} failed: {result.stderr.decode('utf-8', 'ignore')}"
        )
    return result.stdout.decode("utf-8", "ignore")


def changed_files(base: str | None, target: str | None, include_untracked: bool) -> list[str]:
    args = ["git", "diff", "--name-only"]
    if base is not None and target is not None:
        args.append(f"{base}..{target}")
    elif base is not None:
        args.append(base)
    output = run(args)
    candidates = {line.strip() for line in output.splitlines() if line.strip()}
    if include_untracked:
        status = run(["git", "status", "--porcelain"])
        for line in status.splitlines():
            if line.startswith("?? "):
                candidates.add(line[3:].strip())

    expanded: set[str] = set()
    for rel in candidates:
        if not rel:
            continue
        path = Path(rel)
        if path.is_dir():
            try:
                extra = run([
                    "git",
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    rel,
                ])
            except RuntimeError:
                extra = ""
            extra_paths = [line.strip() for line in extra.splitlines() if line.strip()]
            if not extra_paths:
                extra_paths = [str(p) for p in path.rglob("*") if p.is_file()]
            expanded.update(extra_paths)
        else:
            expanded.add(rel)

    return sorted(expanded)


def changed_line_numbers(path: str, base: str | None, target: str | None) -> set[int]:
    args = ["git", "diff", "--unified=0"]
    if base is not None and target is not None:
        args.append(f"{base}..{target}")
    elif base is not None:
        args.append(base)
    args.extend(["--", path])
    output = run(args)
    numbers: set[int] = set()
    for line in output.splitlines():
        if line.startswith("@@"):
            # Example: @@ -10,0 +11,5 @@
            try:
                hunk = line.split("+")[1].split(" ")[0]
            except IndexError:
                continue
            if "," in hunk:
                start, length = hunk.split(",", 1)
                start_line = int(start)
                length_int = int(length)
            else:
                start_line = int(hunk)
                length_int = 1
            for offset in range(length_int or 1):
                numbers.add(start_line + offset)
    return numbers


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []


def scan_realness(path: Path, lines: set[int]) -> Iterable[Finding]:
    rows = read_lines(path)
    for idx in sorted(lines):
        if idx <= 0 or idx > len(rows):
            continue
        text = rows[idx - 1]
        for kind, pattern in REALNESS_PATTERNS:
            if pattern.search(text):
                yield Finding(kind="realness", file=str(path), line=idx, snippet=text.strip(), pattern=kind)


def scan_secrets(path: Path, lines: set[int]) -> Iterable[Finding]:
    rows = read_lines(path)
    for idx in sorted(lines):
        if idx <= 0 or idx > len(rows):
            continue
        text = rows[idx - 1]
        for kind, pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                snippet = match.group(0)
                yield Finding(kind="secret", file=str(path), line=idx, snippet=snippet, pattern=kind)


def should_inspect(path: str) -> bool:
    return path.startswith(TARGET_PREFIXES)


def build_report(
    base: str | None,
    target: str | None,
    include_untracked: bool,
    json_path: Path | None,
) -> dict:
    files = changed_files(base, target, include_untracked)
    findings: list[dict] = []
    errors: list[str] = []

    for rel in files:
        if not should_inspect(rel):
            continue
        path = Path(rel)
        try:
            lines = changed_line_numbers(rel, base, target)
        except RuntimeError as exc:
            errors.append(f"diff_failed:{rel}:{exc}")
            continue
        if not lines:
            # for new files git diff --unified=0 может не дать строк; сканируем весь файл
            rows = read_lines(path)
            lines = set(range(1, len(rows) + 1))
        for finding in scan_realness(path, lines):
            findings.append(asdict(finding))
        for finding in scan_secrets(path, lines):
            findings.append(asdict(finding))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "target": target,
        "files_scanned": files,
        "findings": findings,
        "errors": errors,
    }

    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Realness & secrets scanning helper")
    parser.add_argument("--base", dest="base", help="Базовый ревизионный указатель", default=None)
    parser.add_argument("--target", dest="target", help="Целевой ревизионный указатель", default=None)
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Добавлять непроиндексированные файлы",
    )
    parser.add_argument("--output", dest="output", help="Путь к JSON-отчёту", default=None)
    args = parser.parse_args(argv)

    try:
        report = build_report(args.base, args.target, args.include_untracked, Path(args.output) if args.output else None)
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stdout)
        return 2

    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

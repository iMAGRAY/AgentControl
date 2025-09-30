#!/usr/bin/env python3
"""Единый CLI для управления GPT-5 Codex SDK."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> int:
    proc = subprocess.run(command)
    return proc.returncode


def cmd_verify(args: argparse.Namespace) -> int:
    return run([str(ROOT / "scripts" / "verify.sh")])


def cmd_review(args: argparse.Namespace) -> int:
    script = str(ROOT / "scripts" / "review.sh")
    if args.base:
        return run(["env", f"REVIEW_BASE_REF={args.base}", script])
    return run([script])


def cmd_doctor(args: argparse.Namespace) -> int:
    return run([str(ROOT / "scripts" / "doctor.sh")])


def cmd_status(args: argparse.Namespace) -> int:
    return run([str(ROOT / "scripts" / "status.sh")])


def cmd_qa(args: argparse.Namespace) -> int:
    if cmd_verify(args) != 0:
        return 1
    return cmd_review(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sdk", description="GPT-5 Codex SDK helper")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="Запустить make verify")
    verify.set_defaults(func=cmd_verify)

    review = sub.add_parser("review", help="Запустить make review")
    review.add_argument("--base", help="Базовый коммит для diff", default=None)
    review.set_defaults(func=cmd_review)

    doctor = sub.add_parser("doctor", help="Проверка окружения и зависимостей")
    doctor.set_defaults(func=cmd_doctor)

    status = sub.add_parser("status", help="make status")
    status.set_defaults(func=cmd_status)

    qa = sub.add_parser("qa", help="verify -> review")
    qa.add_argument("--base", help="Базовый коммит для review", default=None)
    qa.set_defaults(func=cmd_qa)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

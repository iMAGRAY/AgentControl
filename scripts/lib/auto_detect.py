#!/usr/bin/env python3
"""Автоматическое определение команд для разных стеков.

Скрипт печатает shell-скрипт, который дополняет переменные SDK_*_COMMANDS,
если в config/commands.sh оставлены значения по умолчанию.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path


def wrap(condition: str, command: str, skip: str) -> str:
    """Сформировать безопасную конструкцию if/else."""

    skip_quoted = shlex.quote(skip)
    return f"if {condition}; then {command}; else echo {skip_quoted}; fi"


def detect_node(root: Path, result: dict) -> None:
    package_json = root / "package.json"
    if not package_json.exists():
        return
    condition = "[ -f package.json ] && command -v npm >/dev/null 2>&1"
    result["dev"].append(
        wrap(condition, "npm install", "skip npm install (package.json/npm not available)")
    )
    lint_cmd = "npm run lint --if-present"
    test_cmd = "npm run test --if-present"
    build_cmd = "npm run build --if-present"

    result["verify"].append(wrap(condition, lint_cmd, "skip npm lint"))
    result["verify"].append(wrap(condition, test_cmd, "skip npm test"))
    result["review_linters"].append(wrap(condition, lint_cmd, "skip npm lint"))
    result["ship"].append(wrap(condition, build_cmd, "skip npm build"))
    result.setdefault("test_candidates", []).append(wrap(condition, test_cmd, "skip npm test"))

    coverage_file = root / "coverage" / "lcov.info"
    if coverage_file.exists():
        result.setdefault("coverage_candidates", []).append(str(coverage_file.relative_to(root)))


def detect_poetry(root: Path, result: dict) -> bool:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return False

    try:
        pyproject_text = pyproject.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False

    if "tool.poetry" not in pyproject_text:
        return False

    condition = "[ -f pyproject.toml ] && command -v poetry >/dev/null 2>&1"
    result["dev"].append(
        wrap(condition, "poetry install", "skip poetry install (missing poetry)")
    )
    pytest_cmd = "poetry run pytest"
    result["verify"].append(wrap(condition, pytest_cmd, "skip pytest (poetry)") )
    result.setdefault("test_candidates", []).append(
        wrap(condition, pytest_cmd, "skip pytest (poetry)")
    )

    if "[tool.ruff" in pyproject_text or (root / "ruff.toml").exists():
        result["review_linters"].append(
            wrap(condition, "poetry run ruff check", "skip ruff (poetry)")
        )

    coverage_xml = root / "coverage.xml"
    if coverage_xml.exists():
        result.setdefault("coverage_candidates", []).append(str(coverage_xml.relative_to(root)))

    result["ship"].append(wrap(condition, "poetry build", "skip poetry build"))
    return True


def detect_python_generic(root: Path, result: dict) -> None:
    requirements = root / "requirements.txt"
    requirements_text = ""
    if requirements.exists():
        condition = "[ -f requirements.txt ] && command -v pip >/dev/null 2>&1"
        result["dev"].append(
            wrap(condition, "pip install -r requirements.txt", "skip pip install (requirements/pip missing)")
        )
        try:
            requirements_text = requirements.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            requirements_text = ""

    pyproject = root / "pyproject.toml"
    pyproject_text = ""
    if pyproject.exists():
        try:
            pyproject_text = pyproject.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pyproject_text = ""

    pytest_cond = "command -v pytest >/dev/null 2>&1"
    has_tests_dir = (root / "tests").exists()
    if has_tests_dir or "pytest" in requirements_text or "pytest" in pyproject_text:
        result["verify"].append(wrap(pytest_cond, "pytest", "skip pytest (not installed)"))
        result.setdefault("test_candidates", []).append(
            wrap(pytest_cond, "pytest", "skip pytest (not installed)")
        )

    if "ruff" in requirements_text or "[tool.ruff" in pyproject_text or (root / "ruff.toml").exists():
        result["review_linters"].append(
            wrap("command -v ruff >/dev/null 2>&1", "ruff check", "skip ruff (not installed)")
        )
    elif "flake8" in requirements_text or "flake8" in pyproject_text:
        result["review_linters"].append(
            wrap("command -v flake8 >/dev/null 2>&1", "flake8", "skip flake8 (not installed)")
        )

    coverage_xml = root / "coverage.xml"
    if coverage_xml.exists():
        result.setdefault("coverage_candidates", []).append(str(coverage_xml.relative_to(root)))


def detect_go(root: Path, result: dict) -> None:
    if not (root / "go.mod").exists():
        return
    condition = "[ -f go.mod ] && command -v go >/dev/null 2>&1"
    result["dev"].append(wrap(condition, "go mod download", "skip go mod download"))
    go_test = "go test ./..."
    result["verify"].append(wrap(condition, go_test, "skip go test"))
    result.setdefault("test_candidates", []).append(wrap(condition, go_test, "skip go test"))
    result["review_linters"].append(
        wrap(condition + " && command -v golangci-lint >/dev/null 2>&1", "golangci-lint run", "skip golangci-lint")
    )


def detect_rust(root: Path, result: dict) -> None:
    if not (root / "Cargo.toml").exists():
        return
    condition = "[ -f Cargo.toml ] && command -v cargo >/dev/null 2>&1"
    result["dev"].append(wrap(condition, "cargo fetch", "skip cargo fetch"))
    cargo_test = "cargo test"
    result["verify"].append(wrap(condition, cargo_test, "skip cargo test"))
    result.setdefault("test_candidates", []).append(wrap(condition, cargo_test, "skip cargo test"))
    result["review_linters"].append(
        wrap(condition + " && command -v cargo >/dev/null 2>&1", "cargo fmt -- --check", "skip cargo fmt")
    )


def build_snippet(root: Path) -> str:
    result: dict[str, list[str] | str] = {
        "dev": [],
        "verify": [],
        "ship": [],
        "review_linters": [],
        "test_candidates": [],
        "coverage_candidates": [],
    }

    detect_node(root, result)
    poetry_used = detect_poetry(root, result)
    if not poetry_used:
        detect_python_generic(root, result)
    detect_go(root, result)
    detect_rust(root, result)

    lines: list[str] = []
    for key in ("dev", "verify", "ship", "review_linters"):
        values = result.get(key, [])
        if not values:
            continue
        array_name = {
            "dev": "SDK_DEV_COMMANDS",
            "verify": "SDK_VERIFY_COMMANDS",
            "ship": "SDK_SHIP_COMMANDS",
            "review_linters": "SDK_REVIEW_LINTERS",
        }[key]
        joined = " ".join(shlex.quote(v) for v in values)  # type: ignore[arg-type]
        lines.append(f"if [[ ${{#{array_name}[@]}} -eq 0 ]]; then")
        lines.append(f"  {array_name}=({joined})")
        lines.append("fi")

    test_candidates = result.get("test_candidates", [])
    if test_candidates:
        test_cmd = test_candidates[0]
        lines.append("if [[ -z \"${SDK_TEST_COMMAND:-}\" ]]; then")
        lines.append(f"  SDK_TEST_COMMAND={shlex.quote(test_cmd)}")
        lines.append("fi")

    coverage_candidates = result.get("coverage_candidates", [])
    if coverage_candidates:
        cov = coverage_candidates[0]
        lines.append("if [[ -z \"${SDK_COVERAGE_FILE:-}\" ]]; then")
        lines.append(f"  SDK_COVERAGE_FILE={shlex.quote(cov)}")
        lines.append("fi")

    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    root = Path(sys.argv[1]).resolve()
    snippet = build_snippet(root)
    if snippet:
        print(snippet)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib import auto_detect


def snippet_lines(snippet: str) -> list[str]:
    return [line.strip() for line in snippet.splitlines() if line.strip()]


def test_prefers_yarn_over_npm(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "yarn.lock").write_text("", encoding="utf-8")
    snippet = auto_detect.build_snippet(tmp_path)
    lines = snippet_lines(snippet)
    assert any("yarn install" in line for line in lines)
    assert all("npm install" not in line for line in lines)


def test_pipenv_detection(tmp_path: Path):
    (tmp_path / "Pipfile").write_text("[[source]]\n", encoding="utf-8")
    snippet = auto_detect.build_snippet(tmp_path)
    lines = snippet_lines(snippet)
    assert any("pipenv install" in line for line in lines)
    assert any("pipenv run pytest" in line for line in lines)


def test_gradle_detection(tmp_path: Path):
    (tmp_path / "build.gradle").write_text("apply plugin: 'java'\n", encoding="utf-8")
    snippet = auto_detect.build_snippet(tmp_path)
    lines = snippet_lines(snippet)
    assert any("gradle build" in line or "gradlew" in line for line in lines)


def test_coverage_candidate(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    coverage_dir = tmp_path / "coverage"
    coverage_dir.mkdir()
    (coverage_dir / "lcov.info").write_text("TN:\n", encoding="utf-8")
    snippet = auto_detect.build_snippet(tmp_path)
    assert "SDK_COVERAGE_FILE" in snippet

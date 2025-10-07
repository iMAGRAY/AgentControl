from __future__ import annotations

import shutil
from pathlib import Path

from agentcontrol.app.extension import integrity


def test_extension_integrity_success() -> None:
    summary = integrity.verify_extensions()
    assert summary.status == "ok"
    assert all(report.status == "ok" for report in summary.extensions)
    assert summary.packaging_issues == []


def test_extension_integrity_detects_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "extensions"
    shutil.copytree(integrity.DEFAULT_EXTENSIONS_ROOT, root)
    target = root / "auto_docs" / "README.md"
    target.write_text("# mutated\n", encoding="utf-8")

    summary = integrity.verify_extensions(root=root, sources_file=None, project_root=tmp_path)
    status_map = {report.name: report.status for report in summary.extensions}

    assert summary.status == "error"
    assert status_map["auto_docs"] == "mismatch"


def test_extension_packaging_banned_path(tmp_path: Path) -> None:
    sources = tmp_path / "SOURCES.txt"
    sources.write_text(
        "\n".join(
            [
                "examples/extensions/auto_docs/manifest.json",
                "examples/extensions/auto_docs/extension.sha256",
                "examples/extensions/auto_perf/extension.sha256",
                ".test_place/tmp",
            ]
        ),
        encoding="utf-8",
    )

    summary = integrity.verify_extensions(
        sources_file=sources,
        project_root=integrity.DEFAULT_PROJECT_ROOT,
    )

    assert summary.status == "error"
    assert any(".test_place" in issue for issue in summary.packaging_issues)

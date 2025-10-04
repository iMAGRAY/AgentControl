from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/cache.py").resolve()


def run_cache(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=merged_env,
    )


def test_cache_add_and_list(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    wheel = tmp_path / "agentcontrol-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"test")

    result = run_cache(["--dest", str(cache_dir), "add", str(wheel)])
    assert result.returncode == 0
    assert (cache_dir / wheel.name).exists()

    result = run_cache(["--dest", str(cache_dir), "list", "--json"])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["artifacts"][0]["name"] == wheel.name


def test_cache_verify_handles_empty(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    result = run_cache(["--dest", str(cache_dir), "verify"])
    assert result.returncode == 0
    assert "No wheel" in result.stdout

from __future__ import annotations

from datetime import datetime

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib import deps_checker


def test_deps_checker_generated_at_iso(tmp_path):
    report = deps_checker.collect(tmp_path)
    generated = report["generated_at"]
    parsed = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.year >= 2025

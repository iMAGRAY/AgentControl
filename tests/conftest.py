from __future__ import annotations

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SANDBOX_HOME = ROOT / ".test_place" / "global-home"
os.environ.setdefault("AGENTCONTROL_HOME", str(SANDBOX_HOME))
SANDBOX_HOME.mkdir(parents=True, exist_ok=True)
PYTEST_TEMP = Path(os.environ.get("PYTEST_DEBUG_TEMPROOT", "/tmp/agentcontrol-pytest")).resolve()
os.environ.setdefault("PYTEST_DEBUG_TEMPROOT", str(PYTEST_TEMP))
PYTEST_TEMP.mkdir(parents=True, exist_ok=True)
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

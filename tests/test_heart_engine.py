from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.agents import heart_engine


def test_heart_engine_build_and_query(tmp_path: Path):
    cfg = heart_engine.load_config()
    cfg = {
        **cfg,
        "index_dir": "context/heart_test",
        "include_globs": ["README.md"],
        "exclude_globs": [],
        "top_k": 3,
        "max_results": 3,
    }
    heart_engine.build_index(cfg)
    index_dir = (Path(__file__).resolve().parents[1] / cfg["index_dir"]).resolve()
    assert index_dir.exists()
    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["chunks"] > 0
    results = heart_engine.query_chunks(cfg, "roadmap")
    assert isinstance(results, list)
    assert results
    assert any("README" in item["path"] for item in results)

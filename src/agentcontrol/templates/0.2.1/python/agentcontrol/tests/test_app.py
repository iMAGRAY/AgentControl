from __future__ import annotations

from src import app


def test_main_returns_greeting() -> None:
    assert app.main() == "hello-agentcontrol"

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from agentcontrol.domain.docs.editor import ENGINE
from agentcontrol.domain.docs.value_objects import InsertionPolicy

CARRIAGE_RETURN = "\r"


@settings(max_examples=50)
@given(content=st.text(alphabet=st.characters(blacklist_characters=CARRIAGE_RETURN)))
def test_managed_region_roundtrip(content: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "region.md"
        ENGINE.apply(target, {"alpha": content})
        result = ENGINE.read(target, "alpha")
        expected = content.strip("\n") if content else ""
        assert result == expected


@settings(max_examples=100)
@given(
    contents=st.lists(
        st.one_of(st.text(alphabet=st.characters(blacklist_characters=CARRIAGE_RETURN)), st.none()),
        min_size=1,
        max_size=5,
    )
)
def test_managed_region_sequence(contents: list[str | None]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "doc.md"
        state: str | None = None
        for item in contents:
            ENGINE.apply(target, {"alpha": item})
            state = item if item is None or isinstance(item, str) else state
        result = ENGINE.read(target, "alpha")
        if state is None:
            assert result is None
        else:
            assert result == state.strip("\n")


@settings(max_examples=50)
@given(
    content=st.text(alphabet=st.characters(blacklist_characters=CARRIAGE_RETURN)),
    heading=st.text(),
)
def test_insertion_policies_anchor(content: str, heading: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "doc.md"
        target.write_text(f"# {heading}\n\nBody\n", encoding="utf-8")
        policy = InsertionPolicy(kind="after_heading", value=f"# {heading}")
        ENGINE.apply(target, {"alpha": (content, policy)})
        text = target.read_text(encoding="utf-8")
        assert "agentcontrol:start:alpha" in text

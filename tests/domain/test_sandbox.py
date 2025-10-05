from __future__ import annotations

from pathlib import Path

from agentcontrol.domain.sandbox import SandboxAggregate, SandboxContext


def test_sandbox_aggregate_create_and_remove(tmp_path: Path) -> None:
    context = SandboxContext(project_root=tmp_path)
    aggregate = SandboxAggregate(context)

    def materialise(target: Path) -> None:
        (target / "README.md").write_text("sandbox", encoding="utf-8")

    descriptor = aggregate.create("sandbox", materialise, metadata={"mode": "test"})
    assert descriptor.path.exists()
    entries = list(aggregate.list())
    assert [entry.sandbox_id for entry in entries] == [descriptor.sandbox_id]

    aggregate.remove(descriptor.sandbox_id)
    assert not descriptor.path.exists()
    assert list(aggregate.list()) == []


def test_sandbox_purge_all(tmp_path: Path) -> None:
    aggregate = SandboxAggregate(SandboxContext(project_root=tmp_path))

    def materialise(target: Path) -> None:
        (target / "marker.txt").write_text("ok", encoding="utf-8")

    first = aggregate.create("sandbox", materialise)
    second = aggregate.create("sandbox", materialise)
    assert first.path.exists() and second.path.exists()

    removed = list(aggregate.purge_all())
    assert {item.sandbox_id for item in removed} == {first.sandbox_id, second.sandbox_id}
    assert not first.path.exists()
    assert not second.path.exists()
    assert list(aggregate.list()) == []

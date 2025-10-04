"""Plugin loading utilities for agentcall."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Callable, Iterable, Protocol

from agentcontrol.settings import RuntimeSettings


@dataclass(frozen=True)
class PluginContext:
    settings: RuntimeSettings


class SubparserBuilder(Protocol):  # pragma: no cover
    def __call__(self, parser, context: PluginContext) -> Callable[[object], int]:
        ...


class PluginRegistrar(Protocol):  # pragma: no cover
    def add_subparser(self, name: str, help_text: str, builder: SubparserBuilder) -> None:
        ...


class AgentcallPlugin(Protocol):  # pragma: no cover
    name: str

    def register(self, registrar: PluginRegistrar, context: PluginContext) -> None:
        ...


def iter_entry_points() -> Iterable[metadata.EntryPoint]:
    return metadata.entry_points().select(group="agentcontrol.plugins")


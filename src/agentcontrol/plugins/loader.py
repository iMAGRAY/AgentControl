"""Runtime plugin loading for agentcall."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, ItemsView

from agentcontrol.plugins import PluginContext, PluginRegistrar, SubparserBuilder, iter_entry_points
from agentcontrol.settings import RuntimeSettings


@dataclass
class RegisteredCommand:
    name: str
    help: str
    builder: SubparserBuilder


class Registry(PluginRegistrar):
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._commands: Dict[str, RegisteredCommand] = {}

    def add_subparser(self, name: str, help_text: str, builder: SubparserBuilder) -> None:
        if name in self._commands:
            raise ValueError(f"Plugin command {name} already registered")
        self._commands[name] = RegisteredCommand(name=name, help=help_text, builder=builder)

    @property
    def settings(self) -> RuntimeSettings:
        return self._settings

    def items(self) -> ItemsView[str, RegisteredCommand]:
        return self._commands.items()


def load_plugins(settings: RuntimeSettings) -> Registry:
    registry = Registry(settings)
    context = PluginContext(settings=settings)
    for entry_point in iter_entry_points():
        plugin = entry_point.load()
        register = getattr(plugin, "register", None)
        if callable(register):
            register(registry, context)
    return registry

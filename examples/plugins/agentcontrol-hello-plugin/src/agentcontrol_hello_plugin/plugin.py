from __future__ import annotations

import argparse
from typing import Callable

from agentcontrol.plugins import PluginContext, PluginRegistrar


class HelloPlugin:
    name = "hello"

    def register(self, registrar: PluginRegistrar, context: PluginContext) -> None:
        def builder(parser: argparse.ArgumentParser, ctx: PluginContext) -> Callable[[argparse.Namespace], int]:
            parser.add_argument("--name", default="Agent", help="Name to greet")

            def handler(args: argparse.Namespace) -> int:
                print(f"Hello, {args.name}! AgentControl version {ctx.settings.cli_version}")
                return 0

            return handler

        registrar.add_subparser("hello-plugin", "Say hello from a plugin", builder)


def register(registrar: PluginRegistrar, context: PluginContext) -> None:
    HelloPlugin().register(registrar, context)

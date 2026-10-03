"""Plugins: what the command line composes around the engine.

A plugin is an entry point in the ``gnode.plugins`` group that returns a ``Plugin``: the
standard node types, the file facts reader, the image readers and writers bodies use,
the routes gnode can call and the provider adapters that serve them. The engine imports
no plugin by name; ``load_plugins`` merges whatever is installed.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from gnode.workflow.host import CapabilityHandler
from gnode.workflow.registry import BuiltinType
from gnode.workflow.routes import RouteTable
from gnode.workflow.values import FactsReader

GROUP = "gnode.plugins"


@dataclass(frozen=True)
class Plugin:
    name: str
    builtins: Sequence[BuiltinType] = ()
    facts_reader: FactsReader | None = None
    routes: RouteTable = field(default_factory=RouteTable)
    #: Built when a run is live: reads credentials, returns the handlers it can serve.
    capabilities: Callable[[], Mapping[str, CapabilityHandler]] | None = None


@dataclass(frozen=True)
class Composition:
    """Every installed plugin, merged."""

    plugins: tuple[Plugin, ...]

    @property
    def builtins(self) -> list[BuiltinType]:
        return [builtin for plugin in self.plugins for builtin in plugin.builtins]

    @property
    def facts_reader(self) -> FactsReader | None:
        for plugin in self.plugins:
            if plugin.facts_reader is not None:
                return plugin.facts_reader
        return None

    @property
    def routes(self) -> RouteTable:
        merged = RouteTable()
        for plugin in self.plugins:
            merged = merged.merged(plugin.routes)
        return merged

    def capabilities(self) -> dict[str, CapabilityHandler]:
        handlers: dict[str, CapabilityHandler] = {}
        for plugin in self.plugins:
            if plugin.capabilities is not None:
                handlers.update(plugin.capabilities())
        return handlers


def load_plugins() -> Composition:
    plugins = []
    for entry in sorted(importlib.metadata.entry_points(group=GROUP), key=lambda e: e.name):
        factory = entry.load()
        plugin = factory() if callable(factory) else factory
        if not isinstance(plugin, Plugin):
            raise TypeError(f"gnode plugin {entry.name} returned {type(plugin).__name__}")
        plugins.append(plugin)
    return Composition(tuple(plugins))


__all__ = ["GROUP", "Composition", "Plugin", "load_plugins"]

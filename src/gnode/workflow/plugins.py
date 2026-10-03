"""Plugins: what the command line composes around the engine.

A plugin is an entry point in the ``gnode.plugins`` group that returns a ``Plugin``: the
standard node types, the file facts reader, the image readers and writers bodies use,
the routes gnode can call, the provider adapters that serve them, and the workflows it
publishes for ``gnode run <id>``. The engine imports
no plugin by name; ``load_plugins`` merges whatever is installed.
"""

from __future__ import annotations

import importlib.metadata
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from gnode.workflow.host import CapabilityHandler
from gnode.workflow.registry import BuiltinType
from gnode.workflow.routes import RouteTable
from gnode.workflow.store import Store
from gnode.workflow.values import FactsReader

GROUP = "gnode.plugins"


@dataclass(frozen=True)
class Plugin:
    name: str
    builtins: Sequence[BuiltinType] = ()
    facts_reader: FactsReader | None = None
    routes: RouteTable = field(default_factory=RouteTable)
    #: Built when a run is live, given the run's store for the files calls return.
    capabilities: Callable[[Store], Mapping[str, CapabilityHandler]] | None = None
    #: Workflows it publishes, by id: each file's own ``gnode.yaml`` folder is its home.
    workflows: Mapping[str, Path] = field(default_factory=dict)
    #: Generic view templates by file kind (``image``, ``json``), for ``view: true`` on a
    #: step whose type has no view of its own.
    views: Mapping[str, Path] = field(default_factory=dict)


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

    @property
    def workflows(self) -> dict[str, Path]:
        published: dict[str, Path] = {}
        for plugin in self.plugins:
            for identifier, path in plugin.workflows.items():
                if identifier in published:
                    raise ValueError(f"two plugins publish the workflow {identifier}")
                published[identifier] = path
        return published

    @property
    def views(self) -> dict[str, Path]:
        merged: dict[str, Path] = {}
        for plugin in self.plugins:
            merged.update(plugin.views)
        return merged

    def capabilities(self, store: Store) -> dict[str, CapabilityHandler]:
        handlers: dict[str, CapabilityHandler] = {}
        for plugin in self.plugins:
            if plugin.capabilities is not None:
                handlers.update(plugin.capabilities(store))
        return handlers


def load_plugins() -> Composition:
    """Every installed plugin; ``GNODE_PLUGINS=std,...`` loads only the ones named."""

    named = os.environ.get("GNODE_PLUGINS")
    wanted = None if named is None else {name.strip() for name in named.split(",") if name.strip()}
    plugins = []
    for entry in sorted(importlib.metadata.entry_points(group=GROUP), key=lambda e: e.name):
        if wanted is not None and entry.name not in wanted:
            continue
        factory = entry.load()
        plugin = factory() if callable(factory) else factory
        if not isinstance(plugin, Plugin):
            raise TypeError(f"gnode plugin {entry.name} returned {type(plugin).__name__}")
        plugins.append(plugin)
    return Composition(tuple(plugins))


__all__ = ["GROUP", "Composition", "Plugin", "load_plugins"]

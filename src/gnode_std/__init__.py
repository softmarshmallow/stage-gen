"""gnode's standard library: the media node types workflows use by name, and file facts.

``uses: gnode/<name>@<major>`` resolves here. The engine (``gnode``) stays media-free;
this package holds what needs pictures, sound and video.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from gnode import BuiltinType, Plugin
from gnode_std.catalog import STANDARD_TYPES
from gnode_std.facts import file_facts
from gnode_std.media import BODIES
from gnode_std.pictures import register_pictures


def standard_types() -> list[BuiltinType]:
    """Every standard node type, as the registry takes them, with the bodies built so far."""

    register_pictures()
    return [
        BuiltinType(major, dataclasses.replace(spec, body=BODIES.get(spec.name)))
        for major, spec in STANDARD_TYPES
    ]


def plugin() -> Plugin:
    """The ``gnode.plugins`` entry point: standard types, file facts, picture helpers."""

    register_pictures()
    views = Path(__file__).resolve().parent / "views"
    return Plugin(
        name="std",
        builtins=standard_types(),
        facts_reader=file_facts,
        views={"image": views / "image.html", "json": views / "json.html"},
    )


__all__ = ["file_facts", "plugin", "standard_types"]

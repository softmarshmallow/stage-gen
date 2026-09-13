"""Compile authored sequences into the current, independently executable program."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from .catalog import empty_catalog, read_catalog
from .program import admit_program
from .syntax import parse_source
from .validation import ScenarioError


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


@dataclass(frozen=True)
class Compilation:
    program: dict[str, Any]
    source_map: dict[str, dict[str, Any]]
    source_sha256: str

    @property
    def program_bytes(self) -> bytes:
        return canonical_json(self.program)

    @property
    def program_sha256(self) -> str:
        return hashlib.sha256(self.program_bytes).hexdigest()


def compile_scenario(
    source: str,
    *,
    catalog: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
    source_name: str = "<memory>",
) -> Compilation:
    """Compile and admit v3 content without invoking a game or generating assets."""

    if source_name != "<memory>":
        path = PurePosixPath(source_name)
        if (
            not source_name
            or "\\" in source_name
            or ":" in source_name
            or path.is_absolute()
            or str(path) != source_name
            or ".." in path.parts
        ):
            raise ScenarioError("source_name must be a portable relative source identity")
    parsed = parse_source(source, source_name=source_name)
    document: dict[str, Any] = {
        "kind": "scenario-program-v3",
        "schema_version": 3,
        "scenario_id": parsed.scenario_id,
        "entry": parsed.entry or parsed.nodes[0]["id"],
        "nodes": parsed.nodes,
        "speakers": parsed.speakers,
        "facts": parsed.facts,
        "required_capabilities": parsed.requirements,
    }
    admitted = admit_program(
        document,
        read_catalog(
            empty_catalog() if catalog is None else catalog,
            {} if capabilities is None else capabilities,
        ),
    )
    return Compilation(
        program=admitted,
        source_map=parsed.locations,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
    )

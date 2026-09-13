"""Standalone authoring for the Godot-owned, game-invoked Scenario contract."""

from .catalog import Catalog, empty_catalog, read_catalog
from .compiler import Compilation, canonical_json, compile_scenario
from .content import build_content_package, verify_content_package
from .program import admit_program
from .syntax import parse_source
from .validation import ScenarioError, validate_capabilities

__all__ = [
    "Catalog",
    "Compilation",
    "ScenarioError",
    "admit_program",
    "build_content_package",
    "canonical_json",
    "compile_scenario",
    "empty_catalog",
    "parse_source",
    "read_catalog",
    "validate_capabilities",
    "verify_content_package",
]

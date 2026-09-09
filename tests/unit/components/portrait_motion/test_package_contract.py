"""Public-package ownership checks, usable unchanged in an ordinary installed wheel."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from stage_gen.components import portrait_motion

REQUIRED = {
    "MotionState",
    "PlaybackSegment",
    "PortraitMotionSpec",
    "PortraitMotionResult",
    "PortraitMotionHandlers",
    "PortraitMotionHost",
    "add_portrait_motion_nodes",
}


def component_root() -> Path:
    assert portrait_motion.__file__ is not None
    return Path(portrait_motion.__file__).resolve().parent


def test_public_component_surface_is_complete_without_loading_experiments() -> None:
    assert set(portrait_motion.__all__) >= REQUIRED
    assert len(set(portrait_motion.__all__)) == len(portrait_motion.__all__)
    for name in portrait_motion.__all__:
        assert getattr(portrait_motion, name) is not None
    assert callable(portrait_motion.add_portrait_motion_nodes)


@pytest.mark.parametrize(
    "module",
    [
        "models",
        "processing",
        "playback",
        "review",
        "nodes",
        "storage",
    ],
)
def test_capability_modules_are_ordinary_package_imports(module: str) -> None:
    loaded = importlib.import_module(f"stage_gen.components.portrait_motion.{module}")
    assert loaded.__file__ is not None
    assert Path(loaded.__file__).resolve().parent == component_root()
    assert loaded.__package__ == "stage_gen.components.portrait_motion"


def test_component_imports_respect_provider_and_composition_boundaries() -> None:
    forbidden = (
        "stage_gen.recipes",
        "stage_gen.orchestration",
        "stage_gen.interfaces",
        "gnode.providers",
        "repainting",
        "native_preview",
        "four_panel",
        "vlm_",
        "transfer_trial",
        "httpx",
        "openai",
        "requests",
    )
    violations: list[str] = []
    for path in sorted(component_root().glob("*.py")):
        tree = ast.parse(path.read_text(), filename=path.name)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name.startswith(forbidden):
                    violations.append(f"{path.name}:{getattr(node, 'lineno', 0)}:{name}")
                if name.startswith("gnode."):
                    violations.append(
                        f"{path.name}:{getattr(node, 'lineno', 0)}:private gnode surface {name}"
                    )
    assert not violations, violations


def test_component_has_no_checkout_or_experiment_execution_dependency() -> None:
    forbidden = (
        "spikes/",
        ".cache/uv",
        "/Users/",
        "sys.path",
        "sys.modules",
        "importlib.util",
        "native_preview",
        "four_panel_analyze",
        "transfer_trial",
        "subprocess",
    )
    violations: list[str] = []
    for path in sorted(component_root().glob("*.py")):
        source = path.read_text()
        violations.extend(f"{path.name}: {token}" for token in forbidden if token in source)
    assert not violations, violations

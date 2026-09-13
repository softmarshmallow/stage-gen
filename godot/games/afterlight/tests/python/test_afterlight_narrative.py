"""Afterlight's playable episode follows its genuine authored Scenario source."""

import importlib.util
from pathlib import Path


def test_compiled_episode_is_current() -> None:
    path = Path(__file__).parents[2] / "tools/compile_narrative.py"
    spec = importlib.util.spec_from_file_location("afterlight_compile", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.compile_narrative(check=True)

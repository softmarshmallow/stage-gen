"""Procedural example content uses the same public compiler as consuming games."""

import importlib.util
from pathlib import Path


def test_compiled_examples_are_current() -> None:
    path = Path(__file__).parents[2] / "tools/compile_examples.py"
    spec = importlib.util.spec_from_file_location("scenario_examples_compile", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.compile_examples(check=True)

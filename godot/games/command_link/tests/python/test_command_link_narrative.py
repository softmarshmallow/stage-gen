"""The playable mission is built from its owned source and installed contracts."""

import importlib.util
from pathlib import Path


def test_compiled_mission_is_current() -> None:
    path = Path(__file__).parents[2] / "tools/compile_mission.py"
    spec = importlib.util.spec_from_file_location("command_link_compile", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.compile_mission(check=True)

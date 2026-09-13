"""An actual wheel consumer must not see the source checkout or game dependencies."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import build
import pydantic
import pytest

from scenario_authoring.compatibility.v2 import ScenarioDeclarations, TrackDeclaration

from .fixtures import declarations_value

PACKAGE = Path(__file__).resolve().parents[2]


def test_narrative_declarations_require_no_game_or_generation_metadata() -> None:
    declarations = ScenarioDeclarations.model_validate(declarations_value())
    assert declarations.scenario_id == "last_class"
    assert TrackDeclaration(track_id="room_tone").track_id == "room_tone"
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ScenarioDeclarations.model_validate(declarations_value(game_id="unneeded_game"))


def test_source_dependency_closure_is_standalone() -> None:
    forbidden = {"stage_gen", "gnode", "demo_game_tools", "demo_game_collection"}
    for path in (PACKAGE / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imported = {node.module.split(".")[0]}
            else:
                continue
            assert not imported & forbidden, f"{path.name} imports {imported & forbidden}"


def test_built_wheel_compiles_without_the_checkout_or_game_packages(tmp_path: Path) -> None:
    wheel = build.ProjectBuilder(str(PACKAGE)).build("wheel", str(tmp_path / "dist"))
    # -I ignores PYTHONPATH/cwd; -S disables editable-install .pth files. The only
    # extra search roots are the wheel and the installed third-party dependencies.
    dependencies = Path(pydantic.__file__).resolve().parent.parent
    script = """
import importlib.util
import json
import sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(1, sys.argv[2])
for name in ("stage_gen", "gnode", "demo_game_tools", "demo_game_collection"):
    assert importlib.util.find_spec(name) is None, name
import scenario_authoring
from scenario_authoring.compatibility.v2 import (
    ScenarioDeclarations, admit_scenario, compile_scenario, parse_scenario,
)
assert ".whl/" in scenario_authoring.__file__
declarations = ScenarioDeclarations.model_validate({
    "scenario_id": "arrival", "entry": "start",
    "cast": [{"actor_id": "guide"}], "stages": [{"stage_id": "station"}],
    "endings": [{"outcome_id": "finished", "label": "Finished"}],
})
program = compile_scenario(declarations, parse_scenario(
    'label start:\\n    stage station\\n    guide "Welcome."\\n    end finished\\n'
))
report = admit_scenario(declarations, program)
assert report.admitted
current = scenario_authoring.compile_scenario(
    'scenario standalone\\n@hello\\n"Welcome."\\n@done\\nend complete\\n'
)
assert current.program["kind"] == "scenario-program-v3"
assert current.program["nodes"][0]["id"] == "hello"
print(json.dumps({"scenario_id": report.scenario_id, "ending": report.witnesses[0].outcome_id}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script, wheel, str(dependencies)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {"scenario_id": "arrival", "ending": "finished"}

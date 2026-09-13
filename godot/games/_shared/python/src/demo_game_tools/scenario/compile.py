"""Keep the supported production envelope while the standalone compiler owns syntax."""

from __future__ import annotations

from scenario_authoring.compatibility.v2 import (
    RawBlock,
    ScenarioAdmissionReport,
)
from scenario_authoring.compatibility.v2 import (
    admit_scenario as admit_narrative,
)
from scenario_authoring.compatibility.v2 import (
    compile_scenario as compile_narrative,
)

from .models import ScenarioDeclarations, ScenarioProgram


def compile_scenario(
    declarations: ScenarioDeclarations, raw_blocks: tuple[RawBlock, ...]
) -> ScenarioProgram:
    compiled = compile_narrative(declarations.narrative(), raw_blocks)
    return ScenarioProgram(
        game_id=declarations.game_id,
        scenario_id=declarations.scenario_id,
        display_name=declarations.display_name,
        revision=declarations.revision,
        script_sha256=declarations.script_sha256,
        entry=declarations.entry,
        cast=list(declarations.cast),
        stages=list(declarations.stages),
        tracks=list(declarations.tracks),
        flags=list(declarations.flags),
        endings=list(declarations.endings),
        blocks=list(compiled.blocks),
    )


def admit_scenario(
    declarations: ScenarioDeclarations, program: ScenarioProgram
) -> ScenarioAdmissionReport:
    return admit_narrative(declarations.narrative(), program.narrative())

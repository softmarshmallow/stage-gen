"""Resolve one authored scenario offline: read, prove, refuse, then materialize.

The order is the point, and it is `resolve_pointclick_room`'s order: parse the
declarations, read the script and hold it to its digest, compile, and prove -
*before* anything downstream is built and long before a provider is reached. A
scenario that cannot be finished costs nothing.

The two halves are one authored member. `scenario.toml` names the script by path
and pins it with `script_sha256`, exactly as `[[references]]` pins an image, and
they are admitted together or not at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from stage_gen.components._authored_package import (
    read_digest_bound_member,
    read_package_member,
)
from stage_gen.components._game_input import (
    parse_toml_contract,
    sha256_bytes,
)
from stage_gen.components.scenario.admission import admit_scenario
from stage_gen.components.scenario.compile import compile_scenario
from stage_gen.components.scenario.models import (
    SCENARIO_DOCUMENT_NAME,
    ScenarioAdmissionReport,
    ScenarioDeclarations,
    ScenarioProgram,
)
from stage_gen.components.scenario.parser import parse_scenario

SCENARIO_RESOLUTION_VERSION = "scenario-resolution-v1"


@dataclass(frozen=True, slots=True)
class ResolvedScenario:
    """One authored scenario, proven finishable and ready to plan or play."""

    declarations: ScenarioDeclarations
    program: ScenarioProgram
    admission: ScenarioAdmissionReport
    program_bytes: bytes
    program_sha256: str

    def identity(self) -> dict[str, object]:
        """The portable record of exactly which scenario this run was planned from."""

        return {
            "schema_version": 1,
            "kind": "scenario-identity-v1",
            "game_id": self.declarations.game_id,
            "scenario_id": self.declarations.scenario_id,
            "revision": self.declarations.revision,
            "resolution_version": SCENARIO_RESOLUTION_VERSION,
            "script_sha256": self.declarations.script_sha256,
            "program_sha256": self.program_sha256,
            "reachable_states": self.admission.reachable_states,
        }


def canonical_program_json(program: ScenarioProgram) -> bytes:
    """Serialize the program with its optional fields present, not omitted.

    The repository's usual canonical form drops nulls, which is right for a
    document whose reader tolerates absence. This one is read by a consumer that
    refuses unknown *and missing* keys, so `speaker: null` has to be on the wire:
    an absent key and a null one would otherwise mean the same thing to the
    producer and different things to the reader.
    """

    return json.dumps(
        program.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def read_scenario_declarations(root: Path) -> ScenarioDeclarations:
    """Read and validate `scenario.toml`, following no symlink at any depth."""

    data = read_package_member(root, SCENARIO_DOCUMENT_NAME, label="scenario document")
    return parse_toml_contract(data, model=ScenarioDeclarations, label="scenario-v1")


def read_script_text(root: Path, declarations: ScenarioDeclarations) -> str:
    """Read the script bytes and refuse prose the author did not sign for."""

    data = read_digest_bound_member(
        root,
        declarations.script,
        expected_sha256=declarations.script_sha256,
        label="scenario script",
    )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"scenario script is not valid UTF-8: {error}") from None


def script_digest(root: Path, declarations: ScenarioDeclarations) -> str:
    """The digest the script's current bytes *would* need, for `--write-digest`.

    Authoring prose against a hand-copied hash is miserable - every save
    invalidates it - so the CLI can report and repair the digest rather than
    leaving the author to run `sha256sum` by hand.
    """

    return sha256_bytes(read_package_member(root, declarations.script, label="scenario script"))


def resolve_scenario(root: Path) -> ResolvedScenario:
    """Admit one authored scenario package, touching no provider."""

    declarations = read_scenario_declarations(root)
    script = read_script_text(root, declarations)
    program = compile_scenario(declarations, parse_scenario(script))
    admission = admit_scenario(declarations, program)
    _check_cast_profiles(root, declarations)
    program_bytes = canonical_program_json(program)
    return ResolvedScenario(
        declarations=declarations,
        program=program,
        admission=admission,
        program_bytes=program_bytes,
        program_sha256=sha256_bytes(program_bytes),
    )


def _check_cast_profiles(root: Path, declarations: ScenarioDeclarations) -> None:
    """A drawn actor names a package member, so the member has to be there.

    Admission proves the narrative; this proves the package. Without it a cast
    member pointing at a profile nobody wrote would be discovered during
    generation, which is the one place the whole contract exists to move failures
    out of.
    """

    for member in declarations.cast:
        if member.profile is None:
            continue
        try:
            read_package_member(root, member.profile, label="cast profile")
        except (OSError, ValueError) as error:
            raise ValueError(
                f"cast member `{member.actor_id}` names profile {member.profile}, "
                f"which is not a readable package member: {error}"
            ) from None


__all__ = [
    "SCENARIO_RESOLUTION_VERSION",
    "canonical_program_json",
    "ResolvedScenario",
    "read_scenario_declarations",
    "read_script_text",
    "resolve_scenario",
    "script_digest",
]

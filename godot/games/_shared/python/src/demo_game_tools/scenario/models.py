"""Existing game-owned scenario-v2 production declarations and artifact envelope.

Narrative syntax and admission belong to scenario_authoring. This adapter alone
owns game IDs, fixed input member paths, digests and media generation briefs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from scenario_authoring.compatibility.v2 import models as narrative
from scenario_authoring.compatibility.v2.models import (
    Block,
    CastMember,
    EndingDeclaration,
    FlagDeclaration,
    ScenarioAdmissionReport,
    ScenarioModel,
)
from stage_gen.components._game_input import (
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    normalized_text,
    portable_relative_path,
    unique_values,
)
from stage_gen.components.music import TrackGenerationIntent

SCENARIO_SCHEMA_VERSION = 2
SCENARIO_KIND = "scenario-v2"
SCENARIO_CATALOG_SCHEMA_VERSION = 1
SCENARIO_CATALOG_KIND = "scenario-catalog-v1"
SCENARIO_CATALOG_NAME = "scenarios/index.toml"
GAME_REFERENCE_PATTERN = r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$"


class StageDeclaration(ScenarioModel):
    stage_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    brief: str = Field(min_length=1, max_length=600)

    @field_validator("brief")
    @classmethod
    def validate_brief(cls, value: str) -> str:
        return normalized_text(value, "stage brief")


class TrackDeclaration(ScenarioModel):
    """One music identity the script can play, with how it should be produced.

    `generation` is the soundtrack component's own `TrackGenerationIntent`, not a
    second shape that means the same thing: whoever produces the track - this
    recipe, another one, or a human handing over a file - reads the same
    provider-neutral intent, and the shared prompt compiler turns it into the
    same guarantees about performance, ending and originality.
    """

    track_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    brief: str = Field(min_length=1, max_length=600)
    generation: TrackGenerationIntent

    @field_validator("brief")
    @classmethod
    def validate_brief(cls, value: str) -> str:
        return normalized_text(value, "track brief")


class ScenarioSource(ScenarioModel):
    """One catalog entry. The declarations file is derived, not authored twice."""

    scenario_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)

    @property
    def source(self) -> str:
        return f"scenarios/{self.scenario_id}.toml"


class ScenarioCatalog(ScenarioModel):
    """The retained game input catalog at `scenarios/index.toml`."""

    schema_version: Literal[1]
    kind: Literal["scenario-catalog-v1"]
    game_id: str = Field(pattern=GAME_REFERENCE_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    scenarios: list[ScenarioSource] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_closure(self) -> ScenarioCatalog:
        unique_values((entry.scenario_id for entry in self.scenarios), "catalog scenario_id")
        return self

    @property
    def scenario_ids(self) -> tuple[str, ...]:
        return tuple(entry.scenario_id for entry in self.scenarios)


class ScenarioDeclarations(ScenarioModel):
    """`scenarios/<id>.toml`: every name the script may use, and no prose."""

    schema_version: Literal[2]
    kind: Literal["scenario-v2"]
    game_id: str = Field(pattern=GAME_REFERENCE_PATTERN, max_length=96)
    scenario_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str = Field(min_length=1, max_length=96)
    revision: int = Field(ge=1)
    script: str
    script_sha256: str = Field(pattern=SHA256_PATTERN)
    entry: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    cast: list[CastMember] = Field(min_length=1, max_length=32)
    stages: list[StageDeclaration] = Field(min_length=1, max_length=32)
    tracks: list[TrackDeclaration] = Field(default_factory=list, max_length=32)
    #: Forty-eight, not thirty-two. The old number was never tested against an
    #: ensemble scene: a supper of eight with three courses and a strand each runs
    #: to nearly forty flags before anyone has answered a question. The ceiling
    #: that actually protects the proof is `MAX_REACHABLE_STATES`, and liveness
    #: projection means a flag nothing downstream reads no longer costs the search
    #: anything - so counting flag declarations was guarding the wrong quantity.
    flags: list[FlagDeclaration] = Field(default_factory=list, max_length=48)
    endings: list[EndingDeclaration] = Field(min_length=1, max_length=32)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "scenario display_name")

    @model_validator(mode="after")
    def validate_closure(self) -> ScenarioDeclarations:
        expected = f"scenarios/{self.scenario_id}.scenario"
        if portable_relative_path(self.script, "scenario script") != expected:
            raise ValueError(f"scenario script must equal {expected}")
        unique_values((member.actor_id for member in self.cast), "cast actor_id")
        unique_values((stage.stage_id for stage in self.stages), "stage_id")
        unique_values((track.track_id for track in self.tracks), "track_id")
        unique_values((flag.flag_id for flag in self.flags), "flag_id")
        unique_values((ending.outcome_id for ending in self.endings), "ending outcome_id")
        return self

    @property
    def actor_ids(self) -> frozenset[str]:
        return frozenset(member.actor_id for member in self.cast)

    @property
    def flag_ids(self) -> frozenset[str]:
        return frozenset(flag.flag_id for flag in self.flags)

    @property
    def imported_flag_ids(self) -> frozenset[str]:
        """The facts this scenario expects a case to have established before it."""

        return frozenset(flag.flag_id for flag in self.flags if flag.origin == "imported")

    @property
    def stage_ids(self) -> frozenset[str]:
        return frozenset(stage.stage_id for stage in self.stages)

    @property
    def track_ids(self) -> frozenset[str]:
        return frozenset(track.track_id for track in self.tracks)

    @property
    def outcome_ids(self) -> frozenset[str]:
        return frozenset(ending.outcome_id for ending in self.endings)

    def member(self, actor_id: str) -> CastMember | None:
        return next((member for member in self.cast if member.actor_id == actor_id), None)

    def narrative(self) -> narrative.ScenarioDeclarations:
        """Project package declarations into the independent language contract."""

        return narrative.ScenarioDeclarations(
            scenario_id=self.scenario_id,
            entry=self.entry,
            cast=list(self.cast),
            stages=[narrative.StageDeclaration(stage_id=item.stage_id) for item in self.stages],
            tracks=[narrative.TrackDeclaration(track_id=item.track_id) for item in self.tracks],
            flags=list(self.flags),
            endings=list(self.endings),
        )


class ScenarioProgram(ScenarioModel):
    """The compiled text IR: declarations plus blocks, both halves admitted together.

    This is what the runtime walks and what the proof searched. It carries the
    script's digest so a consumer can tell which exact prose it was compiled from.
    """

    schema_version: Literal[2] = 2
    kind: Literal["scenario-program-v2"] = "scenario-program-v2"
    game_id: str = Field(pattern=GAME_REFERENCE_PATTERN, max_length=96)
    scenario_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str
    revision: int = Field(ge=1)
    script_sha256: str = Field(pattern=SHA256_PATTERN)
    entry: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    cast: list[CastMember] = Field(min_length=1)
    stages: list[StageDeclaration] = Field(min_length=1)
    tracks: list[TrackDeclaration] = Field(default_factory=list)
    flags: list[FlagDeclaration] = Field(default_factory=list)
    endings: list[EndingDeclaration] = Field(min_length=1)
    blocks: list[Block] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_labels(self) -> ScenarioProgram:
        unique_values((block.label for block in self.blocks), "scenario block label")
        if self.entry not in {block.label for block in self.blocks}:
            raise ValueError(f"scenario entry {self.entry} does not name a block")
        return self

    def block(self, label: str) -> Block | None:
        return next((block for block in self.blocks if block.label == label), None)

    def narrative(self) -> narrative.ScenarioProgram:
        """Remove production-only metadata before language admission."""

        return narrative.ScenarioProgram(
            scenario_id=self.scenario_id,
            entry=self.entry,
            cast=list(self.cast),
            stages=[narrative.StageDeclaration(stage_id=item.stage_id) for item in self.stages],
            tracks=[narrative.TrackDeclaration(track_id=item.track_id) for item in self.tracks],
            flags=list(self.flags),
            endings=list(self.endings),
            blocks=list(self.blocks),
        )


__all__ = [
    "SCENARIO_CATALOG_KIND",
    "SCENARIO_CATALOG_NAME",
    "SCENARIO_CATALOG_SCHEMA_VERSION",
    "SCENARIO_KIND",
    "SCENARIO_SCHEMA_VERSION",
    "ScenarioModel",
    "StageDeclaration",
    "TrackDeclaration",
    "ScenarioSource",
    "ScenarioCatalog",
    "ScenarioDeclarations",
    "ScenarioProgram",
    "ScenarioAdmissionReport",
]

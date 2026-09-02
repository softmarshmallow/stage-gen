"""The `scenario-v2` authored contract and the program it compiles to.

Two documents, split by what the content *is*. `scenario.toml` carries everything
with a digest, a rights basis, or a generation brief - cast, stages, tracks, flags,
endings - because those are package facts. The `.scenario` script carries only
narrative, because that is the part a person writes. See
`docs/spec/game/scenario.md`.

The statement vocabulary is closed. A statement kind outside `Statement` is
refused; it is never passed through and never interpreted. Conditions are flag
tests only - a set that must hold and a set that must not - which is the single
rule that keeps a scenario provable and keeps the runtime from becoming an
interpreter.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    normalized_text,
    portable_relative_path,
    unique_values,
)
from stage_gen.components.game_soundtrack import TrackGenerationIntent

SCENARIO_SCHEMA_VERSION = 2
SCENARIO_KIND = "scenario-v2"
SCENARIO_CATALOG_SCHEMA_VERSION = 1
SCENARIO_CATALOG_KIND = "scenario-catalog-v1"
SCENARIO_CATALOG_NAME = "scenarios/index.toml"

#: Statement keywords may not be actor ids. `say` begins with a bare identifier, so
#: a cast member named `end` would make `end talked` mean two things and the file
#: would parse differently depending on which reading a parser preferred. Refused
#: at admission rather than resolved by lookahead.
RESERVED_WORDS: frozenset[str] = frozenset(
    {
        "label",
        "show",
        "hide",
        "stage",
        "play",
        "stop",
        "set",
        "menu",
        "if",
        "jump",
        "end",
        "at",
        "and",
        "not",
    }
)

#: Five staging slots, left to right across the frame. `scenario-v1` carried the
#: middle three; a supper table of eight needs more than three positions before
#: composition can carry meaning, so v2 adds the outer pair. The three-slot
#: vocabulary is a strict subset, so a v1 script's staging still reads the same -
#: what changed is the contract identity, because a consumer that switched on the
#: old three values would mis-draw the new two rather than refuse them.
Slot = Literal["far_left", "left", "center", "right", "far_right"]

#: In frame order, so the parser, the error message, and the document all read the
#: slots from one list rather than three that can drift apart.
SLOTS: tuple[Slot, ...] = ("far_left", "left", "center", "right", "far_right")

#: A scenario is recipe-neutral, and the two families it has to sit between do
#: not agree on how a game id is spelled: the prepared game package is kebab
#: (`GAME_ID_PATTERN`) while the dialogue scene document is snake. Both are
#: accepted here rather than forcing a third spelling on one of them, because a
#: scenario has to name whichever game it belongs to. Reconciling the two is real
#: work owned by the exact-current-contracts cleanup, not by this contract.
GAME_REFERENCE_PATTERN = r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$"

TEXT_MAX_LENGTH = 600


class ScenarioModel(PersistedContractModel):
    """Strict base: unknown fields refused, no coercion, no camelCase aliases.

    Because the base is strict, a TOML array does not become a tuple. Authored
    fields therefore use `list`, exactly as the room contract does, and the fields
    this repository constructs in Python use `tuple`.
    """


# --------------------------------------------------------------------- statements


class LineStatement(ScenarioModel):
    """One utterance. No speaker is narration; an expression restages the speaker."""

    kind: Literal["line"] = "line"
    speaker: str | None = Field(default=None, pattern=SNAKE_ID_PATTERN, max_length=96)
    expression: str | None = Field(default=None, pattern=SNAKE_ID_PATTERN, max_length=96)
    text: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return normalized_text(value, "scenario line text")

    @model_validator(mode="after")
    def validate_expression_has_a_speaker(self) -> LineStatement:
        if self.expression is not None and self.speaker is None:
            raise ValueError("scenario narration cannot carry an expression")
        return self


class ShowStatement(ScenarioModel):
    kind: Literal["show"] = "show"
    actor: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    expression: str | None = Field(default=None, pattern=SNAKE_ID_PATTERN, max_length=96)
    slot: Slot = "center"


class HideStatement(ScenarioModel):
    kind: Literal["hide"] = "hide"
    actor: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class StageStatement(ScenarioModel):
    kind: Literal["stage"] = "stage"
    stage: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class AudioStatement(ScenarioModel):
    kind: Literal["audio"] = "audio"
    action: Literal["play", "stop"]
    track: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class SetStatement(ScenarioModel):
    kind: Literal["set"] = "set"
    flag: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    value: bool = True


class Condition(ScenarioModel):
    """Flag tests only: everything in `requires` set, everything in `forbids` clear."""

    requires: list[str] = Field(default_factory=list)
    forbids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_terms(self) -> Condition:
        unique_values(self.requires, "condition requires")
        unique_values(self.forbids, "condition forbids")
        both = set(self.requires) & set(self.forbids)
        if both:
            raise ValueError("condition cannot both require and forbid: " + ", ".join(sorted(both)))
        if not self.requires and not self.forbids:
            raise ValueError("condition must test at least one flag")
        return self

    def holds(self, flags: frozenset[str]) -> bool:
        return all(flag in flags for flag in self.requires) and not any(
            flag in flags for flag in self.forbids
        )


class ChoiceOption(ScenarioModel):
    text: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)
    target: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    condition: Condition | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return normalized_text(value, "scenario choice text")


class ChoiceStatement(ScenarioModel):
    """Authored options in authored order. Terminal: control leaves the block."""

    kind: Literal["choice"] = "choice"
    options: list[ChoiceOption] = Field(min_length=2, max_length=8)

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: list[ChoiceOption]) -> list[ChoiceOption]:
        unique_values((option.text for option in value), "choice option text")
        return value


class BranchEdge(ScenarioModel):
    condition: Condition
    target: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class BranchStatement(ScenarioModel):
    """First satisfied edge wins; the default is required, so a branch always leaves."""

    kind: Literal["branch"] = "branch"
    edges: list[BranchEdge] = Field(min_length=1, max_length=16)
    default: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class JumpStatement(ScenarioModel):
    kind: Literal["jump"] = "jump"
    target: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class EndStatement(ScenarioModel):
    kind: Literal["end"] = "end"
    outcome: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


Statement = Annotated[
    LineStatement
    | ShowStatement
    | HideStatement
    | StageStatement
    | AudioStatement
    | SetStatement
    | ChoiceStatement
    | BranchStatement
    | JumpStatement
    | EndStatement,
    Field(discriminator="kind"),
]

#: A block never falls through to the next one in file order. Every block ends on
#: one of these, which is what makes the control flow a graph the proof can walk
#: rather than a guess about author intent.
TERMINAL_KINDS: frozenset[str] = frozenset({"choice", "branch", "jump", "end"})


class Block(ScenarioModel):
    label: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    statements: list[Statement] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_terminates_exactly_once(self) -> Block:
        kinds = [statement.kind for statement in self.statements]
        terminal_at = [index for index, kind in enumerate(kinds) if kind in TERMINAL_KINDS]
        if not terminal_at:
            raise ValueError(
                f"scenario block {self.label} has no terminal statement; "
                "a block must end with jump, menu, if, or end"
            )
        if terminal_at[0] != len(kinds) - 1:
            unreachable = kinds[terminal_at[0] + 1]
            raise ValueError(
                f"scenario block {self.label} continues past its terminal "
                f"{kinds[terminal_at[0]]} statement with an unreachable {unreachable}"
            )
        return self

    @property
    def terminal(self) -> Statement:
        return self.statements[-1]


# ------------------------------------------------------------------- declarations


class CastMember(ScenarioModel):
    """One actor the narrative can name.

    An actor that declares expressions can be shown; one that declares none
    speaks but is never drawn - the protagonist convention. Drawability is stated
    that way, in narrative terms, because a scenario must not know which package
    member supplies an actor's face. Which profile and which authored plate draw
    this actor is the consuming scene's binding, so the same scenario can be
    staged by the visual novel and by the platformer's dialogue box.
    """

    actor_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str | None = Field(default=None, max_length=96)
    expressions: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        return None if value is None else normalized_text(value, "cast display_name")

    @model_validator(mode="after")
    def validate_drawability(self) -> CastMember:
        if self.actor_id in RESERVED_WORDS:
            raise ValueError(
                f"cast actor_id {self.actor_id} is a reserved statement keyword; "
                "rename it so the script cannot parse two ways"
            )
        for expression in self.expressions:
            if expression in RESERVED_WORDS:
                raise ValueError(f"cast expression {expression} is a reserved statement keyword")
        unique_values(self.expressions, "cast expression")
        return self

    @property
    def drawable(self) -> bool:
        return bool(self.expressions)


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


class FlagDeclaration(ScenarioModel):
    """One boolean the script may test and set.

    `origin` says where the value comes from. A `local` flag starts clear and only
    this scenario's own `set` statements establish it - the ordinary case, and the
    one admission proves outright. An `imported` flag is a **fact carried in from an
    earlier beat of a case**: the scenario reads it but may never set it, so
    admission exempts it from the "read but nothing sets it" refusal and instead
    proves the scenario from every assignment of the imported flags. The identifier
    is the same on both sides of the boundary, which is the whole of the crossing
    mechanism; see `docs/spec/game/case.md`.
    """

    flag_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    origin: Literal["local", "imported"] = "local"


class EndingDeclaration(ScenarioModel):
    outcome_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    label: str = Field(min_length=1, max_length=96)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return normalized_text(value, "ending label")


class ScenarioSource(ScenarioModel):
    """One catalog entry. The declarations file is derived, not authored twice."""

    scenario_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)

    @property
    def source(self) -> str:
        return f"scenarios/{self.scenario_id}.toml"


class ScenarioCatalog(ScenarioModel):
    """`scenarios/index.toml`: which scenarios a game holds.

    A game is not one story. The visual novel happens to ship a single scenario
    and the platformer ships one per conversation, and both read the same
    catalog: a game that held its narrative in a differently-shaped file
    depending on genre would be two contracts wearing one name.
    """

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


# ------------------------------------------------------------------- the program


class ScenarioProgram(PersistedContractModel):
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


class EndingWitness(PersistedContractModel):
    """One shortest path reaching an ending - evidence, not gameplay."""

    outcome_id: str
    #: Block labels from the entry to the block whose `end` names this outcome.
    path: list[str] = Field(min_length=1)


class ScenarioAdmissionReport(PersistedContractModel):
    """The proof that ships beside the run, the way `puzzle.validation.json` does."""

    schema_version: Literal[1] = 1
    kind: Literal["scenario-admission-v1"] = "scenario-admission-v1"
    scenario_id: str
    admitted: bool
    reachable_states: int = Field(ge=1)
    reachable_labels: list[str] = Field(default_factory=list)
    witnesses: list[EndingWitness] = Field(default_factory=list)
    #: The imported flags the search enumerated. The proof started from every
    #: assignment of these, because a fact carried in from an earlier beat may
    #: arrive either way and a scenario proven only for one of them is unproven.
    imported_flags: list[str] = Field(default_factory=list)


__all__ = [
    "RESERVED_WORDS",
    "SCENARIO_CATALOG_KIND",
    "SCENARIO_CATALOG_NAME",
    "SCENARIO_CATALOG_SCHEMA_VERSION",
    "SCENARIO_KIND",
    "SCENARIO_SCHEMA_VERSION",
    "SLOTS",
    "TERMINAL_KINDS",
    "AudioStatement",
    "Block",
    "BranchEdge",
    "BranchStatement",
    "CastMember",
    "ChoiceOption",
    "ChoiceStatement",
    "Condition",
    "EndStatement",
    "EndingDeclaration",
    "EndingWitness",
    "FlagDeclaration",
    "HideStatement",
    "JumpStatement",
    "LineStatement",
    "ScenarioAdmissionReport",
    "ScenarioCatalog",
    "ScenarioDeclarations",
    "ScenarioSource",
    "ScenarioProgram",
    "SetStatement",
    "ShowStatement",
    "Slot",
    "StageDeclaration",
    "StageStatement",
    "Statement",
    "TrackDeclaration",
]

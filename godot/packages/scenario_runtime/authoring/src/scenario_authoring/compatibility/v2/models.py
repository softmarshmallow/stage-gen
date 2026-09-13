"""The supported v2 narrative subset, independent of game production metadata.

These are compiler values, not a new persisted program envelope. Games adapt their
existing declarations and package the compiled blocks for the v2 runtime reader.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._validation import SNAKE_ID_PATTERN, normalized_text, unique_values

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
#: middle three; v2 adds the outer pair. The three-slot
#: vocabulary is a strict subset, so a v1 script's staging still reads the same -
#: what changed is the contract identity, because a consumer that switched on the
#: old three values would mis-draw the new two rather than refuse them.
Slot = Literal["far_left", "left", "center", "right", "far_right"]

#: In frame order, so the parser, the error message, and the document all read the
#: slots from one list rather than three that can drift apart.
SLOTS: tuple[Slot, ...] = ("far_left", "left", "center", "right", "far_right")


TEXT_MAX_LENGTH = 600


class ScenarioModel(BaseModel):
    """Strict content values with explicit snake-case fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


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


class FlagDeclaration(ScenarioModel):
    """A local boolean or an initial fact supplied by the invoking game.

    Imported flags are initialized by the game and remain writable within the
    invocation. Admission enumerates their possible initial assignments.
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


class EndingWitness(ScenarioModel):
    """One shortest path reaching an ending - evidence, not gameplay."""

    outcome_id: str
    #: Block labels from the entry to the block whose `end` names this outcome.
    path: list[str] = Field(min_length=1)


class ScenarioAdmissionReport(ScenarioModel):
    """Bounded reachable-state and ending-witness evidence for a compiled narrative."""

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


class StageDeclaration(ScenarioModel):
    stage_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class TrackDeclaration(ScenarioModel):
    track_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class ScenarioDeclarations(ScenarioModel):
    """Names available to the supported v2 script; no game package is required."""

    scenario_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
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

    @model_validator(mode="after")
    def validate_closure(self) -> ScenarioDeclarations:
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
        """Initial facts supplied by the invoking game."""

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


class ScenarioProgram(ScenarioModel):
    """Compiled narrative values; the host owns a persisted delivery envelope."""

    scenario_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
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

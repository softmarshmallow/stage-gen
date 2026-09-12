"""The `case-v1` authored contract: the container above the narrative leaves.

A scenario is one movement and a room is one screen. Neither knows what follows
it, and until now nothing did: a game that wanted six scenarios and two rooms
played in sequence had to chain them in a consumer, which put story structure in
a place no proof could see.

A **case** is that structure, authored and provable. It is an ordered graph of
**beats** - each beat naming a leaf member and the kind of leaf it is - joined by
**edges keyed on outcomes**: a scenario beat leaves through the `end <outcome>`
the player reached, a room beat leaves when its win condition is met. It declares
a **fact** namespace, and facts are the only thing that crosses a beat boundary.
No inventory crosses; a room's items are that room's.

Two things this deliberately is *not*.

It is **not a second scenario**. A case has no lines, no staging, no conditions
and no choices. Everything a player reads happens inside a leaf, and a leaf's own
proof is untouched by the case - `scenario check` and `prove_room_solvable` still
run per leaf, exactly as they did.

It is **not a state machine over facts**. The case proof never enumerates fact
assignments, because that is the state-space explosion the leaf ceiling already
guards against and doing it twice would buy nothing. It runs a must-availability
dataflow over the beat graph instead, which is linear in beats and edges: see
`proof.py`.

See `docs/spec/game/case.md`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    SNAKE_ID_PATTERN,
    normalized_text,
    portable_relative_path,
    unique_values,
)

CASE_SCHEMA_VERSION = 1
CASE_KIND = "case-v1"
CASE_CATALOG_SCHEMA_VERSION = 1
CASE_CATALOG_KIND = "case-catalog-v1"
CASE_CATALOG_NAME = "cases/index.toml"

#: A scenario is a package-relative game reference in either house spelling, the
#: same accommodation the scenario contract makes and for the same reason.
GAME_REFERENCE_PATTERN = r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$"

#: A room beat has exactly one way out - it is won or it is not being left - so
#: its single edge is keyed on this reserved outcome rather than on a name the
#: room contract does not carry. A scenario beat's outcomes are its own.
ROOM_WIN_OUTCOME = "win"

#: Where a room beat's member path must end. The room recipe reads a directory
#: holding `room.toml` beside its `references/` and `ui.toml`, so a case names the
#: document and the recipe is handed its parent - which is what lets one game hold
#: several rooms without the recipe learning anything new.
ROOM_DOCUMENT_SUFFIX = "room.toml"


class CaseModel(PersistedContractModel):
    """Strict base: unknown fields refused, no coercion, no camelCase aliases."""


class FactDeclaration(CaseModel):
    """One boolean that crosses beat boundaries, and how it comes to be true.

    `establishment` is the whole of the fact discipline, and it is required rather
    than defaulted because the author has to have decided:

    - `required` - every path into a beat that reads this fact must pass through a
      beat that exports it. The proof refuses the authoring where one route
      reaches the reader with the fact unestablished, which is the bug that
      otherwise shows up as a line of dialogue about something that never
      happened.
    - `defaults_false` - the fact may be read before anything sets it, and reads
      false when it is. That is the ordinary shape of an optional look: the player
      who never touched the carton is a player for whom `carton_on_gallery` is
      simply false.

    There is no `defaults_true`. A fact is a record of something that happened,
    and nothing has happened before the entry beat runs.
    """

    fact_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    establishment: Literal["required", "defaults_false"]
    summary: str = Field(min_length=1, max_length=300)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return normalized_text(value, "fact summary")


class BeatEdge(CaseModel):
    """One outcome of a beat, and the beat it hands control to."""

    outcome: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    to: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class Beat(CaseModel):
    """One leaf as the case plays it: which member, what it reads, what it exports.

    `reads` and `writes` are the beat's declared contract with the rest of the
    case, and they are authored rather than derived on purpose. Deriving them from
    the leaf would make the case silently follow whatever the leaf happened to do
    this morning; authoring them means a leaf that stops exporting a fact fails
    against the case that depends on it, which is the failure worth having. The
    binding pass checks the declaration against the leaf in both directions.
    """

    beat_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    kind: Literal["scenario", "room"]
    #: The exact package-relative path of the leaf's authored document.
    member: str
    display_name: str = Field(min_length=1, max_length=96)
    #: Facts this beat's leaf tests. A room reads nothing: rooms in this contract
    #: start from an empty state and their guards are their own.
    reads: list[str] = Field(default_factory=list, max_length=64)
    #: Facts this beat's leaf can establish on some path through it.
    writes: list[str] = Field(default_factory=list, max_length=64)
    #: A terminal beat ends the case. It declares no edges, and a non-terminal beat
    #: must declare at least one - so forgetting an edge is a refusal rather than
    #: an accidental ending.
    terminal: bool = False
    edges: list[BeatEdge] = Field(default_factory=list, max_length=32)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "beat display_name")

    @field_validator("member")
    @classmethod
    def validate_member(cls, value: str) -> str:
        return portable_relative_path(value, "beat member")

    @model_validator(mode="after")
    def validate_shape(self) -> Beat:
        unique_values(self.reads, f"beat {self.beat_id} reads")
        unique_values(self.writes, f"beat {self.beat_id} writes")
        unique_values((edge.outcome for edge in self.edges), f"beat {self.beat_id} edge outcome")
        if self.terminal and self.edges:
            raise ValueError(
                f"beat {self.beat_id} is terminal and also declares edges; "
                "a terminal beat ends the case"
            )
        if not self.terminal and not self.edges:
            raise ValueError(
                f"beat {self.beat_id} declares no edges and is not marked terminal; "
                "mark it `terminal = true` or say where each outcome goes"
            )
        if self.kind == "scenario":
            self._validate_scenario_member()
        else:
            self._validate_room()
        return self

    def _validate_scenario_member(self) -> None:
        if not (self.member.startswith("scenarios/") and self.member.endswith(".toml")):
            raise ValueError(
                f"beat {self.beat_id} names scenario member `{self.member}`; "
                "a scenario beat plays `scenarios/<scenario_id>.toml`"
            )

    def _validate_room(self) -> None:
        if not self.member.endswith(ROOM_DOCUMENT_SUFFIX):
            raise ValueError(
                f"beat {self.beat_id} names room member `{self.member}`; "
                f"a room beat plays a directory's `{ROOM_DOCUMENT_SUFFIX}`"
            )
        if self.reads:
            raise ValueError(
                f"beat {self.beat_id} is a room and declares reads: "
                + ", ".join(sorted(self.reads))
                + ". A room starts from an empty state and its guards are its own; "
                "only scenarios import facts."
            )
        if self.terminal:
            return
        outcomes = [edge.outcome for edge in self.edges]
        if outcomes != [ROOM_WIN_OUTCOME]:
            raise ValueError(
                f"beat {self.beat_id} is a room and must declare exactly one edge keyed "
                f"`{ROOM_WIN_OUTCOME}`; a room is left by meeting its win condition and "
                "there is no other way out"
            )

    @property
    def scenario_member_id(self) -> str:
        """The scenario id this beat's `member` path names. Meaningless for a room.

        Spelled out rather than shortened to `scenario_id` because the runtime
        projection publishes a field by that name, and a property and a field of
        one name on a base and its subclass is the shape that makes two things
        look like one.
        """

        return self.member.removeprefix("scenarios/").removesuffix(".toml")

    @property
    def room_root(self) -> str:
        """The directory the room recipe is handed. `""` means the package root."""

        return self.member.removesuffix(ROOM_DOCUMENT_SUFFIX).rstrip("/")


#: One safe path segment, matching the producer's run-tag contract exactly - the
#: same shape `web/lib/shell/runs.ts` enforces before it resolves a run directory.
#: Generated tags happen to be lower-case, but an explicit producer tag may carry
#: upper case, `_`, or `.`.
RUN_TAG_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"


class RuntimeBeat(Beat):
    """One beat as the consumer plays it: the authored beat plus the run it reads.

    A `member` is an authored path and a `run_tag` is a generated directory, and
    nothing before this joined them - the case knew which scenario a beat plays,
    and the consumer knew which runs exist, and neither could get from one to the
    other. That join is the whole of this document.

    **A run tag alone does not locate a scenario.** One `dialogue-scene` run
    publishes several scenarios - that is the point of binding them together, so
    the cast is drawn once - and its manifest keys them by `scenario_id`. So a
    scenario beat carries that id beside its tag. It is derived from `member`
    rather than supplied, because the two would otherwise be the same fact
    authored twice and free to disagree. A room beat carries no id: a room run
    publishes one room.
    """

    run_tag: str = Field(pattern=RUN_TAG_PATTERN, max_length=128)
    #: Which scenario inside `run_tag` this beat plays. Absent for a room beat.
    scenario_id: str | None = Field(default=None, pattern=SNAKE_ID_PATTERN, max_length=96)

    @model_validator(mode="after")
    def validate_leaf_locator(self) -> RuntimeBeat:
        if self.kind == "scenario":
            if self.scenario_id != self.scenario_member_id:
                raise ValueError(
                    f"beat {self.beat_id} publishes scenario_id `{self.scenario_id}`, which "
                    f"its member `{self.member}` does not name"
                )
        elif self.scenario_id is not None:
            raise ValueError(f"beat {self.beat_id} is a room and carries no scenario_id")
        return self


class CaseRuntime(CaseModel):
    """`case.json`: the authored case, verbatim, with each beat bound to its run.

    A runtime projection beside an authored contract, the way every other recipe
    publishes one. It carries its own identity rather than the authored `case-v1`
    kind, because it is a different document - the beats have grown a field that
    only exists after generation - and this repository refuses a mixed identity
    rather than guessing which shape it was handed.

    Nothing is added beyond the run tags. The consumer walks the same beat graph
    the proof walked, reads the same facts, and looks up each leaf in the run the
    beat names.
    """

    schema_version: Literal[1] = 1
    kind: Literal["case-runtime-v1"] = "case-runtime-v1"
    game_id: str = Field(pattern=GAME_REFERENCE_PATTERN, max_length=96)
    case_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str = Field(min_length=1, max_length=96)
    revision: int = Field(ge=1)
    entry: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    facts: list[FactDeclaration] = Field(default_factory=list, max_length=128)
    beats: list[RuntimeBeat] = Field(min_length=1, max_length=128)


class CaseSource(CaseModel):
    """One catalog entry."""

    case_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)

    @property
    def source(self) -> str:
        return f"cases/{self.case_id}.toml"


class CaseCatalog(CaseModel):
    """`cases/index.toml`: which cases a game holds.

    A game is not one case, for the same reason it is not one scenario: an episodic
    story is several, and a game that held one in a differently shaped file would be
    two contracts wearing one name. The shape deliberately mirrors the scenario
    catalog rather than inventing a second convention.
    """

    schema_version: Literal[1]
    kind: Literal["case-catalog-v1"]
    game_id: str = Field(pattern=GAME_REFERENCE_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    cases: list[CaseSource] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_closure(self) -> CaseCatalog:
        unique_values((entry.case_id for entry in self.cases), "catalog case_id")
        return self

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(entry.case_id for entry in self.cases)


class CaseDocument(CaseModel):
    """`cases/<id>.toml`: the beats, their edges, and the facts that cross them."""

    schema_version: Literal[1]
    kind: Literal["case-v1"]
    game_id: str = Field(pattern=GAME_REFERENCE_PATTERN, max_length=96)
    case_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    display_name: str = Field(min_length=1, max_length=96)
    revision: int = Field(ge=1)
    #: Exactly one. A case with two ways in is two cases.
    entry: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    facts: list[FactDeclaration] = Field(default_factory=list, max_length=128)
    beats: list[Beat] = Field(min_length=1, max_length=128)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "case display_name")

    @model_validator(mode="after")
    def validate_closure(self) -> CaseDocument:
        unique_values((beat.beat_id for beat in self.beats), "beat_id")
        unique_values((fact.fact_id for fact in self.facts), "fact_id")
        unique_values((beat.member for beat in self.beats), "beat member")
        return self

    @property
    def beat_ids(self) -> frozenset[str]:
        return frozenset(beat.beat_id for beat in self.beats)

    @property
    def fact_ids(self) -> frozenset[str]:
        return frozenset(fact.fact_id for fact in self.facts)

    @property
    def defaulting_fact_ids(self) -> frozenset[str]:
        return frozenset(
            fact.fact_id for fact in self.facts if fact.establishment == "defaults_false"
        )

    def beat(self, beat_id: str) -> Beat | None:
        return next((beat for beat in self.beats if beat.beat_id == beat_id), None)


class TerminalWitness(PersistedContractModel):
    """One shortest run of beats from the entry to a terminal - evidence, not play."""

    beat_id: str
    path: list[str] = Field(min_length=1)


class FactAvailability(PersistedContractModel):
    """What the proof concluded about one fact, for the reader of the report."""

    fact_id: str
    establishment: Literal["required", "defaults_false"]
    exported_by: list[str] = Field(default_factory=list)
    read_by: list[str] = Field(default_factory=list)


class CaseAdmissionReport(PersistedContractModel):
    """The proof that ships beside the case, the way the scenario's does."""

    schema_version: Literal[1] = 1
    kind: Literal["case-admission-v1"] = "case-admission-v1"
    case_id: str
    admitted: bool
    beat_count: int = Field(ge=1)
    reachable_beats: list[str] = Field(default_factory=list)
    terminals: list[str] = Field(default_factory=list)
    witnesses: list[TerminalWitness] = Field(default_factory=list)
    facts: list[FactAvailability] = Field(default_factory=list)


__all__ = [
    "CASE_CATALOG_KIND",
    "CASE_CATALOG_NAME",
    "CASE_CATALOG_SCHEMA_VERSION",
    "CASE_KIND",
    "CASE_SCHEMA_VERSION",
    "ROOM_DOCUMENT_SUFFIX",
    "ROOM_WIN_OUTCOME",
    "RUN_TAG_PATTERN",
    "Beat",
    "BeatEdge",
    "CaseAdmissionReport",
    "CaseCatalog",
    "CaseDocument",
    "CaseRuntime",
    "CaseSource",
    "FactAvailability",
    "FactDeclaration",
    "RuntimeBeat",
    "TerminalWitness",
]

"""Exact-current prepared-package root contract (``game-contract-v9``).

The root is a genre-neutral container: one game states its identity, its
universe, the look every asset in it must hold (style, proportion, scale),
its evidence, and its rights - and then declares one or more GENRE MEMBERS,
each carrying the camera and the member table its own family needs. The
platformer RPG family is one such member; a second genre is a new member
model beside it, not a rewrite of the container.

Presentation and cast live on the member, not the container, because they are
genre facts: the container stays camera-neutral (docs/spec/asset-taxonomy.md
types it "the container; not itself camera-scoped"), and a runner's single
avatar and an RPG's mob roster are different shapes that should not share one
model of optional halves. Character identity is shared across members the way
everything visual is shared here - by binding the same digest-locked reference
bytes - so the container needs no cast join of its own.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    GAME_ID_PATTERN,
    KEBAB_ID_PATTERN,
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    canonical_contract_json,
    normalized_text,
    parse_toml_contract,
    portable_relative_path,
    sha256_bytes,
    unique_values,
)

PREPARED_GAME_CONTRACT_SCHEMA_VERSION = 9


class PackageSource(PersistedContractModel):
    source: str

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return portable_relative_path(value, "package source")


class UniverseSource(PackageSource):
    pass


class MapSource(PackageSource):
    map_id: str = Field(pattern=KEBAB_ID_PATTERN, max_length=96)

    @model_validator(mode="after")
    def validate_filename(self) -> MapSource:
        if self.source != f"maps/{self.map_id}.toml":
            raise ValueError("map source must equal maps/<map_id>.toml")
        return self


class ScenarioCatalogSource(PersistedContractModel):
    index_source: str

    @field_validator("index_source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return portable_relative_path(value, "sequence index source")


class PreparedContactShadows(PersistedContractModel):
    """Runtime-only grounding treatment shared by world entities."""

    enabled: bool
    opacity: float = Field(ge=0.0, le=1.0)
    softness_screen_pixels: float = Field(ge=0.0, le=32.0)


class PreparedPresentation(PersistedContractModel):
    view_profile: Literal["side_view_2d"]
    gameplay_space: Literal["side_plane"]
    contact_shadows: PreparedContactShadows


class PreparedStyle(PersistedContractModel):
    label: str
    keywords: list[str] = Field(min_length=1, max_length=32)
    avoid: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return normalized_text(value, "style.label")

    @field_validator("keywords", "avoid")
    @classmethod
    def validate_entries(cls, value: list[str], info: ValidationInfo) -> list[str]:
        normalized = [
            normalized_text(entry, f"style.{info.field_name or 'entry'}") for entry in value
        ]
        unique_values(normalized, f"style.{info.field_name or 'entry'}")
        return normalized


class PreparedProportion(PersistedContractModel):
    heads_tall: float = Field(ge=1.5, le=12.0)
    by_body_kind: dict[str, float] = Field(default_factory=dict)

    @field_validator("by_body_kind")
    @classmethod
    def validate_body_kinds(cls, value: dict[str, float]) -> dict[str, float]:
        for body_kind, heads_tall in value.items():
            if not body_kind or body_kind != body_kind.strip():
                raise ValueError("proportion body kinds must be non-empty trimmed strings")
            if heads_tall < 1.5 or heads_tall > 12.0:
                raise ValueError("proportion body-kind values must be between 1.5 and 12.0")
        return value

    def heads_for(self, body_kind: str) -> float:
        return self.by_body_kind.get(body_kind, self.heads_tall)


#: Nothing a player can interact with resolves below a quarter of the player by default. The
#: floor is a legibility rule rather than a realism one: a subject drawn smaller than this is not
#: a readable target at any viewport this profile supports.
MINIMUM_HEIGHT_UNITS = 0.05
MAXIMUM_HEIGHT_UNITS = 32.0


def _rounded_units(value: float, label: str) -> float:
    if value < MINIMUM_HEIGHT_UNITS or value > MAXIMUM_HEIGHT_UNITS:
        raise ValueError(
            f"{label} must be between {MINIMUM_HEIGHT_UNITS} and {MAXIMUM_HEIGHT_UNITS} "
            "player heights"
        )
    # Two decimals. A finer distinction does not survive a sprite a few hundred pixels tall, and
    # rounding keeps the run tag stable across equivalent authored values.
    return round(value, 2)


class PreparedScale(PersistedContractModel):
    """The game's size vocabulary: one canonical player height, and everything as a multiple.

    The unit is deliberately anatomy-free. A head or a shoulder width is a property of the *art
    style* rather than of the world - at `heads_tall = 2.25` a head is 0.44 of the figure and at
    realistic proportions 0.125 - so a vocabulary built on one is unusable in the other. The
    player is invariant across every build a game may author, so no style parameter enters here.
    `proportion` and this table answer different questions and are never reconciled: a figure at
    the right magnitude with the wrong build is a distinct defect.

    It is also not a pixel. `player_height_tiles` is the single place in a package where the unit
    meets a render projection, and a consumer multiplies through it exactly once.
    """

    unit: Literal["player_height"] = "player_height"
    player_height_tiles: float = Field(gt=0.0, le=64.0)
    minimum: float = Field(default=0.25, ge=MINIMUM_HEIGHT_UNITS, le=MAXIMUM_HEIGHT_UNITS)
    steps: list[float] = Field(default_factory=list, max_length=32)
    ranks: dict[str, float] = Field(default_factory=dict)

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, value: list[float]) -> list[float]:
        if not value:
            return value
        rounded = [_rounded_units(float(item), "steps") for item in value]
        if rounded != sorted(rounded):
            raise ValueError("steps must ascend, so a recovered index selects a larger subject")
        if len(set(rounded)) != len(rounded):
            raise ValueError("steps must be unique")
        return rounded

    @field_validator("ranks")
    @classmethod
    def validate_ranks(cls, value: dict[str, float]) -> dict[str, float]:
        resolved: dict[str, float] = {}
        for rank, units in value.items():
            if not rank or rank != rank.strip():
                raise ValueError("scale rank names must be non-empty trimmed strings")
            resolved[rank] = _rounded_units(float(units), f"ranks[{rank}]")
        return resolved

    @model_validator(mode="after")
    def validate_floor(self) -> PreparedScale:
        object.__setattr__(self, "minimum", _rounded_units(self.minimum, "minimum"))
        object.__setattr__(self, "player_height_tiles", round(self.player_height_tiles, 2))
        for index, step in enumerate(self.steps):
            if step < self.minimum:
                raise ValueError(f"steps[{index}] resolves below the declared minimum")
        for rank, units in self.ranks.items():
            if units < self.minimum:
                raise ValueError(f"ranks[{rank}] resolves below the declared minimum")
        return self

    def rank_units(self, rank: str) -> float | None:
        """The magnitude a mob of this rank resolves to, if the game declares one."""

        return self.ranks.get(rank)


class PreparedCast(PersistedContractModel):
    player_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    mob_ids: list[str] = Field(min_length=1, max_length=64)
    npc_ids: list[str] = Field(min_length=1, max_length=64)

    @field_validator("mob_ids", "npc_ids")
    @classmethod
    def validate_ids(cls, value: list[str], info: ValidationInfo) -> list[str]:
        for identifier in value:
            if not identifier or identifier != identifier.strip():
                raise ValueError(f"cast.{info.field_name} must contain trimmed IDs")
            if re.fullmatch(SNAKE_ID_PATTERN, identifier) is None:
                raise ValueError(f"cast.{info.field_name} contains an invalid ID")
        unique_values(value, f"cast.{info.field_name}")
        return value


class PreparedContentSources(PersistedContractModel):
    player: PackageSource
    mobs: PackageSource
    npcs: PackageSource
    props: PackageSource
    items: PackageSource
    #: Optional, and the only content family that is.
    #:
    #: Every other catalog describes something a playable package must have: a character, a roster,
    #: residents, scenery, things to carry. A projectile is owed only by a game whose weapons throw
    #: one, so requiring the file would make every melee package author an empty catalog. Absent
    #: means the game fires nothing, which is what every package written before this field said.
    projectiles: PackageSource | None = None


class PreparedEvidence(PersistedContractModel):
    artifact_source: str
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    provenance_source: str
    provenance_sha256: str = Field(pattern=SHA256_PATTERN)
    review_source: str
    review_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("artifact_source", "provenance_source", "review_source")
    @classmethod
    def validate_source(cls, value: str, info: ValidationInfo) -> str:
        source = portable_relative_path(value, f"evidence.{info.field_name}")
        if not source.startswith("references/"):
            raise ValueError("evidence sources must live under references/")
        return source

    @model_validator(mode="after")
    def validate_extensions(self) -> PreparedEvidence:
        if not self.provenance_source.endswith(".provenance.json"):
            raise ValueError("evidence provenance_source must end in .provenance.json")
        if not self.review_source.endswith(".visual-review.md"):
            raise ValueError("evidence review_source must end in .visual-review.md")
        return self


class PreparedRights(PersistedContractModel):
    status: Literal["unreviewed", "restricted", "redistribution-approved"]
    basis: list[str] = Field(min_length=1, max_length=32)

    @field_validator("basis")
    @classmethod
    def validate_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "rights basis") for entry in value]
        unique_values(normalized, "rights basis")
        return normalized


class PlatformerGenreMember(PersistedContractModel):
    """The side-view platformer RPG family as one genre member of the container.

    The member carries exactly what is genre-scoped: the camera it is played
    under, the cast roles its runtime knows how to spawn, and the contract
    members its own family reads. Its fixed paths are the same unprefixed
    paths the family has always used; a second genre claims its own prefix.
    """

    genre: Literal["platformer"]
    presentation: PreparedPresentation
    cast: PreparedCast
    gameplay: PackageSource
    ui: PackageSource
    soundtrack: PackageSource
    maps: list[MapSource] = Field(min_length=1, max_length=64)
    content: PreparedContentSources
    scenarios: ScenarioCatalogSource

    @field_validator("maps")
    @classmethod
    def validate_maps(cls, value: list[MapSource]) -> list[MapSource]:
        unique_values((entry.map_id for entry in value), "map_id")
        unique_values((entry.source for entry in value), "map source")
        return value

    @model_validator(mode="after")
    def validate_member_sources(self) -> PlatformerGenreMember:
        exact_sources = {
            "gameplay": (self.gameplay.source, "gameplay.toml"),
            "ui": (self.ui.source, "ui.toml"),
            "soundtrack": (self.soundtrack.source, "soundtrack.toml"),
            "content.player": (self.content.player.source, "content/player.toml"),
            "content.mobs": (self.content.mobs.source, "content/mobs.toml"),
            "content.npcs": (self.content.npcs.source, "content/npcs.toml"),
            "content.props": (self.content.props.source, "content/props.toml"),
            "content.items": (self.content.items.source, "content/items.toml"),
            **(
                {}
                if self.content.projectiles is None
                else {
                    "content.projectiles": (
                        self.content.projectiles.source,
                        "content/projectiles.toml",
                    )
                }
            ),
            "scenarios": (self.scenarios.index_source, "scenarios/index.toml"),
        }
        for label, (actual, expected) in exact_sources.items():
            if actual != expected:
                raise ValueError(f"{label} source must equal {expected}")
        return self

    def member_sources(self) -> list[str]:
        """Every contract member this genre owns, in declaration order."""

        return [
            self.gameplay.source,
            self.ui.source,
            self.soundtrack.source,
            *(entry.source for entry in self.maps),
            self.content.player.source,
            self.content.mobs.source,
            self.content.npcs.source,
            self.content.props.source,
            self.content.items.source,
            *([] if self.content.projectiles is None else [self.content.projectiles.source]),
            self.scenarios.index_source,
        ]


class RunnerCast(PersistedContractModel):
    """The runner casts exactly one drawn character: the avatar that runs."""

    avatar_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class RunnerContentSources(PersistedContractModel):
    avatar: PackageSource
    props: PackageSource
    items: PackageSource


class RunnerGenreMember(PersistedContractModel):
    """The infinite-runner family as one genre member of the container.

    The member table is minimal on purpose: gameplay (named profiles), one
    track of authored tiled segments, one avatar, obstacle props, and pickup
    items, and explicit event-to-effect audio. Soundtrack is optional, and so
    is the screen-FX document (``fx.toml``, a root sibling the genre consumes at
    its stage start); there is no UI member (the runtime draws its
    distance/score HUD itself) and no scenario member in v1. The family
    claims the fixed `runner/` prefix so its members can never collide with a
    sibling genre's.
    """

    genre: Literal["runner"]
    presentation: PreparedPresentation
    cast: RunnerCast
    gameplay: PackageSource
    track: PackageSource
    content: RunnerContentSources
    audio: PackageSource
    soundtrack: PackageSource | None = None
    fx: PackageSource | None = None

    @model_validator(mode="after")
    def validate_member_sources(self) -> RunnerGenreMember:
        exact_sources = {
            "gameplay": (self.gameplay.source, "runner/gameplay.toml"),
            "track": (self.track.source, "runner/track.toml"),
            "content.avatar": (self.content.avatar.source, "runner/content/avatar.toml"),
            "content.props": (self.content.props.source, "runner/content/props.toml"),
            "content.items": (self.content.items.source, "runner/content/items.toml"),
            "audio": (self.audio.source, "runner/audio.toml"),
            **(
                {}
                if self.soundtrack is None
                else {"soundtrack": (self.soundtrack.source, "runner/soundtrack.toml")}
            ),
            **({} if self.fx is None else {"fx": (self.fx.source, "fx.toml")}),
        }
        for label, (actual, expected) in exact_sources.items():
            if actual != expected:
                raise ValueError(f"runner {label} source must equal {expected}")
        return self

    def member_sources(self) -> list[str]:
        """Every contract member this genre owns, in declaration order."""

        return [
            self.gameplay.source,
            self.track.source,
            self.content.avatar.source,
            self.content.props.source,
            self.content.items.source,
            self.audio.source,
            *([] if self.soundtrack is None else [self.soundtrack.source]),
            *([] if self.fx is None else [self.fx.source]),
        ]


#: The genre-member union, discriminated on ``genre``. A third genre widens
#: this union rather than touching the container.
GenreMember = Annotated[
    PlatformerGenreMember | RunnerGenreMember,
    Field(discriminator="genre"),
]


class PreparedGameContract(PersistedContractModel):
    """One prepared game's genre-neutral container, named by exact source path."""

    schema_version: Literal[9]
    kind: Literal["game-contract-v9"]
    game_id: str = Field(pattern=GAME_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    universe: UniverseSource
    style: PreparedStyle
    proportion: PreparedProportion
    scale: PreparedScale
    genres: list[GenreMember] = Field(min_length=1, max_length=8)
    evidence: dict[str, PreparedEvidence] = Field(min_length=1, max_length=64)
    rights: PreparedRights

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalized_text(value, "display_name")

    @field_validator("genres")
    @classmethod
    def validate_genres(cls, value: list[GenreMember]) -> list[GenreMember]:
        unique_values((entry.genre for entry in value), "genre member")
        return value

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: dict[str, PreparedEvidence]) -> dict[str, PreparedEvidence]:
        for evidence_id in value:
            if re.fullmatch(SNAKE_ID_PATTERN, evidence_id) is None:
                raise ValueError("evidence keys must be lower_snake_case IDs")
        paths = [
            path
            for entry in value.values()
            for path in (entry.artifact_source, entry.provenance_source, entry.review_source)
        ]
        unique_values(paths, "evidence source")
        return value

    @model_validator(mode="after")
    def validate_member_sources(self) -> PreparedGameContract:
        if self.universe.source != "universe.md":
            raise ValueError("universe source must equal universe.md")
        member_sources = [
            self.universe.source,
            *(source for member in self.genres for source in member.member_sources()),
        ]
        # Contract members are exclusively owned by one genre; only digest-locked
        # reference images may be shared across members.
        unique_values(member_sources, "package member source")
        return self

    def member(self, genre: str) -> GenreMember | None:
        """The declared member for one genre, or None when the game does not carry it."""

        for entry in self.genres:
            if entry.genre == genre:
                return entry
        return None

    def platformer_member(self) -> PlatformerGenreMember | None:
        member = self.member("platformer")
        return member if isinstance(member, PlatformerGenreMember) else None


def load_prepared_game_contract_bytes(data: bytes) -> PreparedGameContract:
    return parse_toml_contract(data, model=PreparedGameContract, label="prepared game contract")


def canonical_prepared_game_contract_json(contract: PreparedGameContract) -> bytes:
    return canonical_contract_json(contract)


def prepared_game_contract_sha256(contract: PreparedGameContract) -> str:
    return sha256_bytes(canonical_prepared_game_contract_json(contract))


__all__ = [
    "PREPARED_GAME_CONTRACT_SCHEMA_VERSION",
    "GenreMember",
    "MapSource",
    "PlatformerGenreMember",
    "RunnerCast",
    "RunnerContentSources",
    "RunnerGenreMember",
    "PackageSource",
    "PreparedCast",
    "PreparedContentSources",
    "PreparedContactShadows",
    "PreparedEvidence",
    "PreparedGameContract",
    "PreparedPresentation",
    "PreparedProportion",
    "PreparedRights",
    "PreparedStyle",
    "ScenarioCatalogSource",
    "UniverseSource",
    "canonical_prepared_game_contract_json",
    "load_prepared_game_contract_bytes",
    "prepared_game_contract_sha256",
]

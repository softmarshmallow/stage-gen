"""The authored game contract: game-wide art direction and versioned gameplay subsystems.

Before this contract a run's direction was a flat bag of independent opt-ins on the request -
`theme`, `style_anchor`, `character_profile`, `character_heads_tall`, `village` - each parsed on
its own and none of them aware of the others. That worked while there was one character. It stops
working the moment a game has a cast: `character_heads_tall` names the *player's* build, so when
the village arrived its residents were drawn to whatever build the image model felt like, and the
head-matched runtime rendered a seven-head elf beside a two-head player at three and a half times
the player's height. Nothing was misconfigured. There was simply nowhere to say "this game is
two heads tall" as opposed to "this player is".

So this contract is the place a game states the facts that must hold across every asset in it:
the words that fix its look, the build its bodies are drawn to, and how each role's artwork is
made. It is authored - by a person or by an agent - and it is data, not prose: every open string
is checked against the closed vocabulary in `vocabulary.py`, so a contract cannot introduce a
word the pipeline has not reviewed.

The container is a *game* rather than a world or a scene. A recipe here produces one kind of
thing - a side-scrolling stage, a visual-novel dialogue bundle - and a real game is several of
those sharing one identity: the dialogue spike is usable inside an RPG, and the scrolling stage is
a hunting ground in that same RPG. What has to hold across all of them is precisely what this file
carries. It also keeps the name clear of `WorldSpec` and `world_spec_<tag>.json`, which already
exist and mean the per-run generated bible for one scrolling stage.

The current document is game-contract-v3. It composes independently versioned gameplay policies
and materializes default-on combat text while leaving population optional. Historical document
shapes are not accepted by this loader; independently versioned nested policies and bindings keep
their own current identities.

Camera is a required field rather than a filename convention. `sideview-game.toml` would carry
the same information, but a filename can be renamed without invalidating anything downstream and
cannot be refused by a recipe that does not implement it; `projection = "side_view_2d"` can be
validated, can be rejected with a message that says why, and travels into provenance. Adding a
top-down camera later is a new member of `CameraProjection` plus a recipe that accepts it, and
touches no existing game file - which is the isolation the convention was reaching for.

The two cast entries are deliberately different shapes rather than one parameterised one. A
player and a village resident are not the same subject drawn at different settings: the player is
a side-view actor whose artwork is animation strips across six states and whose facing is
contractual, and a resident is a still figure who stands in a town, faces the viewer, and holds
something. Giving them one model with `animation = "strip" | "still"` would have made every
player-only field optional and every resident-only field optional, and the schema would then
permit an animated forward-facing player and a posed side-view still - neither of which any part
of this pipeline can produce. Two models refuse both at parse time.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Collection, Mapping
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from stage_gen.components.character_profile import CharacterProfileRights
from stage_gen.components.game_contract.gameplay import GameplayDirection
from stage_gen.components.game_contract.vocabulary import (
    REQUIRED_STYLE_FACET,
    GameVocabulary,
)
from stage_gen.contracts.artifacts import PersistedContractModel

GAME_CONTRACT_SCHEMA_VERSION = 3

#: Cameras this repository has a recipe for. One member today, by design: the enum exists so the
#: second one is an addition rather than a rewrite, and so a game authored for a camera nobody
#: has implemented fails at the binding instead of halfway through a paid run.
CameraProjection = Literal["side_view_2d"]

#: How a role's artwork is drawn from the game's camera.
#:
#: `side` is the scrolling camera's own view and the only orientation an animation strip is drawn
#: in - the runtime mirrors a side-view sprite to turn it around, which is meaningless for a front
#: view. `front` faces the viewer and `three_quarter` sits between them; both are still-only.
RoleOrientation = Literal["side", "front", "three_quarter"]

#: Whether a role ships as a multi-frame strip or a single drawn cell.
RoleAnimation = Literal["strip", "still"]

#: Widest and narrowest builds an author may state, matching `recipes.scrolling_preview
#: .proportion`. Repeated as bounds rather than imported because this component may not import a
#: recipe; the pair is asserted equal in `tests/unit/components/game_contract/test_models.py`.
MINIMUM_HEADS_TALL = 2.0
MAXIMUM_HEADS_TALL = 8.0

_MINIMUM_STYLE_KEYWORDS = 3
_MAXIMUM_STYLE_KEYWORDS = 10


def _normalized_text(value: str, label: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized != normalized.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return normalized


def _rounded_heads(value: float, label: str) -> float:
    if value < MINIMUM_HEADS_TALL or value > MAXIMUM_HEADS_TALL:
        raise ValueError(
            f"{label} must be between {MINIMUM_HEADS_TALL} and {MAXIMUM_HEADS_TALL} heads"
        )
    # One decimal, for the same reason the recipe rounds: finer distinctions do not survive a
    # sprite a few hundred pixels tall, and rounding keeps the run tag stable across equivalent
    # authored values.
    return round(value, 1)


class CameraDirection(PersistedContractModel):
    """Which camera this game is authored for."""

    projection: CameraProjection


class StyleDirection(PersistedContractModel):
    """The words that carry this game's look into every image prompt.

    Ordering is preserved as authored. The keywords are rendered into one clause in the order
    they are written, so an author who leads with the medium gets a clause that leads with the
    medium, and re-ordering the list is a real edit that re-forks the run.
    """

    keywords: list[str] = Field(
        min_length=_MINIMUM_STYLE_KEYWORDS, max_length=_MAXIMUM_STYLE_KEYWORDS
    )
    avoid: list[str] = Field(default_factory=list)

    @field_validator("keywords", "avoid")
    @classmethod
    def validate_unique(cls, value: list[str], info: ValidationInfo) -> list[str]:
        field_name = info.field_name or "style entry"
        normalized = [_normalized_text(item, field_name) for item in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"{field_name} entries must be unique")
        return normalized


class ProportionDirection(PersistedContractModel):
    """One build for the game, with per-body-kind exceptions.

    This is the field the village defect above is fixed by. `heads_tall` is a property of the
    *game*, so the player and every resident resolve their build from the same number and the
    head-matched runtime renders them at the same scale by construction. `by_body_kind` exists
    because one number genuinely does not fit every body: a heron drawn to a human's two heads is
    a different mistake than no direction at all.
    """

    heads_tall: float
    by_body_kind: dict[str, float] = Field(default_factory=dict)

    # `heads_tall = 2` is what an author writes, and TOML decodes it to an `int` that strict
    # validation then refuses for a `float` field with a message about types. Widened before
    # validation rather than by loosening the field, so the stored value is still a float and
    # `True` - an `int` in Python - is still refused.
    @field_validator("heads_tall", "by_body_kind", mode="before")
    @classmethod
    def widen_integer_heads(cls, value: object) -> object:
        if isinstance(value, int) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, dict):
            return {
                key: float(item) if isinstance(item, int) and not isinstance(item, bool) else item
                for key, item in value.items()
            }
        return value

    @field_validator("heads_tall")
    @classmethod
    def validate_heads_tall(cls, value: float) -> float:
        return _rounded_heads(value, "heads_tall")

    @field_validator("by_body_kind")
    @classmethod
    def validate_by_body_kind(cls, value: dict[str, float]) -> dict[str, float]:
        return {
            body_kind: _rounded_heads(heads, f"by_body_kind[{body_kind}]")
            for body_kind, heads in value.items()
        }

    def heads_for(self, body_kind: str) -> float:
        """The build a body of this kind is drawn to."""

        return self.by_body_kind.get(body_kind, self.heads_tall)


class PlayerDirection(PersistedContractModel):
    """How the player's artwork is made.

    `orientation` and `animation` are stated and pinned rather than assumed, so the file records
    what the recipe actually does and a future camera cannot silently inherit a side-view player.
    They are `Literal` singletons because the scrolling recipe produces exactly one player shape:
    six side-view state strips plus an attack and a climb.
    """

    body_kind: str = Field(min_length=1)
    orientation: Literal["side"] = "side"
    animation: Literal["strip"] = "strip"


class ResidentDirection(PersistedContractModel):
    """How every village resident's artwork is made.

    This is the half of the contract that changed what the pipeline draws. Residents used to be
    generated exactly as mobs were - a three-view turnaround, then a four-frame side-view idle
    strip held to the same facing review - and then the runtime drew frame zero and never played
    the animation. Three of the four frames were paid for and discarded, and the one that was
    kept showed a townsperson in profile, walking on the spot, ignoring the player standing in
    front of them.

    `still` and `front` are therefore not settings that happen to be the defaults; they are what
    a person standing in a town looks like. `allow_pose` and `allow_held_prop` open the two
    fields on the generated roster that make four residents read as four people rather than one
    silhouette in four palettes: a stance and something in the hands. Both are opt-out because a
    game can reasonably want its townsfolk uniform, and because a run that turns them off still
    validates against the same closed vocabulary.
    """

    body_kind_default: str = Field(min_length=1)
    orientation: RoleOrientation = "front"
    animation: RoleAnimation = "still"
    allow_pose: bool = True
    allow_held_prop: bool = True

    @model_validator(mode="after")
    def validate_orientation_supports_animation(self) -> ResidentDirection:
        # A strip is a sequence of frames from one fixed camera, and the only camera this
        # repository holds a strip to is the side view: `GridContract.fixed_side_view_frames`
        # measures frame-to-frame symmetry against a side-view ceiling, and the facing review
        # asks which edge the subject points at. Neither question has an answer for a front view,
        # so the combination is refused here rather than failing in the raster gate.
        if self.animation == "strip" and self.orientation != "side":
            raise ValueError("an animated resident strip must be drawn in the side orientation")
        return self


class CastDirection(PersistedContractModel):
    """The two roles this game draws characters for."""

    player: PlayerDirection
    resident: ResidentDirection


class GameContractBinding(PersistedContractModel):
    """Versioned, digest-bound reference to one authored game contract source."""

    schema_version: Literal[1]
    kind: Literal["game-contract-binding-v1"]
    ref: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        normalized = _normalized_text(value, "game contract ref")
        if "\\" in normalized or ":" in normalized or normalized.startswith("/"):
            raise ValueError("game contract ref must be a portable relative path")
        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("game contract ref must not contain empty, dot, or parent segments")
        return normalized


class GameContract(PersistedContractModel):
    """A whole authored game, with independently versioned gameplay mechanisms."""

    schema_version: Literal[3]
    kind: Literal["game-contract-v3"]
    game_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", max_length=96)
    revision: int = Field(ge=1)
    display_name: str
    camera: CameraDirection
    style: StyleDirection
    proportion: ProportionDirection
    cast: CastDirection
    gameplay: GameplayDirection | None = None
    rights: CharacterProfileRights

    @model_validator(mode="before")
    @classmethod
    def materialize_combat_text_default(cls, value: object) -> object:
        """Give the current document one explicit canonical combat-text default.

        The aggregate gameplay model has no implicit mechanism defaults of its own. The contract
        is therefore the single author of this policy: an omitted block materializes
        ``combat-text-v1`` with ``enabled=true``.
        """

        if not isinstance(value, Mapping):
            return value
        materialized = dict(value)
        gameplay = materialized.get("gameplay")
        if "gameplay" not in materialized:
            materialized["gameplay"] = {"combat_text": {}}
        elif isinstance(gameplay, Mapping) and "combat_text" not in gameplay:
            materialized["gameplay"] = {**gameplay, "combat_text": {}}
        return materialized

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return _normalized_text(value, "display_name")

    @model_validator(mode="after")
    def validate_current_shape(self) -> GameContract:
        if self.gameplay is None or self.gameplay.combat_text is None:
            raise ValueError("game-contract-v3 requires gameplay.combat_text")
        return self

    def validate_against(self, vocabulary: GameVocabulary) -> None:
        """Reject every authored word the approved vocabulary does not carry.

        Kept off the pydantic validators on purpose. The vocabulary is a packaged file read from
        disk, and a model that loaded it during validation could not be constructed in a test
        without that file, could not report which resource it disagreed with, and would tie the
        contract's schema to a resource digest. So the shape is validated by pydantic and the
        wording by this call, which every loader in this package makes.
        """

        facets = {vocabulary.style_facet(keyword) for keyword in self.style.keywords}
        if REQUIRED_STYLE_FACET not in facets:
            raise ValueError(
                f"style.keywords must name the {REQUIRED_STYLE_FACET}: without one, the "
                "remaining keywords qualify a style that was never stated"
            )
        approved_avoidances = set(vocabulary.style_avoidances)
        for entry in self.style.avoid:
            if entry not in approved_avoidances:
                raise ValueError(f"unapproved style avoidance: {entry!r}")

        player_body = vocabulary.body(self.cast.player.body_kind)
        if not player_body.people:
            raise ValueError(
                f"cast.player.body_kind {player_body.body_kind!r} is not a body a person has"
            )
        resident_body = vocabulary.body(self.cast.resident.body_kind_default)
        if not resident_body.people:
            raise ValueError(
                f"cast.resident.body_kind_default {resident_body.body_kind!r} is not a body a "
                "person has"
            )
        for body_kind in self.proportion.by_body_kind:
            vocabulary.body(body_kind)

    def heads_for(self, body_kind: str) -> float:
        """The build any body in this game is drawn to. One table, every role."""

        return self.proportion.heads_for(body_kind)

    def mob_population_manifest(
        self,
        *,
        mob_count: int,
        allowed_map_ids: Collection[str] | None = None,
        stage_column_count: int | None = None,
    ) -> dict[str, object] | None:
        """Project population authoring after resolving the generated mob roster."""

        if self.gameplay is None or self.gameplay.mob_population is None:
            return None
        return self.gameplay.mob_population.manifest_projection(
            mob_count=mob_count,
            allowed_map_ids=allowed_map_ids,
            stage_column_count=stage_column_count,
        )

    def combat_text_manifest(self) -> dict[str, object] | None:
        """Project the combat-text policy when this contract declares it."""

        if self.gameplay is None or self.gameplay.combat_text is None:
            return None
        return self.gameplay.combat_text.manifest_projection()


__all__ = [
    "MAXIMUM_HEADS_TALL",
    "MINIMUM_HEADS_TALL",
    "GAME_CONTRACT_SCHEMA_VERSION",
    "CameraDirection",
    "CameraProjection",
    "CastDirection",
    "PlayerDirection",
    "ProportionDirection",
    "ResidentDirection",
    "RoleAnimation",
    "RoleOrientation",
    "StyleDirection",
    "GameContract",
    "GameContractBinding",
]

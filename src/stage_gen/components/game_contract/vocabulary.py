"""The closed word lists an authored game contract is allowed to draw from.

Every prompt this repository sends is assembled from words, and until now most of those words
were invented fresh on each run. A game bible written by a model chose its own adjectives; a
resident's `body_plan` was free prose held only to containing an anatomical noun; the run's look
was whatever the concept image happened to come out as. Two runs of the same prompt could
therefore disagree about the medium, the palette and the build, and nothing in the pipeline could
name what had changed.

A closed vocabulary fixes that by removing the choice rather than by asking more politely for
consistency. An author picks `warm dusk palette` from this file or the contract does not load; a
model picks `leaning_on_counter` from this file or its structured output fails schema validation.
The wording that reaches the provider is then the wording in this file, which is reviewed, brand-
neutral and stable across runs, instead of whatever a model produced that afternoon.

Facets exist because a keyword list that never names a medium does not control a style. Six
facets are recognised - medium, palette, light, shape, surface, mood - and a contract must name
the medium; the rest are optional and are what separates one game from another built on the same
medium.

`body_kinds` carries the anatomy sentence for each kind because that sentence, not the label, is
what an image model can draw from: "elf" is a word, "a slender, upright humanoid body with
tapered ears" is a silhouette. `people` marks the kinds a village resident may be - the four-
legged and limbless kinds are legitimate mobs and are not townsfolk - and is also what lets one
build be shared across a cast: a two-head player and a two-head baker are the same instruction
applied twice, while a quadruped measured in heads is not the same claim at all.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from stage_gen.resources import game_vocabulary_path

GAME_VOCABULARY_SCHEMA_VERSION = 1

StyleFacet = Literal["medium", "palette", "light", "shape", "surface", "mood"]

#: The facet a contract must name. See the module docstring: without a medium the remaining
#: keywords qualify a style that was never stated.
REQUIRED_STYLE_FACET: StyleFacet = "medium"


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class StyleKeyword(_StrictFrozenModel):
    """One approved style word and the aspect of the look it controls."""

    keyword: str = Field(min_length=1)
    facet: StyleFacet


class BodyKind(_StrictFrozenModel):
    """One approved body, with the anatomy sentence that reaches the image model."""

    body_kind: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    anatomy: str = Field(min_length=1)
    #: Whether a village resident may have this body. A quadruped is a fine mob and a poor baker.
    people: bool


class ResidentStance(_StrictFrozenModel):
    """One approved standing or seated pose for a still resident."""

    stance: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    direction: str = Field(min_length=1)


class ResidentProp(_StrictFrozenModel):
    """One approved held object, including the explicit empty-handed case."""

    prop: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    direction: str = Field(min_length=1)


#: The identifier for "holding nothing". Present as a real vocabulary entry rather than as a
#: null, so a roster that means empty hands says so and the prompt says so too - an absent field
#: would leave the image model to decide, which is the freedom this whole module removes.
EMPTY_HANDED_PROP = "none"


class GameVocabulary(_StrictFrozenModel):
    """The whole approved word list, loaded once from the packaged resource."""

    schema_version: Literal[1]
    kind: Literal["game_vocabulary_v1"]
    style_keywords: tuple[StyleKeyword, ...] = Field(min_length=1)
    style_avoidances: tuple[str, ...] = Field(min_length=1)
    body_kinds: tuple[BodyKind, ...] = Field(min_length=1)
    resident_stances: tuple[ResidentStance, ...] = Field(min_length=1)
    resident_props: tuple[ResidentProp, ...] = Field(min_length=1)

    @field_validator("style_avoidances")
    @classmethod
    def validate_avoidances(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not item or item != item.strip():
                raise ValueError("style avoidance must be a non-empty trimmed string")
        if len(set(value)) != len(value):
            raise ValueError("style avoidances must be unique")
        return value

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> GameVocabulary:
        for label, identifiers in (
            ("style keyword", [entry.keyword for entry in self.style_keywords]),
            ("body kind", [entry.body_kind for entry in self.body_kinds]),
            ("resident stance", [entry.stance for entry in self.resident_stances]),
            ("resident prop", [entry.prop for entry in self.resident_props]),
        ):
            if len(set(identifiers)) != len(identifiers):
                raise ValueError(f"{label} identifiers must be unique")
        if not any(entry.facet == REQUIRED_STYLE_FACET for entry in self.style_keywords):
            raise ValueError(f"the vocabulary must offer at least one {REQUIRED_STYLE_FACET}")
        if not any(entry.people for entry in self.body_kinds):
            raise ValueError("the vocabulary must offer at least one people body kind")
        if all(entry.prop != EMPTY_HANDED_PROP for entry in self.resident_props):
            raise ValueError(f"the vocabulary must offer the {EMPTY_HANDED_PROP!r} prop")
        return self

    def style_facet(self, keyword: str) -> StyleFacet:
        for entry in self.style_keywords:
            if entry.keyword == keyword:
                return entry.facet
        raise ValueError(f"unapproved style keyword: {keyword!r}")

    def body(self, body_kind: str) -> BodyKind:
        for entry in self.body_kinds:
            if entry.body_kind == body_kind:
                return entry
        raise ValueError(f"unapproved body kind: {body_kind!r}")

    def stance(self, stance: str) -> ResidentStance:
        for entry in self.resident_stances:
            if entry.stance == stance:
                return entry
        raise ValueError(f"unapproved resident stance: {stance!r}")

    def prop(self, prop: str) -> ResidentProp:
        for entry in self.resident_props:
            if entry.prop == prop:
                return entry
        raise ValueError(f"unapproved resident prop: {prop!r}")

    @property
    def people_body_kinds(self) -> tuple[str, ...]:
        return tuple(entry.body_kind for entry in self.body_kinds if entry.people)

    @property
    def stance_names(self) -> tuple[str, ...]:
        return tuple(entry.stance for entry in self.resident_stances)

    @property
    def prop_names(self) -> tuple[str, ...]:
        return tuple(entry.prop for entry in self.resident_props)


class LoadedGameVocabulary(_StrictFrozenModel):
    """The parsed vocabulary together with the digest of the exact bytes it came from.

    The digest travels into the run tag and into every game-contract identity, so a vocabulary
    edit invalidates the artwork it directed instead of silently sharing a cache with it.
    """

    vocabulary: GameVocabulary
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def load_game_vocabulary(path: str | Path | None = None) -> LoadedGameVocabulary:
    """Load, strictly validate, and digest the packaged game vocabulary."""

    source = game_vocabulary_path() if path is None else Path(path)
    raw = source.read_bytes()
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("game vocabulary must be valid UTF-8") from error
    try:
        # Parsed from JSON text rather than from a decoded mapping: these models are strict, and
        # strict Python-mode validation refuses a `list` for a `tuple` field while JSON-mode
        # validation accepts an array for one. `load_image_style_resources` reads its vocabulary
        # the same way for the same reason.
        vocabulary = GameVocabulary.model_validate_json(document)
    except ValidationError as error:
        raise ValueError(f"invalid game vocabulary: {error}") from error
    return LoadedGameVocabulary(
        vocabulary=vocabulary,
        sha256=sha256(raw).hexdigest(),
    )


__all__ = [
    "EMPTY_HANDED_PROP",
    "REQUIRED_STYLE_FACET",
    "GAME_VOCABULARY_SCHEMA_VERSION",
    "BodyKind",
    "LoadedGameVocabulary",
    "ResidentProp",
    "ResidentStance",
    "StyleFacet",
    "StyleKeyword",
    "GameVocabulary",
    "load_game_vocabulary",
]

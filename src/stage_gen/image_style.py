"""The application's closed image-style vocabulary and its prompt-anchor compiler.

Style is art direction, not a model interface: the engine only knows the
generic ``PromptAnchor`` it is handed. This module owns the closed
``StyleMode``/``ImageAssetKind`` vocabulary, the canonical anchor contract,
and the compiler from an anchor to the engine's prompt-anchor shape.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gnode import PromptAnchor

STYLE_ANCHOR_SCHEMA_VERSION: Literal[1] = 1
STYLE_ANCHOR_RENDERER_VERSION: Literal[1] = 1
STYLE_COMPILER_VERSION: Literal[1] = 1

StyleMode = Literal[
    "cel_shaded_anime_2d",
    "photorealistic_natural",
    "gouache_illustration_2d",
]
ImageAssetKind = Literal[
    "concept_art",
    "character_sprite",
    "environment_background",
    "illustration",
    "asset_sheet",
    "tileable_texture",
    "interface_art",
    "effect_sheet",
]

STYLE_ANCHOR_PREFIX = "Canonical style anchor — "
_SHA256_LENGTH = 64


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class StyleModeSelection(_StrictFrozenModel):
    """The complete and deliberately narrow edge-model output contract."""

    schema_version: Literal[1]
    kind: Literal["image_style_selection_v1"]
    style_mode: StyleMode


class StyleVocabularyMode(_StrictFrozenModel):
    style_mode: StyleMode
    medium_keyword: str = Field(min_length=1)
    observable_traits: tuple[str, ...] = Field(min_length=1)
    asset_treatments: dict[ImageAssetKind, str] = Field(min_length=1)
    exclusions: tuple[str, ...]

    @field_validator("medium_keyword")
    @classmethod
    def validate_keyword(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("medium_keyword must not contain surrounding whitespace")
        return value

    @field_validator("observable_traits", "exclusions")
    @classmethod
    def validate_phrases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not phrase.strip() or phrase != phrase.strip() for phrase in value):
            raise ValueError("style phrases must be non-empty and trimmed")
        if len(set(value)) != len(value):
            raise ValueError("style phrases must be unique")
        return value

    @field_validator("asset_treatments")
    @classmethod
    def validate_treatments(cls, value: dict[ImageAssetKind, str]) -> dict[ImageAssetKind, str]:
        if any(
            not treatment.strip() or treatment != treatment.strip() for treatment in value.values()
        ):
            raise ValueError("asset treatments must be non-empty and trimmed")
        return value


class ImageStyleVocabulary(_StrictFrozenModel):
    schema_version: Literal[1]
    kind: Literal["image_style_vocabulary_v1"]
    modes: tuple[StyleVocabularyMode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_modes(self) -> Self:
        mode_names = [mode.style_mode for mode in self.modes]
        if len(set(mode_names)) != len(mode_names):
            raise ValueError("style_mode entries must be unique")
        return self

    def mode(self, style_mode: StyleMode) -> StyleVocabularyMode:
        for candidate in self.modes:
            if candidate.style_mode == style_mode:
                return candidate
        raise ValueError(f"style_mode {style_mode!r} is not present in the vocabulary")


class CanonicalStyleAnchor(_StrictFrozenModel):
    """Locally materialized style instructions safe for an image boundary."""

    schema_version: Literal[1]
    kind: Literal["canonical_style_anchor_v1"]
    style_mode: StyleMode
    medium_keyword: str = Field(min_length=1)
    observable_traits: tuple[str, ...] = Field(min_length=1)
    asset_treatments: dict[ImageAssetKind, str] = Field(min_length=1)
    exclusions: tuple[str, ...]
    skill_sha256: str = Field(min_length=_SHA256_LENGTH, max_length=_SHA256_LENGTH)
    vocabulary_sha256: str = Field(min_length=_SHA256_LENGTH, max_length=_SHA256_LENGTH)
    resource_sha256: str = Field(min_length=_SHA256_LENGTH, max_length=_SHA256_LENGTH)
    compiler_sha256: str = Field(min_length=_SHA256_LENGTH, max_length=_SHA256_LENGTH)
    compiler_version: Literal[1]

    @field_validator(
        "skill_sha256",
        "vocabulary_sha256",
        "resource_sha256",
        "compiler_sha256",
    )
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError("resource digests must be lowercase SHA-256 values")
        return value


def canonical_style_anchor_bytes(anchor: CanonicalStyleAnchor) -> bytes:
    return json.dumps(
        anchor.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_style_anchor_digest(anchor: CanonicalStyleAnchor) -> str:
    return sha256(canonical_style_anchor_bytes(anchor)).hexdigest()


def render_style_anchor(anchor: CanonicalStyleAnchor, asset_kind: ImageAssetKind) -> str:
    """Render one exact, asset-aware prompt clause from a validated anchor."""

    treatment = anchor.asset_treatments.get(asset_kind)
    if not treatment:
        raise ValueError(f"style anchor has no asset treatment for {asset_kind!r}")
    traits = "; ".join(anchor.observable_traits)
    exclusions = "; ".join(anchor.exclusions)
    rendered = (
        f"{STYLE_ANCHOR_PREFIX}medium: {anchor.medium_keyword}. "
        f"Observable traits: {traits}. Asset treatment: {treatment}."
    )
    if exclusions:
        rendered += f" Exclude: {exclusions}."
    return rendered


def append_style_anchor_once(
    prompt: str,
    anchor: CanonicalStyleAnchor,
    asset_kind: ImageAssetKind,
) -> str:
    """Append the canonical clause idempotently and reject conflicting pre-anchors."""

    rendered = render_style_anchor(anchor, asset_kind)
    occurrences = prompt.count(STYLE_ANCHOR_PREFIX)
    if occurrences == 0:
        return f"{prompt.rstrip()}\n\n{rendered}"
    if occurrences == 1 and rendered in prompt:
        return prompt
    raise ValueError("image prompt already contains a different or malformed style anchor")


def compile_style_prompt_anchor(
    anchor: CanonicalStyleAnchor,
    asset_kind: ImageAssetKind,
) -> PromptAnchor:
    """Compile one anchor into the engine's generic prompt-anchor shape.

    Key order below is the persisted provenance order; it must not change.
    """

    return PromptAnchor(
        clause=render_style_anchor(anchor, asset_kind),
        marker=STYLE_ANCHOR_PREFIX,
        provenance_key="style_anchor",
        provenance={
            "anchor_sha256": canonical_style_anchor_digest(anchor),
            "asset_kind": asset_kind,
            "compiler_sha256": anchor.compiler_sha256,
            "compiler_version": anchor.compiler_version,
            "renderer_version": STYLE_ANCHOR_RENDERER_VERSION,
            "resource_sha256": anchor.resource_sha256,
            "skill_sha256": anchor.skill_sha256,
            "style_mode": anchor.style_mode,
            "vocabulary_sha256": anchor.vocabulary_sha256,
        },
    )


__all__ = [
    "STYLE_ANCHOR_PREFIX",
    "STYLE_ANCHOR_RENDERER_VERSION",
    "STYLE_ANCHOR_SCHEMA_VERSION",
    "STYLE_COMPILER_VERSION",
    "CanonicalStyleAnchor",
    "ImageAssetKind",
    "ImageStyleVocabulary",
    "StyleMode",
    "StyleModeSelection",
    "StyleVocabularyMode",
    "append_style_anchor_once",
    "canonical_style_anchor_bytes",
    "canonical_style_anchor_digest",
    "compile_style_prompt_anchor",
    "render_style_anchor",
]

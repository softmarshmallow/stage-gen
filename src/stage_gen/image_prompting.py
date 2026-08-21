"""Trusted pre-image style compilation from tracked packaged resources."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from stage_gen.components.image_generation.style import (
    STYLE_ANCHOR_RENDERER_VERSION,
    STYLE_COMPILER_VERSION,
    CanonicalStyleAnchor,
    ImageAssetKind,
    ImageStyleVocabulary,
    StyleModeSelection,
    canonical_style_anchor_digest,
)
from stage_gen.components.structured_generation import (
    StructuredGenerationRequest,
    StructuredOutputSchema,
)
from stage_gen.reliability import CancellationToken
from stage_gen.resources import image_style_skill_path, image_style_vocabulary_path

IMAGE_STYLE_SKILL_NAME = "anchor-image-style"
IMAGE_STYLE_SELECTION_SCHEMA = "image_style_selection_v1"

_EXPECTED_STYLE_MODES = {
    "cel_shaded_anime_2d",
    "photorealistic_natural",
    "gouache_illustration_2d",
}
_EXPECTED_ASSET_KINDS = {
    "concept_art",
    "character_sprite",
    "environment_background",
    "illustration",
    "asset_sheet",
    "tileable_texture",
    "interface_art",
    "effect_sheet",
}


@dataclass(frozen=True, slots=True)
class ImageStyleSkill:
    name: str
    description: str
    body: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ImageStyleResources:
    skill: ImageStyleSkill
    vocabulary: ImageStyleVocabulary
    vocabulary_document: str
    vocabulary_sha256: str
    resource_sha256: str
    compiler_sha256: str


def load_image_style_skill(path: str | Path | None = None) -> ImageStyleSkill:
    """Load and strictly validate the exact UTF-8 runtime skill bytes."""

    source = image_style_skill_path() if path is None else Path(path)
    raw = source.read_bytes()
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("image style skill must be valid UTF-8") from error
    if not document.startswith("---\n"):
        raise ValueError("image style skill must begin with YAML frontmatter")
    closing = document.find("\n---\n", 4)
    if closing < 0:
        raise ValueError("image style skill frontmatter is not terminated")
    frontmatter: dict[str, str] = {}
    for line in document[4:closing].splitlines():
        key, separator, value = line.partition(":")
        normalized_key = key.strip()
        normalized_value = value.strip()
        if (
            not separator
            or normalized_key not in {"name", "description"}
            or not normalized_value
            or normalized_key in frontmatter
        ):
            raise ValueError("image style skill frontmatter is invalid")
        frontmatter[normalized_key] = normalized_value
    if set(frontmatter) != {"name", "description"}:
        raise ValueError("image style skill frontmatter must contain name and description")
    if frontmatter["name"] != IMAGE_STYLE_SKILL_NAME:
        raise ValueError(f"image style skill name must be {IMAGE_STYLE_SKILL_NAME!r}")
    body = document[closing + len("\n---\n") :]
    if body.startswith("\n"):
        body = body[1:]
    if not body.strip():
        raise ValueError("image style skill body must be non-empty")
    return ImageStyleSkill(
        name=frontmatter["name"],
        description=frontmatter["description"],
        body=body,
        sha256=sha256(raw).hexdigest(),
    )


def load_image_style_resources(
    *,
    skill_path: str | Path | None = None,
    vocabulary_path: str | Path | None = None,
) -> ImageStyleResources:
    """Load, validate, and digest both style-compiler resources."""

    skill = load_image_style_skill(skill_path)
    source = image_style_vocabulary_path() if vocabulary_path is None else Path(vocabulary_path)
    raw = source.read_bytes()
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("image style vocabulary must be valid UTF-8") from error
    vocabulary = ImageStyleVocabulary.model_validate_json(document)
    mode_names = {mode.style_mode for mode in vocabulary.modes}
    if mode_names != _EXPECTED_STYLE_MODES:
        raise ValueError("image style vocabulary must contain exactly the supported modes")
    for mode in vocabulary.modes:
        if set(mode.asset_treatments) != _EXPECTED_ASSET_KINDS:
            raise ValueError("every style mode must define every supported asset treatment")
    vocabulary_sha256 = sha256(raw).hexdigest()
    resource_sha256 = _canonical_digest(
        {
            "skill_sha256": skill.sha256,
            "vocabulary_sha256": vocabulary_sha256,
        }
    )
    compiler_sha256 = _canonical_digest(
        {
            "anchor_kind": "canonical_style_anchor_v1",
            "compiler_version": STYLE_COMPILER_VERSION,
            "renderer_version": STYLE_ANCHOR_RENDERER_VERSION,
            "selection_schema": StyleModeSelection.model_json_schema(),
        }
    )
    return ImageStyleResources(
        skill=skill,
        vocabulary=vocabulary,
        vocabulary_document=document,
        vocabulary_sha256=vocabulary_sha256,
        resource_sha256=resource_sha256,
        compiler_sha256=compiler_sha256,
    )


def materialize_style_anchor(
    selection: StyleModeSelection,
    resources: ImageStyleResources,
) -> CanonicalStyleAnchor:
    """Resolve an edge-selected mode into trusted local prompt material."""

    mode = resources.vocabulary.mode(selection.style_mode)
    return CanonicalStyleAnchor(
        schema_version=1,
        kind="canonical_style_anchor_v1",
        style_mode=mode.style_mode,
        medium_keyword=mode.medium_keyword,
        observable_traits=mode.observable_traits,
        asset_treatments=mode.asset_treatments,
        exclusions=mode.exclusions,
        skill_sha256=resources.skill.sha256,
        vocabulary_sha256=resources.vocabulary_sha256,
        resource_sha256=resources.resource_sha256,
        compiler_sha256=resources.compiler_sha256,
        compiler_version=STYLE_COMPILER_VERSION,
    )


def image_style_compiler_cache_key(
    prompt: str,
    asset_kinds: Sequence[ImageAssetKind],
    *,
    resources: ImageStyleResources | None = None,
) -> str:
    """Return the resource-bound identity for a pre-image style decision."""

    loaded = resources or load_image_style_resources()
    kinds = _validated_asset_kinds(asset_kinds)
    return _canonical_digest(
        {
            "asset_kinds": sorted(kinds),
            "compiler_version": STYLE_COMPILER_VERSION,
            "compiler_sha256": loaded.compiler_sha256,
            "prompt_sha256": sha256(prompt.encode("utf-8")).hexdigest(),
            "resource_sha256": loaded.resource_sha256,
        }
    )


def build_image_style_compiler_request(
    *,
    prompt: str,
    artifact_path: str | Path,
    asset_kinds: Sequence[ImageAssetKind],
    resources: ImageStyleResources | None = None,
    timeout_seconds: float | None = None,
    cancellation: CancellationToken | None = None,
) -> StructuredGenerationRequest[CanonicalStyleAnchor]:
    """Build the only edge-model operation used by the style compiler."""

    if not prompt.strip():
        raise ValueError("style compiler prompt must be non-empty")
    loaded = resources or load_image_style_resources()
    kinds = _validated_asset_kinds(asset_kinds)
    cache_key = image_style_compiler_cache_key(prompt, kinds, resources=loaded)
    system = (
        f"{loaded.skill.body.rstrip()}\n\n"
        "The following JSON vocabulary is trusted and exhaustive.\n"
        f"APPROVED_IMAGE_STYLE_VOCABULARY_JSON:\n{loaded.vocabulary_document.rstrip()}"
    )
    edge_prompt = (
        "Select one approved style_mode for the requested asset set.\n"
        f"ASSET_KINDS_JSON: {json.dumps(sorted(kinds), separators=(',', ':'))}\n"
        f"CREATIVE_BRIEF_JSON_STRING: {json.dumps(prompt, ensure_ascii=False)}"
    )

    def parse(value: object) -> CanonicalStyleAnchor:
        selection = StyleModeSelection.model_validate(value)
        return materialize_style_anchor(selection, loaded)

    def validate(anchor: CanonicalStyleAnchor) -> dict[str, object]:
        for asset_kind in kinds:
            if asset_kind not in anchor.asset_treatments:
                raise ValueError(f"selected style lacks treatment for {asset_kind!r}")
        return {
            "anchor_sha256": canonical_style_anchor_digest(anchor),
            "asset_kinds": sorted(kinds),
            "compiler_version": STYLE_COMPILER_VERSION,
            "compiler_sha256": loaded.compiler_sha256,
            "resource_sha256": loaded.resource_sha256,
            "skill_sha256": loaded.skill.sha256,
            "vocabulary_sha256": loaded.vocabulary_sha256,
        }

    return StructuredGenerationRequest(
        prompt=edge_prompt,
        artifact_path=artifact_path,
        schema=StructuredOutputSchema(
            name=IMAGE_STYLE_SELECTION_SCHEMA,
            json_schema=StyleModeSelection.model_json_schema(),
            description="Select exactly one approved image style mode.",
            strict=True,
        ),
        parse=parse,
        system=system,
        metadata={
            "cache_key": cache_key,
            "compiler_sha256": loaded.compiler_sha256,
            "compiler_version": STYLE_COMPILER_VERSION,
            "renderer_version": STYLE_ANCHOR_RENDERER_VERSION,
            "resource_sha256": loaded.resource_sha256,
            "skill_name": loaded.skill.name,
            "skill_sha256": loaded.skill.sha256,
            "vocabulary_sha256": loaded.vocabulary_sha256,
        },
        timeout_seconds=timeout_seconds,
        cancellation=cancellation,
        artifact_value=lambda anchor: anchor.model_dump(mode="json"),
        validate=validate,
        provenance_schema_version=2,
    )


def _validated_asset_kinds(
    asset_kinds: Sequence[ImageAssetKind],
) -> tuple[ImageAssetKind, ...]:
    kinds = tuple(asset_kinds)
    if not kinds:
        raise ValueError("style compiler requires at least one asset_kind")
    if len(set(kinds)) != len(kinds):
        raise ValueError("style compiler asset_kinds must be unique")
    if any(kind not in _EXPECTED_ASSET_KINDS for kind in kinds):
        raise ValueError("style compiler asset_kind is unsupported")
    return kinds


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


__all__ = [
    "IMAGE_STYLE_SELECTION_SCHEMA",
    "IMAGE_STYLE_SKILL_NAME",
    "ImageStyleResources",
    "ImageStyleSkill",
    "build_image_style_compiler_request",
    "image_style_compiler_cache_key",
    "load_image_style_resources",
    "load_image_style_skill",
    "materialize_style_anchor",
]

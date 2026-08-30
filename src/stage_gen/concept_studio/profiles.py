"""Current model-specific request profiles for concept images."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from gnode import ImageQuality, ImageResolution

GPT_IMAGE_2: Literal["openai/gpt-image-2"] = "openai/gpt-image-2"
GROK_IMAGINE_IMAGE_2: Literal["x-ai/grok-imagine-image-2.0"] = "x-ai/grok-imagine-image-2.0"

ConceptImageModel = Literal[
    "openai/gpt-image-2",
    "x-ai/grok-imagine-image-2.0",
]


@dataclass(frozen=True, slots=True)
class ConceptImageModelProfile:
    model: ConceptImageModel
    aliases: frozenset[str]
    qualities: frozenset[ImageQuality]
    resolutions: frozenset[ImageResolution]
    aspect_ratios: frozenset[str]
    maximum_references: int
    default_quality: ImageQuality
    default_resolution: ImageResolution | None


@dataclass(frozen=True, slots=True)
class ConceptImageExecution:
    profile: ConceptImageModelProfile
    quality: ImageQuality
    resolution: ImageResolution | None
    aspect_ratio: str


_PROFILES = (
    ConceptImageModelProfile(
        model=GPT_IMAGE_2,
        aliases=frozenset({GPT_IMAGE_2, "gpt", "gpt-image-2"}),
        qualities=frozenset({"auto", "low", "medium", "high"}),
        resolutions=frozenset(),
        aspect_ratios=frozenset(
            {"auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "21:9"}
        ),
        maximum_references=16,
        default_quality="high",
        default_resolution=None,
    ),
    ConceptImageModelProfile(
        model=GROK_IMAGINE_IMAGE_2,
        aliases=frozenset(
            {
                GROK_IMAGINE_IMAGE_2,
                "grok",
                "grok-image-2",
                "grok-imagine-image-2.0",
            }
        ),
        qualities=frozenset({"low", "medium"}),
        resolutions=frozenset({"1K", "2K"}),
        aspect_ratios=frozenset(
            {
                "auto",
                "1:1",
                "3:4",
                "4:3",
                "9:16",
                "16:9",
                "2:3",
                "3:2",
                "9:19.5",
                "19.5:9",
                "9:20",
                "20:9",
                "1:2",
                "2:1",
            }
        ),
        maximum_references=3,
        default_quality="low",
        default_resolution="1K",
    ),
)


def resolve_model(value: str) -> ConceptImageModelProfile:
    normalized = value.strip().lower()
    for profile in _PROFILES:
        if normalized in profile.aliases:
            return profile
    supported = ", ".join(profile.model for profile in _PROFILES)
    raise ValueError(f"concept image model must be one of: {supported}")


def resolve_execution(
    *,
    model: str,
    quality: str | None,
    resolution: str | None,
    aspect_ratio: str,
    reference_count: int,
) -> ConceptImageExecution:
    profile = resolve_model(model)
    selected_quality = cast(ImageQuality, quality or profile.default_quality)
    if selected_quality not in profile.qualities:
        allowed = ", ".join(sorted(profile.qualities))
        raise ValueError(f"{profile.model} quality must be one of: {allowed}")
    selected_resolution = cast(ImageResolution | None, resolution or profile.default_resolution)
    if selected_resolution is not None and selected_resolution not in profile.resolutions:
        allowed = ", ".join(sorted(profile.resolutions)) or "none"
        raise ValueError(f"{profile.model} resolution must be one of: {allowed}")
    if aspect_ratio not in profile.aspect_ratios:
        allowed = ", ".join(sorted(profile.aspect_ratios))
        raise ValueError(f"{profile.model} aspect ratio must be one of: {allowed}")
    if reference_count > profile.maximum_references:
        raise ValueError(
            f"{profile.model} accepts at most {profile.maximum_references} reference images"
        )
    if reference_count < 0:
        raise ValueError("reference count must be non-negative")
    return ConceptImageExecution(
        profile=profile,
        quality=selected_quality,
        resolution=selected_resolution,
        aspect_ratio=aspect_ratio,
    )


def model_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "game_concept_image_model_report_v1",
        "models": [
            {
                "model": profile.model,
                "aliases": sorted(profile.aliases - {profile.model}),
                "qualities": sorted(profile.qualities),
                "resolutions": sorted(profile.resolutions),
                "aspect_ratios": sorted(profile.aspect_ratios),
                "maximum_references": profile.maximum_references,
                "default_quality": profile.default_quality,
                "default_resolution": profile.default_resolution,
            }
            for profile in _PROFILES
        ],
    }

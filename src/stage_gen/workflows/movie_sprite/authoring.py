"""Movie sprite authoring and deterministic preparation of matching endpoint images."""

from __future__ import annotations

import hashlib
import io
import json
from typing import Annotated, Any, Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator

TEMPLATE_VERSION = "movie-sprite-idle-v2"
SYSTEM_PROMPT = (
    "Animate this illustrated sprite as a subtle recurring idle for repeated playback "
    "during dialogue.\n"
    "Use the identical start and end images as the resting pose. Preserve the subject's "
    "identity, proportions, clothing, accessories, illustration style and color palette.\n"
    "By default, keep the head, neck and shoulders fixed throughout: preserve their exact "
    "screen positions, angles, scale and resting outlines. Retain the original head tilt "
    "and shoulder line. No head straightening, turn, tilt, nod or bob; no neck movement; "
    "no shoulder lift, drop, shrug, roll or sway. Keep hair roots and the attachment points "
    "of accessories worn on the head or shoulders anchored to those stationary parts.\n"
    "Place restrained local movement elsewhere, where appropriate to the supplied sprite: "
    "forearms, wrists, hands, loose hair or ear tips, and loose clothing. Breathing may "
    "produce a tiny, slow vertical rise and fall below the fixed shoulder line, without "
    "changing body proportions or volume. Do not drive these motions with shoulder "
    "breathing, a whole-body pulse, torso rocking, balance corrections or external wind. "
    "Preserve the resting pose, planted feet, hand gestures and contact points. Unmentioned "
    "parts need not move.\n"
    "Hold the facial features, gaze and expression still by default. Explicitly requested "
    "blinks, mouth motion or expressions may animate locally without releasing the fixed "
    "head, neck or shoulders.\n"
    "Supplied artistic direction may override a motion default only for the explicitly "
    "named part. A request for breathing, chest, hair or hand motion does not implicitly "
    "permit head, neck or shoulder movement. If user directions conflict, follow the "
    "user's Constraints section.\n"
    "Keep the camera, scale, framing, lighting and uniform green backing fixed. Keep the "
    "full subject inside the frame. Add no scene, text, extra objects, cuts, particles, "
    "cast shadow or sound.\n"
    "Use smooth, understated overlapping movement with a natural return to the starting "
    "pose and compatible motion through the loop boundary."
)


class Authoring(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    canonical_image: str
    prompt: str = ""
    positive_prompts: list[str] = Field(default_factory=list)
    negative_prompts: list[str] = Field(default_factory=list)

    @field_validator("canonical_image")
    @classmethod
    def portable_source(cls, value: str) -> str:
        from pathlib import PurePosixPath

        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
            raise ValueError("canonical_image must be a portable input-root-relative path")
        return value

    @field_validator("positive_prompts", "negative_prompts", mode="before")
    @classmethod
    def normalize_section(cls, value: object) -> list[str]:
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            raise ValueError("prompt section must be text or an ordered list of text")
        return [item for item in items if item.strip()]


class GenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    duration_seconds: Annotated[int, Field(strict=True, ge=1, le=60)] = 8
    resolution: Literal["360p", "720p", "1080p", "4k"] = "720p"
    aspect_ratio: Literal["9:16", "16:9"] = "9:16"
    padding_pixels: Annotated[int, Field(strict=True, ge=1, le=100)] = 32
    alpha_floor: Annotated[int, Field(strict=True, ge=0, le=64)] = 24
    candidate_id: str = "take-01"

    @field_validator("candidate_id")
    @classmethod
    def candidate_name(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
            raise ValueError("candidate_id must be a simple lowercase identifier")
        return value


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def compile_prompt(authoring: Authoring, settings: GenerationSettings) -> str:
    general = authoring.prompt
    if not general.strip() and not authoring.positive_prompts and not authoring.negative_prompts:
        general = (
            "A quiet listening idle with barely perceptible local breathing below the fixed "
            "shoulders and gentle settling of loose hair ends or clothing, where present. "
            "Keep the original pose and contact points."
        )
    sections = [SYSTEM_PROMPT, f"Loop duration: {settings.duration_seconds} seconds."]
    if general.strip():
        sections.append("General direction:\n" + general)
    if authoring.positive_prompts:
        sections.append(
            "Requested motion:\n" + "\n".join("- " + item for item in authoring.positive_prompts)
        )
    if authoring.negative_prompts:
        sections.append(
            "Constraints:\n" + "\n".join("- " + item for item in authoring.negative_prompts)
        )
    return "\n\n".join(sections)


def prepare_endpoint(source: bytes, settings: GenerationSettings) -> tuple[bytes, dict[str, Any]]:
    """Fit meaningful source alpha inside a green plate without repainting art."""
    with Image.open(io.BytesIO(source)) as opened:
        if opened.width * opened.height > 32_000_000:
            raise ValueError("source exceeds local preparation allocation limit")
        rgba = np.array(opened.convert("RGBA"))
    visible = rgba[:, :, 3] > settings.alpha_floor
    if not visible.any():
        raise ValueError("canonical source has no visible subject")
    yy, xx = np.nonzero(visible)
    crop = (int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1)
    rgba[~visible] = 0
    subject = Image.fromarray(rgba).crop(crop)
    width, height = (720, 1280) if settings.aspect_ratio == "9:16" else (1280, 720)
    pad = settings.padding_pixels
    scale = min((width - 2 * pad) / subject.width, (height - 2 * pad) / subject.height)
    resized = subject.resize(
        (round(subject.width * scale), round(subject.height * scale)), Image.Resampling.LANCZOS
    )
    offset = ((width - resized.width) // 2, (height - resized.height) // 2)
    plate = Image.new("RGBA", (width, height), (0, 255, 0, 255))
    plate.alpha_composite(resized, offset)
    output = io.BytesIO()
    plate.convert("RGB").save(output, format="PNG")
    return output.getvalue(), {
        "source_sha256": digest(source),
        "source_size": [rgba.shape[1], rgba.shape[0]],
        "crop_xyxy": list(crop),
        "alpha_floor": settings.alpha_floor,
        "resized_size": list(resized.size),
        "scale_xy": [resized.width / subject.width, resized.height / subject.height],
        "paste_xy": list(offset),
        "endpoint_size": [width, height],
        "background_rgb": [0, 255, 0],
        "method": (
            "clear faint alpha, crop meaningful silhouette, uniform contain resize, alpha composite"
        ),
    }

"""Deterministic, independently inspectable parallax from supplied layer images.

This component does not infer occluded content or extract layers from a finished
reference. Each input is already a layer. Reflection constructs an exact repeat;
whether reflected content is suitable artwork remains a separate review question.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageOps
from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import portable_relative_path, unique_values
from stage_gen.media.codec import decode_rgba, encode_png

PARALLAX_KIND = "parallax-background-v1"


class ParallaxLayer(PersistedContractModel):
    """A supplied layer plus placement; no camera or gameplay system is required."""

    layer_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    source: str
    order: int = 0
    parallax: float = Field(default=1.0, allow_inf_nan=False)
    offset_x: float = Field(default=0.0, allow_inf_nan=False)
    offset_y: float = Field(default=0.0, allow_inf_nan=False)
    repeat_x: bool = True
    repeat_y: bool = False

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return portable_relative_path(value, "parallax layer source")

    @property
    def asset_ref(self) -> str:
        return f"parallax/layers/{self.layer_id}.png"

    def generation_identity(self, source_sha256: str) -> dict[str, object]:
        """Only image preparation inputs; movement and placement cannot redraw pixels."""

        return {
            "source_sha256": source_sha256,
            "repeat_x": self.repeat_x,
            "repeat_y": self.repeat_y,
            "construction": "mirror_repeat_v1",
        }


class ParallaxSpec(PersistedContractModel):
    schema_version: Literal[1] = 1
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)
    layers: list[ParallaxLayer] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_layers(self) -> ParallaxSpec:
        unique_values((layer.layer_id for layer in self.layers), "parallax layer_id")
        return self


@dataclass(frozen=True, slots=True)
class PreparedParallaxLayer:
    data: bytes
    width: int
    height: int
    source_sha256: str


def prepare_parallax_layer(data: bytes, layer: ParallaxLayer) -> PreparedParallaxLayer:
    """Normalize a supplied still to PNG and reflect requested repeating axes."""

    image = decode_rgba(data)
    width, height = image.size
    if width * (2 if layer.repeat_x else 1) > 16384:
        raise ValueError("parallax repeat width exceeds 16384 pixels")
    if height * (2 if layer.repeat_y else 1) > 16384:
        raise ValueError("parallax repeat height exceeds 16384 pixels")
    if layer.repeat_x:
        repeated = Image.new("RGBA", (width * 2, height))
        repeated.paste(image, (0, 0))
        repeated.paste(ImageOps.mirror(image), (width, 0))
        image = repeated
    if layer.repeat_y:
        width, height = image.size
        repeated = Image.new("RGBA", (width, height * 2))
        repeated.paste(image, (0, 0))
        repeated.paste(ImageOps.flip(image), (0, height))
        image = repeated
    return PreparedParallaxLayer(
        data=encode_png(image),
        width=image.width,
        height=image.height,
        source_sha256=hashlib.sha256(data).hexdigest(),
    )


def parallax_manifest(
    spec: ParallaxSpec, prepared: Mapping[str, PreparedParallaxLayer]
) -> dict[str, object]:
    """Portable asset geometry consumed by the browser or a game's own adapter."""

    return {
        "kind": PARALLAX_KIND,
        "schema_version": 1,
        "canvas": {"width": spec.width, "height": spec.height},
        "layers": [
            {
                "layer_id": layer.layer_id,
                "asset_ref": layer.asset_ref,
                "order": layer.order,
                "parallax": layer.parallax,
                "offset_x": layer.offset_x,
                "offset_y": layer.offset_y,
                "repeat_x": layer.repeat_x,
                "repeat_y": layer.repeat_y,
                "width": prepared[layer.layer_id].width,
                "height": prepared[layer.layer_id].height,
            }
            for layer in sorted(spec.layers, key=lambda layer: layer.order)
        ],
        "construction": "mirror_repeat_v1",
        "semantic_review": "not_performed",
    }


def _repeat(image: Image.Image, width: int, height: int) -> Image.Image:
    """Tile with doubling copies, so a one-pixel unit is not a per-pixel loop."""

    result = Image.new("RGBA", (width, height))
    result.paste(image, (0, 0))
    filled_x = min(image.width, width)
    filled_y = min(image.height, height)
    while filled_x < width:
        copied = min(filled_x, width - filled_x)
        result.paste(result.crop((0, 0, copied, filled_y)), (filled_x, 0))
        filled_x += copied
    while filled_y < height:
        copied = min(filled_y, height - filled_y)
        result.paste(result.crop((0, 0, width, copied)), (0, filled_y))
        filled_y += copied
    return result


def render_parallax(
    spec: ParallaxSpec,
    prepared: Mapping[str, PreparedParallaxLayer],
    *,
    scroll_x: float = 0.0,
    scroll_y: float = 0.0,
) -> bytes:
    """Composite one diagnostic frame for arbitrary caller-supplied scroll input."""

    if not math.isfinite(scroll_x) or not math.isfinite(scroll_y):
        raise ValueError("parallax scroll input must be finite")
    canvas = Image.new("RGBA", (spec.width, spec.height))
    for layer in sorted(spec.layers, key=lambda layer: layer.order):
        image = decode_rgba(prepared[layer.layer_id].data)
        projected_x = layer.offset_x - scroll_x * layer.parallax
        projected_y = layer.offset_y - scroll_y * layer.parallax
        if not math.isfinite(projected_x) or not math.isfinite(projected_y):
            raise ValueError("parallax placement exceeds finite coordinate range")
        x = round(projected_x)
        y = round(projected_y)
        if not layer.repeat_x and (x >= spec.width or x + image.width <= 0):
            continue
        if not layer.repeat_y and (y >= spec.height or y + image.height <= 0):
            continue
        if layer.repeat_x:
            x %= image.width
            if x:
                x -= image.width
        if layer.repeat_y:
            y %= image.height
            if y:
                y -= image.height
        target_width = spec.width - x if layer.repeat_x else image.width
        target_height = spec.height - y if layer.repeat_y else image.height
        if target_width <= 0 or target_height <= 0:
            continue
        raster = _repeat(image, target_width, target_height)
        canvas.alpha_composite(raster, (x, y))
    return encode_png(canvas)


def prepare_parallax(
    spec: ParallaxSpec, read_source: Callable[[str], bytes]
) -> dict[str, PreparedParallaxLayer]:
    """Prepare in memory; the host owns confined reads and atomic publication."""

    return {
        layer.layer_id: prepare_parallax_layer(read_source(layer.source), layer)
        for layer in spec.layers
    }


__all__ = [
    "PARALLAX_KIND",
    "ParallaxLayer",
    "ParallaxSpec",
    "PreparedParallaxLayer",
    "parallax_manifest",
    "prepare_parallax",
    "prepare_parallax_layer",
    "render_parallax",
]

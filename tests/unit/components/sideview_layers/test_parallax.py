"""A complete supplied-layer recipe, including independently reusable image caches."""

import pytest
from PIL import Image
from pydantic import ValidationError

from stage_gen.components.sideview_layers.parallax import (
    ParallaxLayer,
    ParallaxSpec,
    prepare_parallax,
    render_parallax,
)
from stage_gen.media.codec import decode_rgba, encode_png


def _source() -> bytes:
    image = Image.new("RGBA", (8, 4), "#182d47")
    for x in range(4):
        for y in range(4):
            image.putpixel((x, y), (80, 120, 160, 255))
    return encode_png(image)


def _spec(offset_x: float = 0.0) -> ParallaxSpec:
    return ParallaxSpec(
        width=32,
        height=8,
        layers=[
            ParallaxLayer(
                layer_id="clouds",
                source="clouds.png",
                parallax=1.0,
                offset_x=offset_x,
                repeat_y=True,
            )
        ],
    )


def test_constructed_repeat_has_exact_edges_and_periodic_playback() -> None:
    spec = _spec()
    prepared = prepare_parallax(spec, lambda _ref: _source())
    image = decode_rgba(prepared["clouds"].data)
    assert image.size == (16, 8)
    assert image.crop((0, 0, 1, 8)).tobytes() == image.crop((15, 0, 16, 8)).tobytes()
    assert render_parallax(spec, prepared) == render_parallax(spec, prepared, scroll_x=16)
    assert render_parallax(spec, prepared) != render_parallax(spec, prepared, scroll_x=4)


def test_layer_request_rejects_traversal_and_nonfinite_placement() -> None:
    with pytest.raises(ValidationError):
        ParallaxLayer(layer_id="clouds", source="../clouds.png")
    with pytest.raises(ValidationError):
        ParallaxLayer(layer_id="clouds", source="clouds.png", parallax=float("inf"))
    spec = _spec()
    spec.layers[0].parallax = 1e308
    prepared = prepare_parallax(spec, lambda _ref: _source())
    with pytest.raises(ValueError, match="finite coordinate"):
        render_parallax(spec, prepared, scroll_x=1e308)

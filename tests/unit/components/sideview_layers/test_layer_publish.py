"""A painted layer's gate and publication: placement, the host's floors, display scale."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from demo_game_tools.input_formats.sideview_stage import PreparedMapLayer
from stage_gen.components.sideview_layers.contract import (
    NON_GENERATIVE_LAYER_FIELDS,
    RUNTIME_ONLY_LAYER_FIELDS,
)
from stage_gen.components.sideview_layers.publish import (
    LAYER_VALIDATION_KIND,
    LayerGate,
    admit_layer_candidate,
    publish_layer,
)


def _layer(**overrides: object) -> PreparedMapLayer:
    fields: dict[str, object] = {
        "layer_id": "hills",
        "plane": "background",
        "order": 1,
        "parallax": 0.4,
        "alpha_mode": "transparent",
        "vertical_anchor": "walk_surface",
        "prompt": "rolling hills",
        "reference_ids": ["ref"],
        "presentation": {
            "contrast": 1.0,
            "saturation": 1.0,
            "atmosphere_color": "#8899aa",
            "atmosphere_strength": 0.0,
            "detail_blur_screen_pixels": 0.0,
        },
    }
    fields.update(overrides)
    return PreparedMapLayer.model_validate(fields)


def _strip(*, transparent_rows: int) -> bytes:
    image = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(transparent_rows, 1024 - transparent_rows):
        draw.line([0, y, 1535, y], fill=(90, 120, 60, 255))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_publishing_places_a_transparent_layer_and_leaves_an_opaque_cover_to_its_anchor() -> None:
    published, record = publish_layer(_layer(), _strip(transparent_rows=200), place_opaque=False)
    assert len(published) > 0
    assert record["kind"] == LAYER_VALIDATION_KIND
    assert record["height"] == 624 and record["width"] == 1536
    assert isinstance(record["placement"], dict)
    assert record["placement"]["vertical_anchor"] == "walk_surface"
    assert record["repeat"]["verdict"] == "pass"  # type: ignore[index]
    cover = _layer(alpha_mode="opaque", vertical_anchor="canvas_cover")
    untouched, cover_record = publish_layer(cover, _strip(transparent_rows=0), place_opaque=False)
    assert cover_record["placement"] is None and cover_record["trim"] == {"trimmed": False}
    assert untouched == _strip(transparent_rows=0)
    _placed, placed_record = publish_layer(cover, _strip(transparent_rows=0), place_opaque=True)
    assert isinstance(placed_record["placement"], dict)


def test_the_provider_gate_applies_the_hosts_floors_only_to_transparent_layers() -> None:
    bare = LayerGate()
    strict = LayerGate(minimum_transparent_fraction=0.5)
    mostly_opaque = _strip(transparent_rows=40)
    admit_layer_candidate(mostly_opaque, transparent=True, gate=bare)
    with pytest.raises(ValueError):
        admit_layer_candidate(mostly_opaque, transparent=True, gate=strict)
    # An opaque plate is never held to the transparency floors.
    admit_layer_candidate(_strip(transparent_rows=0), transparent=False, gate=strict)


def test_display_scale_is_placement_only_and_never_scales_the_cover() -> None:
    """An authored scale reaches the runtime and no image or admission key."""

    assert "display_scale" in NON_GENERATIVE_LAYER_FIELDS
    assert "display_scale" in RUNTIME_ONLY_LAYER_FIELDS
    assert _layer().display_scale == 1.0
    assert _layer(display_scale=1.4).display_scale == 1.4
    for value in (0.4, 3.5, float("nan")):
        with pytest.raises(ValueError):
            _layer(display_scale=value)
    with pytest.raises(ValueError, match="canvas_cover layer cannot declare a display scale"):
        _layer(alpha_mode="opaque", vertical_anchor="canvas_cover", display_scale=1.2)

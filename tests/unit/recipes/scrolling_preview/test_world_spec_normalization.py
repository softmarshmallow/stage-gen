"""Direct tests for canonical scrolling world-layer normalization."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from stage_gen.recipes.scrolling_preview.models import (
    NEAR_FOREGROUND_PARALLAX,
    WORLD_SPEC_NORMALIZATION_VERSION,
    WorldSpec,
    canonicalize_generated_world_spec,
)


def valid_world() -> dict[str, object]:
    kinds = [
        "sun-coin",
        "spore-vial",
        "rune-shard",
        "gate-key",
        "bone-charm",
        "signal-map",
        "flint-tool",
        "thorn-blade",
    ]
    return {
        "world": {"name": "Vale", "one_liner": "A quiet ruin.", "narrative": "Rain falls."},
        "mobs": [
            {
                "tier_label": "scout",
                "body_plan": "winged avian",
                "name": "Mote",
                "brief": "A pale bird.",
            },
            {
                "tier_label": "apex",
                "body_plan": "four-legged quadruped",
                "name": "Maw",
                "brief": "A stone beast.",
            },
        ],
        "obstacles": [
            {
                "sheet_theme": "mossy ruins",
                "props": [{"name": f"prop {index}", "brief": "weathered"} for index in range(8)],
            }
        ],
        "items": [
            {"kind": kind, "name": f"item {index}", "brief": "small"}
            for index, kind in enumerate(kinds)
        ],
        "layers": [
            {
                "id": "deep_sky",
                "title": "Deep sky",
                "z_index": 0,
                "parallax": 0.0,
                "opaque": True,
                "paint_region": "all canvas",
                "description": "Clouds",
            },
            {
                "id": "near_ruins",
                "title": "Near ruins",
                "z_index": 1,
                "parallax": 1.8,
                "opaque": False,
                "paint_region": "lower half",
                "description": "Arches",
            },
        ],
    }


def test_world_schema_enforces_cross_asset_invariants() -> None:
    parsed = WorldSpec.model_validate(valid_world())
    assert len(parsed.items) == 8
    duplicate = valid_world()
    duplicate["mobs"][1]["body_plan"] = "winged avian"  # type: ignore[index]
    with pytest.raises(ValidationError, match="must differ"):
        WorldSpec.model_validate(duplicate)


def test_world_schema_requires_one_canonical_near_foreground() -> None:
    stale = valid_world()
    stale["layers"][1]["parallax"] = 1.0  # type: ignore[index]
    with pytest.raises(ValidationError, match=r"near foreground at parallax=1\.8"):
        WorldSpec.model_validate(stale)

    extra_near = valid_world()
    layers = extra_near["layers"]
    assert isinstance(layers, list)
    layers.insert(
        1,
        {
            "id": "middle_ruins",
            "title": "Middle ruins",
            "z_index": 1,
            "parallax": 1.2,
            "opaque": False,
            "paint_region": "middle",
            "description": "Arches",
        },
    )
    extra_near["layers"][2]["z_index"] = 2  # type: ignore[index]
    with pytest.raises(ValidationError, match="only the front-most"):
        WorldSpec.model_validate(extra_near)


@pytest.mark.parametrize("input_parallax", [1.0, 1.2])
def test_generated_world_canonicalizes_only_frontmost_parallax(
    input_parallax: float,
) -> None:
    payload = valid_world()
    layers = payload["layers"]
    assert isinstance(layers, list)
    layers.insert(
        1,
        {
            "id": "middle_ruins",
            "title": "Middle ruins",
            "z_index": 1,
            "parallax": 0.6,
            "opaque": False,
            "paint_region": "middle",
            "description": "Arches",
        },
    )
    near = layers[2]
    assert isinstance(near, dict)
    near["z_index"] = 2
    near["parallax"] = input_parallax
    source_layers = json.loads(json.dumps(layers))

    result = canonicalize_generated_world_spec(payload)

    assert [layer.id for layer in result.spec.layers] == [
        "deep_sky",
        "middle_ruins",
        "near_ruins",
    ]
    assert result.spec.layers[0].parallax == 0
    assert result.spec.layers[1].parallax == 0.6
    assert result.spec.layers[2].parallax == NEAR_FOREGROUND_PARALLAX
    assert payload["layers"] == source_layers
    record = result.validation["world_spec_normalization"]
    assert isinstance(record, dict)
    assert record == {
        "version": WORLD_SPEC_NORMALIZATION_VERSION,
        "target_layer_id": "near_ruins",
        "target_z_index": 2,
        "input_parallax": input_parallax,
        "output_parallax": NEAR_FOREGROUND_PARALLAX,
        "changed": True,
        "changed_fields": ["layers[2].parallax"],
        "layer_ids": ["deep_sky", "middle_ruins", "near_ruins"],
        "unchanged_layer_ids": ["deep_sky", "middle_ruins"],
        "layer_order_preserved": True,
        "unrelated_layers_unchanged": True,
    }


def test_generated_world_preserves_already_canonical_foreground() -> None:
    result = canonicalize_generated_world_spec(valid_world())
    record = result.validation["world_spec_normalization"]

    assert isinstance(record, dict)
    assert result.spec.layers[-1].parallax == NEAR_FOREGROUND_PARALLAX
    assert record["input_parallax"] == NEAR_FOREGROUND_PARALLAX
    assert record["changed"] is False
    assert record["changed_fields"] == []


def test_generated_world_rejects_missing_or_ambiguous_foreground() -> None:
    missing = valid_world()
    layers = missing["layers"]
    assert isinstance(layers, list)
    missing["layers"] = layers[:1]
    with pytest.raises(ValidationError, match="at least one transparent"):
        canonicalize_generated_world_spec(missing)

    ambiguous = valid_world()
    layers = ambiguous["layers"]
    assert isinstance(layers, list)
    layers.append(
        {
            "id": "near_branches",
            "title": "Near branches",
            "z_index": 1,
            "parallax": 1.0,
            "opaque": False,
            "paint_region": "edges",
            "description": "Branches",
        }
    )
    with pytest.raises(ValidationError, match="exactly one front-most transparent"):
        canonicalize_generated_world_spec(ambiguous)

"""What the runner admits from a painting and publishes: pure, so judges and publishers agree."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from iron_petal_unit_pipeline.admission import (
    RUNNER_LAYER_GATE,
    admit_catalog_candidate,
    admit_motion_candidate,
    admit_transparent_sprite,
    canonicalize_runner_catalog_sprite,
    motion_source_facts,
)
from iron_petal_unit_pipeline.manifest import manifest_ground, manifest_rebase_multipliers
from iron_petal_unit_pipeline.runner_request import resolve_runner_package
from stage_gen.components.sideview_layers.nodes import admit_layer_candidate

from ..._runner_fixture import WIDE_FLAT_ROWS, chunk_toml, runner_only_package


def test_the_motion_vocabulary_is_declared_exactly_once() -> None:
    """The states that validate, the tuple that fans out nodes, and the plate
    band order are all one declaration; editing one without the others emits
    strips no contract admits, or refuses avatars no node serves."""

    from iron_petal_unit_pipeline.content import (
        RUNNER_AVATAR_BASE_MOTION_STATES,
        RUNNER_AVATAR_MOTION_STATES,
        RUNNER_MOTION_ORDER,
    )

    assert frozenset(RUNNER_MOTION_ORDER) == RUNNER_AVATAR_MOTION_STATES
    assert RUNNER_AVATAR_BASE_MOTION_STATES < RUNNER_AVATAR_MOTION_STATES
    # The runtime's copy (web/lib/sideview-runner/contract.ts) pins the same
    # order in its own suite; a drift there fails the web gate.
    assert RUNNER_MOTION_ORDER == ("run", "jump", "slide", "fly", "hurt", "death")


def test_motion_source_requires_meaningful_alpha_in_every_declared_cell() -> None:
    source = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for column in range(4):
        left = column * 384 + 20
        draw.rectangle((left, 300, left + 300, 700), fill=(80, 140, 220, 17))
    for left in (30, 90, 150, 210):
        draw.rectangle((left, 400, left + 40, 500), fill=(80, 140, 220, 255))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    with pytest.raises(ValueError, match="missing a required visible cell"):
        motion_source_facts(encoded.getvalue())


def test_motion_provider_gate_includes_decisive_component_repacking() -> None:
    source = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((20, 300, 1515, 700), fill=(80, 140, 220, 255))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    assert motion_source_facts(encoded.getvalue())["cell_visible_fractions"]
    with pytest.raises(ValueError, match="principal components for 4 required cells"):
        admit_motion_candidate(encoded.getvalue(), anchor="bottom")


def test_motion_provider_gate_refuses_disconnected_rider_components() -> None:
    source = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    for column in range(4):
        left = column * 384 + 90
        draw.rectangle((left, 450, left + 200, 750), fill=(80, 140, 220, 255))
        draw.rectangle((left + 80, 330, left + 110, 380), fill=(240, 180, 90, 255))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    with pytest.raises(ValueError, match="refuses unassigned meaningful alpha components"):
        admit_motion_candidate(encoded.getvalue(), anchor="bottom")


def test_manifest_reads_the_admitted_rebase_states_and_fails_closed_on_shape_drift() -> None:
    states = ("run", "jump", "slide", "death")
    assert manifest_rebase_multipliers(
        {"states": {"death": 0.95, "jump": 1.01, "run": 1, "slide": 0.99}},
        published_states=states,
    ) == {"run": 1.0, "jump": 1.01, "slide": 0.99, "death": 0.95}

    with pytest.raises(ValueError, match="must publish a states object"):
        manifest_rebase_multipliers({"multipliers_by_state": {"run": 1.0}}, published_states=states)
    with pytest.raises(ValueError, match="states differ from published motions"):
        manifest_rebase_multipliers(
            {"states": {"run": 1.0, "jump": 1.0, "slide": 1.0}},
            published_states=states,
        )
    with pytest.raises(ValueError, match="multiplier for death must be positive"):
        manifest_rebase_multipliers(
            {
                "states": {
                    "run": 1.0,
                    "jump": 1.0,
                    "slide": 1.0,
                    "death": float("nan"),
                }
            },
            published_states=states,
        )


def test_catalog_canonicalization_trims_only_a_short_sparse_terminal_prop_tail() -> None:
    source = Image.new("RGBA", (400, 1000), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    draw.rectangle((100, 100, 299, 899), fill=(240, 210, 170, 255))
    draw.rectangle((195, 900, 204, 949), fill=(80, 150, 80, 255))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    prop, _trim, report = canonicalize_runner_catalog_sprite(encoded.getvalue(), family="prop")
    with Image.open(BytesIO(prop)) as opened:
        assert opened.size == (400, 800)
    assert report["applied"] is True
    assert report["tail_rows"] == 50
    assert report["removed_rows"] == 50

    item, _item_trim, item_report = canonicalize_runner_catalog_sprite(
        encoded.getvalue(), family="item"
    )
    with Image.open(BytesIO(item)) as opened:
        assert opened.size == (400, 850)
    assert item_report["applied"] is False
    assert item_report["reason"] == "family_is_not_prop"

    long_tail = source.copy()
    ImageDraw.Draw(long_tail).rectangle((195, 950, 204, 999), fill=(80, 150, 80, 255))
    long_encoded = BytesIO()
    long_tail.save(long_encoded, format="PNG", optimize=False)
    untrimmed, _long_trim, long_report = canonicalize_runner_catalog_sprite(
        long_encoded.getvalue(), family="prop"
    )
    with Image.open(BytesIO(untrimmed)) as opened:
        assert opened.size == (400, 900)
    assert long_report["applied"] is False


def test_catalog_provider_gate_rejects_effectively_invisible_cutouts() -> None:
    source = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((100, 100, 900, 900), fill=(80, 140, 220, 1))
    encoded = BytesIO()
    source.save(encoded, format="PNG", optimize=False)

    with pytest.raises(ValueError, match="meaningful visible alpha"):
        admit_catalog_candidate(encoded.getvalue(), family="prop")

    weak = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(weak).rectangle((100, 100, 900, 900), fill=(80, 140, 220, 32))
    encoded = BytesIO()
    weak.save(encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="no pixels above painted alpha threshold"):
        admit_catalog_candidate(encoded.getvalue(), family="prop")


def test_native_alpha_gates_reject_an_opaque_canvas_with_one_transparent_corner() -> None:
    cutout = Image.new("RGBA", (1024, 1024), (80, 140, 220, 255))
    cutout.putpixel((0, 0), (0, 0, 0, 0))
    encoded = BytesIO()
    cutout.save(encoded, format="PNG", optimize=False)

    with pytest.raises(ValueError, match="transparent negative space"):
        admit_transparent_sprite(encoded.getvalue())
    with pytest.raises(ValueError, match="transparent negative space"):
        admit_catalog_candidate(encoded.getvalue(), family="item")

    layer = Image.new("RGBA", (1536, 1024), (80, 140, 220, 255))
    layer.putpixel((0, 0), (0, 0, 0, 0))
    layer_encoded = BytesIO()
    layer.save(layer_encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent negative space"):
        admit_layer_candidate(layer_encoded.getvalue(), transparent=True, gate=RUNNER_LAYER_GATE)


def test_native_alpha_gates_reject_near_opaque_canvases_below_the_negative_space_floor() -> None:
    cutout = Image.new("RGBA", (1024, 1024), (80, 140, 220, 255))
    ImageDraw.Draw(cutout).rectangle((0, 0, 80, 1023), fill=(0, 0, 0, 0))
    encoded = BytesIO()
    cutout.save(encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent negative space"):
        admit_transparent_sprite(encoded.getvalue())

    layer = Image.new("RGBA", (1536, 1024), (80, 140, 220, 255))
    ImageDraw.Draw(layer).rectangle((0, 0, 60, 1023), fill=(0, 0, 0, 0))
    layer_encoded = BytesIO()
    layer.save(layer_encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent negative space"):
        admit_layer_candidate(layer_encoded.getvalue(), transparent=True, gate=RUNNER_LAYER_GATE)


def test_native_alpha_gates_require_negative_space_to_reach_the_canvas_edge() -> None:
    cutout = Image.new("RGBA", (1024, 1024), (80, 140, 220, 255))
    ImageDraw.Draw(cutout).rectangle((300, 250, 723, 773), fill=(0, 0, 0, 0))
    encoded = BytesIO()
    cutout.save(encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent edge separation"):
        admit_transparent_sprite(encoded.getvalue())

    layer = Image.new("RGBA", (1536, 1024), (80, 140, 220, 255))
    ImageDraw.Draw(layer).rectangle((500, 250, 1035, 773), fill=(0, 0, 0, 0))
    layer_encoded = BytesIO()
    layer.save(layer_encoded, format="PNG", optimize=False)
    with pytest.raises(ValueError, match="transparent edge separation"):
        admit_layer_candidate(layer_encoded.getvalue(), transparent=True, gate=RUNNER_LAYER_GATE)


def test_structural_ground_publishes_one_chunk_per_segment_in_the_manifest(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = runner_only_package(
        tmp_path,
        chunks="\n".join(
            [chunk_toml("warmup_flat", WIDE_FLAT_ROWS), chunk_toml("first_gap", WIDE_FLAT_ROWS)]
        ),
    )
    track = package / "runner/track.toml"
    track.write_text(
        track.read_text(encoding="utf-8").replace(
            'mode = "terrain-atlas-3x3-minimal-v1"', 'mode = "runner-structural-ground-v1"', 1
        ),
        encoding="utf-8",
    )

    ground = manifest_ground(resolve_runner_package(package).runner.track)

    assert ground["mode"] == "runner-structural-ground-v1"
    chunks = ground["chunks"]
    assert isinstance(chunks, list)
    assert [chunk["image"] for chunk in chunks] == [
        "world/ground/warmup_flat.png",
        "world/ground/first_gap.png",
    ]

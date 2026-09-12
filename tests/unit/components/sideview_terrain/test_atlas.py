from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from PIL import Image, ImageDraw

from stage_gen.components.sideview_terrain.atlas import (
    CANONICAL_CELL_PX,
    GRID_COLUMNS,
    GUIDE_INSET_PX,
    GUIDE_RGB,
    PAINT_CANVAS_HEIGHT,
    PAINT_CANVAS_WIDTH,
    PLACEHOLDER_CELL,
    SOURCE_CELL_PX,
    assemble_terrain_atlas,
    cells_from_canonical_atlas,
    compose_canonical_terrain,
    load_terrain_atlas_lookup,
    peering_mask,
    require_terrain_atlas_source,
    terrain_atlas_cells,
    terrain_atlas_generation_prompt,
    terrain_atlas_paint_target,
)
from stage_gen.resources import terrain_atlas_lookup_path, terrain_atlas_template_path
from stage_gen_legacy.recipes.sideview_platformer.climbable_atlas import (
    ClimbableRole,
    nominal_cell_box,
    plan_climbable_atlas,
)
from stage_gen_legacy.recipes.sideview_platformer.prepared_world import (
    _canonicalize_map_presentation,
    _validate_map_presentation_source,
)


def _template() -> bytes:
    return terrain_atlas_template_path().read_bytes()


def _png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _paint_source(
    *,
    base: tuple[int, int, int] = (132, 86, 50),
    patchwork: int = 0,
) -> bytes:
    """A synthetic draw at the provider canvas: the paint target restated in one material.

    Structure is carried by the target's own luminance, so a cap stays lighter than the
    fill it sits on and the sheet exercises the real slicing path. ``patchwork`` offsets
    alternating cells, which is exactly the defect the join-tone gate exists to catch.
    """

    with Image.open(BytesIO(terrain_atlas_paint_target())) as opened:
        image = opened.convert("RGB")
    pixels = image.load()
    assert pixels is not None
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = cast(tuple[int, int, int], pixels[x, y])
            shade = 0.55 + 0.75 * (red * 0.299 + green * 0.587 + blue * 0.114) / 255.0
            variation = ((x // 19 + y // 23) % 9) - 4
            step = 0
            if patchwork:
                cell = (x // SOURCE_CELL_PX + y // SOURCE_CELL_PX) % 2
                step = patchwork if cell else -patchwork
            pixels[x, y] = cast(
                tuple[int, int, int],
                tuple(
                    max(0, min(255, round(channel * shade) + variation + step)) for channel in base
                ),
            )
    return _png(image)


def _flat_source(base: tuple[int, int, int] = (100, 80, 60)) -> bytes:
    return _png(Image.new("RGB", (PAINT_CANVAS_WIDTH, PAINT_CANVAS_HEIGHT), base))


def _busy_source() -> bytes:
    """One pebble in the middle of every cell: the lattice a repeated tile makes."""

    with Image.open(BytesIO(_paint_source())) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    for row in range(4):
        for column in range(12):
            left = column * SOURCE_CELL_PX + SOURCE_CELL_PX // 8
            top = row * SOURCE_CELL_PX + SOURCE_CELL_PX // 8
            draw.ellipse(
                (left, top, left + (SOURCE_CELL_PX * 3) // 4, top + (SOURCE_CELL_PX * 3) // 4),
                fill=(226, 218, 198),
            )
    return _png(image)


def _climbable_source(roles: Sequence[str]) -> tuple[bytes, tuple[int, int]]:
    """One synthetic atlas column per declared role, at the plan's own request size."""

    plan = plan_climbable_atlas(len(roles))
    image = Image.new("RGBA", (plan.width_px, plan.height_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index, role in enumerate(roles):
        left, top, right, bottom = nominal_cell_box(plan, index)
        centre = (left + right) // 2
        if role == "ladder":
            # Two rails plus rungs: wide enough to land inside the ladder aspect envelope.
            draw.rectangle(
                (centre - 90, top + 40, centre - 50, bottom - 40), fill=(116, 74, 37, 255)
            )
            draw.rectangle(
                (centre + 50, top + 40, centre + 90, bottom - 40), fill=(116, 74, 37, 255)
            )
            for y in range(top + 120, bottom - 80, 120):
                draw.rectangle((centre - 50, y, centre + 50, y + 28), fill=(172, 122, 61, 255))
        else:
            # A single narrow strand, which only the rope envelope admits.
            draw.rectangle(
                (centre - 16, top + 40, centre + 16, bottom - 40), fill=(202, 174, 117, 255)
            )
    return _png(image), (plan.width_px, plan.height_px)


def _presentation_source(asset: str) -> bytes:
    assert asset == "portal"
    image = Image.new("RGBA", (1536, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if True:
        for left in (150, 900):
            draw.rectangle((left, 180, left + 55, 850), fill=(202, 174, 117, 255))
            draw.rectangle((left + 330, 180, left + 385, 850), fill=(202, 174, 117, 255))
            draw.rectangle((left, 150, left + 385, 240), fill=(202, 174, 117, 255))
    return _png(image)


def test_lookup_has_47_unique_and_reachable_masks() -> None:
    lookup = load_terrain_atlas_lookup()
    assert len(lookup.by_mask) == 47
    assert len(set(lookup.by_mask.values())) == 47
    observed = set()
    for bits in range(256):
        occupied = [[False] * 3 for _ in range(3)]
        occupied[1][1] = True
        positions = ((0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2), (1, 2), (2, 2))
        for index, (x, y) in enumerate(positions):
            occupied[y][x] = bool((bits >> index) & 1)
        frozen = tuple(tuple(row) for row in occupied)
        observed.add(peering_mask(frozen, 1, 1))
    assert observed == set(lookup.by_mask)


def test_host_consumer_lookup_matches_the_authoritative_packaged_contract() -> None:
    # Byte equality, not JSON equality: nothing generates one file from the
    # other, so the only affordable sync proof is that there is exactly one
    # sequence of bytes on both sides of the language boundary.
    #
    # The consumer used to be the browser's `web/lib/sideview/`, which was
    # deleted with the rest of the browser platformer in decision 0069. The
    # copy did not go with it: the Godot host reads the same table from its
    # own project, so the drift this guards against is exactly as possible as
    # it was, and the assertion only changed which file it points at.
    repository = Path(__file__).parents[4]
    consumer = (
        repository / "godot/legacy/runtime/families/sideview/terrain/lookup.json"
    ).read_bytes()
    authoritative = terrain_atlas_lookup_path().read_bytes()
    assert consumer == authoritative


@pytest.mark.parametrize("mutation", ("missing", "duplicate"))
def test_missing_or_duplicate_lookup_entries_fail_closed(mutation: str) -> None:
    payload = json.loads(terrain_atlas_lookup_path().read_text(encoding="utf-8"))
    keys = list(payload["lookup"])
    if mutation == "missing":
        del payload["lookup"][keys[0]]
    else:
        payload["lookup"][keys[1]] = payload["lookup"][keys[0]]
    with pytest.raises(ValueError):
        load_terrain_atlas_lookup(json.dumps(payload).encode("utf-8"))


@pytest.mark.parametrize(
    "rows",
    (
        ("00000000", "11111111", "11111111"),
        ("000000000", "011111110", "000000000"),
        ("000000111", "000011111", "001111111", "111111111"),
        ("111111111", "110000011", "110111011", "110101011", "111111111"),
    ),
)
def test_composes_solid_floating_steps_concavities_and_holes(rows: tuple[str, ...]) -> None:
    canonical, report = assemble_terrain_atlas(_paint_source())
    assert report["classification"] == "direct_pass"
    composed, composition = compose_canonical_terrain(canonical, rows)
    with Image.open(BytesIO(composed)) as image:
        assert image.size == (len(rows[0]) * CANONICAL_CELL_PX, len(rows) * CANONICAL_CELL_PX)
    coordinates = cast(list[list[list[int] | None]], composition["coordinates"])
    assert sum(cell is not None for row in coordinates for cell in row) == sum(
        line.count("1") for line in rows
    )
    metrics = cast(dict[str, float], composition["connector_metrics"])
    # Every published tile is opaque, so a join can no longer disagree about coverage.
    assert metrics["connector_alpha_mismatch_fraction"] == 0.0


def test_draw_is_locally_canonicalized_into_locked_direct_pass_atlas() -> None:
    source = _paint_source()
    source_report = require_terrain_atlas_source(source)
    canonical, report = assemble_terrain_atlas(source)

    assert source_report["contract"] == "terrain-atlas-paintover-source-v9"
    assert source_report["registration"] == "fixed-pitch-exact-canvas-v1"
    assert report["canonicalizer"] == "terrain-atlas-paintover-canonicalization-v10"
    assert report["classification"] == "direct_pass"
    # The connector figure is a fact now, not a gate. It used to be measured after a
    # three-pixel median blend had overwritten the very pixels it samples, so it read zero
    # on every draw; the blend is gone because it stamped a pale lattice down every join.
    assert cast(float, report["connector_rgb_mean"]) >= 0.0
    assert cast(dict[str, object], report["construction"])["connector_harmonization"] == "none"
    assert report["template_sha256"] == sha256(_template()).hexdigest()
    assert report["paint_target_sha256"] == sha256(terrain_atlas_paint_target()).hexdigest()
    assert report["lookup_sha256"] == sha256(terrain_atlas_lookup_path().read_bytes()).hexdigest()
    cells = cells_from_canonical_atlas(canonical)
    assert cells[(10, 1)].getchannel("A").getextrema() == (0, 0)
    lookup = load_terrain_atlas_lookup()
    # The published sheet carries no holes at all. The magenta chroma key it replaces was
    # eating the template's own pale-pink rock highlights, and every atlas published under
    # it carried 31,701 transparent pixels through solid ground.
    assert cast(dict[str, object], report["canonical"])["published_transparent_pixels"] == 0
    for coordinate in lookup.by_mask.values():
        assert cells[coordinate].getchannel("A").getextrema() == (255, 255)


def test_paint_target_packs_the_locked_template_behind_a_hairline_fence() -> None:
    target = terrain_atlas_paint_target()
    assert target == terrain_atlas_paint_target(_template())
    with Image.open(BytesIO(target)) as opened:
        packed = opened.convert("RGB")
    assert packed.size == (PAINT_CANVAS_WIDTH, PAINT_CANVAS_HEIGHT)
    pixels = cast("list[tuple[int, int, int]]", list(packed.get_flattened_data()))
    # Magenta is gone for good: it was never a keep-out marker, only art the chroma key ate.
    for red, green, blue in pixels:
        assert not (red > 180 and blue > 180 and green < 80), "magenta survived packing"
    # The fence is there, and only on the boundaries.
    for column in range(GRID_COLUMNS + 1):
        x = min(max(column * SOURCE_CELL_PX, 1), PAINT_CANVAS_WIDTH - 2)
        assert packed.getpixel((x, PAINT_CANVAS_HEIGHT // 2)) == GUIDE_RGB
    middle = packed.getpixel((SOURCE_CELL_PX // 2, SOURCE_CELL_PX // 2))
    assert middle != GUIDE_RGB, "a cell interior is fenced"
    # The reserved cell goes to the provider as ordinary buried ground. A grey checker is
    # the universal picture of transparency, and handed one the model painted that cell in
    # a different material from every other cell on the sheet.
    filler = load_terrain_atlas_lookup().by_mask[(1,) * 9]

    def target_cell(coordinate: tuple[int, int]) -> bytes:
        column, row = coordinate
        return packed.crop(
            (
                column * SOURCE_CELL_PX + GUIDE_INSET_PX,
                row * SOURCE_CELL_PX + GUIDE_INSET_PX,
                (column + 1) * SOURCE_CELL_PX - GUIDE_INSET_PX,
                (row + 1) * SOURCE_CELL_PX - GUIDE_INSET_PX,
            )
        ).tobytes()

    assert target_cell(PLACEHOLDER_CELL) == target_cell(filler), (
        "the checker placeholder reached the paint target"
    )
    # And the published cell is cut inside it, so no fence pixel is ever published.
    for cell in terrain_atlas_cells(target).values():
        for red, green, blue, _alpha in cast(
            "list[tuple[int, int, int, int]]", list(cell.get_flattened_data())
        ):
            assert not (red < 80 and green > 170 and blue > 170), "a fence pixel was published"


def test_material_appearance_changes_canonical_rgb_without_opening_the_silhouette() -> None:
    first, _ = assemble_terrain_atlas(_paint_source())
    second, _ = assemble_terrain_atlas(_paint_source(base=(76, 62, 118)))
    with Image.open(BytesIO(first)) as opened:
        first_image = opened.convert("RGBA")
    with Image.open(BytesIO(second)) as opened:
        second_image = opened.convert("RGBA")

    assert first_image.getchannel("A").tobytes() == second_image.getchannel("A").tobytes()
    assert first_image.convert("RGB").tobytes() != second_image.convert("RGB").tobytes()


def test_source_refuses_a_wrong_canvas_flat_material_and_cell_to_cell_tone_drift() -> None:
    wrong_canvas = Image.new("RGB", (1600, 900), (100, 80, 60))
    with pytest.raises(ValueError, match="must be exactly 2880x960"):
        require_terrain_atlas_source(_png(wrong_canvas))

    with pytest.raises(ValueError, match="lacks usable painted material variation"):
        require_terrain_atlas_source(_flat_source())

    # The defect that survives every structural check: forty-seven separate paintings of
    # one material that do not agree on its value, which composes as visible patchwork.
    # Measured on published atlases rather than invented -- the two whose material a
    # reviewer accepted score 26.3, the one the reviewer complained about scores 84.6.
    admitted = require_terrain_atlas_source(_paint_source())
    assert cast(float, admitted["worst_join_tone_step"]) < 65.0
    with pytest.raises(ValueError, match="do not share one tone"):
        require_terrain_atlas_source(_paint_source(patchwork=60))

    # How much of the repeated hillside tile reads as an object is recorded, never refused.
    # Three thresholds were tried and none ordered the corpus: the atlas a reviewer liked
    # scores 0.157 on its largest region, a hillside visibly chained with repeated boulders
    # scores 0.179, and a sheet that reads well scores 0.345. Whether a repeat is legible is
    # a judgement for the semantic review, not a statistic.
    assert 0.0 <= cast(float, admitted["hillside_tile_object_share"]) <= 1.0
    busy = require_terrain_atlas_source(_busy_source())
    assert cast(float, busy["hillside_tile_object_share"]) > cast(
        float, admitted["hillside_tile_object_share"]
    )


def test_portal_presentation_is_repacked_from_native_alpha() -> None:
    source = _presentation_source("portal")
    facts = _validate_map_presentation_source(source, asset="portal", expected_size=(1536, 1024))
    canonical, report = _canonicalize_map_presentation(source, asset="portal")

    assert facts["required_subject_count"] == 2
    assert report["selected_component_count"] == 2
    with Image.open(BytesIO(canonical)) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getextrema()[0] == 0


@pytest.mark.parametrize(
    "roles",
    (
        ("ladder",),
        ("ladder", "rope"),
        ("ladder", "ladder", "ladder", "rope", "rope", "rope"),
    ),
)
def test_climbable_atlas_is_repacked_one_cell_per_declared_variant(
    roles: tuple[ClimbableRole, ...],
) -> None:
    source, size = _climbable_source(roles)
    facts = _validate_map_presentation_source(
        source, asset="climbable", expected_size=size, roles=roles
    )
    canonical, report = _canonicalize_map_presentation(source, asset="climbable", roles=roles)

    assert facts["required_subject_count"] == len(roles)
    assert facts["index_order"] == "left_to_right"
    assert report["selected_component_count"] == len(roles)
    assert report["atlas_roles"] == list(roles)
    with Image.open(BytesIO(canonical)) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getextrema()[0] == 0


def test_climbable_rejects_a_column_whose_silhouette_is_not_its_declared_role() -> None:
    # A sheet of two ladders, declared as one ladder and one rope. The rope column is far too
    # wide for a strand, which is exactly what the per-role envelope exists to catch.
    source, size = _climbable_source(("ladder", "ladder"))

    with pytest.raises(ValueError, match="does not hold a rope silhouette"):
        _validate_map_presentation_source(
            source, asset="climbable", expected_size=size, roles=("ladder", "rope")
        )


def test_climbable_rejects_a_sheet_carrying_more_subjects_than_declared() -> None:
    # Three drawn columns, two declared. The extra component must fail admission rather than be
    # silently dropped in favour of whichever two happened to have the most area.
    source, _ = _climbable_source(("ladder", "ladder", "ladder"))
    two = plan_climbable_atlas(2)

    with pytest.raises(ValueError):
        _validate_map_presentation_source(
            source,
            asset="climbable",
            expected_size=(two.width_px, two.height_px),
            roles=("ladder", "ladder"),
        )


def test_validation_report_is_portable_and_prompt_is_material_neutral() -> None:
    _, report = assemble_terrain_atlas(_paint_source())
    serialized = json.dumps(report, sort_keys=True)
    assert "/private/" not in serialized
    assert "/tmp/" not in serialized
    assert "authorization" not in serialized.lower()
    assert "signature=" not in serialized.lower()
    prompt = terrain_atlas_generation_prompt("thin mineral cap, layered crystalline fill")
    assert "Repaint reference image 1 completely" in prompt
    assert "thin mineral cap, layered crystalline fill" in prompt
    assert "GRASS CAP" not in prompt
    assert "DIRT FILL" not in prompt
    assert "mirrored repetition" in prompt
    # The sheet is not a landscape, and the draws that forgot it capped the wrong row.
    assert "There is no skyline and no ground level on this sheet" in prompt
    # The fence is load-bearing: without it the model paints the sheet as one canvas
    # and a side that should terminate never gets a face.
    assert "cyan lines are the fence" in prompt

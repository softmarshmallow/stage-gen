"""What the runner admits from a painting, and how it publishes a catalog sprite.

A painted sprite must carry real transparent negative space and meaningful visible alpha;
a motion strip must fill every required cell and repack into canonical cells; a catalog
asset is trimmed to its alpha box, with a proven short sparse tail removed from props. Pure,
so the judges that run them and the steps that publish agree on every byte.
"""

from __future__ import annotations

import io
from typing import Literal, cast

from PIL import Image

from demo_game_tools.input_formats.game_contract.asset_scale import measure_subject_extent
from demo_game_tools.kits.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from stage_gen.components.sideview_layers.publish import LayerGate
from stage_gen.media.layer_rasters import trim_layer_to_alpha_box
from stage_gen.media.sprite_sheets import AlphaComponentRepackContract, repack_alpha_components

RUNNER_CATALOG_SPARSE_TAIL_TRIM_VERSION = "runner-catalog-sparse-tail-trim-v1"
RUNNER_MOTION_SOURCE_VISIBLE_ALPHA_MIN = 128
RUNNER_SPRITE_VISIBLE_ALPHA_MIN = 16
RUNNER_CUTOUT_MIN_TRANSPARENT_FRACTION = 0.10
RUNNER_CUTOUT_MIN_VISIBLE_FRACTION = 0.005
RUNNER_CUTOUT_MIN_TRANSPARENT_EDGE_FRACTION = 0.10
#: A runner's transparent layers must carry meaningful content: the floors measured on the
#: shipped tracks, below which a "layer" is a wash or a blank.
RUNNER_LAYER_GATE = LayerGate(
    minimum_transparent_fraction=0.05,
    minimum_visible_fraction=0.005,
    minimum_transparent_edge_fraction=0.05,
)


def admit_transparent_sprite(data: bytes) -> dict[str, object]:
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    extrema = cast("tuple[int, int]", image.getchannel("A").getextrema())
    if not (extrema[0] == 0 and extrema[1] >= RUNNER_SPRITE_VISIBLE_ALPHA_MIN):
        raise ValueError(
            "sprite output must contain transparent pixels and meaningful visible alpha"
        )
    alpha = image.getchannel("A")
    alpha_bytes = alpha.tobytes()
    pixel_count = image.width * image.height
    transparent_fraction = alpha_bytes.count(0) / pixel_count
    visible_fraction = sum(alpha.histogram()[RUNNER_SPRITE_VISIBLE_ALPHA_MIN:]) / pixel_count
    edge_bytes = b"".join(
        (
            alpha.crop((0, 0, image.width, 1)).tobytes(),
            alpha.crop((0, image.height - 1, image.width, image.height)).tobytes(),
            alpha.crop((0, 1, 1, image.height - 1)).tobytes(),
            alpha.crop((image.width - 1, 1, image.width, image.height - 1)).tobytes(),
        )
    )
    transparent_edge_fraction = edge_bytes.count(0) / len(edge_bytes)
    if transparent_fraction < RUNNER_CUTOUT_MIN_TRANSPARENT_FRACTION:
        raise ValueError("sprite output lacks meaningful transparent negative space")
    if visible_fraction < RUNNER_CUTOUT_MIN_VISIBLE_FRACTION:
        raise ValueError("sprite output lacks meaningful visible alpha coverage")
    if transparent_edge_fraction < RUNNER_CUTOUT_MIN_TRANSPARENT_EDGE_FRACTION:
        raise ValueError("sprite output lacks meaningful transparent edge separation")
    return {
        "width": image.width,
        "height": image.height,
        "alpha_min": extrema[0],
        "alpha_max": extrema[1],
        "visible_alpha_min": RUNNER_SPRITE_VISIBLE_ALPHA_MIN,
        "transparent_fraction": round(transparent_fraction, 9),
        "visible_fraction": round(visible_fraction, 9),
        "transparent_edge_fraction": round(transparent_edge_fraction, 9),
    }


def canonicalize_runner_catalog_sprite(
    data: bytes, *, family: str
) -> tuple[bytes, dict[str, object], dict[str, object]]:
    """Trim transparent framing and a proven short sparse tail from runner props.

    A generated prop may carry a decorative leaf or glow a few rows below the broad hardware or
    foot that gameplay must register. We trim only a narrow, low-area terminal tail: the median
    meaningful-alpha column bottom must sit 2-8% above the alpha box, its row must span at least a
    quarter of the painted width, and pixels below it must be at most 1% of painted pixels. Long
    cables, roots, legs, and other meaningful narrow silhouettes therefore remain untouched.
    """

    published, vertical_trim = trim_layer_to_alpha_box(data)
    tail_report: dict[str, object] = {
        "schema_version": 1,
        "kind": RUNNER_CATALOG_SPARSE_TAIL_TRIM_VERSION,
        "painted_alpha_threshold": 64,
        "minimum_tail_height_fraction": 0.02,
        "maximum_tail_height_fraction": 0.08,
        "minimum_contact_row_coverage": 0.25,
        "maximum_tail_painted_fraction": 0.01,
        "applied": False,
        "reason": "family_is_not_prop" if family != "prop" else "tail_not_proven_sparse",
    }
    if family != "prop":
        return published, vertical_trim, tail_report

    bounds = cast("dict[str, object]", vertical_trim["bounds"])
    median_raw = bounds.get("column_bottom_median")
    if not isinstance(median_raw, int) or isinstance(median_raw, bool):
        tail_report["reason"] = "missing_column_bottom_median"
        return published, vertical_trim, tail_report
    trimmed_top = cast("int", vertical_trim["trimmed_top"])
    trimmed_height = cast("int", vertical_trim["trimmed_height"])
    contact_row = median_raw - trimmed_top
    if not 0 <= contact_row < trimmed_height:
        raise ValueError("runner catalog median contact row lies outside the alpha trim")

    with Image.open(io.BytesIO(published)) as opened:
        image = opened.convert("RGBA")
    alpha = image.getchannel("A")
    painted = alpha.point(lambda value: 255 if value > 64 else 0)
    painted_box = painted.getbbox()
    if painted_box is None:
        raise ValueError("runner catalog sprite has no pixels above painted alpha threshold")
    painted_bytes = painted.tobytes()
    painted_count = painted_bytes.count(255)
    painted_width = painted_box[2] - painted_box[0]
    contact_start = contact_row * image.width
    contact_count = painted_bytes[contact_start : contact_start + image.width].count(255)
    tail_start = (contact_row + 1) * image.width
    tail_count = painted_bytes[tail_start:].count(255)
    tail_rows = image.height - contact_row - 1
    tail_height_fraction = tail_rows / image.height
    contact_row_coverage = contact_count / painted_width
    tail_painted_fraction = tail_count / painted_count
    tail_report.update(
        {
            "candidate_contact_row": contact_row,
            "candidate_output_height": contact_row + 1,
            "tail_rows": tail_rows,
            "tail_height_fraction": round(tail_height_fraction, 6),
            "contact_row_coverage": round(contact_row_coverage, 6),
            "tail_painted_fraction": round(tail_painted_fraction, 6),
        }
    )
    admitted = (
        0.02 <= tail_height_fraction <= 0.08
        and contact_row_coverage >= 0.25
        and tail_painted_fraction <= 0.01
    )
    if not admitted:
        return published, vertical_trim, tail_report

    cropped = image.crop((0, 0, image.width, contact_row + 1))
    stream = io.BytesIO()
    cropped.save(stream, format="PNG", optimize=False)
    tail_report.update(
        {
            "applied": True,
            "reason": "short_sparse_terminal_tail",
            "source_height": image.height,
            "output_height": cropped.height,
            "removed_rows": image.height - cropped.height,
        }
    )
    return stream.getvalue(), vertical_trim, tail_report


def admit_catalog_candidate(data: bytes, *, family: str) -> dict[str, object]:
    """Keep meaningful-alpha trimming inside the catalog provider retry owner."""

    source = admit_transparent_sprite(data)
    published, trim, sparse_tail_trim = canonicalize_runner_catalog_sprite(data, family=family)
    extent = measure_subject_extent(published, subject=f"runner {family}")
    return {
        "source": source,
        "trim": trim,
        "sparse_tail_trim": sparse_tail_trim,
        "painted_extent_px": extent,
    }


def motion_source_facts(data: bytes) -> dict[str, object]:
    geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
    facts = admit_transparent_sprite(data)
    if (facts["width"], facts["height"]) != (geometry.width, geometry.height):
        raise ValueError(f"motion atlas must be exactly {geometry.provider_size}")
    with Image.open(io.BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    cell_width = alpha.width / geometry.columns
    coverage: list[float] = []
    for index in range(geometry.required_cells):
        left = round(index * cell_width)
        right = round((index + 1) * cell_width)
        cell = alpha.crop((left, 0, right, alpha.height))
        visible = sum(cell.histogram()[RUNNER_MOTION_SOURCE_VISIBLE_ALPHA_MIN:]) / (
            cell.width * cell.height
        )
        coverage.append(visible)
    if any(value < 0.005 for value in coverage):
        raise ValueError("motion atlas is missing a required visible cell")
    return {
        **facts,
        "cell_coverage_alpha_min": RUNNER_MOTION_SOURCE_VISIBLE_ALPHA_MIN,
        "cell_visible_fractions": [round(value, 6) for value in coverage],
    }


def admit_motion_candidate(
    data: bytes, *, anchor: Literal["center", "bottom", "top"]
) -> dict[str, object]:
    """Keep decisive deterministic repacking inside the provider retry owner."""

    geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
    source = motion_source_facts(data)
    _canonical, repack = repack_alpha_components(
        data,
        AlphaComponentRepackContract(
            rows=geometry.rows,
            columns=geometry.columns,
            required_cells=geometry.required_cells,
            anchor=anchor,
            source_slot_policy="exact_required_slots",
        ),
    )
    return {"source": source, "repack": repack}


def listening_verdict(*, pinned: bool) -> str:
    """A pinned take was chosen by a person; a fresh draw has not been heard."""

    return "author_selected" if pinned else "not_performed"


__all__ = [
    "RUNNER_CATALOG_SPARSE_TAIL_TRIM_VERSION",
    "RUNNER_LAYER_GATE",
    "admit_catalog_candidate",
    "admit_motion_candidate",
    "admit_transparent_sprite",
    "canonicalize_runner_catalog_sprite",
    "listening_verdict",
    "motion_source_facts",
]

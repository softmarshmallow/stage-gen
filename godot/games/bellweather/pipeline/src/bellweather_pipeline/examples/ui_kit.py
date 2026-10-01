"""Importer for Bellweather's UI sheets: the panel frame, the button states and the icon grid.

Each sheet is one small chain in the game's graph: the image model paints over a geometry
template with the game's cover as the style reference, a local pixel gate measures what came
back (insets, cells, text area, glyph bounds), and a reviewer judges the style. Every node is
taken from the run where it ran, matched by digest to what the current package delivers.

The templates are rendered again from today's code and must match the digests the paint
requests recorded. The gate's own measurements and thresholds go into the example unchanged,
so a page can lay the sheets out exactly as a game engine would.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import Field

from stage_gen.components.ui_art import (
    ATLAS_ROLES,
    ICON_ROLES,
    PREVIEW_ICON_GLYPHS,
    render_atlas_template,
)
from stage_gen.components.ui_art.icons import render_icon_template
from stage_gen.examples import (
    ImportRequest,
    Media,
    RecordingReader,
    index,
    models_of,
    record_node,
    source_run,
)

from ._common import (
    Imported,
    ImporterOptions,
    digest,
    imported,
    lineage,
    package_reference,
    sent_digests,
    verdict_of,
)

REVIEWER = {"image_generation": "Image model", "structured_generation": "Reviewer"}


class UiKitOptions(ImporterOptions):
    """``delivered`` is the package run whose sheets the kit shows; ``sheets`` are its roles,
    in the order the kit lays them out."""

    delivered: str = Field(min_length=1)
    sheets: list[str] = Field(min_length=1)


def template_for(role: str) -> bytes:
    """The geometry template the model painted over, as the code renders it today."""
    if role in ATLAS_ROLES:
        return render_atlas_template(ATLAS_ROLES[role])
    if role in ICON_ROLES:
        return render_icon_template(ICON_ROLES[role])
    raise ValueError(
        f"{role} is not a UI sheet role this kit knows: {', '.join([*ATLAS_ROLES, *ICON_ROLES])}"
    )


def rel(rect: Mapping[str, int], cell: Mapping[str, int]) -> dict[str, int]:
    return {
        "x": rect["x"] - cell["x"],
        "y": rect["y"] - cell["y"],
        "width": rect["width"],
        "height": rect["height"],
    }


def box(rect: Mapping[str, int]) -> tuple[int, int, int, int]:
    return rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"]


def gate_checks(role: str, validation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The pixel gate's decisions, restated from its recorded measurements and thresholds."""
    facts = validation["facts"]["source"]
    limits = facts["thresholds"]
    checks: list[dict[str, Any]] = [
        {
            "name": "exterior_transparent",
            "passed": facts["alpha"]["border_max"] <= limits["transparent_admission_max"],
        }
    ]
    if role in ICON_ROLES:
        expected = [name for name, _ in PREVIEW_ICON_GLYPHS]
        checks += [
            {"name": "glyphs_in_order", "passed": facts["glyphs"] == expected},
            {
                "name": "glyphs_one_size",
                "passed": facts["set"]["extent_ratio"] <= limits["set_extent_ratio_max"],
            },
            {
                "name": "nothing_outside_cells",
                "passed": facts["alpha"]["outside_cells_max"]
                <= limits["transparent_admission_max"],
            },
        ]
        return checks
    cells = facts["cells"]
    checks += [
        {
            "name": "bands_tile_cleanly",
            "passed": all(
                v <= limits["tile_seam_excess_max"]
                for c in cells
                for v in c["tile_seam_excess"].values()
            ),
        },
        {
            "name": "text_area_quiet",
            "passed": all(
                c["content"]["luma_std"] <= limits["content_luma_std_max"] for c in cells
            ),
        },
        {
            "name": "text_readable",
            "passed": all(
                c["content"]["best_contrast"] >= limits["content_contrast_min"] for c in cells
            ),
        },
    ]
    if facts["state_checks"]:
        states = facts["state_checks"].values()
        checks += [
            {
                "name": "states_same_shape",
                "passed": all(
                    s["silhouette_iou"] >= limits["state_iou_min"]
                    and s["size_delta_px"] <= limits["state_size_delta_max_px"]
                    for s in states
                ),
            },
            {
                "name": "states_distinct",
                "passed": all(
                    s["distinct_from_normal_mae"] >= limits["state_distinct_min"] for s in states
                ),
            },
        ]
    return checks


def build(request: ImportRequest, options: UiKitOptions) -> Imported:
    reader, media = request.reader, request.media
    runs = lineage(request)
    package = request.base / options.package
    delivered_root = request.base / options.delivered

    nodes: dict[str, dict[str, Any]] = {}
    outputs: dict[str, dict[str, Any]] = {}
    cover: dict[str, Any] | None = None
    spent_ms = 0
    estimated = 0.0
    for role in options.sheets:
        ids = {step: f"ui-{role}-{step}" for step in ("generate", "validate", "review")}
        ran = {step: runs.where_it_ran(nid) for step, nid in ids.items()}
        for _, summary, planned in ran.values():
            spent_ms += summary["duration_ms"] or 0
            estimated += (planned.get("estimated_cost_high_usd") or 0) * (
                summary.get("attempts") or 1
            )

        # Paint: the model repaints the geometry template in the look of the cover.
        gen_dir = ran["generate"][0]
        raw = gen_dir / "ui" / f"{role}.raw.png"
        sidecar = reader.json(raw.with_name(raw.name + ".meta.json"))
        sent = sent_digests(sidecar)
        template_bytes = template_for(role)
        if hashlib.sha256(template_bytes).hexdigest() not in sent:
            raise ValueError(f"{role}: today's template is not the one the paint request sent")
        cover_path = package_reference(package, sent)
        if digest(reader, cover_path) not in sent:
            raise ValueError(f"{cover_path.name} is not the style reference the request sent")
        with Image.open(io.BytesIO(template_bytes)) as im:
            template = media.image(
                f"{role}-template.webp",
                im.convert("RGBA"),
                [raw],
                "the geometry template the paint request sent, rendered from code",
                640,
            )
        with Image.open(reader.path(raw)) as im:
            painted = media.image(
                f"{role}-painted.webp",
                im.convert("RGBA"),
                [raw],
                "the sheet as the model returned it",
                640,
            )
        if cover is None:
            cover = media.still("cover.webp", cover_path, 720)

        # Gate: the delivered sheet, its measurements and the evidence it drew.
        val_dir = ran["validate"][0]
        sheet_path = val_dir / "ui" / f"{role}.png"
        if digest(reader, sheet_path) != digest(reader, delivered_root / "ui" / f"{role}.png"):
            raise ValueError(f"{role}: the gated sheet is not the one {options.delivered} delivers")
        validation = reader.json(val_dir / "ui" / f"{role}.validation.json")
        with Image.open(sheet_path) as im:
            sheet_im = im.convert("RGBA")
        sheet = media.image(
            f"{role}-sheet.webp", sheet_im, [sheet_path], "the delivered sheet", 640
        )
        evidence_path = val_dir / "ui" / f"{role}.evidence.png"
        with Image.open(reader.path(evidence_path)) as im:
            evidence = media.image(
                f"{role}-evidence.webp",
                im.convert("RGBA"),
                [evidence_path],
                "the gate's evidence sheet",
                640,
            )

        # Review: the verdict, as recorded.
        review = reader.json(ran["review"][0] / "ui" / f"{role}.review.json")
        verdict = verdict_of(review)

        # The upstream nodes of this sheet's chain, as the plan wired them.
        feeds = {step: [d for d in ran[step][2]["depends_on"] if d in ids.values()] for step in ids}

        nodes[ids["generate"]] = record_node(
            ids["generate"],
            *ran["generate"],
            kinds=REVIEWER,
            prompt=sidecar["prompt"],
            thumb=painted,
            pictures=[template, painted],
        )
        nodes[ids["validate"]] = record_node(
            ids["validate"],
            *ran["validate"],
            kinds=REVIEWER,
            depends_on=feeds["validate"],
            checks=gate_checks(role, validation),
            thumb=sheet,
            pictures=[sheet, evidence],
        )
        nodes[ids["review"]] = record_node(
            ids["review"],
            *ran["review"],
            kinds=REVIEWER,
            depends_on=feeds["review"],
            verdict=verdict,
            rationale=review.get("evidence"),
        )

        out: dict[str, Any] = {
            "kind": "ui_sheet",
            "role": role,
            "file": sheet_path.name,
            "bytes": sheet_path.stat().st_size,
            "sha256": digest(reader, sheet_path),
            "poster": sheet,
            "accepted": verdict["accepted"],
        }
        if role in ICON_ROLES:
            words = dict(PREVIEW_ICON_GLYPHS)
            out["glyphs"] = [
                {
                    "name": c["glyph"],
                    "words": words[c["glyph"]],
                    "src": media.png(
                        f"icon-{c['glyph']}.png",
                        sheet_im.crop(box(c["cell"])),
                        [sheet_path],
                        f"the {c['glyph']} cell",
                    )["src"],
                }
                for c in validation["cells"]
            ]
        else:
            facts = validation["facts"]["source"]["cells"]
            out |= {
                "insets": validation["insets"],
                "draw_scale": validation["draw_scale"],
                "band_fill": validation["band_fill"],
                "states": [
                    {
                        "state": c["state"],
                        "src": media.png(
                            f"{role}-{c['state']}.png",
                            sheet_im.crop(box(c["cell"])),
                            [sheet_path],
                            f"the {c['state']} cell",
                        )["src"],
                        "width": c["cell"]["width"],
                        "height": c["cell"]["height"],
                        "content": rel(c["content_rect"], c["cell"]),
                        "text": f["content"]["best_text"],
                    }
                    for c, f in zip(validation["cells"], facts, strict=True)
                ],
            }
        outputs[role] = out

    outputs["kit"] = {
        "kind": "image",
        "file": "ui/",
        "bytes": sum(o["bytes"] for o in outputs.values()),
        "poster": kit_poster(media, reader, delivered_root, options.sheets),
    }
    plan = reader.json(runs.last / "execution-plan.json")
    return imported(
        request,
        {
            "example_id": request.example_id,
            "made_by": request.made_by,
            "importer": "ui_kit",
            "delivered_run": options.delivered,
            "source_runs": [source_run(request.base, run) for run in request.runs],
            "source_files": reader.files,
            "status": "succeeded",
            "graph_kind": plan["kind"],
            "graph_sha256": plan["graph_sha256"],
            "inputs": {"cover": {"kind": "image", "picture": cover, "file": "cover.png"}},
            "outputs": outputs,
            "metrics": {
                "wall_seconds": spent_ms / 1000,
                "estimated_cost_usd": estimated,
                "sheets": len(options.sheets),
            },
            "models": models_of(nodes),
            "tree": index(delivered_root),
            "nodes": nodes,
        },
        delivered_root,
    )


def kit_poster(
    media: Media, reader: RecordingReader, root: Path, roles: Sequence[str]
) -> dict[str, Any]:
    """The delivered sheets trimmed to their art, for the example's first picture.

    Four sheets go two by two; with three, the first two stack on the left and the last takes
    the right.
    """
    sources = [root / "ui" / f"{role}.png" for role in roles]
    trimmed: list[Image.Image] = []
    for path in sources:
        with Image.open(reader.path(path)) as im:
            rgba = im.convert("RGBA")
        trimmed.append(rgba.crop(rgba.getchannel("A").getbbox()))
    cell = 520
    boxes = (
        [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 2)]
        if len(trimmed) == 3
        else [(i % 2, i // 2, 1, 1) for i in range(len(trimmed))]
    )
    canvas = Image.new(
        "RGBA",
        (cell * 2, cell * ((len(trimmed) + 1) // 2 if len(trimmed) != 3 else 2)),
        (0, 0, 0, 0),
    )
    for art, (col, row, wide, tall) in zip(trimmed, boxes, strict=True):
        w, h = cell * wide - 48, cell * tall - 48
        art.thumbnail((w, min(h, w)), Image.Resampling.LANCZOS)
        canvas.alpha_composite(
            art,
            (
                col * cell + (cell * wide - art.width) // 2,
                row * cell + (cell * tall - art.height) // 2,
            ),
        )
    return media.image(
        "kit.webp",
        canvas,
        sources,
        f"the {len(trimmed)} delivered sheets trimmed to their art",
        720,
    )


__all__ = ["UiKitOptions", "build", "gate_checks", "template_for"]

"""Adapter for side-view terrain atlases made inside a platformer's world preparation.

The atlas is one part of a larger graph that also paints each map's backgrounds, so a page takes
only the nodes that make the ground: the level layout, the paintover and the cut. Each node is
taken from the run where it actually ran, and only when its outputs are byte-identical to what the
last run delivered; anything else is refused. The paint target is derived again from the packaged
template and must match the digest the paint request recorded, so the picture shown as "what the
model was given" is exactly that.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw

from stage_gen.components.sideview_terrain.atlas import terrain_atlas_paint_target
from stage_gen.resources import terrain_atlas_lookup_path, terrain_atlas_template_path

from ..media import Media, sha256
from ..record import RECORD_SCHEMA
from ..tree import index
from .lineage import Lineage, load, models_of, record_node

STEPS = ("terrain-generate", "ground-generate", "ground-validate")


def build_record(repo: Path, media: Media, options: dict) -> dict:
    lineage = Lineage([(repo / p).resolve() for p in options["runs"]])
    last = lineage.last

    lookup_path, template_path = terrain_atlas_lookup_path(), terrain_atlas_template_path()
    lookup = load(lookup_path)["lookup"]
    target_bytes = terrain_atlas_paint_target()
    target_sha = hashlib.sha256(target_bytes).hexdigest()
    with Image.open(io.BytesIO(target_bytes)) as im:
        target = media.image(
            "paint-target.webp",
            im.convert("RGB"),
            [template_path],
            "the template's 48 cells packed with the cyan fence, as the paint request sent it",
            480,
        )

    nodes: dict[str, dict] = {}
    inputs: dict[str, dict] = {}
    outputs: dict[str, dict] = {}
    metrics: dict[str, float] = {}
    for position, entry in enumerate(options["maps"]):
        map_id, name = entry["map"], entry["name"]
        ids = {step: f"map-{map_id}-{step}" for step in STEPS}
        ran = {step: lineage.where_it_ran(nid) for step, nid in ids.items()}
        maps = last / "maps" / map_id

        # Level layout: the occupancy grid a language model answered the map's terrain request with.
        level = load(maps / "terrain.json")["occupancy"]
        grid = Image.new("RGB", (len(level[0]) * 12, len(level) * 12), (244, 244, 245))
        draw = ImageDraw.Draw(grid)
        for y, row in enumerate(level):
            for x, cell in enumerate(row):
                if cell == "1":
                    draw.rectangle((x * 12, y * 12, x * 12 + 11, y * 12 + 11), fill=(113, 113, 122))
        layout = media.image(
            f"{name}-level.webp",
            grid,
            [maps / "terrain.json"],
            "the occupancy grid drawn as blocks",
            240,
        )

        # Paintover: the model repaints the packed template in the look of the scene reference.
        _, paint, paint_plan = ran["ground-generate"]
        raw = maps / "ground.raw.png"
        sidecar = load(raw.with_name(raw.name + ".meta.json"))
        bound = {i["sha256"]: i["ref"] for i in sidecar["inputs"]}
        if target_sha not in bound:
            raise ValueError(
                f"{map_id}: the paint request did not send the paint target derived from "
                "today's template"
            )
        scene_ref = next(ref for ref in bound.values() if ref.startswith("package://"))
        scene_path = (
            repo
            / options["package"]
            / "references"
            / scene_ref.split("/references/", 1)[1].split("#", 1)[0]
        )
        if sha256(scene_path) not in bound:
            raise ValueError(f"{scene_path} is not the reference the paint request sent")
        painted = media.still(f"{name}-painted.webp", raw, 480)
        admission = sidecar["validation"]
        paint_checks = [
            {
                "name": "paint_canvas_exact",
                "passed": f"{admission['source']['width']}x{admission['source']['height']}"
                == admission["thresholds"]["paint_canvas"],
            },
            {
                "name": "joins_within_tone_limit",
                "passed": admission["worst_join_tone_step"]
                <= admission["thresholds"]["maximum_join_tone_step"],
            },
            {
                "name": "material_painted",
                "passed": admission["painted_material_mean_standard_deviation"]
                >= admission["thresholds"]["minimum_painted_material_standard_deviation"],
            },
        ]

        # Cut: fixed-pitch slice, the 47-mask lookup, and the level composed through it.
        cut = ran["ground-validate"][1]
        atlas_path = maps / "ground.png"
        validation = load(maps / "ground.validation.json")
        if validation["lookup_sha256"] != sha256(lookup_path) or validation[
            "template_sha256"
        ] != sha256(template_path):
            raise ValueError(
                f"{map_id}: the atlas was cut against a different lookup or template than today's"
            )
        if validation["canonical"]["sha256"] != sha256(atlas_path):
            raise ValueError(f"{map_id}: ground.png is not the atlas its validation describes")
        atlas_still = media.still_alpha(f"{name}-atlas.webp", atlas_path, 480)
        atlas_file = media.copy(
            f"{name}-atlas.png",
            atlas_path,
            "the exact atlas bytes the game loads, for the tile painter",
        )
        with Image.open(maps / "ground.evidence.png") as im:
            evidence = im.convert("RGBA")
        preview = media.image(
            f"{name}-level-preview.webp",
            evidence.crop(evidence.getchannel("A").getbbox()),
            [maps / "ground.evidence.png"],
            "cropped to the ground",
            240,
        )
        canonical = validation["canonical"]
        cut_checks = [
            {
                "name": "no_transparent_pixels",
                "passed": canonical["published_transparent_pixels"] == 0,
            },
            {"name": "lookup_complete", "passed": validation["lookup_masks"] == 47},
            {
                "name": "reserved_cell_clear",
                "passed": canonical["placeholder_transparent_in_canonical"],
            },
        ]

        nodes[ids["terrain-generate"]] = record_node(
            ids["terrain-generate"], *ran["terrain-generate"], thumb=layout, pictures=[layout]
        )
        nodes[ids["ground-generate"]] = record_node(
            ids["ground-generate"],
            *ran["ground-generate"],
            prompt=sidecar["prompt"],
            checks=paint_checks,
            thumb=painted,
            pictures=[target, painted],
        )
        nodes[ids["ground-validate"]] = record_node(
            ids["ground-validate"],
            *ran["ground-validate"],
            depends_on=[ids["ground-generate"], ids["terrain-generate"]],
            checks=cut_checks,
            thumb=atlas_still,
            pictures=[atlas_still, preview],
        )

        scene = media.still(f"{name}-scene.webp", scene_path, 480)
        inputs[f"{name}_scene"] = {"kind": "image", "picture": scene, "file": scene_path.name}
        outputs[f"{name}_atlas"] = {
            "kind": "atlas",
            "file": atlas_path.name,
            "bytes": atlas_path.stat().st_size,
            "sha256": sha256(atlas_path),
            "poster": atlas_still,
            "src": atlas_file["src"],
            "cell_px": canonical["cell_px"],
            "columns": canonical["width"] // canonical["cell_px"],
            "rows": canonical["height"] // canonical["cell_px"],
            "lookup": lookup,
            "shapes": {k: v["rows"] for k, v in validation["maps"].items()},
            "level": level,
        }
        if position == 0:
            metrics = {
                "wall_seconds": (paint["duration_ms"] + cut["duration_ms"]) / 1000,
                "estimated_cost_usd": paint_plan["estimated_cost_high_usd"],
                "attempts": paint["attempts"],
                "tiles": validation["lookup_masks"],
            }

    plan = load(last / "execution-plan.json")
    return {
        "schema": RECORD_SCHEMA,
        "adapter": "terrain_atlas",
        "run": {
            "path": str(last.relative_to(repo)),
            "runs": options["runs"],
            "status": "succeeded",
            "graph_sha256": plan["graph_sha256"],
            "graph_kind": plan["kind"],
        },
        "inputs": inputs,
        "outputs": outputs,
        "metrics": metrics,
        "models": models_of(nodes),
        "tree": index(last),
        "nodes": nodes,
    }

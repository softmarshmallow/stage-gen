"""Adapter for a side-scrolling map's parallax backgrounds: depth layers that loop without a seam.

Each map is drawn as a few layers from its reference picture and a brief, far to near. A layer
that does not already loop has its own wrap moved to the middle of a canvas the image model
repaints, and the repaint is cut back in along the path where the two pictures agree. Every join,
the wrap and both cuts, is judged against the layer's own interior before the layer is published.
Every node is taken from the run where it ran, matched by digest to what the last run holds.

The page's stage draws the maps the way the game does: each layer resized to the 720-pixel view
and given its contrast, saturation, haze and blur by the game's own formulas, placed by its
anchor, and scrolled at its parallax; the ground is composed from the map's own atlas and grid,
and the character walks on it.
"""

from __future__ import annotations

import hashlib
import io
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from stage_gen.components.sideview_layers.pipeline import loop_conditioning
from stage_gen.components.sideview_terrain.atlas import compose_canonical_terrain

from ..media import Media, sha256
from ..record import RECORD_SCHEMA
from ..tree import index
from .lineage import Lineage, load, models_of, record_node

JUDGES = {"image_generation": "Image model", "structured_generation": "Vision model"}
REVIEWER = {"structured_generation": "Reviewer"}
# The game's design space and ruler, as godot/games/bellweather/gameplay/maps.gd sets them.
VIEW_WIDTH, VIEW_HEIGHT, TILE_PX = 1280, 720, 64
# The character on the stage, as the page's sprite set serves it.
WALKER_STATES = ("idle", "walk", "run", "jump")
WALKER_SCALE = 0.5
# The alpha a pixel needs to count as content, as the layer trim measures it.
ALPHA_THRESHOLD = 16
# How densely a cut is drawn over the stage: one point every this many source rows.
STITCH_ROW_STEP = 8
HOW = {
    "seam_repaint": "repainted through its wrap",
    "none": "looped as drawn",
    "mirror_repeat": "reflected",
}


# ---------------------------------------------------------------- the game's layer baking


def colour(rgba: np.ndarray, presentation: dict) -> np.ndarray:
    """Contrast, saturation and haze, as sideview_rendering/pixels.gd applies them."""
    out = rgba.copy()
    contrast, saturation = float(presentation["contrast"]), float(presentation["saturation"])
    strength = float(presentation["atmosphere_strength"])
    hex_ = presentation["atmosphere_color"].lstrip("#")
    haze = np.array([int(hex_[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float64) * strength
    rgb = ((rgba[..., :3] / 255.0 - 0.5) * contrast + 0.5) * 255.0
    luminance = rgb @ np.array([0.2126, 0.7152, 0.0722])
    rgb = luminance[..., None] + (rgb - luminance[..., None]) * saturation
    rgb = np.floor(np.clip(rgb * (1.0 - strength) + haze, 0, 255) + 0.5)
    shown = rgba[..., 3] > 0
    out[..., :3] = np.where(shown[..., None], rgb, rgba[..., :3])
    return out


def kernel(sigma: float) -> np.ndarray:
    radius = max(1, int(np.ceil(sigma * 2.5)))
    offsets = np.arange(-radius, radius + 1)
    weights = np.exp(-(offsets.astype(np.float64) ** 2) / (2 * sigma * sigma))
    return weights / weights.sum()


def blur(rgba: np.ndarray, sigma: float) -> np.ndarray:
    """The depth blur: alpha-weighted, wrapping across x, clamped down y, alpha itself untouched."""
    weights = kernel(sigma)
    radius = len(weights) // 2
    alpha = rgba[..., 3] / 255.0

    def one_pass(source: np.ndarray, horizontal: bool) -> np.ndarray:
        colour_sum = np.zeros((*source.shape[:2], 3))
        contributing = np.zeros(source.shape[:2])
        for k, weight in enumerate(weights):
            offset = k - radius
            if horizontal:
                shifted, shifted_alpha = (
                    np.roll(source, -offset, axis=1),
                    np.roll(alpha, -offset, axis=1),
                )
            else:
                rows = np.clip(np.arange(source.shape[0]) + offset, 0, source.shape[0] - 1)
                shifted, shifted_alpha = source[rows], alpha[rows]
            w = shifted_alpha * weight
            colour_sum += shifted[..., :3] * w[..., None]
            contributing += w
        out = source.copy()
        ok = contributing > 0
        out[..., :3] = np.where(
            ok[..., None],
            np.floor(np.clip(colour_sum / np.where(ok, contributing, 1)[..., None], 0, 255) + 0.5),
            source[..., :3],
        )
        return out

    return one_pass(one_pass(rgba, True), False)


def bake(path: Path, presentation: dict, source_height: int, size: float = 1.0) -> Image.Image:
    """A layer as the game bakes it: resized to the view, coloured, then blurred at screen size.

    ``size`` is the page's hand tuning on top of the game's own scale, baked in so a tuned layer
    stays as sharp as the game's.
    """
    scale = VIEW_HEIGHT / source_height * size
    with Image.open(path) as im:
        rgba = im.convert("RGBA").resize(
            (max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS
        )
    pixels = np.asarray(rgba, dtype=np.float64)
    neutral = (
        presentation["contrast"] == 1
        and presentation["saturation"] == 1
        and presentation["atmosphere_strength"] == 0
        and presentation["detail_blur_screen_pixels"] == 0
    )
    if not neutral:
        pixels = colour(pixels, presentation)
        if presentation["detail_blur_screen_pixels"] >= 0.05:
            pixels = blur(pixels, float(presentation["detail_blur_screen_pixels"]))
    return Image.fromarray(pixels.astype(np.uint8), "RGBA")


def layer_top(anchor: str, offset: float, rendered_height: float, walk_surface_y: float) -> float:
    """Where a layer's top edge sits in the view, as sideview_rendering/parallax.gd places it."""
    if anchor == "canvas_cover":
        return 0.0
    if anchor == "screen_top":
        return offset * rendered_height
    if anchor == "screen_center":
        return VIEW_HEIGHT / 2 - rendered_height / 2 + offset * rendered_height
    datum = VIEW_HEIGHT if anchor == "screen_bottom" else walk_surface_y
    return datum - (1 - offset) * rendered_height


# ---------------------------------------------------------------- pictures of the joins


def tiled(path: Path) -> Image.Image:
    with Image.open(path) as im:
        rgba = im.convert("RGBA")
    out = Image.new("RGBA", (rgba.width * 2, rgba.height), (0, 0, 0, 0))
    out.paste(rgba, (0, 0))
    out.paste(rgba, (rgba.width, 0))
    return out


def content_rows(im: Image.Image) -> tuple[int, int]:
    """Rows holding content, at the pipeline's alpha threshold.

    A raw drawing is faintly noisy everywhere.
    """
    box = im.getchannel("A").point(lambda a: 255 if a >= ALPHA_THRESHOLD else 0).getbbox() or (
        0,
        0,
        im.width,
        im.height,
    )
    return box[1], box[3]


def around(im: Image.Image, x: int, half: int = 300) -> Image.Image:
    """The content rows either side of a join, with a short tick above and below, not across it."""
    top, bottom = content_rows(im)
    pad = 18
    out = Image.new("RGBA", (half * 2, bottom - top + pad * 2), (0, 0, 0, 0))
    out.paste(im.crop((x - half, top, x + half, bottom)), (0, pad))
    draw = ImageDraw.Draw(out)
    for y0, y1 in ((0, pad - 4), (out.height - pad + 4, out.height)):
        draw.line([(half, y0), (half, y1)], fill=(225, 29, 72, 255), width=4)
    return out


def cuts_drawn(window: Image.Image, paths: list[list[int]], offsets: list[int]) -> Image.Image:
    """The assembled window with each cut drawn where it fell, row by row."""
    out = window.copy()
    draw = ImageDraw.Draw(out)
    for path, offset in zip(paths, offsets, strict=True):
        points = [(x + offset, y) for y, x in enumerate(path)][::4]
        draw.line(points, fill=(225, 29, 72, 255), width=5)
    return out


def marks(width: int, height: int, stitches: list[dict], trimmed_top: int, scale: float) -> str:
    """One period of a layer's joins as SVG, to repeat under the layer at its own scroll.

    The wrap is a line at the period's start; each cut is drawn where it fell on every row.
    """
    parts = [
        f'<line x1="1" y1="0" x2="1" y2="{height}" stroke="#e11d48" '
        'stroke-width="2" stroke-dasharray="6 5"/>'
    ]
    for s in stitches:
        rows = range(trimmed_top, trimmed_top + round(height / scale), STITCH_ROW_STEP)
        pts = " ".join(
            f"{s['positions'][r] * scale:.1f},{(r - trimmed_top) * scale:.1f}"
            for r in rows
            if r < len(s["positions"])
        )
        parts.append(f'<polyline points="{pts}" fill="none" stroke="#e11d48" stroke-width="2"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">' + "".join(parts) + "</svg>"
    )


# ---------------------------------------------------------------- record


def build_record(repo: Path, media: Media, options: dict) -> dict:
    lineage = Lineage([(repo / p).resolve() for p in options["runs"]])
    last = lineage.last
    package = repo / options["package"]
    ids = [
        nid
        for nid in lineage.delivered
        if nid.startswith("map-") and ("-layer-" in nid or nid.endswith(("-composite", "-review")))
    ]
    ran = {nid: lineage.where_it_ran(nid) for nid in ids}
    feeds = {nid: [d for d in ran[nid][2]["depends_on"] if d in ran] for nid in ids}

    def made(nid: str, name: str) -> Path:
        return ran[nid][0] / name

    nodes: dict[str, dict] = {}
    maps_out, references, layer_files = [], {}, []
    tuning = options.get("tuning", {})
    walker = walker_record(repo, media, options)

    for map_id in options["maps"]:
        authored = tomllib.loads((package / "maps" / f"{map_id}.toml").read_text(encoding="utf-8"))
        folder = Path("maps") / map_id
        reference = authored["references"][0]
        ref_path = package / reference["source"]
        if sha256(ref_path) != reference["source_sha256"]:
            raise ValueError(f"{ref_path} is not the reference {map_id} names")
        references[map_id] = ref_path
        terrain = load(last / folder / "terrain.json")
        grid = terrain["occupancy"]
        walk_surface_y = VIEW_HEIGHT - (len(grid) - terrain["walk_surface_row"]) * TILE_PX

        layers = []
        for spec in authored["layers"]:
            lid = spec["layer_id"]
            gen, loop, val = (
                f"map-{map_id}-layer-{lid}-{step}" for step in ("generate", "loop", "validate")
            )
            base = folder / "layers" / lid
            raw = made(gen, f"{base}.raw.png")
            meta = load(made(gen, f"{base}.raw.png.meta.json"))
            if reference["source_sha256"] not in {i["sha256"] for i in meta["inputs"]}:
                raise ValueError(f"{lid}: the drawing request did not send {map_id}'s reference")
            drawn = media.still_alpha(f"{map_id}-{lid}-drawn.webp", raw, 360)
            nodes[gen] = record_node(
                gen, *ran[gen], kinds=JUDGES, prompt=meta["prompt"], thumb=drawn, pictures=[drawn]
            )

            record = load(made(loop, f"{base}.loop.json"))
            joins = record["repeat"]["joins"]
            construction = record["construction"]
            checks = [{"name": "wrap_like_its_interior", "passed": joins[0]["verdict"] == "pass"}]
            if construction == "seam_repaint":
                checks.append(
                    {
                        "name": "cuts_like_its_interior",
                        "passed": all(j["verdict"] == "pass" for j in joins[1:]),
                    }
                )
            if record.get("rejected_construction"):
                checks.append({"name": "repaint_admitted", "passed": False})
            pictures = loop_pictures(
                media,
                f"{map_id}-{lid}",
                raw,
                made(loop, f"{base}.loop.png"),
                made(loop, f"{base}.edit.png") if construction == "seam_repaint" else None,
                record,
            )
            nodes[loop] = record_node(
                loop,
                *ran[loop],
                kinds=JUDGES,
                depends_on=feeds[loop],
                checks=checks,
                rationale=loop_words(record),
                thumb=pictures[-1],
                pictures=pictures,
            )

            validation = load(made(val, f"{base}.validation.json"))
            published = last / f"{base}.png"
            if made(val, f"{base}.png").read_bytes() != published.read_bytes():
                raise ValueError(f"{lid}: the published layer is not the one {last.name} holds")
            placement = validation["placement"]
            nodes[val] = record_node(
                val,
                *ran[val],
                kinds=JUDGES,
                depends_on=feeds[val],
                checks=[
                    {
                        "name": "loops_after_trim",
                        "passed": validation["repeat"]["verdict"] == "pass",
                    },
                ],
                thumb=pictures[-1],
                pictures=[pictures[-1]],
            )
            layer_files.append(published)

            # The game authors each layer's size; any front-matter tuning overrides it here only.
            game_scale = float(spec.get("display_scale", 1.0))
            tuned = tuning.get(map_id, {}).get(lid, {})
            size, dy = float(tuned.get("scale", game_scale)), float(tuned.get("dy", 0.0))
            baked = bake(published, spec["presentation"], placement["source_height"], size)
            scale = VIEW_HEIGHT / placement["source_height"] * size
            shown = media.image(
                f"{map_id}-{lid}.webp",
                baked,
                [published],
                "baked as the game bakes it: resized to the "
                f"720-pixel view at {size:g} times the game's size, "
                "then contrast, saturation, haze and blur",
                baked.height,
            )
            stitches = (record.get("cut") or {}).get("stitches", [])
            svg = marks(baked.width, baked.height, stitches, placement["trimmed_top"], scale)
            layers.append(
                {
                    "id": lid,
                    "plane": spec["plane"],
                    "order": spec["order"],
                    "parallax": spec["parallax"],
                    "src": shown["src"],
                    "baked": size,
                    "width": baked.width / size,
                    "height": baked.height / size,
                    "anchor": placement["vertical_anchor"],
                    "offset": placement["vertical_offset"],
                    "scale": size,
                    "dy": dy,
                    "game_scale": game_scale,
                    "how": construction,
                    "period": validation["width"],
                    "cuts": len(stitches),
                    "marks": "data:image/svg+xml;utf8," + svg.replace("#", "%23").replace('"', "'"),
                }
            )

        composite_id, review_id = f"map-{map_id}-composite", f"map-{map_id}-review"
        board = media.still(
            f"{map_id}-composite.webp", made(composite_id, f"{folder}/composite.png"), 480
        )
        nodes[composite_id] = record_node(
            composite_id,
            *ran[composite_id],
            depends_on=feeds[composite_id],
            thumb=board,
            pictures=[board],
        )
        review = load(made(review_id, f"{folder}/review.json"))
        nodes[review_id] = record_node(
            review_id,
            *ran[review_id],
            kinds=REVIEWER,
            depends_on=feeds[review_id],
            rationale=review.get("evidence"),
            verdict={
                "accepted": review["verdict"] == "accept",
                "criteria": [
                    {"name": k, "passed": v, "evidence": ""} for k, v in review["checks"].items()
                ],
                "issues": review.get("issues", []),
            },
        )

        ground_path = last / folder / "ground.png"
        composed, _ = compose_canonical_terrain(ground_path.read_bytes(), grid)
        with Image.open(io.BytesIO(composed)) as im:
            ground = im.convert("RGBA").resize(
                (len(grid[0]) * TILE_PX, len(grid) * TILE_PX), Image.LANCZOS
            )
        ground_shown = media.image(
            f"{map_id}-ground.webp",
            ground,
            [ground_path, last / folder / "terrain.json"],
            "the map's grid composed from its ground atlas, 64 px to a tile",
            ground.height,
        )
        ground_top = VIEW_HEIGHT - ground.height
        picture = media.still(f"{map_id}-reference.webp", ref_path, 720)
        maps_out.append(
            {
                "id": map_id,
                "label": authored["display_name"],
                "width": ground.width,
                "walk_surface": walk_surface_y,
                "reference": {"src": picture["src"], "file": ref_path.name},
                "ground": {
                    "src": ground_shown["src"],
                    "width": ground.width,
                    "height": ground.height,
                    "top": ground_top,
                },
                "grid": grid,
                "tile": TILE_PX,
                "layers": layers,
            }
        )

    missing = sorted(set(ids) - set(nodes))
    if missing:
        raise ValueError(f"nodes this page does not show: {missing}")

    first = options["maps"][0]
    world = lineage.summaries[0][0]
    spent = [n for n in ids if (ran[n][1].get("provider_operations") or 0) > 0]
    return {
        "schema": RECORD_SCHEMA,
        "adapter": "parallax_layers",
        "run": {
            "path": str((last / "maps").relative_to(repo)),
            "runs": options["runs"],
            "status": "succeeded",
            "graph_sha256": load(last / "execution-plan.json")["graph_sha256"],
            "graph_kind": "sideview-platformer",
        },
        "inputs": {
            "reference": {
                "kind": "image",
                "picture": media.still("reference.webp", references[first], 720),
                "file": references[first].name,
            },
        },
        "outputs": {
            "backgrounds": {
                "kind": "parallax",
                "file": "maps/",
                "bytes": sum(p.stat().st_size for p in layer_files),
                "poster": still_view(media, maps_out[0], layer_files),
                "maps": maps_out,
                "walker": walker,
                "view": [VIEW_WIDTH, VIEW_HEIGHT],
            },
        },
        "metrics": {
            "wall_seconds": load(world / "execution-summary.json")["duration_ms"] / 1000,
            "estimated_cost_usd": sum(
                (ran[n][2].get("estimated_cost_high_usd") or 0) * (ran[n][1].get("attempts") or 1)
                for n in spent
            ),
            "layers": sum(len(m["layers"]) for m in maps_out),
            "repainted": sum(
                1 for m in maps_out for layer in m["layers"] if layer["how"] == "seam_repaint"
            ),
        },
        "models": models_of(nodes),
        "tree": index(last / "maps"),
        "nodes": nodes,
    }


def loop_words(record: dict) -> str:
    construction = record["construction"]
    if construction == "none":
        return (
            "The drawing already looped: its wrap measured like any column inside it, "
            "so it was published untouched."
        )
    if construction == "seam_repaint":
        cuts = record["cut"]["stitches"]
        spans = ", ".join(f"columns {s['x_min']} to {s['x_max']}" for s in cuts)
        window = record["repaint_span"] + 2 * record["context_span"]
        return (
            f"The wrap was moved to the middle of a {window}-pixel window and repainted, "
            "then cut back in along the path where the two pictures agreed "
            f"({spans}). The period stays {record['period_width']} pixels."
        )
    rejected = record.get("rejected_repeat", {}).get("failure_codes", [])
    return (
        "The repaint came back from a plain gradient off by more than the gradient's own steps"
        f"{' (' + ', '.join(c.replace('_', ' ') for c in rejected) + ')' if rejected else ''}"
        ", so the layer fell back to "
        "its reflection, which for an empty gradient is the same picture."
    )


def loop_pictures(
    media: Media, name: str, raw: Path, loop: Path, edit: Path | None, record: dict
) -> list[dict]:
    """The wrap as drawn, then the loop.

    For a repaint, the model's window and where it was cut in come between them.
    """
    with Image.open(raw) as im:
        width = im.width
    before = media.image(
        f"{name}-wrap-drawn.webp",
        around(tiled(raw), width),
        [raw],
        "the drawing tiled, around its wrap",
        360,
    )
    after = media.image(
        f"{name}-wrap-looped.webp",
        around(tiled(loop), width),
        [loop],
        "the loop tiled, around its wrap",
        360,
    )
    if edit is None:
        return [before, after]
    with Image.open(edit) as im:
        window = im.convert("RGBA")
    # What the model was given, rebuilt with the pipeline's own code and held to the digests the
    # request recorded, so the page shows the exact canvas and mask that were sent.
    conditioning = loop_conditioning("seam_repaint", raw.read_bytes())
    sent = {i["ref"]: i["sha256"] for i in load(edit.with_name(edit.name + ".meta.json"))["inputs"]}
    for ref, data in (
        ("loop-conditioning", conditioning.conditioning_png),
        ("loop-mask", conditioning.mask_png),
    ):
        if hashlib.sha256(data).hexdigest() != sent[ref]:
            raise ValueError(
                f"{name}: rebuilding the {ref} does not give the bytes the request sent"
            )
    with Image.open(io.BytesIO(conditioning.conditioning_png)) as im:
        given = im.convert("RGBA")
    rows = [content_rows(given), content_rows(window)]
    top, bottom = min(r[0] for r in rows), max(r[1] for r in rows)
    returned = media.image(
        f"{name}-window.webp",
        window.crop((0, top, window.width, bottom)),
        [edit],
        "the model's return for the window around the wrap",
        480,
    )
    outlined = given.crop((0, top, given.width, bottom))
    left, right = conditioning.context_span, conditioning.context_span + conditioning.editable_span
    draw = ImageDraw.Draw(outlined)
    for y in range(0, outlined.height, 18):
        for x in (left, right - 1):
            draw.line([(x, y), (x, min(y + 9, outlined.height))], fill=(225, 29, 72, 255), width=3)
    # The join itself, the layer's last column against its first, ticked at both edges rather than
    # drawn across, so the seam it points at stays visible.
    middle = outlined.width // 2
    for y0, y1 in ((0, 22), (outlined.height - 22, outlined.height)):
        draw.line([(middle, y0), (middle, y1)], fill=(225, 29, 72, 255), width=6)
    shown = media.image(
        f"{name}-given.webp",
        outlined,
        [raw],
        "the window the model was sent, rebuilt from the drawing and "
        "matched to the request's digest, with the span it was asked to repaint marked",
        480,
    )
    half = window.width // 2
    assembled = Image.new("RGBA", window.size)
    with Image.open(loop) as im:
        unit = im.convert("RGBA")
    assembled.paste(unit.crop((unit.width - half, 0, unit.width, unit.height)), (0, 0))
    assembled.paste(unit.crop((0, 0, half, unit.height)), (half, 0))
    stitches = record["cut"]["stitches"]
    drawn = cuts_drawn(assembled, [s["positions"] for s in stitches], [-(unit.width - half), half])
    cut = media.image(
        f"{name}-cuts.webp",
        drawn.crop((0, top, window.width, bottom)),
        [loop],
        "the loop around its wrap, with each cut drawn where it fell",
        360,
    )
    return [before, returned, cut, after, shown]


def walker_record(repo: Path, media: Media, options: dict) -> dict:
    """The character the stage walks, from the game's package, as the sprite set page serves it."""
    delivered = repo / options["walker"]
    manifest = load(delivered / "manifest.json")
    player = manifest["player"]
    states = {}
    for state in WALKER_STATES:
        spec = player["states"][state]
        path = delivered / "content/players" / player["player_id"] / "states" / f"{state}.png"
        if sha256(path) != spec["asset"]["sha256"]:
            raise ValueError(f"{path} is not the strip the package publishes")
        with Image.open(path) as im:
            strip = im.convert("RGBA")
        served = strip.resize(
            (round(strip.width * WALKER_SCALE), round(strip.height * WALKER_SCALE)), Image.LANCZOS
        )
        playback = spec["playback"]
        states[state] = {
            "src": media.image(
                f"walker-{state}.webp", served, [path], f"scaled to {WALKER_SCALE:g}", served.height
            )["src"],
            "columns": spec["columns"],
            "cell": [strip.width // spec["columns"], strip.height // spec["rows"]],
            "frames": playback["canonical_frame_indices"],
            "fps": playback.get("frames_per_second"),
            "rebase": player["calibration"]["state_rebase"][state],
            "mirror": spec["runtime_mirror"],
        }
    unit = manifest["scale"]["player_height_tiles"] * TILE_PX
    return {"states": states, "per_unit": player["calibration"]["source_px_per_unit"], "unit": unit}


def placed_top(layer: dict, walk_surface: float) -> float:
    """A layer's top as tuned: the game's anchor rule on the tuned height, then the tuned shift."""
    return (
        layer_top(layer["anchor"], layer["offset"], layer["height"] * layer["scale"], walk_surface)
        + layer["dy"]
    )


def still_view(media: Media, map_out: dict, sources: list[Path]) -> dict:
    """The first map's layers alone, tuned, as one picture for the index card.

    The page scrolls them live.
    """
    canvas = Image.new("RGBA", (VIEW_WIDTH, VIEW_HEIGHT), (0, 0, 0, 255))
    for layer in sorted(
        map_out["layers"], key=lambda layer: (layer["plane"] != "background", layer["order"])
    ):
        with Image.open(media.out / Path(layer["src"]).name) as im:
            band = im.convert("RGBA")
        top = round(placed_top(layer, map_out["walk_surface"]))
        for x in range(0, VIEW_WIDTH, band.width):
            canvas.alpha_composite(band, (x, top))
    return media.image(
        "layers.webp",
        canvas.convert("RGB"),
        sources,
        f"{map_out['label']}'s layers alone, as tuned for this page",
        VIEW_HEIGHT // 2,
    )

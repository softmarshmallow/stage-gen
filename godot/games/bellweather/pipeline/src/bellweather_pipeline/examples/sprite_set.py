"""Importer for Bellweather's player animation set: one strip per state, drawn to one size.

The character is drawn once as a concept from the game's cover and a short brief. Every
state (idle, walk, run and so on) is then its own image call from that concept, cut by a
local gate into a strip of evenly spaced frames, and a vision model compares all the strips
on one plate to set each one's size against idle. Every node is taken from the run where it
ran, matched by digest to what the current package delivers.

Each delivered strip is rebuilt from the model's raw picture with today's cutting code and
must match byte for byte, and the size table the package publishes must be the one the judge
wrote. The example's lineup draws the strips the way the game does: the cell's bottom at the
feet, the strip's size times the ruler times its correction, right-facing strips mirrored for
left.
"""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import Field

from stage_gen.examples import (
    ImportRequest,
    Media,
    RecordingReader,
    index,
    models_of,
    record_node,
    relative_to_base,
    source_run,
)
from stage_gen.media.sprite_sheets import AlphaComponentRepackContract, repack_alpha_components

from ._common import (
    Imported,
    ImporterOptions,
    digest,
    estimated_cost,
    feeds,
    imported,
    lineage,
    missing_nodes,
    verdict_of,
    where,
)

JUDGES = {"image_generation": "Image model", "structured_generation": "Vision model"}
REVIEWER = {"structured_generation": "Reviewer"}
# The gate's border limits, as prepared_content._validate_transparent_image applies them.
BORDER_ALPHA_MAX = 16
BORDER_ALPHA_MEAN_MAX = 0.5
# The strips a page's player loads, as a fraction of their delivered size. The player draws a
# unit of height at about 150 px against 700 source px, so half size stays sharp on a 2x screen.
SERVED_SCALE = 0.5


class SpriteSetOptions(ImporterOptions):
    """``delivered`` is the package run that ships the set; ``actor`` its player id."""

    delivered: str = Field(min_length=1)
    actor: str = Field(min_length=1)


def strip_checks(validation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The strip gate's decisions, restated from what it recorded."""
    source, repack = validation["source_validation"], validation["repack"]
    return [
        {
            "name": "transparent_ground",
            "passed": source["alpha_min"] == 0 and source["alpha_max"] > 0,
        },
        {
            "name": "canvas_edges_clear",
            "passed": source["border_alpha_max"] <= BORDER_ALPHA_MAX
            and source["border_alpha_mean"] <= BORDER_ALPHA_MEAN_MAX,
        },
        {"name": "every_frame_drawn", "passed": source["all_required_cells_visible"]},
        {
            "name": "one_pose_per_frame",
            "passed": repack["selected_component_count"] == repack["required_cells"],
        },
    ]


def rebuild(
    reader: RecordingReader,
    source: Path,
    delivered: Path,
    contract: AlphaComponentRepackContract,
) -> None:
    """Cut the model's picture into its strip again and require the delivered bytes."""
    data, _ = repack_alpha_components(reader.bytes(source), contract)
    if hashlib.sha256(data).hexdigest() != digest(reader, delivered):
        raise ValueError(
            f"{delivered.name}: cutting {source.name} again does not give the delivered strip"
        )


def build(request: ImportRequest, options: SpriteSetOptions) -> Imported:
    reader, media = request.reader, request.media
    runs = lineage(request)
    delivered = request.base / options.delivered
    actor = options.actor
    folder = Path("content/players") / actor
    player = reader.json(delivered / "manifest.json")["player"]
    if player["player_id"] != actor:
        raise ValueError(
            f"{options.delivered} delivers the player {player['player_id']}, not {actor}"
        )
    calibration = player["calibration"]

    prefix = f"player-{actor}-"
    ids = [nid for nid in runs.delivered if nid.startswith(prefix)]
    ran = where(runs, ids)
    upstream = feeds(ran)

    def made(nid: str, name: str) -> Path:
        return ran[nid][0] / folder / name

    def sidecar(nid: str, name: str) -> dict[str, Any]:
        document: dict[str, Any] = reader.json(made(nid, name + ".meta.json"))
        return document

    nodes: dict[str, dict[str, Any]] = {}

    # Concept: the one picture every later drawing is held to, from the cover and the brief.
    concept_id = f"{prefix}concept-generate"
    concept_meta = sidecar(concept_id, "concept.png")
    package = request.base / options.package
    cover_path = package / "references" / "cover.png"
    if digest(reader, cover_path) not in {i["sha256"] for i in concept_meta["inputs"]}:
        raise ValueError(f"{cover_path.name} is not the reference the concept request sent")
    authored = tomllib.loads(reader.bytes(package / "content" / "player.toml").decode("utf-8"))
    brief = next(p for p in authored["players"] if p["player_id"] == actor)["prompt"]
    if " ".join(brief.split()) not in " ".join(concept_meta["prompt"].split()):
        raise ValueError("the packaged brief is not the one the concept request sent")
    concept = media.still_alpha("concept.webp", made(concept_id, "concept.png"), 640)
    nodes[concept_id] = record_node(
        concept_id,
        *ran[concept_id],
        kinds=JUDGES,
        prompt=concept_meta["prompt"],
        thumb=concept,
        pictures=[concept],
    )

    # Each state: drawn from the concept, then cut into evenly spaced frames on one line.
    states: list[dict[str, Any]] = []
    for state, spec in player["states"].items():
        gen_id, val_id = f"{prefix}state-{state}-generate", f"{prefix}state-{state}-validate"
        raw_path = made(gen_id, f"states/{state}.source.png")
        drawn = media.still_alpha(f"{state}-drawn.webp", raw_path)
        nodes[gen_id] = record_node(
            gen_id,
            *ran[gen_id],
            kinds=JUDGES,
            depends_on=upstream[gen_id],
            prompt=sidecar(gen_id, f"states/{state}.source.png")["prompt"],
            thumb=drawn,
            pictures=[drawn],
        )

        validation = reader.json(made(val_id, f"states/{state}.validation.json"))
        strip_path = delivered / folder / "states" / f"{state}.png"
        if digest(reader, strip_path) != spec["asset"]["sha256"] or reader.bytes(
            made(val_id, f"states/{state}.png")
        ) != reader.bytes(strip_path):
            raise ValueError(
                f"{state}: the gated strip is not the one {options.delivered} delivers"
            )
        rebuild(
            reader,
            raw_path,
            strip_path,
            AlphaComponentRepackContract(
                rows=spec["rows"],
                columns=spec["columns"],
                required_cells=spec["source_frame_count"],
                anchor=validation["repack"]["anchor"],
            ),
        )
        with Image.open(strip_path) as im:
            strip = im.convert("RGBA")
        shown = media.image(f"{state}-strip.webp", strip, [strip_path], "the delivered strip")
        nodes[val_id] = record_node(
            val_id,
            *ran[val_id],
            kinds=JUDGES,
            depends_on=upstream[val_id],
            checks=strip_checks(validation),
            thumb=shown,
            pictures=[shown],
        )

        served = strip.resize(
            (round(strip.width * SERVED_SCALE), round(strip.height * SERVED_SCALE)),
            Image.Resampling.LANCZOS,
        )
        playback = spec["playback"]
        states.append(
            {
                "state": state,
                "src": media.image(
                    f"{state}.webp",
                    served,
                    [strip_path],
                    f"scaled to {SERVED_SCALE:g}",
                    served.height,
                )["src"],
                "columns": spec["columns"],
                "cell": [strip.width // spec["columns"], strip.height // spec["rows"]],
                "frames": playback["canonical_frame_indices"],
                "mode": playback["mode"],
                "fps": playback.get("frames_per_second"),
                "anchor": spec["anchor"],
                "facing": spec["source_facing"],
                "mirror": spec["runtime_mirror"],
                "rebase": calibration["state_rebase"][state],
                "bytes": strip_path.stat().st_size,
            }
        )

    # Dialogue: five expressions in one sheet, cut the same way.
    dgen, dval = f"{prefix}dialogue-generate", f"{prefix}dialogue-validate"
    dialogue_path = delivered / folder / "dialogue.png"
    dvalidation = reader.json(made(dval, "dialogue.validation.json"))
    if digest(reader, dialogue_path) != player["dialogue"]["asset"]["sha256"]:
        raise ValueError(f"the dialogue sheet is not the one {options.delivered} delivers")
    rebuild(
        reader,
        made(dgen, "dialogue.source.png"),
        dialogue_path,
        AlphaComponentRepackContract(
            rows=dvalidation["rows"],
            columns=dvalidation["columns"],
            required_cells=len(dvalidation["expressions"]),
            anchor="center",
        ),
    )
    ddrawn = media.still_alpha("dialogue-drawn.webp", made(dgen, "dialogue.source.png"))
    dialogue = media.still_alpha("dialogue.webp", dialogue_path)
    nodes[dgen] = record_node(
        dgen,
        *ran[dgen],
        kinds=JUDGES,
        depends_on=upstream[dgen],
        prompt=sidecar(dgen, "dialogue.source.png")["prompt"],
        thumb=ddrawn,
        pictures=[ddrawn],
    )
    nodes[dval] = record_node(
        dval,
        *ran[dval],
        kinds=JUDGES,
        depends_on=upstream[dval],
        checks=strip_checks(dvalidation),
        thumb=dialogue,
        pictures=[dialogue],
    )

    # One size: a first judgement on a plate of every strip, then a check of the plate with it.
    rebase_id, verify_id = f"{prefix}motion-rebase", f"{prefix}motion-rebase-verify"
    first = reader.json(made(rebase_id, "motion-rebase-first-pass.json"))
    final = reader.json(made(verify_id, "motion-rebase.json"))
    if final["states"] != calibration["state_rebase"]:
        raise ValueError("the size table the package publishes is not the one the check wrote")
    for nid, name, key in (
        (rebase_id, "motion-rebase-plate.png", "plate_sha256"),
        (verify_id, "motion-rebase-verification-plate.png", "verification_plate_sha256"),
    ):
        if digest(reader, made(nid, name)) != final[key]:
            raise ValueError(f"{name} is not the plate the size check judged")
    plate = media.still("rebase-plate.webp", made(rebase_id, "motion-rebase-plate.png"), 1400)
    checked = media.still(
        "rebase-checked.webp", made(verify_id, "motion-rebase-verification-plate.png"), 1400
    )
    nodes[rebase_id] = record_node(
        rebase_id,
        *ran[rebase_id],
        kinds=JUDGES,
        depends_on=upstream[rebase_id],
        rationale=" ".join(f"{s}: {t}" for s, t in first["evidence"].items()),
        thumb=plate,
        pictures=[plate],
    )
    nodes[verify_id] = record_node(
        verify_id,
        *ran[verify_id],
        kinds=JUDGES,
        depends_on=upstream[verify_id],
        rationale=" ".join(f"{s}: {t}" for s, t in final["evidence"].items()),
        thumb=checked,
        pictures=[checked],
    )

    # Review: a contact sheet of everything, judged by a model that drew none of it.
    sheet_id, review_id = f"{prefix}contact-sheet", f"{prefix}review"
    sheet = media.still("contact-sheet.webp", made(sheet_id, "contact-sheet.png"), 1400)
    nodes[sheet_id] = record_node(
        sheet_id, *ran[sheet_id], depends_on=upstream[sheet_id], thumb=sheet, pictures=[sheet]
    )
    review = reader.json(made(review_id, "review.json"))
    nodes[review_id] = record_node(
        review_id,
        *ran[review_id],
        kinds=REVIEWER,
        depends_on=upstream[review_id],
        verdict=verdict_of(review),
        rationale=review.get("evidence"),
    )
    missing_nodes(ids, nodes)

    strips = [delivered / folder / "states" / f"{s['state']}.png" for s in states]
    # When the whole set ran in one run, that run's clock is the set's; otherwise steps are summed.
    ran_in = {ran[n][0] for n in ids}
    wall_ms = (
        reader.json(ran_in.pop() / "execution-summary.json")["duration_ms"]
        if len(ran_in) == 1
        else sum(ran[n][1]["duration_ms"] or 0 for n in ids)
    )
    plan = reader.json(runs.last / "execution-plan.json")
    return imported(
        request,
        {
            "example_id": request.example_id,
            "made_by": request.made_by,
            "importer": "sprite_set",
            "delivered_run": relative_to_base(request.base, delivered / folder),
            "source_runs": [source_run(request.base, run) for run in request.runs],
            "source_files": reader.files,
            "status": "succeeded",
            "graph_kind": plan["kind"],
            "graph_sha256": plan["graph_sha256"],
            "inputs": {
                "cover": {
                    "kind": "image",
                    "picture": media.still("cover.webp", cover_path, 720),
                    "file": "cover.png",
                },
                "brief": {"kind": "text", "text": " ".join(brief.split())},
            },
            "outputs": {
                "set": {
                    "kind": "sprite_set",
                    "file": "states/",
                    "bytes": sum(p.stat().st_size for p in strips),
                    "poster": lineup(media, reader, strips, states, calibration),
                    "states": states,
                    "per_unit": calibration["source_px_per_unit"],
                    "baseline": calibration["baseline_state"],
                    "first_pass": first["states"],
                },
                "dialogue": {
                    "kind": "image",
                    "file": "dialogue.png",
                    "bytes": dialogue_path.stat().st_size,
                    "poster": dialogue,
                    "expressions": player["dialogue"]["expressions"],
                },
            },
            "metrics": {
                "wall_seconds": wall_ms / 1000,
                "estimated_cost_usd": estimated_cost(ran, ids),
                "animations": len(states),
                "frames": sum(len(s["frames"]) for s in states),
            },
            "models": models_of(nodes),
            "tree": index(delivered / folder),
            "nodes": nodes,
        },
        delivered,
    )


def _frame_at(spec: Mapping[str, Any], t: float) -> int:
    n = len(spec["frames"])
    if spec["mode"] == "hold":
        return 0
    if spec["mode"] == "gameplay_driven":
        return int(t / 0.3) % n
    i = int(t * spec["fps"])
    return i % n if spec["mode"] == "loop" else min(i, n - 1)


def lineup(
    media: Media,
    reader: RecordingReader,
    strips: Sequence[Path],
    states: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Any],
    per_row: int = 4,
) -> dict[str, Any]:
    """Every animation playing side by side at the size the game draws it, four to a row.

    Each strip is scaled by the ruler and its own correction and stood on its row's line by
    the bottom of its cell, as the game places it; loops loop, one-shots play and hold, a hold
    holds, and a climb steps its frames as if climbing steadily.
    """
    unit = 190  # px per unit of height
    per_unit = calibration["source_px_per_unit"]
    step_ms, cycle_ms = 50, 2400
    pieces: list[dict[str, Any]] = []
    for path, s in zip(strips, states, strict=True):
        with Image.open(reader.path(path)) as im:
            rgba = im.convert("RGBA")
        cw, ch = s["cell"]
        cells = [rgba.crop((i * cw, 0, (i + 1) * cw, ch)) for i in s["frames"]]
        boxes = [b for c in cells if (b := c.getchannel("A").getbbox()) is not None]
        union = (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        k = unit * s["rebase"] / per_unit
        size = (max(1, round((union[2] - union[0]) * k)), max(1, round((union[3] - union[1]) * k)))
        pieces.append(
            {
                "frames": [c.crop(union).resize(size, Image.Resampling.LANCZOS) for c in cells],
                "above": round((ch - union[1]) * k),
                "below": round((ch - union[3]) * k),
                "spec": s,
            }
        )
    gap, margin = round(unit * 0.22), round(unit * 0.12)
    rows = [pieces[i : i + per_row] for i in range(0, len(pieces), per_row)]
    width = (
        max(sum(p["frames"][0].width for p in r) + gap * (len(r) - 1) for r in rows) + margin * 2
    )
    heights = [max(p["above"] for p in r) for r in rows]
    height = sum(heights) + gap * (len(rows) - 1) + margin * 2

    frames: list[Image.Image] = []
    for tick in range(cycle_ms // step_ms):
        t = tick * step_ms / 1000
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        top = margin
        for r, row_height in zip(rows, heights, strict=True):
            ground = top + row_height
            x = (width - sum(p["frames"][0].width for p in r) - gap * (len(r) - 1)) // 2
            for p in r:
                im = p["frames"][_frame_at(p["spec"], t)]
                canvas.alpha_composite(im, (x, ground - p["below"] - im.height))
                x += im.width + gap
            top = ground + gap
        frames.append(canvas)
    return media.sequence(
        "lineup.webp",
        frames,
        step_ms,
        strips,
        f"every strip at its corrected size, {cycle_ms} ms cycle at {step_ms} ms steps",
        max_height=height,
        quality=80,
    )


__all__ = ["SpriteSetOptions", "build", "strip_checks"]

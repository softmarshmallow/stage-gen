"""Adapter for a side-view character's animation set: one strip per state, drawn to one size.

The character is drawn once as a concept from the game's cover and a short brief. Every state
(idle, walk, run and so on) is then its own image call from that concept, cut by a local gate into
a strip of evenly spaced frames, and a vision model compares all the strips on one plate to set
each one's size against idle. Every node is taken from the run where it ran, matched by digest to
what the current package delivers.

Each delivered strip is rebuilt from the model's raw picture with today's cutting code and must
match byte for byte, and the size table the package publishes must be the one the judge wrote. The
page's player draws the strips the way the game does: the cell's bottom at the feet, the strip's
size times the ruler times its correction, right-facing strips mirrored for left.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from PIL import Image

from stage_gen.media.sprite_sheets import AlphaComponentRepackContract, repack_alpha_components

from ..media import Media, sha256
from ..record import RECORD_SCHEMA
from ..tree import index
from .lineage import Lineage, load, models_of, record_node

JUDGES = {"image_generation": "Image model", "structured_generation": "Vision model"}
REVIEWER = {"structured_generation": "Reviewer"}
# The gate's border limits, as prepared_content._validate_transparent_image applies them.
BORDER_ALPHA_MAX = 16
BORDER_ALPHA_MEAN_MAX = 0.5
# The strips the page's player loads, as a fraction of their delivered size. The player draws a
# unit of height at about 150 px against 700 source px, so half size stays sharp on a 2x screen.
SERVED_SCALE = 0.5


def strip_checks(validation: dict) -> list[dict]:
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
    source: Path, delivered: Path, rows: int, columns: int, cells: int, anchor: str
) -> None:
    """Cut the model's picture into its strip again and require the delivered bytes."""
    data, _ = repack_alpha_components(
        source.read_bytes(),
        AlphaComponentRepackContract(
            rows=rows, columns=columns, required_cells=cells, anchor=anchor
        ),
    )
    if hashlib.sha256(data).hexdigest() != sha256(delivered):
        raise ValueError(
            f"{delivered.name}: cutting {source.name} again does not give the delivered strip"
        )


def build_record(repo: Path, media: Media, options: dict) -> dict:
    lineage = Lineage([(repo / p).resolve() for p in options["runs"]])
    delivered = repo / options["path"]
    actor = options["actor"]
    folder = Path("content/players") / actor
    player = load(delivered / "manifest.json")["player"]
    if player["player_id"] != actor:
        raise ValueError(
            f"{options['path']} delivers the player {player['player_id']}, not {actor}"
        )
    calibration = player["calibration"]

    prefix = f"player-{actor}-"
    ids = [nid for nid in lineage.delivered if nid.startswith(prefix)]
    ran = {nid: lineage.where_it_ran(nid) for nid in ids}
    feeds = {nid: [d for d in ran[nid][2]["depends_on"] if d in ran] for nid in ids}

    def made(nid: str, name: str) -> Path:
        return ran[nid][0] / folder / name

    def sidecar(nid: str, name: str) -> dict:
        return load(made(nid, name + ".meta.json"))

    nodes: dict[str, dict] = {}

    # Concept: the one picture every later drawing is held to, from the cover and the brief.
    concept_id = f"{prefix}concept-generate"
    concept_meta = sidecar(concept_id, "concept.png")
    package = repo / options["package"]
    cover_path = package / "references" / "cover.png"
    if sha256(cover_path) not in {i["sha256"] for i in concept_meta["inputs"]}:
        raise ValueError(f"{cover_path} is not the reference the concept request sent")
    brief = next(
        p
        for p in tomllib.loads((package / "content" / "player.toml").read_text(encoding="utf-8"))[
            "players"
        ]
        if p["player_id"] == actor
    )["prompt"]
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
    states = []
    for state, spec in player["states"].items():
        gen_id, val_id = f"{prefix}state-{state}-generate", f"{prefix}state-{state}-validate"
        raw_path = made(gen_id, f"states/{state}.source.png")
        drawn = media.still_alpha(f"{state}-drawn.webp", raw_path)
        nodes[gen_id] = record_node(
            gen_id,
            *ran[gen_id],
            kinds=JUDGES,
            depends_on=feeds[gen_id],
            prompt=sidecar(gen_id, f"states/{state}.source.png")["prompt"],
            thumb=drawn,
            pictures=[drawn],
        )

        validation = load(made(val_id, f"states/{state}.validation.json"))
        strip_path = delivered / folder / "states" / f"{state}.png"
        if (
            sha256(strip_path) != spec["asset"]["sha256"]
            or made(val_id, f"states/{state}.png").read_bytes() != strip_path.read_bytes()
        ):
            raise ValueError(f"{state}: the gated strip is not the one {options['path']} delivers")
        rebuild(
            raw_path,
            strip_path,
            spec["rows"],
            spec["columns"],
            spec["source_frame_count"],
            validation["repack"]["anchor"],
        )
        with Image.open(strip_path) as im:
            strip = im.convert("RGBA")
        shown = media.image(f"{state}-strip.webp", strip, [strip_path], "the delivered strip")
        nodes[val_id] = record_node(
            val_id,
            *ran[val_id],
            kinds=JUDGES,
            depends_on=feeds[val_id],
            checks=strip_checks(validation),
            thumb=shown,
            pictures=[shown],
        )

        served = strip.resize(
            (round(strip.width * SERVED_SCALE), round(strip.height * SERVED_SCALE)), Image.LANCZOS
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
    dvalidation = load(made(dval, "dialogue.validation.json"))
    if sha256(dialogue_path) != player["dialogue"]["asset"]["sha256"]:
        raise ValueError(f"the dialogue sheet is not the one {options['path']} delivers")
    rebuild(
        made(dgen, "dialogue.source.png"),
        dialogue_path,
        dvalidation["rows"],
        dvalidation["columns"],
        len(dvalidation["expressions"]),
        "center",
    )
    ddrawn = media.still_alpha("dialogue-drawn.webp", made(dgen, "dialogue.source.png"))
    dialogue = media.still_alpha("dialogue.webp", dialogue_path)
    nodes[dgen] = record_node(
        dgen,
        *ran[dgen],
        kinds=JUDGES,
        depends_on=feeds[dgen],
        prompt=sidecar(dgen, "dialogue.source.png")["prompt"],
        thumb=ddrawn,
        pictures=[ddrawn],
    )
    nodes[dval] = record_node(
        dval,
        *ran[dval],
        kinds=JUDGES,
        depends_on=feeds[dval],
        checks=strip_checks(dvalidation),
        thumb=dialogue,
        pictures=[dialogue],
    )

    # One size: a first judgement on a plate of every strip, then a check of the plate with it.
    rebase_id, verify_id = f"{prefix}motion-rebase", f"{prefix}motion-rebase-verify"
    first = load(made(rebase_id, "motion-rebase-first-pass.json"))
    final = load(made(verify_id, "motion-rebase.json"))
    if final["states"] != calibration["state_rebase"]:
        raise ValueError("the size table the package publishes is not the one the check wrote")
    for nid, name, key in (
        (rebase_id, "motion-rebase-plate.png", "plate_sha256"),
        (verify_id, "motion-rebase-verification-plate.png", "verification_plate_sha256"),
    ):
        if sha256(made(nid, name)) != final[key]:
            raise ValueError(f"{name} is not the plate the size check judged")
    plate = media.still("rebase-plate.webp", made(rebase_id, "motion-rebase-plate.png"), 1400)
    checked = media.still(
        "rebase-checked.webp", made(verify_id, "motion-rebase-verification-plate.png"), 1400
    )
    nodes[rebase_id] = record_node(
        rebase_id,
        *ran[rebase_id],
        kinds=JUDGES,
        depends_on=feeds[rebase_id],
        rationale=" ".join(f"{s}: {t}" for s, t in first["evidence"].items()),
        thumb=plate,
        pictures=[plate],
    )
    nodes[verify_id] = record_node(
        verify_id,
        *ran[verify_id],
        kinds=JUDGES,
        depends_on=feeds[verify_id],
        rationale=" ".join(f"{s}: {t}" for s, t in final["evidence"].items()),
        thumb=checked,
        pictures=[checked],
    )

    # Review: a contact sheet of everything, judged by a model that drew none of it.
    sheet_id, review_id = f"{prefix}contact-sheet", f"{prefix}review"
    sheet = media.still("contact-sheet.webp", made(sheet_id, "contact-sheet.png"), 1400)
    nodes[sheet_id] = record_node(
        sheet_id, *ran[sheet_id], depends_on=feeds[sheet_id], thumb=sheet, pictures=[sheet]
    )
    review = load(made(review_id, "review.json"))
    verdict = {
        "accepted": review["verdict"] == "accept",
        "criteria": [{"name": k, "passed": v, "evidence": ""} for k, v in review["checks"].items()],
        "issues": review.get("issues", []),
    }
    nodes[review_id] = record_node(
        review_id,
        *ran[review_id],
        kinds=REVIEWER,
        depends_on=feeds[review_id],
        verdict=verdict,
        rationale=review.get("evidence"),
    )

    missing = sorted(set(ids) - set(nodes))
    if missing:
        raise ValueError(f"nodes this page does not show: {missing}")

    strips = [delivered / folder / "states" / f"{s['state']}.png" for s in states]
    # When the whole set ran in one run, that run's clock is the set's; otherwise steps are summed.
    where = {ran[n][0] for n in ids}
    wall_ms = (
        load(where.pop() / "execution-summary.json")["duration_ms"]
        if len(where) == 1
        else sum(ran[n][1]["duration_ms"] or 0 for n in ids)
    )
    return {
        "schema": RECORD_SCHEMA,
        "adapter": "sprite_set",
        "run": {
            "path": str((delivered / folder).relative_to(repo)),
            "runs": options["runs"],
            "status": "succeeded",
            "graph_sha256": load(lineage.last / "execution-plan.json")["graph_sha256"],
            "graph_kind": "sideview-platformer",
        },
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
                "poster": lineup(media, strips, states, calibration),
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
            "estimated_cost_usd": sum(
                (ran[n][2].get("estimated_cost_high_usd") or 0) * (ran[n][1].get("attempts") or 1)
                for n in ids
            ),
            "animations": len(states),
            "frames": sum(len(s["frames"]) for s in states),
        },
        "models": models_of(nodes),
        "tree": index(delivered / folder),
        "nodes": nodes,
    }


def lineup(
    media: Media, strips: list[Path], states: list[dict], calibration: dict, per_row: int = 4
) -> dict:
    """Every animation playing side by side at the size the game draws it, four to a row.

    Each strip is scaled by the ruler and its own correction and stood on its row's line by the
    bottom of its cell, as the game places it; loops loop, one-shots play and hold, a hold holds,
    and a climb steps its frames as if climbing steadily.
    """
    unit = 190  # px per unit of height
    per_unit = calibration["source_px_per_unit"]
    step_ms, cycle_ms = 50, 2400
    pieces = []
    for path, s in zip(strips, states, strict=True):
        with Image.open(path) as im:
            rgba = im.convert("RGBA")
        cw, ch = s["cell"]
        cells = [rgba.crop((i * cw, 0, (i + 1) * cw, ch)) for i in s["frames"]]
        boxes = [c.getchannel("A").getbbox() for c in cells]
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
                "frames": [c.crop(union).resize(size, Image.LANCZOS) for c in cells],
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

    def index_at(spec: dict, t: float) -> int:
        n = len(spec["frames"])
        if spec["mode"] == "hold":
            return 0
        if spec["mode"] == "gameplay_driven":
            return int(t / 0.3) % n
        i = int(t * spec["fps"])
        return i % n if spec["mode"] == "loop" else min(i, n - 1)

    frames = []
    for tick in range(cycle_ms // step_ms):
        t = tick * step_ms / 1000
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        top = margin
        for r, row_height in zip(rows, heights, strict=True):
            ground = top + row_height
            x = (width - sum(p["frames"][0].width for p in r) - gap * (len(r) - 1)) // 2
            for p in r:
                im = p["frames"][index_at(p["spec"], t)]
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

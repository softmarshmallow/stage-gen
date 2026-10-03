"""What Ember Hollow's build holds each picture and sound to, and how it finishes each one.

Pure: the builder names a gate or a finish and states its arguments while planning, and the
judges and publishing steps call these over bytes. A gate refuses with a ``ValueError``
whose message lists every reason; a finish returns the published bytes and the record the
manifest reads, in the shape every earlier run of this game wrote, so ``manifest.py`` reads
a gnode build exactly as it read one of those.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from io import BytesIO
from typing import Any, Final, cast

from PIL import Image

from demo_game_tools.kits.effects_art.sprite import (
    canonicalize_dust_atlas,
    dust_atlas_contract,
    validate_dust_atlas,
)
from ember_hollow_pipeline import gates
from ember_hollow_pipeline.preparation_media import _look_drift, _normalise_look
from stage_gen.components.sound_effect import admit_sound_effect_bytes_sync
from stage_gen.media import measure_level_and_duration_sync, validate_music_payload

#: The canvases: a sprite or a sheet cell's look, an actor strip, a ground plate.
SPRITE_CANVAS: Final = (1024, 1024)
STRIP_CANVAS: Final = (1536, 1024)
GROUND_CANVAS: Final = (1024, 1024)
#: Columns of every actor motion strip.
MOTION_COLUMNS: Final = 4
#: The four cells of a lightning strike sheet, in reading order.
STRIKE_CELL_KINDS: Final = ("bolt_0", "bolt_1", "bolt_2", "bolt_3")
#: A music loop shorter or quieter than this is refused.
MUSIC_MIN_SECONDS: Final = 45.0
MUSIC_PEAK_MIN_DBFS: Final = -30.0
#: How far short of its asked length a clip may come back.
SOUND_DURATION_TOLERANCE_SECONDS: Final = 0.5

Args = Mapping[str, Any]
#: Arguments that arrive as JSON lists and are ranges or tuples to the gates.
_TUPLES: Final = frozenset({"luma_range", "coverage", "coverage_range", "states", "kinds"})


def _plain(args: Args) -> dict[str, Any]:
    return {key: tuple(value) if key in _TUPLES else value for key, value in args.items()}


def _need(reference: bytes | None, what: str) -> bytes:
    if reference is None:
        raise ValueError(f"this gate reads {what}, and none was given")
    return reference


# ----------------------------------------------------------------------------- gates


def _prop(data: bytes, args: Args, _reference: bytes | None) -> dict[str, object]:
    return gates.gate_prop(data, **_plain(args))


def _prop_sheet(data: bytes, args: Args, _reference: bytes | None) -> dict[str, object]:
    _sprites, record = gates.gate_prop_sheet(data, **_plain(args))
    return record


def _canvas(data: bytes, args: Args, _reference: bytes | None) -> dict[str, object]:
    return gates.gate_transparent_canvas(data, **_plain(args))


def _ground(data: bytes, args: Args, _reference: bytes | None) -> dict[str, object]:
    return gates.gate_ground_texture(data, **_plain(args))


def _macro(data: bytes, args: Args, _reference: bytes | None) -> dict[str, object]:
    return gates.gate_macro_plate(data, **_plain(args))


def _decal(data: bytes, args: Args, _reference: bytes | None) -> dict[str, object]:
    # The feather is applied at publish, deterministically, so the draw is not held to it.
    return gates.gate_decal(data, soft_edge=False, **_plain(args))


def _motion(data: bytes, args: Args, _reference: bytes | None) -> dict[str, object]:
    _canonical, record = gates.gate_motion_atlas(data, **_plain(args))
    return record


def _pieces(data: bytes, args: Args, reference: bytes | None) -> dict[str, object]:
    _canonical, record = gates.gate_piece_sheet(
        data, template=_need(reference, "the lattice template"), **_plain(args)
    )
    return record


def _fire(data: bytes, args: Args, reference: bytes | None) -> dict[str, object]:
    _canonical, record = gates.gate_fx_strip(
        data, template=_need(reference, "the lattice template"), **_plain(args)
    )
    return record


def _dust(data: bytes, _args: Args, _reference: bytes | None) -> dict[str, object]:
    return dict(validate_dust_atlas(data))


def _quadrant(data: bytes, args: Args, _reference: bytes | None) -> dict[str, object]:
    return gates.gate_quadrant_sheet(data, **_plain(args))


def _look(data: bytes, args: Args, reference: bytes | None) -> dict[str, object]:
    facts = gates.gate_prop(data, **_plain(args))
    # A paintover that came back a different size or moved its foot is a bad draw.
    drift, reasons = _look_drift(_need(reference, "the summer sprite"), data)
    if reasons:
        raise gates.GateError(reasons)
    return {**facts, "drift": drift}


PICTURE_GATES: Final[dict[str, Callable[[bytes, Args, bytes | None], dict[str, object]]]] = {
    "prop": _prop,
    "prop_sheet": _prop_sheet,
    "canvas": _canvas,
    "ground": _ground,
    "macro": _macro,
    "decal": _decal,
    "motion": _motion,
    "pieces": _pieces,
    "fire": _fire,
    "dust": _dust,
    "quadrant": _quadrant,
    "look": _look,
}


def gate_picture(
    gate: str, data: bytes, args: Args, reference: bytes | None = None
) -> dict[str, object]:
    """The named gate's facts about one picture, or a refusal listing every reason."""

    check = PICTURE_GATES.get(gate)
    if check is None:
        raise ValueError(f"no picture gate named {gate!r}")
    return check(data, args, reference)


def gate_music(data: bytes, *, ffmpeg: str = "ffmpeg") -> dict[str, object]:
    """A playable loop at least the floor's length and loud enough to hear.

    The loop seam itself is not measured: the brief asks the model to end where it
    begins, and whether it did is a listening verdict, not a number.
    """

    facts = validate_music_payload(data)
    measured = measure_level_and_duration_sync(data, ffmpeg=ffmpeg)
    reasons: list[str] = []
    if measured.duration_seconds < MUSIC_MIN_SECONDS:
        reasons.append(
            f"loop is {measured.duration_seconds:.1f} s, under the {MUSIC_MIN_SECONDS:.0f} s floor"
        )
    if measured.peak_dbfs < MUSIC_PEAK_MIN_DBFS:
        reasons.append(
            f"peak {measured.peak_dbfs:.1f} dBFS is under the {MUSIC_PEAK_MIN_DBFS:.0f} dBFS floor"
        )
    if reasons:
        raise gates.GateError(reasons)
    return {
        **facts,
        "duration_seconds": round(measured.duration_seconds, 3),
        "peak_dbfs": round(measured.peak_dbfs, 2),
        "duration_floor_seconds": MUSIC_MIN_SECONDS,
        "peak_floor_dbfs": MUSIC_PEAK_MIN_DBFS,
    }


def gate_sound(
    data: bytes, *, duration_seconds: float, ffmpeg: str = "ffmpeg"
) -> dict[str, object]:
    """The shared clip admission (silent or clipped is refused) plus the length asked."""

    facts = admit_sound_effect_bytes_sync(data)
    measured = measure_level_and_duration_sync(data, ffmpeg=ffmpeg)
    if measured.duration_seconds < duration_seconds - SOUND_DURATION_TOLERANCE_SECONDS:
        raise gates.GateError(
            [
                f"clip is {measured.duration_seconds:.2f} s, short of the"
                f" {duration_seconds:.1f} s asked"
            ]
        )
    return {
        **facts,
        "duration_seconds": round(measured.duration_seconds, 3),
        "peak_dbfs": round(measured.peak_dbfs, 2),
        "requested_duration_seconds": duration_seconds,
    }


def gate_audio(gate: str, data: bytes, args: Args, *, ffmpeg: str = "ffmpeg") -> dict[str, object]:
    """The named audio gate: ``music`` or ``sound`` (which reads ``duration_seconds``)."""

    if gate == "music":
        return gate_music(data, ffmpeg=ffmpeg)
    if gate == "sound":
        return gate_sound(data, duration_seconds=float(args["duration_seconds"]), ffmpeg=ffmpeg)
    raise ValueError(f"no audio gate named {gate!r}")


# ----------------------------------------------------------------------------- finishes


def _png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def finish_picture(
    finish: str,
    data: bytes,
    *,
    gate: str,
    args: Args,
    head: Mapping[str, object],
    reference: bytes | None = None,
) -> tuple[bytes, dict[str, object]]:
    """The published picture and its record, for one admitted draw."""

    if finish == "sprite":
        facts = gate_picture(gate, data, args, reference)
        canonical, alpha = gates.canonicalize_sprite_alpha(data)
        return canonical, {**head, "alpha_canonicalization": alpha, **facts}
    if finish == "look":
        summer = _need(reference, "the summer sprite")
        facts = gate_picture("prop", data, args)
        drift, reasons = _look_drift(summer, data)
        if reasons:
            raise gates.GateError(reasons)
        normalised, placement = _normalise_look(summer, data)
        canonical, alpha = gates.canonicalize_sprite_alpha(normalised)
        return canonical, {
            **head,
            "alpha_canonicalization": alpha,
            "drift": drift,
            "normalised": placement,
            **facts,
        }
    if finish == "plate":
        facts = gate_picture(gate, data, args, reference)
        tiled, mirror = gates.mirror_repeat_2d(data)
        edges = gates.gate_tileable_2d(tiled)
        return tiled, {**head, "source": facts, "mirror": mirror, "edges": edges}
    if finish == "decal":
        drawn_share = gates.decal_soft_edge_share(data)
        feathered = gates.feather_decal_edge(data)
        facts = gates.gate_decal(feathered, **_plain(args))
        return feathered, {
            **head,
            "drawn_soft_edge_share": round(drawn_share, 4),
            "feather_radius_px": gates.DECAL_FEATHER_RADIUS_PX,
            **facts,
        }
    if finish == "motion":
        canonical, record = gates.gate_motion_atlas(data, **_plain(args))
        return canonical, {**head, **record}
    if finish == "pieces":
        canonical, record = gates.gate_piece_sheet(
            data, template=_need(reference, "the lattice template"), **_plain(args)
        )
        return canonical, {**record, **head}
    if finish == "fire":
        canonical, record = gates.gate_fx_strip(
            data, template=_need(reference, "the lattice template"), **_plain(args)
        )
        order = gates.strip_playback_order(
            cast("int", record["frames"]), cast("str", record["mode"])
        )
        return canonical, {**record, "playback_order": order}
    if finish == "dust":
        canonical, facts = canonicalize_dust_atlas(data)
        width, height = (int(side) for side in args["canvas"])
        cells = [
            {
                "kind": kind,
                "x": (index % 2) * (width // 2),
                "y": (index // 2) * (height // 2),
                "w": width // 2,
                "h": height // 2,
            }
            for index, kind in enumerate(args["kinds"])
        ]
        return canonical, {**head, "cells": cells, "shared_geometry": dust_atlas_contract(facts)}
    if finish == "quadrant":
        canonical, alpha = gates.canonicalize_sprite_alpha(data)
        facts = gate_picture("quadrant", canonical, args)
        return canonical, {**head, **facts, "alpha": alpha}
    raise ValueError(f"no picture finish named {finish!r}")


def cut_sheet(data: bytes, args: Args) -> tuple[dict[str, bytes], dict[str, object]]:
    """A prop sheet's per-look sprites and its gate record, cut at the emptiest seams."""

    return gates.gate_prop_sheet(data, **_plain(args))


def sheet_look(
    data: bytes, args: Args, *, state: str, head: Mapping[str, object]
) -> tuple[bytes, dict[str, object]]:
    """One look cut from a sheet, with the record a sprite drawn alone would have."""

    sprites, record = cut_sheet(data, args)
    cells = cast("list[dict[str, object]]", record["cells"])
    cell = next((entry for entry in cells if entry["state"] == state), None)
    if cell is None:
        raise ValueError(f"the sheet has no {state} look")
    facts = {
        key: value
        for key, value in cell.items()
        if key not in {"index", "state", "x", "y", "w", "h", "alpha_canonicalization"}
    }
    look = {
        **head,
        "state": state,
        "alpha_canonicalization": cell["alpha_canonicalization"],
        "drawn": {
            "kind": "sheet",
            "columns": args["columns"],
            "rows": args["rows"],
            "cell_px": args["cell_px"],
            "index": cell["index"],
        },
        **facts,
    }
    return sprites[state], look


def sheet_canonical(data: bytes, args: Args, *, prop_id: str) -> tuple[bytes, dict[str, object]]:
    """The canonical looks laid back on the sheet's grid, and the whole sheet's record."""

    sprites, record = cut_sheet(data, args)
    canvas = Image.new(
        "RGBA",
        (int(args["columns"]) * int(args["cell_px"]), int(args["rows"]) * int(args["cell_px"])),
        (0, 0, 0, 0),
    )
    for cell in cast("list[dict[str, object]]", record["cells"]):
        with Image.open(BytesIO(sprites[str(cell["state"])])) as opened:
            canvas.alpha_composite(
                opened.convert("RGBA"), (int(cast(int, cell["x"])), int(cast(int, cell["y"])))
            )
    return _png(canvas), {**record, "prop_id": prop_id}


def finish_audio(
    gate: str, data: bytes, args: Args, *, head: Mapping[str, object], ffmpeg: str = "ffmpeg"
) -> dict[str, object]:
    """An admitted track or clip's record; the bytes are published unchanged."""

    facts = gate_audio(gate, data, args, ffmpeg=ffmpeg)
    # Whether a loop's end meets its beginning is a listening verdict, not a number.
    return {**head, **facts, "seam_measured": False}


__all__ = [
    "GROUND_CANVAS",
    "MOTION_COLUMNS",
    "MUSIC_MIN_SECONDS",
    "MUSIC_PEAK_MIN_DBFS",
    "PICTURE_GATES",
    "SOUND_DURATION_TOLERANCE_SECONDS",
    "SPRITE_CANVAS",
    "STRIKE_CELL_KINDS",
    "STRIP_CANVAS",
    "cut_sheet",
    "finish_audio",
    "finish_picture",
    "gate_audio",
    "gate_music",
    "gate_picture",
    "gate_sound",
    "sheet_canonical",
    "sheet_look",
]

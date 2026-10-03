"""Ember Hollow's pictures: the lattice templates, the judge every draw meets, the finishes.

Every paid picture is held to a named gate by a judge and drawn again when it fails; the
publishing step runs the same gate, finishes the picture (alpha lifted, a plate mirrored, a
strip repacked, a sheet cut at its emptiest seams) and writes the record the manifest
reads. An auditioned take is adopted through the same gate instead of drawn.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ember_hollow_pipeline import build, templates
from gnode import Ctx, node

_GATE = {"gate": str, "args": dict}


def _reference(ctx: Ctx) -> bytes | None:
    return ctx.read.bytes("reference") if "reference" in ctx.inputs else None


@node(
    "lattice_template",
    params={"columns": int, "rows": int, "cell_px": int, "transparent": bool},
    outputs={"image": "image/png"},
    version=1,
)
def lattice_template(ctx: Ctx) -> dict[str, Any]:
    """The cyan-guided paintover lattice a strip or a sheet is painted into."""

    data = templates.lattice_template(
        ctx.params["columns"],
        ctx.params["rows"],
        ctx.params["cell_px"],
        transparent=ctx.params["transparent"],
    )
    return {"image": ctx.out.bytes(data, "image/png")}


@node(
    "admit_picture",
    inputs={"image": "image", "reference": "image?"},
    params=_GATE,
    judge=True,
    version=1,
)
def admit_picture(ctx: Ctx) -> dict[str, Any]:
    """The draw passes its named gate, or it is drawn again."""

    try:
        facts = build.gate_picture(
            ctx.params["gate"], ctx.read.bytes("image"), ctx.params["args"], _reference(ctx)
        )
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "finish_picture",
    inputs={"source": "image", "reference": "image?"},
    params={**_GATE, "finish": str, "head": dict},
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def finish_picture(ctx: Ctx) -> dict[str, Any]:
    """The published picture and the record of the gate it passed."""

    data, record = build.finish_picture(
        ctx.params["finish"],
        ctx.read.bytes("source"),
        gate=ctx.params["gate"],
        args=ctx.params["args"],
        head=ctx.params["head"],
        reference=_reference(ctx),
    )
    return {"image": ctx.out.bytes(data, "image/png"), "validation": ctx.out.json(record)}


@node(
    "cut_look",
    inputs={"sheet": "image"},
    params={"args": dict, "state": str, "head": dict},
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def cut_look(ctx: Ctx) -> dict[str, Any]:
    """One look cut from an admitted sheet, recorded as a sprite drawn alone would be."""

    data, record = build.sheet_look(
        ctx.read.bytes("sheet"),
        ctx.params["args"],
        state=ctx.params["state"],
        head=ctx.params["head"],
    )
    return {"image": ctx.out.bytes(data, "image/png"), "validation": ctx.out.json(record)}


@node(
    "lay_sheet",
    inputs={"sheet": "image"},
    params={"args": dict, "prop_id": str},
    outputs={"image": "image/png", "validation": "json"},
    version=1,
)
def lay_sheet(ctx: Ctx) -> dict[str, Any]:
    """The canonical looks laid back on the sheet's grid, and every look's measurements."""

    data, record = build.sheet_canonical(
        ctx.read.bytes("sheet"), ctx.params["args"], prop_id=ctx.params["prop_id"]
    )
    return {"image": ctx.out.bytes(data, "image/png"), "validation": ctx.out.json(record)}


@node(
    "adopt_picture",
    inputs={"take": "image?", "reference": "image?"},
    params={**_GATE, "path": str, "sha256": str},
    outputs={"image": "image/png"},
    version=1,
)
def adopt_picture(ctx: Ctx) -> dict[str, Any]:
    """An auditioned take, adopted through the gate a fresh draw meets."""

    path = ctx.params["path"]
    if "take" not in ctx.inputs:
        raise ctx.fail(
            f"the take {path} is not on disk: auditioned takes are kept beside the package, "
            "not in git, so copy it into the package before building"
        )
    data = ctx.read.bytes("take")
    found = hashlib.sha256(data).hexdigest()
    if found != ctx.params["sha256"]:
        raise ctx.fail(
            f"the take {path} does not match its declared sha256: "
            f"declared {ctx.params['sha256']}, found {found}"
        )
    try:
        facts = build.gate_picture(ctx.params["gate"], data, ctx.params["args"], _reference(ctx))
    except ValueError as error:
        raise ctx.fail(f"the take {path} does not pass its gate: {error}") from None
    ctx.fact("adoption", {"adopted_from": path, "adopted_sha256": found, **facts})
    return {"image": ctx.out.bytes(data, "image/png")}


__all__ = [
    "adopt_picture",
    "admit_picture",
    "cut_look",
    "finish_picture",
    "lattice_template",
    "lay_sheet",
]

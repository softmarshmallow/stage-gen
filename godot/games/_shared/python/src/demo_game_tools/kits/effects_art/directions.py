"""What the effects family asks for and where it publishes: prompts, schemas, paths, records.

Pure, so the steps that paint, place, review and canonicalize a plate, and the manifest
block that publishes it, read one definition. The provider calls are the host's.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from typing import Any, cast

from PIL import Image

from demo_game_tools.kits.effects_art.cut_in import (
    CUT_IN_FRAME,
    CUT_IN_PORTRAIT,
    PLACEMENT_CENTRE_RANGE,
    PLACEMENT_SCALE_RANGE,
    CutInPlate,
)
from demo_game_tools.kits.effects_art.models import CutInPortraitSubject
from demo_game_tools.kits.effects_art.sprite import canonicalize_dust_atlas, dust_atlas_contract
from stage_gen.media import data_url

#: A plate's validation record, per role: the portrait's gained its placement, the
#: frame's did not.
FX_CUT_IN_FRAME_VALIDATION_VERSION = "prepared-fx-cut-in-validation-v3"
FX_CUT_IN_PORTRAIT_VALIDATION_VERSION = "prepared-fx-cut-in-validation-v3"
FX_SPRITE_DUST_VALIDATION_KIND = "fx-sprite-dust-validation-v1"

#: The placement episode's budget. Six looks is what an art director needs to settle a
#: scale and a centre.
FX_CUT_IN_PLACE_MAX_STEPS = 6
#: The placement agent starts from the portrait at half the frame height, centred on the
#: opening, and looks at compositions this wide, JPEG, over the stage colour.
START_SCALE = 0.5
_RENDER_WIDTH = 768
_RENDER_STAGE = (28, 34, 48)

CUT_IN_PLATES_BY_ROLE: dict[str, CutInPlate] = {"frame": CUT_IN_FRAME, "portrait": CUT_IN_PORTRAIT}

_PLATE_COMMON = (
    "Everything outside the described subject is fully transparent, alpha 0, with no glow, "
    "drop shadow, colour wash, backdrop, vignette, or scenery behind it. No text, numbers, "
    "labels, logos, signatures, or watermarks anywhere."
)

#: What the placement agent is told it is.
PLACE_SYSTEM = (
    "You are a 2D game presentation art director. You place a die-cut portrait plate "
    "inside a torn-strip frame by trying placements with the render tool and judging the "
    "result with your eyes. Every turn calls a tool; finish with submit."
)
#: What a reviewer is told it is.
REVIEW_SYSTEM = (
    "You are a strict independent 2D game-art technical director. Return only the "
    "requested structured review."
)


#: The shape an unopinionated game gets. An authored ``cut_in.frame.shape`` replaces it
#: outright rather than arguing with it, so the two can never contradict each other in
#: one prompt; everything around the slot is the invariant a plate must hold whatever
#: its silhouette is.
_FRAME_SHAPE_DEFAULT = (
    "One connected, wide, slightly tilted ragged strip that runs across the entire canvas "
    "from the left edge to the right edge, cut off by both edges, occupying roughly half the "
    "canvas height, with rough hand-torn jagged edges along its top and its bottom."
)

#: The frame around the slot says paper, ink and emptiness — never how the edge is cut.
#: It used to open "one torn-paper rip" and end on "hugging its torn edges", which outvoted
#: an authored shape three to one: two live rejects in a row said the silhouette came back
#: conventionally ragged however clearly the shape asked for clean facets. Edge character
#: belongs to exactly one sentence, and the default one still says hand-torn.
_FRAME_TASK = (
    "Create one paper cut-out silhouette to be used as a game cut-in frame. {shape} It must "
    "read as a single bold graphic element that carries the width of the screen. Fill it with "
    "flat pure white only, and draw a thick uneven black hand-inked outline hugging its "
    "edges, following their shape exactly. Nothing at all inside it: no drawing, no "
    "character, no texture, no shadow, no gradient, no colour. Flat graphic 2D, bold "
    "print-poster cut-out look."
)

_PORTRAIT_TASK = (
    "Create one die-cut character plate for a game cut-in: a tight close-up of the character "
    "in the references, head, hair, neck and collar only, filling the canvas so the hair is "
    "cropped by the top and both side edges and the collar by the bottom edge. Identity comes "
    "from the references alone: exactly that face, eyes, hair, and accessories, at the same "
    "age and proportions as shown. Bold clean ink contours and cel shading, slightly tilted "
    "dynamic angle, eyes toward the viewer. The plate has a clean alpha edge along the "
    "silhouette."
)


def frame_content_task(direction: str, shape: str | None = None) -> str:
    task = _FRAME_TASK.format(shape=shape or _FRAME_SHAPE_DEFAULT)
    return f"{task}\nAuthored direction: {direction}\n{_PLATE_COMMON}"


#: The same plate for an actor the run draws itself. Everything the human portrait
#: takes from an authored face - the identity, the proportions, what a "close-up" even
#: means for this body - this one takes from the concept plate the graph hands it as
#: image 1, so it never has to be described twice and cannot be described differently.
#: The connectedness clause leads rather than trails because the plate gate admits one
#: dominant shape: a machine's hanging parts are exactly what drifts off into debris,
#: and a demand made late in a prompt is the one that gets dropped.
_SUBJECT_TASK = (
    "Create one die-cut plate for a game cut-in: a tight close-up of the front of the "
    "subject in image 1, drawn as one connected mass with every hanging or trailing part "
    "touching the body rather than floating apart, filling the canvas so its silhouette "
    "is cropped by the top and by both side edges. Identity comes from image 1 alone: "
    "exactly that build, those markings, colours, and fittings, in the same proportions, "
    "turned so that whatever on it reads as a face - a lens, a head, a mouth of tools - "
    "faces the viewer. Bold clean ink contours and cel shading, slightly tilted dynamic "
    "angle. The plate has a clean alpha edge along the silhouette."
)


def portrait_content_task(direction: str) -> str:
    return f"{_PORTRAIT_TASK}\nExpression and mood: {direction}\n{_PLATE_COMMON}"


def subject_content_task(direction: str) -> str:
    return f"{_SUBJECT_TASK}\nMoment and mood: {direction}\n{_PLATE_COMMON}"


_PLACE_TASK = (
    "Place this character portrait inside the torn-strip cut-in frame so the composition "
    "reads like a production cut-in. The face should fill the band: eyes in the band's "
    "upper-middle, the mouth fully inside the band, the head neither floating in empty "
    "backdrop nor so large that the eyes or mouth are cut by the torn edges. Hair, ears, "
    "and shoulders may bleed past the edges; that is the look. Prefer the face over the "
    "band's thickest stretch. Iterate: render a placement, look at it, adjust the scale "
    "and the centre, and submit only a placement you have rendered and seen."
)

#: A subject plate has no eyes or mouth to keep inside the band, so the same
#: instruction is written against the parts it does have.
_PLACE_SUBJECT_TASK = (
    "Place this cut-out subject plate inside the torn-strip cut-in frame so the "
    "composition reads like a production cut-in. The subject should fill the band: the "
    "part of it that reads as a face over the band's upper-middle, the body fully inside "
    "the band, neither floating in empty backdrop nor so large that the front of it is "
    "cut away by the torn edges. Outlying parts may bleed past the edges; that is the "
    "look. Prefer the subject over the band's thickest stretch. Iterate: render a "
    "placement, look at it, adjust the scale and the centre, and submit only a placement "
    "you have rendered and seen."
)


def place_content_task(
    portrait_id: str, direction: str, *, subject: CutInPortraitSubject | None = None
) -> str:
    task = _PLACE_TASK if subject is None else _PLACE_SUBJECT_TASK
    return f"{task}\nPortrait: {portrait_id}. Its authored mood: {direction}"


def cut_in_review_prompt(
    plate: CutInPlate,
    direction: str,
    shape: str | None = None,
    *,
    subject: CutInPortraitSubject | None = None,
) -> str:
    """What the judge is asked, given what the pixel gate has already proved.

    The gate no longer fixes the rip's topology, so the frame's silhouette is judged
    here, against the shape its author asked for."""

    if plate.role == "frame":
        return (
            "Review the generated cut-in frame plate against its authored direction. Image 1 "
            "shows the plate over a checkerboard on the left and, on the right, the plate "
            "composed the way the game shows it: a flat backdrop with stripes revealed through "
            "the plate's silhouette. Remaining images are authored visual references. "
            "Deterministic pixel validation has already proved a transparent exterior with a "
            "binary edge, few enough pieces and no debris, a flat white fill, and an inked "
            "rim. It did not judge the silhouette; you do. Do not mistake the checkerboard "
            "for artwork. Judge style coherence with the references, that the plate reads as "
            "a torn cut-out rather than a drawn frame, that its silhouette is the authored "
            "shape and carries the screen's width, that the rim is ink and not a glow, and "
            "the absence of text, pseudo-text, characters, or scenery. Authored shape: "
            f"{shape or _FRAME_SHAPE_DEFAULT} Authored direction: {direction} Uncertainty "
            "must not be called accept."
        )
    if subject is not None:
        return (
            "Review the generated cut-in subject plate against its authored direction. Image 1 "
            "shows the plate over a checkerboard on the left and, on the right, the plate "
            "composed inside the game's cut-in frame exactly as the game shows it. Image 2 is "
            "the identity concept plate of the very subject this cut-in announces, drawn in "
            "the same run; any remaining images are authored style references. Deterministic "
            "pixel validation has already proved a transparent exterior with no painted "
            "backdrop and one dominant shape. Do not mistake the checkerboard for artwork. "
            "Judge that the build, markings, colours and fittings are unmistakably the same "
            "subject as image 2 rather than another of its kind, that it is drawn close and "
            "cropped by the canvas rather than floating small in it, that the mood matches the "
            "direction, and the absence of text, pseudo-text, logos, or scenery. Authored "
            f"direction: {direction} Uncertainty must not be called accept."
        )
    return (
        "Review the generated cut-in portrait plate against its authored direction. Image 1 "
        "shows the plate over a checkerboard on the left and, on the right, the plate composed "
        "inside the game's cut-in frame exactly as the game shows it. Remaining images are the "
        "authored character references. Deterministic pixel validation has already proved a "
        "transparent exterior with no painted backdrop and one subject. Do not mistake the "
        "checkerboard for artwork. Judge that the face, hair, eyes and accessories are the "
        "same character as the references, that the expression matches the direction, that "
        "the head is cropped by the canvas rather than floating, and the absence of text, "
        f"pseudo-text, logos, or scenery. Authored direction: {direction} Uncertainty must "
        "not be called accept."
    )


def plate_id_for(role: str, portrait_id: str | None = None) -> str:
    return "frame" if role == "frame" else f"portrait-{portrait_id}"


def cut_in_artifact_refs(plate_id: str) -> tuple[str, str, str, str, str, str]:
    """Every path one plate writes: raw, canonical, placement, validation, evidence, verdict."""

    name = plate_id.replace("portrait-", "portrait.", 1)
    return (
        f"fx/cut_in/{name}.raw.png",
        f"fx/cut_in/{name}.png",
        f"fx/cut_in/{name}.placement.json",
        f"fx/cut_in/{name}.validation.json",
        f"fx/cut_in/{name}.evidence.png",
        f"fx/cut_in/{name}.review.json",
    )


PLACEMENT_PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "scale": {
            "type": "number",
            "description": (
                "Portrait display height as a fraction of the frame canvas height "
                f"({PLACEMENT_SCALE_RANGE[0]:g} to {PLACEMENT_SCALE_RANGE[1]:g})."
            ),
        },
        "x": {
            "type": "number",
            "description": (
                "Portrait canvas centre x in frame-canvas units, 0 = left edge, 1 = right "
                f"edge ({PLACEMENT_CENTRE_RANGE[0]:g} to {PLACEMENT_CENTRE_RANGE[1]:g})."
            ),
        },
        "y": {
            "type": "number",
            "description": (
                "Portrait canvas centre y in frame-canvas units, 0 = top edge, 1 = bottom "
                f"edge ({PLACEMENT_CENTRE_RANGE[0]:g} to {PLACEMENT_CENTRE_RANGE[1]:g})."
            ),
        },
    },
}


def fx_cut_in_place_schema() -> dict[str, object]:
    """The submit payload: the placement plus the reason it is right."""

    properties = dict(cast(Mapping[str, object], PLACEMENT_PARAMETERS["properties"]))
    properties["rationale"] = {
        "type": "string",
        "description": "One or two sentences on why this placement reads correctly.",
    }
    return {"type": "object", "properties": properties}


def parse_placement(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not {"scale", "x", "y", "rationale"} <= set(value):
        raise ValueError("placement must carry scale, x, y, and rationale")
    return value


def mask_facts(reveal: Mapping[str, Any]) -> str:
    """The opening described to the agent in words, measured from the mask raster.

    Raster, not the published outline: the numbers must stay true for a shape no single
    polygon describes, and ``filled`` is what tells the agent one thick band from two
    thin pieces stacked at the same x."""

    centre_x, centre_y = cast(list[float], reveal["centroid"])
    spans = []
    for column in cast(list[dict[str, float]], reveal["columns"]):
        x = column["x"]
        if "top" not in column:
            spans.append(f"x={x:.1f}: closed")
            continue
        spans.append(
            f"x={x:.1f}: y {column['top']:.2f}-{column['bottom']:.2f} "
            f"({column['filled']:.2f} of the column open)"
        )
    return (
        "The frame's opening (the region the portrait shows through) has its centroid at "
        f"x={centre_x:.3f}, y={centre_y:.3f} and covers {reveal['coverage']:.2f} of the "
        "canvas. Where it lies, in frame-canvas units: " + "; ".join(spans) + "."
    )


def render_data_url(composed: Image.Image) -> str:
    stage = Image.new("RGBA", composed.size, (*_RENDER_STAGE, 255))
    stage.alpha_composite(composed)
    scaled = stage.convert("RGB").resize(
        (_RENDER_WIDTH, round(composed.height * _RENDER_WIDTH / composed.width)),
        Image.Resampling.LANCZOS,
    )
    stream = io.BytesIO()
    scaled.save(stream, format="JPEG", quality=85, optimize=True)
    return data_url(stream.getvalue(), "image/jpeg")


def validation_version_for(role: str) -> str:
    return (
        FX_CUT_IN_FRAME_VALIDATION_VERSION
        if role == "frame"
        else FX_CUT_IN_PORTRAIT_VALIDATION_VERSION
    )


def fx_cut_in_review_schema() -> dict[str, object]:
    """The judge's answer shape: the questions the pixel gate cannot decide."""

    checks = {
        key: {"type": "boolean"}
        for key in (
            "style_coherence",
            "identity_match",
            "expression_matches_direction",
            "reads_as_torn_edge",
            "text_free",
        )
    }
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["accept", "reject", "uncertain"]},
            "confidence": {"type": "number"},
            "checks": {"type": "object", "properties": checks},
            "issues": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "string"},
        },
    }


#: What a particle must survive. Round one of the spike asked for dust and got beautiful
#: plates whose wisps, grit flecks and hairline outlines all became grey speckle at the size
#: a puff is actually drawn. The instruction that fixed it is not about dust at all: it is a
#: size, a floor on lobe scale, and an explicit list of what must not be drawn.
_SPRITE_SMALL = (
    "This is a small game particle: it must stay bold and readable when it is scaled down to "
    "about forty pixels across. Build it from only a few large simple rounded lobes. No thin "
    "wisps, no trailing streaks, no small scattered flecks or specks, no fine internal detail, "
    "no faint haze, no thin tapering tails."
)

#: The sheet's shape. The four silhouettes are named in the reading order
#: ``DUST_CELL_KINDS`` fixes, because that order is what binds a cell to the contact it
#: draws; the gate checks separation and solidity, and this sentence is what makes them
#: likely in the first place.
_DUST_TASK = (
    "A sprite sheet of cartoon dust puffs for a game, laid out as a two-by-two grid of four "
    "separate clouds on one canvas, each puff centred in its own quarter, well clear of the "
    "others and of the canvas edges, and all four drawn at a similar size. The four "
    "silhouettes differ, in reading order: the first low and wide, the second tall and "
    "rounded, the third small and compact, the fourth leaning to one side as if swept. "
    "{direction} " + _SPRITE_SMALL
)


def dust_content_task(direction: str) -> str:
    """The dust atlas brief: the sheet's shape, the package's register, the alpha rule."""

    return f"{_DUST_TASK.format(direction=direction.strip())} {_PLATE_COMMON}"


def sprite_dust_artifact_refs() -> tuple[str, str, str]:
    """Every path the dust atlas writes: raw, canonical, validation."""

    return (
        "fx/sprite/dust.raw.png",
        "fx/sprite/dust.png",
        "fx/sprite/dust.validation.json",
    )


def derive_sprite_dust_validation(raw: bytes) -> tuple[bytes, dict[str, object], dict[str, Any]]:
    """Canonical atlas, the record a consumer reads, and the facts behind it."""

    canonical, facts = canonicalize_dust_atlas(raw)
    record: dict[str, object] = {
        "schema_version": 1,
        "kind": FX_SPRITE_DUST_VALIDATION_KIND,
        "sprite": "dust",
        "pixel_rewrite": facts["pixel_rewrite"],
        "source": facts["source"],
        "canonical": facts["canonical"],
        **dust_atlas_contract(facts),
    }
    return canonical, record, facts


__all__ = [
    "CUT_IN_PLATES_BY_ROLE",
    "FX_CUT_IN_FRAME_VALIDATION_VERSION",
    "FX_CUT_IN_PLACE_MAX_STEPS",
    "FX_CUT_IN_PORTRAIT_VALIDATION_VERSION",
    "FX_SPRITE_DUST_VALIDATION_KIND",
    "PLACEMENT_PARAMETERS",
    "PLACE_SYSTEM",
    "REVIEW_SYSTEM",
    "START_SCALE",
    "cut_in_artifact_refs",
    "cut_in_review_prompt",
    "derive_sprite_dust_validation",
    "dust_content_task",
    "frame_content_task",
    "fx_cut_in_place_schema",
    "fx_cut_in_review_schema",
    "mask_facts",
    "parse_placement",
    "place_content_task",
    "plate_id_for",
    "portrait_content_task",
    "render_data_url",
    "sprite_dust_artifact_refs",
    "subject_content_task",
    "validation_version_for",
]

"""Prompt clauses for the oblique camera.

Two levers carried over from earlier spikes decide the order of everything here.
Separation and isolation clauses **lead** the content task rather than trailing
it, because a rule stated last is the rule the model drops. And a prop prompt
names its one object exactly once: a named prop gets drawn, and a second noun in
the sentence gets drawn too.

The view clause is the genuinely new thing. The scene camera is pitched about
fifty-five degrees, but a screen-aligned billboard is not foreshortened by the
camera at all, so the sprite has to carry its own top-down. Asking for thirty
degrees of pictorial pitch against a fifty-five degree scene camera is the
compromise Don't Starve makes: the mismatch only shows at the base, and the
contact-shadow ellipse covers it.
"""

# ruff: noqa: E501
# Rewrapping a prompt literal here would change the bytes a model is sent, and
# those bytes are a node's input digest: a reflow moves cache keys and re-bills
# paid work. A correctness question, not a style one.

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from stage_gen.components.game_soundtrack.prompt import ORIGINALITY_CLAUSE
from stage_gen.recipes.oblique_survival import templates
from stage_gen.recipes.oblique_survival.models import (
    Actor,
    Biome,
    Clutter,
    Decal,
    Forage,
    IconSheet,
    Item,
    MacroPlate,
    Package,
    Plants,
    Prop,
    Road,
    Track,
    Water,
    WeatherDrops,
    WeatherGround,
    WeatherStrike,
)

# --- the shared wrapper --------------------------------------------------------------
#
# Same shape as the platformer's visual_prompt: world, then style, then the task.


#: Said whenever the style plate is attached. Without it the model copies the
#: plate's clearing: a reference image is a far stronger pull than any adjective,
#: which is the same lesson the skirt decals taught when they drew the tree.
STYLE_PLATE_CLAUSE: Final = (
    "Reference image 1 is a STYLE reference only. Match how it is drawn: the ink line and "
    "its weight, the two flat tones per shape, how few shapes each object is built from, the "
    "palette, and how little interior detail it carries. Do not copy its subject, its "
    "composition, its camera angle, or any object in it. Nothing from that picture appears in "
    "yours except the way it is drawn."
)


#: Every still asset is timeless: a sprite that is not a motion atlas never
#: moves, so nothing in it may say that it does. The puddle decal came back
#: with ripple rings, a wave frozen for ever on a thing that was never meant to
#: move (the brief had asked for them, and the model would have offered them
#: anyway). One short sentence on every still prompt; the strips, the puffs,
#: the splashes, the bolts and the scrolled water plate are motion and skip it.
STILL_CLAUSE: Final = (
    "Static: a timeless still; no ripples, wind, drift, trails, blur or other implied motion."
)


def visual_prompt(
    package: Package, specific: str, *, plate: bool = True, still: bool = True
) -> str:
    """World, then style, then the task.

    ``plate`` is False for the paintovers, which already spend reference image 1
    on their own template or concept sheet; those keep the prose alone rather
    than fight over the numbering. ``still`` is False only for art that is
    meant to move: a strip, a puff, a splash, a bolt, a scrolled plate.
    """

    blocks = [
        f"Visual style: {package.style_label}. "
        f"Use: {'; '.join(package.style_keywords)}. "
        f"Avoid: {'; '.join(package.style_avoid)}." + (f" {STILL_CLAUSE}" if still else "")
    ]
    if plate and package.style_reference is not None:
        blocks.append(STYLE_PLATE_CLAUSE)
    blocks.append(f"Content task:\n{specific}")
    return "\n\n".join(blocks)


ASSET_PITCH_CLAUSE: Final = (
    "seen from a slightly elevated three-quarter-front game camera pitched about thirty "
    "degrees above the horizon, so a little of its top surface reads and its base sits as a "
    "shallow ellipse rather than a straight line"
)

#: Repeated twice on every prop, at the front and at the back of the clause. An
#: oblique prop attracts a painted ground disc more than a side-view one does,
#: because "seen from above" reads to the model as "seen with its ground".
NO_FLOOR_CLAUSE: Final = (
    "Output true alpha with nothing under the object: no ground patch, no soil plate, no "
    "grass, no floor, no cast shadow, no contact shadow, no scenery, no frame, no text, no "
    "label, and no second object of any kind."
)

#: The reference genre's answer to the seam, used only when the package says
#: ground_contact = "painted_base": the art carries its own feathered patch of
#: ground. It replaces the floor ban in both of its positions.
PAINTED_BASE_CLAUSE: Final = (
    "Where the object meets the ground, paint a small patch of the ground it stands on as part "
    "of the same cutout: bare earth with a few fallen needles or leaves, no wider than one and a "
    "half times the object's own base, hugging the base and fading softly to fully transparent at "
    "its edge, with no hard outline around the patch. Nothing else under or around the object: no "
    "wider ground plate, no grass field, no cast shadow, no scenery, no frame, no text, and no "
    "second object."
)

ISOLATION_CLAUSE: Final = (
    "Centre it on an otherwise completely empty transparent canvas with comfortable "
    "transparent padding on all four sides, and keep the whole object inside the canvas."
)

#: The look contract's light, one clause per light the loader accepts. Said on
#: EVERY generative prompt, props and litter and patches and actors alike,
#: because a 2.5D scene has no runtime light: whatever light a thing was drawn
#: under is the light it keeps, from all eight camera angles. The first prop
#: set stated no light, and came back with a birch lit from the left, a boulder
#: lit from the upper left and a pine shadowed on its right, three suns in one
#: clearing. The reference's trees carry no side shadow at all.
LIGHT_CLAUSES: Final = {
    "overhead": (
        "ONE LIGHT, from directly overhead, the same light as every other asset in this set: "
        "surfaces that face up carry the lit tone, and the shadow tone lies only along "
        "undersides and lower edges, under each mass and along the bottom of the whole thing. "
        "The left side and the right side are the same tone as each other: there is no lit "
        "side and no shadowed side, so it reads the same from every direction. No cast shadow "
        "on the ground."
    ),
}


def light_clause(package: Package) -> str:
    return LIGHT_CLAUSES[package.look.light]


def prop_prompt(package: Package, prop: Prop, state: str) -> str:
    """One prop, one state. Isolation leads; the floor ban closes and repeats."""

    state_suffix = prop.state_prompt.get(state, "")
    seam = PAINTED_BASE_CLAUSE if package.ground_contact == "painted_base" else NO_FLOOR_CLAUSE
    pieces = [
        f"Draw exactly ONE isolated {prop.family} and nothing else, {ASSET_PITCH_CLAUSE}.",
        light_clause(package),
        seam,
        prop.prompt,
    ]
    if state_suffix:
        pieces.append(f"This is the {state.replace('_', ' ')} state. {state_suffix}")
    if len(prop.states) > 1:
        share = prop.height_share(state)
        if share is None or state == prop.baseline_state:
            # This look rides the baseline's ruler: the runtime derives its size
            # from the baseline's measurement, so it must be drawn at that scale.
            pieces.append(
                f"Draw it at exactly the same drawing scale and from exactly the same angle as the "
                f"other states of this same {prop.family}, so the two can be swapped in place."
            )
        else:
            # This look has its own canonical size and is calibrated from its
            # own pixels, so it may fill the canvas; the world sizes it.
            pieces.append(
                f"Draw it large, filling the canvas, from exactly the same angle as the other "
                f"states of this same {prop.family}. {share_words(share, prop.baseline_state)}"
            )
    if prop.max_components > 1:
        pieces.append(
            f"It may read as up to {prop.max_components} touching or separate clumps, but no more."
        )
    else:
        pieces.append("It must read as one single connected object.")
    pieces.append(ISOLATION_CLAUSE)
    pieces.append(seam)
    return visual_prompt(package, " ".join(pieces))


#: What makes a pickup read as a pickup rather than as a bit of scenery. The
#: first items (v28) came back drawn exactly like the props: the log in the
#: boulder's tones, the stone in the ground's, and on the ground they vanished.
#: Every relation here is stated against "this set", never against a palette or
#: a genre, because the package author owns the style and this clause must hold
#: under any of them: brighter and more saturated than the terrain BY ONE STEP,
#: a heavier contour THAN THE SCENERY CARRIES, and so on.
ITEM_CLAUSE: Final = (
    "It is a PICKUP, not scenery: draw it the way games draw a collectible icon, so it pops "
    "off any ground it lies on. One chunky, simplified, rounded shape, plumper than the real "
    "thing, with a bold closed silhouette edge all the way around, heavier than the scenery "
    "in this set carries. Clean, bright, saturated colour, vivid rather than muddy, with a "
    "strong pale highlight on its upper surface and a darker band along its underside, so it "
    "reads as one solid little object at thumbnail size."
)


def share_words(share: float, baseline_state: str) -> str:
    """A relative size the model can act on: a fraction in words, then a percentage."""

    fractions = (
        (1 / 6, "a sixth"),
        (1 / 5, "a fifth"),
        (1 / 4, "a quarter"),
        (1 / 3, "a third"),
        (2 / 5, "two fifths"),
        (1 / 2, "half"),
        (3 / 5, "three fifths"),
        (2 / 3, "two thirds"),
        (3 / 4, "three quarters"),
        (0.85, "most"),
        (1.0, "the same as"),
    )
    words = min(fractions, key=lambda entry: abs(entry[0] - share))[1]
    base = baseline_state.replace("_", " ")
    if words == "the same as":
        return f"In the world it stands the same height as the {base} look."
    return f"In the world it stands about {words} the height of the {base} look ({round(share * 100)}%)."


def prop_sheet_prompt(package: Package, prop: Prop) -> str:
    """Every look of one prop on one transparent canvas, at one drawing scale.

    A generative prompt, not a paintover: the first sheets were painted over
    a magenta lattice as an edit, and came back a grade below the sprites, with
    a pink rim the keyer left. This asks the sprite route for the same
    canvas with true alpha, divided into equal cells by arithmetic rather than
    by drawn guides, and the style plate rides as reference image 1 exactly as
    it does for a sprite. What the sheet is still for is the scale: the
    baseline look is the reference, and every other look is drawn at exactly
    that scale, smaller looks smaller in their cells, never enlarged to fill.
    """

    sheet = prop.sheet
    assert sheet is not None
    seam = PAINTED_BASE_CLAUSE if package.ground_contact == "painted_base" else NO_FLOOR_CLAUSE

    def look_line(state: str) -> str:
        brief = prop.state_prompt.get(state, "") or "as described"
        share = prop.height_share(state)
        if state == prop.baseline_state:
            return f"{state.replace('_', ' ')} (the reference, full height): {brief}"
        if share is None:
            return f"{state.replace('_', ' ')} (the same size as the reference): {brief}"
        return f"{state.replace('_', ' ')} ({share_words(share, prop.baseline_state)[len('In the world it stands ') : -1]}): {brief}"

    listing = "; ".join(look_line(state) for state in prop.states)
    family = prop.family
    components = (
        f"Each may read as up to {prop.max_components} touching or separate clumps, but no more."
        if prop.max_components > 1
        else "Each must read as one single connected object."
    )
    grid = f"{sheet.columns} columns and {sheet.rows} rows"
    return visual_prompt(
        package,
        " ".join(
            (
                f"Draw exactly {sheet.cell_count} isolated {family} cutouts and nothing else, "
                f"{ASSET_PITCH_CLAUSE}.",
                light_clause(package),
                seam,
                f"The canvas is divided into an invisible grid of {sheet.cell_count} equal cells, "
                f"{grid}; do not draw the grid. Put exactly ONE {family} in each cell, centred in "
                f"its cell with comfortable transparent padding on all four sides, and never let "
                f"any part of one reach the edge of its cell or touch another.",
                f"Every cell shows the same one {family}. {prop.prompt}",
                f"In reading order, left to right and then top to bottom, the {sheet.cell_count} "
                f"looks are: {listing}.",
                f"All {sheet.cell_count} are drawn at ONE shared drawing scale and from the same "
                f"angle, so any of them can be swapped in place for any other. The "
                f"{prop.baseline_state.replace('_', ' ')} look is the reference: it fills most "
                f"of its cell's height. Every other look is drawn at exactly that scale, so a "
                f"smaller look is smaller in its cell and is never enlarged to fill it, and "
                f"every object's base sits at the same ground level, low in its cell.",
                components,
                seam,
            )
        ),
    )


def season_look_prompt(package: Package, prop: Prop, state: str, look: Any) -> str:
    """One prop state repainted for a season: a paintover of its summer sprite.

    The summer sprite rides as reference image 1 and the style plate as image
    2, so the drawing is held by a picture (the character lesson) and the
    clause only says what the season adds. The season's shared clause is the
    default; a prop's ``season_prompt`` override for this state replaces it.
    ``prop_prompt`` never reads any of this, so a season brief moves no summer
    key.
    """

    seam = PAINTED_BASE_CLAUSE if package.ground_contact == "painted_base" else NO_FLOOR_CLAUSE
    brief = prop.season_prompt.get(look.look_id, {}).get(state, "") or look.prompt
    subject = f"the {prop.family} in image 1, its {state.replace('_', ' ')} look"
    pieces = [
        f"Repaint {subject} EXACTLY as it is drawn, and change one thing only: {brief}",
        "Same canvas, same placement on the canvas, same size, same angle, same silhouette "
        "under the snow, same ink line and the same flat tones; nothing else in the picture "
        "moves, grows, shrinks or is redrawn.",
        light_clause(package),
        seam,
        ISOLATION_CLAUSE,
        seam,
    ]
    return visual_prompt(package, " ".join(pieces))


def item_prompt(package: Package, item_id: str, description: str) -> str:
    return visual_prompt(
        package,
        " ".join(
            (
                f"Draw exactly ONE isolated {item_id.replace('_', ' ')} as a small pickup icon, "
                f"{ASSET_PITCH_CLAUSE}.",
                ITEM_CLAUSE,
                light_clause(package),
                NO_FLOOR_CLAUSE,
                description,
                ISOLATION_CLAUSE,
                NO_FLOOR_CLAUSE,
            )
        ),
    )


# --- actors --------------------------------------------------------------------------

ACTOR_VIEW_CLAUSE: Final = (
    "in a three-quarter-front view with the body turned slightly toward the viewer's right, "
    "seen from about thirty degrees above the horizon so the top of the head and the "
    "shoulders read, with the feet planted on a single shared invisible ground line"
)

_FRAME_WORDS: Final = {2: "two", 3: "three", 4: "four"}

#: The camera-relative pitch every facing shares: the same thirty degrees above
#: the horizon as the three-quarter card, so a turn never changes the top-down.
_FACING_PITCH_CLAUSE: Final = (
    "seen from about thirty degrees above the horizon so the top of the head and the "
    "shoulders read, with the feet planted on a single shared invisible ground line"
)


def facing_view_clause(facing: str, side_view: str) -> str:
    """The view clause for one facing of a four-way set.

    A facing is named from the camera: ``front`` faces the viewer, ``back``
    faces away, ``left`` and ``right`` face the screen's sides. The sides are
    a three-quarter view turned toward that side (``quarter``) or a full
    profile (``profile``); the author chooses, the words follow.
    """

    if facing == "front":
        body = "seen squarely from the front, facing the viewer directly"
    elif facing == "back":
        body = (
            "seen squarely from behind, facing directly away from the viewer, so the back of "
            "the head, the shoulders and the back of every garment are toward the viewer and "
            "the face is not visible at all"
        )
    elif facing in ("left", "right"):
        if side_view == "profile":
            body = f"in a full side profile facing the viewer's {facing}"
        else:
            body = (
                f"in a three-quarter view turned toward the viewer's {facing}: the face and the "
                f"front of the body still read, but the figure clearly faces screen {facing}"
            )
    else:
        raise ValueError(f"unknown facing {facing!r}")
    return f"{body}, {_FACING_PITCH_CLAUSE}"


#: Said only when an actor carries an authored appearance picture. It rides as
#: reference image 1 and the style plate slides to image 2, so both have to be
#: named or the model averages them. Identity comes from the picture; the
#: drawing comes from the plate and the prose.
APPEARANCE_PLATE_CLAUSE: Final = (
    "Reference image 1 is THIS CHARACTER. Reproduce its design exactly: the same body and "
    "head shapes and their proportions to each other, the same face and features, the same "
    "colours and materials, the same equipment, the same wear and the same repairs, part "
    "for part. Do not redesign it, do not restyle its parts and do not add or remove any. "
    "Reference image 2 is a STYLE reference only: match how it is DRAWN, and take nothing "
    "else from it."
)


def actor_concept_prompt(package: Package, actor: Actor) -> str:
    appearance = actor.appearance_reference is not None
    return visual_prompt(
        package,
        " ".join(
            (
                f"Draw exactly ONE complete standing {actor.display_name} and nothing else, "
                f"{ACTOR_VIEW_CLAUSE}.",
                *([APPEARANCE_PLATE_CLAUSE] if appearance else ()),
                light_clause(package),
                NO_FLOOR_CLAUSE,
                actor.concept_prompt,
                "This is the canonical appearance sheet: one figure, neutral standing pose, "
                "every piece of clothing and equipment clearly readable.",
                ISOLATION_CLAUSE,
                NO_FLOOR_CLAUSE,
            )
        ),
        # With an appearance picture the plate is image 2, and the shared
        # clause would claim image 1 for it; APPEARANCE_PLATE_CLAUSE names both.
        plate=not appearance,
    )


def actor_motion_prompt(
    package: Package, actor: Actor, state: str, *, frames: int = 4, facing: str | None = None
) -> str:
    """A single-row strip of ``frames`` cells, one facing, one drawing scale.

    ``facing`` is None for a single mirrored card (the authored three-quarter
    view) or one of the four-way facings. Every facing but the front takes the
    front strip as a second reference and matches it pose for pose, so the
    four strips of one action agree on timing and not only on the character.
    """

    motion = actor.state(state)
    word = _FRAME_WORDS.get(frames, str(frames))
    view = (
        ACTOR_VIEW_CLAUSE if facing is None else facing_view_clause(facing, actor.facings.side_view)
    )
    pieces = [
        f"Draw a strict single-row horizontal strip of {word} equally spaced cells and nothing "
        f"else. Each cell holds the same one {actor.display_name}, {view}.",
        light_clause(package),
        NO_FLOOR_CLAUSE,
        "Reference image 1 fixes the character's appearance exactly: same face, same clothing, "
        "same equipment, same colours in every cell. Do not redesign the character.",
    ]
    if facing is not None:
        pieces.append(
            f"This strip is the {facing} facing of a four-facing set (front, back, left, right) "
            f"of the same action. Any travel in the action is in the direction the figure faces, "
            f"and the figure keeps this facing in every cell."
        )
        if facing != "front":
            pieces.append(
                "Reference image 2 is the same action seen from the front. Match it pose for "
                f"pose and cell for cell: cell N here is cell N there, turned to face {facing}, "
                "at the same moment of the action, the same size and the same ground line."
            )
    pieces += [
        f"The {word} cells are one continuous {state.replace('_', ' ')} action: {motion.direction}",
        # Cross-cell scale drift is the single most expensive defect here, because
        # it survives every deterministic gate and only a judge can see it.
        f"Draw the figure at exactly the same size in all {word} cells, with the feet on the same "
        f"height in all {word} cells, and with the same amount of empty space above the head. "
        f"Do not zoom, crop, or re-frame between cells.",
        "The cells must not overlap and nothing may cross a cell boundary. Do not draw cell "
        "borders, gutters, numbers, captions, or a background of any kind.",
        NO_FLOOR_CLAUSE,
    ]
    return visual_prompt(package, " ".join(pieces), plate=False, still=False)


# --- ground --------------------------------------------------------------------------
#
# The word "seamless" is deliberately absent. It reliably produces a picture of
# a tiling pattern, borders included. Uniformity and feature scale are what
# actually make a plate usable, and mirror-repeat makes the edges exact anyway.

#: Screen density of the ground at the play camera (18 m, 35 degree fov, an
#: 800 px wide view is about 11 m across). Stated in the material clause so the
#: model draws marks that survive that minification.
PLAY_PX_PER_METER: Final = 70


def material_clause(texel_meters: float, feature_max_meters: float) -> str:
    """A ground plate is a material swatch, not a picture of ground.

    The first plates came back as pictures: an eight-metre plate painted as if
    it were one metre, with half-metre leaves and metre-wide stones, and no
    seam anywhere because the seam was never the problem. The reference genre
    paints material at material scale and draws everything recognisable as a
    sprite. So the prompt states the real span of the canvas and the largest
    thing allowed in it, both in centimetres, and leads with that, because a
    rule stated last is the rule the model drops.
    """

    span_cm = round(texel_meters * 100)
    feature_cm = round(feature_max_meters * 100)
    parts = max(2, round(texel_meters / feature_max_meters))
    return (
        f"Draw a seamless MATERIAL SWATCH of ground, not a picture of ground. The whole canvas "
        f"covers a square of real ground only {span_cm} centimetres on each side, seen straight "
        f"down from directly above, so everything in it is drawn at true size: the largest single "
        f"thing visible is about {feature_cm} centimetres across, roughly one part in {parts} of "
        f"the canvas width. A fallen leaf is a small fleck, a twig is a short line, a pebble is "
        f"a dot. MOST OF THE CANVAS IS EMPTY: at least three quarters of it is the plain flat "
        f"ground colour with nothing drawn on it at all, and the marks are scattered sparsely "
        f"and evenly over that, so that from across a room the plate reads as one flat colour "
        f"with a few flecks, never as a pattern or a carpet. Draw each mark in a tone close to "
        f"the ground colour, a little lighter or a little darker, never in strong contrast, "
        f"with a flat fill and an ink outline only on the few largest marks; nothing hair-thin "
        f"and no fine hatching, because in play this plate is shown at about "
        f"{PLAY_PX_PER_METER} pixels per metre and anything finer than a pencil line at that "
        f"size averages into mud, while anything in strong contrast turns into speckle. There "
        f"is no composition, no focal point, no large object and no cluster: the texture is "
        f"statistically the same in every part of the canvas and fills it edge to edge, so that "
        f"any crop of it looks like any other crop. Uniform flat overcast daylight across the "
        f"whole canvas: no vignette, no lighting gradient, no bright spot, no cast shadows, no "
        f"horizon, no sky, and no perspective."
    )


def fabric_clause(texel_meters: float, feature_max_meters: float) -> str:
    """A ground plate as the reference paints its turf: a stroke fabric.

    The field clause leaves three quarters of the canvas bare and scatters
    flecks; at play zoom that read as flat plastic with confetti. The
    reference's turf is the opposite: brush strokes 20 to 40 cm long, dense
    enough that no bare fill shows, all lying one way, in two tones close in
    value, with the dry edge of the brush inside every stroke. That last part
    is why its grain never reads as grain: it follows the stroke, darkens
    where the stroke darkens, and is absent in the gaps. The busy-ness gate
    measures value contrast at play zoom, so the two tones must be close.
    """

    span_cm = round(texel_meters * 100)
    stroke_cm = round(feature_max_meters * 100)
    return (
        f"Draw a seamless MATERIAL SWATCH of ground as a painted FABRIC of brush strokes, not a "
        f"picture of ground. The whole canvas covers a square of real ground only {span_cm} "
        f"centimetres on each side, seen straight down from directly above, so everything in it "
        f"is drawn at true size: every stroke is a brush mark about {stroke_cm} centimetres long "
        f"and a few centimetres wide, and nothing larger than a stroke exists anywhere. THE WHOLE "
        f"CANVAS IS COVERED: the strokes overlap densely edge to edge with no bare ground colour "
        f"showing between them, and every stroke lies the SAME way, leaning together with a "
        f"gentle drift like combed hay or wind-laid grass, never crossing at right angles and "
        f"never radiating. Use exactly TWO flat tones, a lit tone and a slightly deeper tone of "
        f"the same hue, so close in value that from across a room the canvas reads as one flat "
        f"colour with a soft weave in it; no third tone, no dark ink between strokes, no black "
        f"anywhere, no highlights. Inside each stroke let the dry edge of the brush show as a "
        f"few faint lighter and darker threads running along the stroke, in the stroke's own "
        f"two tones only: that grain belongs to the stroke, follows its direction, and does not "
        f"exist in any gap. Draw nothing recognisable: no leaf, no twig, no stone, no seed head, "
        f"no flower, no footprint; anything a player could name is a sprite and is not painted "
        f"here. In play this plate is shown at about {PLAY_PX_PER_METER} pixels per metre, so "
        f"strokes thinner than a pencil line at that size are wasted and strong contrast turns "
        f"into speckle. The texture is statistically the same in every part of the canvas and "
        f"fills it edge to edge so that any crop looks like any other crop. Uniform flat "
        f"overcast daylight across the whole canvas: no vignette, no lighting gradient, no "
        f"bright spot, no cast shadows, no horizon, no sky, and no perspective."
    )


def _value_clause(value_target: float) -> str:
    percent = round(value_target * 100)
    return (
        f"MEASURED REQUIREMENT: converted to greyscale, this plate's average brightness must be "
        f"about {percent} percent of white. Anything darker is rejected outright. Check the whole "
        f"canvas against that target before you finish: it is brighter than a forest interior and "
        f"brighter than most illustration of soil, and that is deliberate."
    )


def _emphasis(style_emphasis: str) -> str:
    return (
        f"For this ground plate specifically, override the mood above: {style_emphasis}"
        if style_emphasis
        else ""
    )


def ground_prompt(package: Package, biome: Biome) -> str:
    """A ground plate takes the package's drawing style but not its mood.

    The package style block is prepended to every prompt, and for props and
    actors that is exactly right. For ground it is not: three rounds of
    strengthening the value language moved a forest floor 0.186 -> 0.235 ->
    0.263 and stalled, because "muted earth palette" and "gothic-whimsical" are
    instructions about value and the plate was obeying them. So a biome declares
    its own value target as a number and its own style emphasis, and both are
    stated after the package's, where a later instruction wins.
    """

    return visual_prompt(
        package,
        " ".join(
            piece
            for piece in (
                (fabric_clause if biome.material == "fabric" else material_clause)(
                    biome.texel_meters, biome.feature_max_meters
                ),
                f"The ground material is: {biome.prompt}",
                _emphasis(biome.style_emphasis),
                _value_clause(biome.value_target),
            )
            if piece
        ),
    )


def cover_prompt(package: Package, cover: Any) -> str:
    """The snow cover: a field plate with a pale band, the biome clause otherwise."""

    return visual_prompt(
        package,
        " ".join(
            piece
            for piece in (
                material_clause(cover.texel_meters, cover.feature_max_meters),
                f"The ground material is: {cover.prompt}",
                _emphasis(cover.style_emphasis),
                _value_clause(cover.value_target),
            )
            if piece
        ),
    )


def road_prompt(package: Package, road: Road) -> str:
    """The road's fill is a material like any biome's; its edge is the splat's."""

    return visual_prompt(
        package,
        " ".join(
            piece
            for piece in (
                material_clause(road.texel_meters, road.feature_max_meters),
                f"The ground material is: {road.prompt}",
                _emphasis(road.style_emphasis),
                _value_clause(road.value_target),
            )
            if piece
        ),
    )


def water_prompt(package: Package, water: Water) -> str:
    """Water is a material plate too, with a darker value and sparser marks."""

    return visual_prompt(
        package,
        " ".join(
            piece
            for piece in (
                material_clause(water.texel_meters, water.feature_max_meters),
                f"The surface material is: {water.prompt}",
                _emphasis(water.style_emphasis),
                _value_clause(water.value_target).replace(
                    "it is brighter than a forest interior and brighter than most illustration of "
                    "soil, and that is deliberate",
                    "it is a dark plane, but not black, and it must stay readable at night",
                ),
            )
            if piece
        ),
        still=False,
    )


def ice_prompt(package: Package, ice: Any) -> str:
    """The water, frozen: the water's clause with the cover's pale band."""

    return visual_prompt(
        package,
        " ".join(
            piece
            for piece in (
                material_clause(ice.texel_meters, 0.25),
                f"The surface material is: {ice.prompt}",
                _emphasis(ice.style_emphasis),
                _value_clause(ice.value_target),
            )
            if piece
        ),
        still=True,
    )


def macro_prompt(macro: MacroPlate) -> str:
    """No style block at all: every keyword in it is an instruction to draw."""

    return (
        "Draw a seamless abstract MOTTLE, not a picture: soft irregular cloud-like patches of "
        "colour, each patch about a fifth to a third of the canvas across, with soft blurred "
        "boundaries between them, filling the canvas edge to edge. This is a colour-variation "
        "overlay for a game ground and will be multiplied over a fine texture, so it must contain "
        "no objects, no leaves, no stones, no lines, no ink contours, no texture, no grain, no "
        "pattern and no drawing of any kind: only broad soft washes of slightly different colour. "
        f"The patches are: {macro.prompt}. "
        "MEASURED REQUIREMENT: overall the plate averages a neutral mid-grey brightness, about "
        "50 percent of white, with the patches only a little lighter and darker than that and "
        "only gently tinted, and no patch is a strong colour. No vignette and no gradient "
        "across the canvas."
    )


#: How a litter piece meets the ground, by contact class. The contact lies
#: along the LOWER edge of the cell for every class, because that is the edge
#: the viewer keeps toward the camera: the layout mirrors and jitters a piece
#: but never spins it, and the litter re-aims when the camera turns.
CONTACT_CLAUSES: Final = {
    "pressed": (
        "PRESSED INTO the ground: only its top shows. Its lower silhouette edge, the edge "
        "nearest the bottom of its cell, is a flat, slightly irregular line where the earth "
        "swallows it, not a rounded underside, and a thin dark contact shadow hugs that lower "
        "edge, inside the cutout."
    ),
    "fallen": (
        "LYING ON the ground: flat, with a thin dark shadow line along its lower edge only, the "
        "edge nearest the bottom of its cell, inside the cutout, so it sits rather than floats."
    ),
    "growing": (
        "GROWING FROM the ground: its base spreads slightly where it meets the earth, with a "
        "narrow dark contact ring along its lower edge, the edge nearest the bottom of its "
        "cell, inside the cutout."
    ),
}


def _pieces_prompt(
    package: Package,
    sheet: Clutter | Forage | Plants,
    *,
    what: str,
    listing: str,
    pop: str = "",
    fill: str = "between a third and two thirds",
) -> str:
    """The lattice paintover for a sheet of still ground pieces, the litter's
    and the forage's alike. ``what`` names the pieces ("ground litter"),
    ``listing`` is the reading-order list, ``pop`` an extra clause between
    the scale rule and the no-ground rule (the forage's pickup pop). The
    litter's output is byte-identical to what it was before the forage
    shared this: its cache key is the proof."""

    cell_cm = round(sheet.cell_meters * 100)
    leave, around = templates.backing_words()
    return visual_prompt(
        package,
        " ".join(
            (
                f"Edit reference image 1 as a strict production sprite-sheet paintover. Preserve "
                f"all {sheet.columns + 1} vertical and {sheet.rows + 1} horizontal cyan guide "
                f"lines exactly where they are, perfectly straight and evenly spaced. {leave}",
                f"The lattice is exactly {sheet.columns} cells wide and {sheet.rows} cells "
                f"tall as already drawn; do not add, move or redraw any guide line.",
                f"Paint exactly ONE small piece of {what} into each of the {sheet.cell_count} "
                f"cells, read left to right and then top to bottom, centred in its cell with "
                f"{around}. Nothing may touch or cross a cyan guide line.",
                f"In reading order the {sheet.cell_count} pieces are, each with its kind of "
                f"contact in brackets: {listing}.",
                "Each piece is seen from slightly above and in front, the way the ground is seen "
                "in play, and every piece is in contact with the ground it is not drawn on. "
                "There are three kinds of contact.",
                f"pressed means {CONTACT_CLAUSES['pressed']}",
                f"fallen means {CONTACT_CLAUSES['fallen']}",
                f"growing means {CONTACT_CLAUSES['growing']}",
                light_clause(package),
                "On this sheet that light is the top of the image: the upper side of every piece "
                "is its lit tone, the lower side its shadow tone, and every contact shadow lies "
                "along the lower edge. Never a shadow on the upper edge.",
                f"All pieces are drawn at ONE shared scale: a cell is about {cell_cm} centimetres "
                f"of real ground across, and each piece fills {fill} of "
                f"its cell.",
                *((pop,) if pop else ()),
                "Do not draw ground, soil, grass or a patch of earth around a piece: the contact "
                "shadow is part of the piece and stops at the piece's own edge. No second object "
                "in a cell, no numbers, captions, or background.",
                (
                    f"For this sheet specifically, override the mood above: {sheet.style_emphasis}"
                    if sheet.style_emphasis
                    else ""
                ),
            )
        ),
        plate=False,
    )


def clutter_prompt(package: Package, clutter: Clutter) -> str:
    """The lattice paintover again, this time for sixteen still cutouts.

    The first sheet was a catalogue: each piece outlined all the way round
    and lit from nowhere, a sticker wherever it landed. What makes a ground
    object convincing is its contact, so every cell names one of three
    contacts and the sheet shares one light.
    """

    # Never number the cells. "cell 1 ... cell 16" made the model draw its own
    # grid, five wide, and lay the sixteen pieces into twenty cells; the
    # lattice count gate refused every attempt. The order is the reading
    # order and the lattice is the one already drawn.
    listing = "; ".join(f"{cell.brief} ({cell.contact})" for cell in clutter.cells)
    return _pieces_prompt(package, clutter, what="ground litter", listing=listing)


#: What makes a forage piece read as a thing to take, said against the litter
#: it lies among rather than against a palette: the same relations as the
#: pickup clause, one step at a time.
FORAGE_POP_CLAUSE: Final = (
    "Every piece here is a PICKUP the player will take, not litter: draw each one plumper and "
    "more rounded than the real thing, with one bold closed contour all the way around, "
    "heavier than any litter in this set carries, in clean colour one step brighter and more "
    "saturated than the ground it will lie on, with a pale highlight on its upper surface, so "
    "it pops off the turf at thumbnail size while still sitting in contact with it."
)


def forage_prompt(package: Package, forage: Forage) -> str:
    """The litter paintover for the pieces the player can take: the same
    lattice, the same contacts and light, plus the pickup pop, and each cell
    named for the item it yields."""

    listing = "; ".join(
        f"{cell.brief}, yielding {cell.item_id.replace('_', ' ')} ({cell.contact})"
        for cell in forage.cells
    )
    return _pieces_prompt(
        package, forage, what="forageable ground pickup", listing=listing, pop=FORAGE_POP_CLAUSE
    )


#: What makes a plant read as standing in the turf rather than lying on it,
#: said against the litter the way the forage pop is: the same sheet rules,
#: one card each, the base on the cell's floor.
PLANT_STAND_CLAUSE: Final = (
    "Every piece here is a PLANT STANDING UP from the ground, drawn whole from its base to its "
    "top as one upright cutout: its base, where its contact shadow is, sits low in its cell "
    "but a clear margin above the lower guide line, and it rises to its full height with a "
    "clear margin below the upper guide line too, its tip never touching it, so a knee-high "
    "plant fills about half the cell and a waist-high plant about three quarters of it. "
    "Foliage in the set's flat tones, one step darker and more saturated than the "
    "ground plates, with a thin ink contour. No glow, no haze, no soft shadow and no dark "
    "vignette around a plant: the clear backing stays fully transparent right up to the ink "
    "line, and the only shadow is the flat contact shadow inside the cutout at its base."
)


def plants_prompt(package: Package, plants: Plants) -> str:
    """The lattice paintover for the mid-scale: sixteen standing plants, the
    same lattice, contacts and light as the litter, plus the standing clause,
    each filling more of its cell than a piece of litter does."""

    listing = "; ".join(f"{cell.brief} ({cell.contact})" for cell in plants.cells)
    return _pieces_prompt(
        package,
        plants,
        what="standing ground plant",
        listing=listing,
        pop=PLANT_STAND_CLAUSE,
        fill="between half and nine tenths of the height",
    )


def plants_look_prompt(package: Package, plants: Plants, look: Any) -> str:
    """The plant sheet repainted for a season: a paintover of its summer
    sheet, guide lines and all, the way a prop state is repainted. The
    summer sheet rides as image 1 and the style plate as image 2."""

    pieces = [
        "Edit reference image 1 as a strict production sprite-sheet paintover. Preserve every "
        "cyan guide line exactly where it is, perfectly straight; do not add, move or redraw "
        "any guide line, and keep the transparent backing transparent.",
        f"Repaint every one of the {plants.cell_count} plants EXACTLY as it is drawn, in its own "
        f"cell, and change one thing only: {look.prompt}",
        "Same cell, same placement in the cell, same size, same silhouette under the snow, same "
        "ink line and the same flat tones; nothing else moves, grows, shrinks or is redrawn, and "
        "nothing may touch or cross a cyan guide line.",
        light_clause(package),
        "Do not draw ground, soil or a patch of snow around a plant: the snow on it is part of "
        "the cutout and stops at the plant's own edge.",
    ]
    return visual_prompt(package, " ".join(pieces), plate=False)


def icon_sheet_prompt(package: Package, icons: IconSheet, items: Sequence[Item]) -> str:
    """One lattice of inventory icons: every item in order, then the glyphs.

    Painted together so the set shares one scale and one contour; the pickup
    sprites are drawn one at a time and never quite agree with each other.
    An icon is flat and frontal, a glyph on a transparent cell, not a thing
    on the ground: no contact, no pitch, no light direction beyond a highlight.
    """

    entries = [
        f"{(item.display_name or item.item_id.replace('_', ' '))}: {(item.icon_brief or item.prompt).rstrip('.')}"
        for item in items
    ] + [
        f"{glyph.glyph.replace('_', ' ')} glyph: {glyph.brief.rstrip('.')}"
        for glyph in icons.glyphs
    ]
    listing = "; ".join(entries)
    leave, around = templates.backing_words()
    return visual_prompt(
        package,
        " ".join(
            (
                f"Edit reference image 1 as a strict production icon-sheet paintover. Preserve "
                f"all {icons.columns + 1} vertical and {icons.rows + 1} horizontal cyan guide "
                f"lines exactly where they are, perfectly straight and evenly spaced. {leave}",
                f"The lattice is exactly {icons.columns} cells wide and {icons.rows} cells "
                f"tall as already drawn; do not add, move or redraw any guide line.",
                f"Paint exactly ONE inventory icon into each of the {icons.cell_count} cells, "
                f"read left to right and then top to bottom, centred in its cell with {around}. "
                "Nothing may touch or cross a cyan guide line.",
                f"In reading order the {icons.cell_count} icons are: {listing}.",
                "Every icon is the same kind of drawing: a flat, frontal, simplified glyph of the "
                "thing, one chunky rounded silhouette that reads at twenty-four pixels, filling "
                "about two thirds of its cell, at the same visual weight, contour thickness and "
                "size across the whole set. A small thing and a large thing are drawn the same "
                "size here; the icon is a symbol, not a measurement.",
                "No cell backgrounds, plates, tiles, frames, badges, shadows or glow behind or "
                "around any icon; no ground under it; no numbers, letters, captions or labels "
                "anywhere. Each icon has a fully opaque body with clean edges.",
                (
                    f"For this sheet specifically, override the mood above: {icons.style_emphasis}"
                    if icons.style_emphasis
                    else ""
                ),
            )
        ),
        plate=False,
    )


#: The shape of a ground patch is the whole point of it. "A ring ... the
#: centre a plain empty circle" came back as exactly that, a disc, and a disc
#: under every tree is the one thing the eye picks out of a clearing. The
#: gate now measures roundness (gates.decal_irregularity), so the shape is
#: asked for first and in the plainest words.
PATCH_SHAPE_CLAUSE: Final = (
    "The patch's SHAPE is the point: an uneven, lopsided, lumpy blot with a ragged edge, "
    "wider on one side than the other, with two or three bulges and a bite taken out of it, "
    "never a circle, never a ring, never a disc, and never symmetrical."
)

#: How the patch's marks meet it: the litter sheet's rule, because the same
#: eye reads both. A mark that sits on the patch like a sticker undoes the
#: patch.
PATCH_CONTACT_CLAUSE: Final = (
    "Every mark on the patch is pressed into it or lying flat on it, half-buried the way "
    "ground litter is, with its contact shadow along its own lower edge only. No ink outline "
    "around the patch's outer edge, and no visible boundary: draw no surrounding ground, no "
    "grass field, no frame, and no cast shadow."
)

DECAL_CLAUSE: Final = (
    f"Draw ONLY ground lying flat, as one isolated patch on true alpha, seen from above the way "
    f"the ground is seen in play. {PATCH_SHAPE_CLAUSE} {PATCH_CONTACT_CLAUSE}"
)


#: A skirt has an empty centre because something drawn separately will stand
#: there, and it must not draw that something: a skirt that names its object
#: comes back with the object in it (a trunk, a boulder), which then stands
#: twice. Stated first, because a rule stated last is the rule the model drops.
SKIRT_CLAUSE: Final = (
    f"Draw ONLY the ground where one heavy thing has stood for years, as one isolated flat "
    f"patch on true alpha, seen from above the way the ground is seen in play. Do not draw the "
    f"thing itself, nor any standing object of any kind: no tree, no trunk, no boulder, no "
    f"bush, no plant standing up, no animal. {PATCH_SHAPE_CLAUSE} It is packed bare earth a "
    f"shade deeper than open ground, and its middle is plain and empty because a separately "
    f"drawn object will stand there. {PATCH_CONTACT_CLAUSE}"
)


def decal_prompt(package: Package, decal: Decal) -> str:
    clause = SKIRT_CLAUSE if decal.use == "skirt" else DECAL_CLAUSE
    return visual_prompt(package, f"{clause} {light_clause(package)} The patch is: {decal.prompt}")


# --- effects -------------------------------------------------------------------------
#
# The strip is a paintover on a generated lattice template, the terrain atlas's
# trick applied to animation frames instead of tile masks. The template is
# mandatory as reference image 1 and its digest is bound into the node identity.


def fire_strip_prompt(package: Package, columns: int, rows: int) -> str:
    frames = columns * rows
    return visual_prompt(
        package,
        " ".join(
            (
                f"Edit reference image 1 as a strict production effect-strip paintover. Preserve "
                f"all {columns + 1} vertical and {rows + 1} horizontal cyan guide lines exactly "
                f"where they are, perfectly straight and evenly spaced. "
                f"{templates.backing_words()[0]}",
                f"Paint one flame into each of the {frames} cells, read left to right and then "
                f"top to bottom, forming ONE single looping cycle of {frames} frames: each cell "
                f"changes only slightly from the cell before it, and the last cell leads straight "
                f"back into the first.",
                package.fire.prompt,
                "The base of the flame sits at the same height in every cell and is the same "
                "width in every cell. Nothing may cross a cyan guide line. Do not draw logs, "
                "stones, ground, embers, smoke, sparks, numbers, captions, or a background.",
            )
        ),
        plate=False,
        still=False,
    )


def dust_prompt(package: Package) -> str:
    return visual_prompt(
        package,
        " ".join(
            (
                "Draw exactly FOUR separate impact puffs on one otherwise completely empty "
                "transparent canvas, one puff in each quarter of the canvas, read left to right "
                "and then top to bottom. The four puffs must not touch each other and each must "
                "sit well inside its own quarter.",
                f"In order, the four puffs are: {package.dust.prompt}",
                "Each puff is ONE solid cloud built from a few large lobes. No thin wisps, no "
                "trailing streaks, no grit specks, and no fine scatter: this art is drawn forty "
                "pixels wide in play, and anything thinner than a lobe becomes speckle.",
                "Output true alpha. Do not draw ground, objects, a grid, cell borders, numbers, "
                "captions, or a background.",
            )
        ),
        still=False,
    )


# --- weather -------------------------------------------------------------------------
#
# Three pictures and no meaning. The condition's clock, its wash and its
# strike interval are numbers in weather.toml and never reach a prompt; what
# reaches a prompt is a tiling plate of streaks, a four-cell sheet laid flat,
# and a four-cell sheet of tall bolts, each wrapped in the words the gate
# will measure.

#: The drops skip the style plate and the world's keywords on purpose: the
#: keywords name conifers and boulders, and a model given them draws them
#: (the runner's dust sheet learned this). Rain is only the ink line.
RAIN_STYLE_CLAUSE: Final = (
    "Drawn with a slightly wobbling hand-drawn ink line, flat, with no rendering inside a "
    "shape: no gradients, no blur, no glow, no airbrush, no photographic texture."
)


def drops_sheet_prompt(package: Package, drops: WeatherDrops) -> str:
    left, right = drops.kinds
    return " ".join(
        (
            f"Visual style: {package.style_label}. {RAIN_STYLE_CLAUSE}",
            "Draw exactly TWO separate things on one otherwise completely empty transparent "
            f"canvas: the {left} centred in the LEFT half and the {right} centred in the RIGHT "
            "half, neither touching the middle of the canvas nor its edges. "
            + (
                "The streak fills most of its half's height and very little of its width; the "
                "drop is small, about a tenth of the canvas height."
                if drops.shape == "streak"
                else f"The {left} is a rounded shape about a third of the canvas height across; "
                f"the {right} is small, about a tenth of the canvas height."
            ),
            f"They are: {' '.join(drops.prompt.split())}",
            "Output true alpha. Do not draw splashes, puddles, ground, sky, clouds, objects, "
            "figures, a background, a border, a grid, numbers, or captions.",
        )
    )


def splash_sheet_prompt(package: Package, ground: WeatherGround) -> str:
    return visual_prompt(
        package,
        " ".join(
            (
                "Draw exactly FOUR separate rain splashes on one otherwise completely empty "
                "transparent canvas, one in each quarter of the canvas, read left to right and "
                "then top to bottom. The four must not touch each other and each must sit well "
                "inside its own quarter.",
                f"In order, the four are: {' '.join(ground.prompt.split())}",
                f"Each lies FLAT on the ground, {ASSET_PITCH_CLAUSE}, so a ring is a wide shallow "
                "ellipse and anything that rises, rises from one. Each is ONE shape built from a few "
                "large flat parts in two tones, a pale lit tone and a slightly deeper shadow tone, "
                "with an ink contour: this art is drawn thirty pixels wide in play, and anything "
                "thinner than a part becomes speckle.",
                light_clause(package),
                "Output true alpha. Do not draw ground, mud, objects, a grid, cell borders, "
                "numbers, captions, or a background.",
            )
        ),
        still=False,
    )


def strike_sheet_prompt(package: Package, strike: WeatherStrike) -> str:
    return visual_prompt(
        package,
        " ".join(
            (
                "Draw exactly FOUR separate lightning bolts on one otherwise completely empty "
                "transparent canvas, one in each quarter of the canvas, read left to right and "
                "then top to bottom. The four must not touch each other and each must sit well "
                "inside its own quarter, filling most of its quarter's height and little of its "
                "width.",
                f"The four are: {' '.join(strike.prompt.split())}",
                "Each bolt is one flat cutout in two tones, a bone-white core and a thin pale "
                "rim, with an ink contour and nothing rendered inside it: no glow, no haze, no "
                "gradient, no soft light.",
                "Output true alpha. Do not draw clouds, sky, rain, ground, a struck object, a "
                "grid, cell borders, numbers, captions, or a background.",
            )
        ),
        still=False,
    )


# --- review --------------------------------------------------------------------------


def family_review_prompt(family: str, subjects: list[str], ground_contact: str = "shadow") -> str:
    """One judgement over a whole family's contact sheet, not per image.

    Question 3 is the seam question and it flips with the package's authored
    ``ground_contact``: under ``painted_base`` a missing skirt is the defect.
    """

    seam_question = (
        "3. Does every sprite carry a small feathered patch of ground at its base, hugging the "
        "base and no wider than about one and a half times it, with no hard outline? Name any "
        "sprite whose base has no ground patch, or whose patch is a wide plate or a hard-edged "
        "disc."
        if ground_contact == "painted_base"
        else "3. Does any sprite have ground, soil, grass, a shadow plate, or a base disc painted "
        "under it, rather than ending in clean alpha? Name each one."
    )

    return "\n".join(
        (
            f"The attached contact sheet shows every generated {family} sprite in one set, "
            f"labelled in reading order: {', '.join(subjects)}.",
            "",
            "Judge the SET, not each picture on its own. Answer these questions:",
            "1. Is every sprite drawn from the same pictorial pitch, about thirty degrees above "
            "horizontal? Name any that are drawn flat side-on, straight down, or much steeper "
            "than the rest.",
            "2. Is every sprite drawn in the same style, with the same line weight and the same "
            "palette? Name any that break the set.",
            seam_question,
            "4. Where two sprites are two states of the same object, are they drawn at the same "
            "scale and from the same angle, so one can replace the other in place? Name any pair "
            "that is not.",
            "5. Is any sprite unreadable at about a hundred pixels tall, which is the size it is "
            "drawn in play?",
            "6. Is every sprite lit from directly overhead, its shadow tone only along undersides "
            "and lower edges, with its left and right sides the same tone? Name any sprite that "
            "has a lit side and a shadowed side, or a shadow tone on its upper edge; that is "
            "blocking, because the scene has no light to reconcile it under.",
            *(
                (
                    "7. For each ground plate, estimate the real-world width of the largest "
                    "identifiable thing in it (a leaf, a stone, a tuft) as a fraction of the plate, "
                    "and say whether the plate reads as a material swatch a couple of metres across "
                    "or as a picture of ground seen from a few metres up. A plate whose largest "
                    "feature is wider than one tenth of the plate is a picture, and that is blocking.",
                )
                if family == "ground"
                else ()
            ),
            *(
                (
                    "7. The sheet pairs each summer look with its season look, the summer first. "
                    "For each pair, is the season look the same drawing with the season added, "
                    "same silhouette, same size, same angle, same placement? Name any pair where "
                    "the season look is a different object, a different size, or has moved on "
                    "its canvas; that is blocking, because the two swap in place.",
                )
                if family == "seasons"
                else ()
            ),
            "",
            "A blocking finding is one that makes a sprite unusable in the scene. Anything else "
            "is advisory. Do not comment on subject matter or taste.",
        )
    )


def music_prompt(track: Track) -> str:
    """The authored brief, verbatim, and the repository's originality clause.

    Nothing is compiled onto a track: the brief already names the length, the
    loop, the instruments and the mood, and a second voice would only argue
    with it. The originality clause is the one non-negotiable addition.
    """

    return f"{track.prompt}\n{ORIGINALITY_CLAUSE}"

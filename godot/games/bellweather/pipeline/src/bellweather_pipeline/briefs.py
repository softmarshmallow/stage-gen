"""Every brief Bellweather's build sends a model, and the shapes of the answers it asks for.

Plan-time and pure: the builder states the exact instruction each step gives a provider, so a
plan reads as the request it will make. The wording is the game's art direction; changing a
sentence here changes what is asked, and the step's identity moves with it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from bellweather_pipeline.maps import PreparedGameMap, PreparedMapLayer
from bellweather_pipeline.motion_contract import (
    MotionActorKind,
    motion_atlas_geometry,
    motion_semantic_direction,
)
from bellweather_pipeline.validation import ResolvedGamePackage
from bellweather_pipeline.weapon_silhouettes import player_equipment_art
from demo_game_tools.input_formats.sideview_content import (
    MobContent,
    MotionPresentation,
    NpcContent,
    PlayerContent,
    ProjectileContent,
    projectile_silhouette_art,
)
from demo_game_tools.kits.sideview_actor.motion_geometry import dialogue_atlas_grid
from stage_gen.media import LoopConstruction

ActorContent = PlayerContent | MobContent | NpcContent
CatalogFamily = Literal["prop", "item", "projectile"]
SourceFacing = Literal["right", "back", "front"]

#: The span placeholders a loop brief carries; the loop step fills them in from the canvas it
#: builds, because the spans are known only once the raw layer exists.
EDITABLE_SPAN = "{editable_span}"
CONTEXT_SPAN = "{context_span}"

REVIEW_SYSTEM = (
    "You are a strict independent 2D game-art technical director. Return only the "
    "requested structured review."
)
MAP_REVIEW_SYSTEM = (
    "You are a strict game-art technical director. Return only the requested structured review."
)
REVIEW_MAX_TOKENS = 1800


# ------------------------------------------------------------------- direction


def universe_text(package: ResolvedGamePackage) -> str:
    return package.file(package.game.universe.source).data.decode("utf-8")


def visual_prompt(package: ResolvedGamePackage, specific: str) -> str:
    """This game's art direction wrapped around one content task."""

    style = package.game.style
    return (
        f"Game universe:\n{universe_text(package)}\n\nVisual style: {style.label}. "
        f"Use: {', '.join(style.keywords)}. Avoid: {', '.join(style.avoid)}.\n\n"
        f"Content task:\n{specific}"
    )


def map_prompt(package: ResolvedGamePackage, specific: str) -> str:
    """The map contract wrapped around one map asset task."""

    style = package.game.style
    return (
        f"Bellweather universe context:\n{universe_text(package)}\n\nVisual style: {style.label}. "
        f"Use: {', '.join(style.keywords)}. Avoid: {', '.join(style.avoid)}.\n\n"
        f"Map contract: fixed 2D side view, scrolling x-axis, seamless horizontal continuity.\n"
        f"Map asset task:\n{specific}"
    )


def material_direction(package: ResolvedGamePackage, game_map: PreparedGameMap) -> str:
    """The ground's authored material, with the game's style named after it."""

    style = package.game.style
    return (
        f"{game_map.ground.prompt.strip()} Target style: {style.label}; "
        f"{', '.join(style.keywords)}."
    )


# ---------------------------------------------------------------------- layers


def layer_prompt(package: ResolvedGamePackage, layer: PreparedMapLayer) -> str:
    """The painting brief: the map's direction around the layer's own, plus the seam rule."""

    prompt = map_prompt(package, layer.prompt) + (
        "\nOutput one horizontally seamless repeat unit. The left and right edges must join "
        "without a visible seam. "
    )
    return prompt + (
        "Isolate only this layer on a fully transparent background with true alpha."
        if layer.alpha_mode == "transparent"
        else "Output a completely opaque sky plate with no transparency."
    )


def _alpha_rule(layer: PreparedMapLayer) -> str:
    return (
        "This is a cut-out layer. Every region that is transparent in the supplied image must "
        "stay fully transparent in yours: above the content, below it, and around it. Paint "
        "only the same band of content the left and right sides occupy, at the same top and "
        "bottom extent. Add no ground, no water, no horizon fill, no backdrop, no matte, and "
        "no vignette. Use true alpha, not a colour approximating emptiness."
        if layer.alpha_mode == "transparent"
        else "Keep the plate completely opaque."
    )


def loop_prompt(
    package: ResolvedGamePackage, layer: PreparedMapLayer, construction: LoopConstruction
) -> str:
    """The loop brief for the construction actually selected.

    A bridge asks the provider to invent a span between two ends it cannot see across; a
    repaint asks it to carry existing content through a region it can see both sides of. The
    spans stay as placeholders until the loop step knows its canvas.
    """

    if construction == "generated_bridge":
        return _bridge_prompt(package, layer)
    return _repaint_prompt(package, layer, mirrored=construction == "fold_repaint")


def _repaint_prompt(
    package: ResolvedGamePackage, layer: PreparedMapLayer, *, mirrored: bool
) -> str:
    style = package.game.style
    material = " ".join(layer.prompt.split())
    if mirrored:
        situation = (
            "The supplied image is one horizontal strip of side-view game art. Its right half "
            "is a mirror image of its left half, so the centre of the image is a reflection "
            "axis: the artwork bounces back on itself there and reads as an obvious mirror."
            f"\n\nRepaint only the marked middle {EDITABLE_SPAN} pixels so the "
            "strip reads as one continuous scene travelling in a single direction through "
            "that region, with no reflection and no axis of symmetry. Break up any left-right "
            "mirrored pairing."
        )
    else:
        situation = (
            "The supplied image is one horizontal strip of side-view game art, formed by "
            "placing the end of a scene directly against its own beginning. The centre of the "
            "image is therefore a hard cut: the artwork does not line up there."
            f"\n\nRepaint only the marked middle {EDITABLE_SPAN} pixels so the "
            "artwork flows through the cut as one unbroken band, with no visible seam, step, "
            "or discontinuity."
        )
    return (
        f"Image repair task. {situation}\n\n"
        "Everything outside that middle region is FINISHED ARTWORK: reproduce it exactly as "
        "given, pixel for pixel, same position, same scale, same vertical alignment. Do not "
        "move, shift, rescale, recompose, or restyle it.\n\n"
        "Match the existing line weight, palette, lighting, ground line, and horizon exactly. "
        "Do not introduce a landmark, a centrepiece, a frame, or text.\n\n"
        "Paint the span at full strength edge to edge. Do not fade, feather, blur, ghost, or "
        "ramp opacity toward either boundary, and do not use a gradient, haze, glow, or "
        "vignette to blend into the neighbours. If the two sides differ, resolve it with "
        "drawn content - foliage, masonry, terrain - not with transparency or a soft wash. "
        "Empty space inside the span is allowed only where the neighbouring artwork is "
        "genuinely empty; elsewhere keep the same density of drawn detail as the sides.\n\n"
        f"Visual style: {style.label}. Avoid: {', '.join(style.avoid)}.\n"
        "Material reference, describing what this layer is made of and not how to compose "
        f"it: {material}\nIgnore anything in that reference about landmarks, rhythm, "
        f"centring, or composition.\n\n{_alpha_rule(layer)}"
    )


def _bridge_prompt(package: ResolvedGamePackage, layer: PreparedMapLayer) -> str:
    style = package.game.style
    material = " ".join(layer.prompt.split())
    return (
        "Image continuation task. The supplied image is one horizontal strip of side-view "
        "game art with an empty gap in the middle.\n\n"
        f"The left {CONTEXT_SPAN} pixels and the right "
        f"{CONTEXT_SPAN} pixels are FINISHED ARTWORK. Reproduce them exactly as "
        "given: pixel for pixel, same position, same scale, same vertical alignment. Do not "
        "move, shift, rescale, recompose, restyle, or redraw them. Do not add, remove, or "
        "relocate any object in them.\n\n"
        f"Only the middle {EDITABLE_SPAN} pixels are empty. Paint that span "
        "so the artwork at the left edge of the gap continues into the artwork at the "
        "right edge as "
        "one unbroken band. Match the existing line weight, palette, lighting, ground line, "
        "and horizon exactly.\n\n"
        "Everything you paint must sit entirely inside the middle span. Do not place any "
        "object across the gap's boundary. Do not introduce a landmark, a centrepiece, a "
        "frame, a midpoint feature, or text.\n\n"
        f"Visual style: {style.label}. Avoid: {', '.join(style.avoid)}.\n"
        f"Material reference, describing what this layer is made of and not how to compose "
        f"it: {material}\n"
        "Ignore anything in that reference about landmarks, rhythm, centring, or "
        f"composition.\n\n{_alpha_rule(layer)}"
    )


# ------------------------------------------------------- map presentation art


def climbable_prompt(
    package: ResolvedGamePackage, game_map: PreparedGameMap, roles: Sequence[str]
) -> str:
    climbable = game_map.climbable
    if climbable is None:
        raise ValueError(f"map {game_map.map_id} does not declare climbable")
    variants = climbable.variants
    roster = "\n".join(
        f"  {index + 1}. {role} — {entry.prompt.strip()}"
        for index, (entry, role) in enumerate(zip(variants, roles, strict=True))
    )
    return map_prompt(
        package,
        "Create one atlas sheet of this map's climbing routes. Every route is maintained "
        "by the same hands, so they share one palette, one line weight, and one world "
        f"scale.\n\nDraw exactly {len(variants)} climbable objects, left to right in a "
        f"single row, in this order:\n{roster}",
    ) + (
        f"\nLayout contract, follow exactly:\nExactly {len(variants)} objects. Not one "
        "more, not one fewer. No duplicates, no coils, no spares, no extra strands, no "
        "stacked copies.\nSpace them evenly across the canvas in one row, each wholly "
        "inside its own vertical column, with a wide fully transparent vertical gap "
        "between neighbours that no object crosses or touches.\nEvery object spans the "
        "same vertical height at the same world scale: all tops level with each other, "
        "all bottoms level with each other, each one tall and narrow.\nEach object is "
        "one continuous connected piece from its top end to its bottom end, with no "
        "break, no gap, and no loose end drifting sideways. Keep each near-vertical.\n"
        "Leave a clear transparent margin at the left, right, top, and bottom.\nUse a "
        "fully transparent exterior with no floor, scenery, shadow, labels, caption, "
        "number, border, frame, panel divider, character, or creature."
    )


def portal_prompt(package: ResolvedGamePackage, game_map: PreparedGameMap) -> str:
    portal = game_map.portal
    if portal is None:
        raise ValueError(f"map {game_map.map_id} does not declare portal")
    return map_prompt(package, portal.prompt) + (
        "\nCreate exactly two complete isolated portal structures in one horizontal "
        "row: entry on the left and exit on the right. Keep each portal wholly inside "
        "its own half with a wide transparent separator. Both bases must be level and "
        "the two structures must be the same world scale. Use a fully transparent "
        "exterior with no floor, scenery, shadow, labels, border, character, or extra "
        "portal."
    )


def map_review_prompt(game_map: PreparedGameMap, declared_presentations: Sequence[str]) -> str:
    return (
        f"Review the generated map artifacts for {game_map.display_name}. "
        "Image 1 is the layer composite: the whole map at gameplay scale, with its "
        "layers, ground and platforms where the runtime places them, cut into equal "
        "strips stacked top to bottom and read left to right, separated by grey "
        "rules. Portals and climbables are placed by the runtime at play time and "
        "are not drawn on it. Image 2 is the deterministic authored-"
        "occupancy terrain composition, and image 3 is the canonical 47-mask "
        "ground atlas. The next images are the declared map-local presentation "
        f"assets in this exact order: {list(declared_presentations)}. A portal image is "
        "one gate's pair of mouths, entry on the left and exit on the right; a "
        "climbable image holds one cell per declared climbable variant. The next "
        "image is "
        "the authored reference. Remaining images alternate "
        "between one isolated canonical layer and its checkerboard three-repeat "
        "evidence, in declared painter order. Transparent empty edge space is an "
        "intentional clean wrap boundary, not missing art. Judge reference fidelity, "
        "layer separation, style coherence, side-view playfield readability, "
        "horizontal looping continuity from the repeat evidence, ground topology "
        "and material compatibility, and the functional readability, isolation, "
        "scale coherence, and map-style fidelity of every declared portal or "
        "climbable. "
        "A looping strip has no privileged horizontal origin: a pure "
        "cyclic x-translation of landmarks is compositionally equivalent and must "
        "not reduce reference fidelity. Report concrete evidence; uncertainty must "
        "not be called accept."
    )


def map_review_schema() -> dict[str, object]:
    return _review_schema(
        (
            "reference_fidelity",
            "layer_separation",
            "style_coherence",
            "playfield_readability",
            "looping_continuity",
            "ground_compatibility",
            "traversal_presentation_compatibility",
        )
    )


# ---------------------------------------------------------------------- actors


def entity_id(entry: ActorContent) -> str:
    if isinstance(entry, PlayerContent):
        return entry.player_id
    if isinstance(entry, MobContent):
        return entry.mob_id
    return entry.npc_id


def _equipment_directive(entry: ActorContent) -> str:
    """The leading equipment clause for a player, and nothing for any other actor."""

    if not isinstance(entry, PlayerContent):
        return ""
    return f"{player_equipment_art(entry.equipment).carry_directive}\n"


def concept_prompt(package: ResolvedGamePackage, kind: MotionActorKind, entry: ActorContent) -> str:
    return visual_prompt(
        package,
        f"{_equipment_directive(entry)}"
        f"Create the canonical identity concept for the {kind} {entity_id(entry)}.\n"
        f"Authored direction: {entry.prompt}\n"
        "Show one complete side-view game-scale figure and one front-three-quarter identity "
        "view, with identical costume, colors, proportions, and equipment. Keep the complete "
        "figures separated, fully visible, and isolated on a truly transparent background. "
        "No frame, floor, scenery, text, labels, symbols, or shadow plate. This image is the "
        "strict identity source for all later motion and dialogue atlases.",
    )


def motion_prompt(
    package: ResolvedGamePackage,
    kind: MotionActorKind,
    entry: ActorContent,
    state: str,
    source_facing: SourceFacing,
) -> str:
    if source_facing == "back":
        facing_directive = "Every figure is shown from behind, facing away from the camera."
    elif source_facing == "front":
        facing_directive = (
            "Every figure directly faces the camera in a strict symmetrical front view: "
            "both eyes, shoulders, hands, and feet remain front-facing in every cell."
        )
    else:
        facing_directive = (
            "Every figure is a strict side view facing RIGHT: eyes, face, chest, and toes "
            "point toward the right edge."
        )
    geometry = motion_atlas_geometry(kind, state)
    return visual_prompt(
        package,
        f"{_equipment_directive(entry)}"
        f"Create the canonical side-view motion atlas for {kind} {entity_id(entry)}, state "
        f"{state}. "
        "Use the supplied identity concept exactly. Output a strict single-row strip of "
        f"{geometry.frame_word} "
        f"sequential frames. {facing_directive} Preserve identity, apparent height, foot "
        "baseline, silhouette, "
        "costume, equipment, and camera scale in every cell. The required motion is: "
        f"{motion_semantic_direction(kind, state)}. Keep every figure wholly inside its cell "
        "on true alpha. "
        "Leave transparent separation between cells. No grid lines, boxes, captions, scenery, "
        "ground, cast shadows, text, or symbols.",
    )


def dialogue_prompt(
    package: ResolvedGamePackage, kind: MotionActorKind, actor_id: str, expressions: Sequence[str]
) -> str:
    columns, rows = dialogue_atlas_grid(len(expressions))
    expression_text = ", ".join(
        f"cell {index + 1}: {expression}" for index, expression in enumerate(expressions)
    )
    return visual_prompt(
        package,
        f"Create a front-three-quarter dialogue portrait atlas for {kind} {actor_id} using "
        "the "
        f"supplied identity concept exactly. Output a strict {columns}-column by {rows}-row "
        f"row-major atlas. Required cells in order: {expression_text}. Preserve head shape, "
        "hair, eyes, costume, palette, and apparent crop across every portrait; change only "
        "the "
        "authored facial expression and restrained supporting pose. Keep each bust centered in "
        "its cell on true alpha. Unused cells must remain transparent. No grid lines, boxes, "
        "labels, text, speech balloons, scenery, or symbols.",
    )


def actor_review_prompt(
    kind: MotionActorKind,
    entry: ActorContent,
    *,
    source_facings: dict[str, str],
) -> str:
    """The actor review: identity, motion, facing, scale and expressions, as the run made them."""

    motions: Sequence[MotionPresentation] = entry.motions
    states = [motion.state for motion in motions]
    expressions: Sequence[str]
    equipment_clause = ""
    if isinstance(entry, PlayerContent):
        expressions = entry.dialogue_art.expressions
        equipment_clause = (
            "The character's declared equipment is "
            f"{entry.equipment}. Confirm that "
            f"{player_equipment_art(entry.equipment).review_clause}. "
        )
    elif isinstance(entry, MobContent):
        expressions = []
    else:
        expressions = entry.dialogue_expressions
    motion_semantics = {state: motion_semantic_direction(kind, state) for state in states}
    playback = {motion.state: motion.model_dump(mode="json") for motion in motions}
    runtime_scale_context = ""
    if kind == "player":
        runtime_scale_context = (
            "The contact sheet shows canonical source-atlas pixels, not final runtime world "
            "scale. The prepared consumer deterministically head-matches every non-crouch "
            "state to the idle character scale and registers it from the bottom/feet, so "
            "different raw atlas crop heights do not imply runtime size or baseline popping. "
            "Crouch is the intentional exception: it preserves canonical atlas scale and a "
            "bottom/feet anchor so the bent, stationary pose remains visibly lower than "
            "standing. Judge cross-state runtime scale under that declared adapter; still "
            "reject inconsistent scale or registration within one four-frame atlas. "
        )
    return (
        f"Review the complete generated {kind} content for {entry.display_name} "
        f"({entity_id(entry)}). "
        f"Authored identity direction: {entry.prompt} "
        f"The complete declared state list is exactly {list(states)}. "
        f"The complete declared dialogue-expression list is exactly {list(expressions)}. "
        f"The exact required visual meaning for each motion is {motion_semantics}. "
        f"The exact authored runtime playback projection is {playback}. For hold playback, "
        "judge motion semantics only on the selected canonical frame; unused generated "
        "candidate cells still require stable identity, facing, scale, registration, and "
        "alpha, but their gestures are not runtime motion coverage and must not cause a "
        "rejection. "
        "Every motion atlas is one row of four frames. The exact required source facing "
        f"for each state is {source_facings}. Ordinary right-facing side-view sources are "
        "mirrored deterministically by the runtime for left-facing play; rear-facing and "
        "front-facing sources are not mirrored. For hold playback, generation still "
        "provides the complete four-cell atlas while runtime presentation selects only "
        "the declared canonical frame. Image 1 is the locally labeled "
        "contact sheet; remaining images are authored identity/style references. The "
        "contact sheet was locally alpha-composited from decoded RGBA sources onto "
        f"checkerboards. {runtime_scale_context}"
        "Deterministic decoding already proved true alpha (minimum alpha 0, visible alpha "
        "greater than 0), zero-alpha canvas borders, and nonempty occupancy in every "
        "required atlas cell. Hidden RGB stored behind fully transparent pixels is not "
        "visible game content. Judge alpha isolation from the checkerboard composition "
        "and these deterministic facts; do not reject it because checkerboard is shown. "
        "Do not require states or expressions outside the exact declared lists. Judge "
        "identity fidelity against both the authored text and applicable image references, "
        "style continuity, complete state coverage, "
        "the declared source-facing consistency for motion, stable scale and registration, "
        "native-alpha "
        "isolation, and declared dialogue-expression coverage where applicable. "
        f"{equipment_clause}A labeled "
        "state tile may itself contain a multi-cell atlas. Report concrete visible "
        "defects. "
        "Uncertainty must not be called accept."
    )


def content_review_schema() -> dict[str, object]:
    return _review_schema(
        (
            "identity_fidelity",
            "style_coherence",
            "state_coverage",
            "facing_coverage",
            "registration_consistency",
            "alpha_isolation",
            "expression_coverage",
            "catalog_coverage",
        )
    )


# --------------------------------------------------------------------- catalog


def catalog_prompt(
    package: ResolvedGamePackage,
    family: CatalogFamily,
    entity: str,
    entry: object,
) -> str:
    """One catalog subject, drawn by the family's own directive.

    A projectile leads with the axis its silhouette must read as and forbids the trail or
    spark a moving object attracts, because the consumer measures the painted bounding box.
    """

    prompt_text = str(getattr(entry, "prompt"))  # noqa: B009 - every catalog entry has one
    if isinstance(entry, ProjectileContent):
        art = projectile_silhouette_art(entry.silhouette)
        return visual_prompt(
            package,
            f"{art.axis_directive}\n"
            f"Generate exactly one canonical projectile asset, stable ID "
            f"{entity}: {art.shape_clause}.\n"
            f"Authored direction: {prompt_text}\n"
            "Draw exactly ONE connected object and nothing else. No motion trail, speed line, "
            "spark, glow streak, impact burst, smoke, or detached fragment: the runtime "
            "supplies motion, and anything painted beside the object is measured as part of "
            "it. Center the complete object with comfortable transparent padding on every "
            "side. Output true alpha with no floor, scenery, shadow plate, frame, text, "
            "label, symbol, or second object.",
        )
    return visual_prompt(
        package,
        f"Generate exactly one canonical {family} asset, stable ID {entity}.\n"
        f"Authored direction: {prompt_text}\n"
        "Use a fixed side-view game-asset camera. Center the complete object with "
        "comfortable transparent padding. Preserve a clear gameplay silhouette and the "
        "authored scale cues. Output true alpha with no floor, scenery, shadow plate, "
        "frame, text, label, symbol, or second object.",
    )


def catalog_review_prompt(family: CatalogFamily, entries: Sequence[tuple[str, object]]) -> str:
    expected_ids = [entity for entity, _entry in entries]
    if family == "projectile":
        authored_directions: list[dict[str, object]] = [
            {
                "asset_id": entity,
                "prompt": entry.prompt,
                "must_read_as": projectile_silhouette_art(entry.silhouette).review_clause,
            }
            for entity, entry in entries
            if isinstance(entry, ProjectileContent)
        ]
        return (
            "Review the complete generated projectile catalog. The exact complete stable-ID "
            f"list is {expected_ids}. Authored directions are {authored_directions}, each "
            "carrying the drawn axis its silhouette requires. Image 1 is a locally labeled "
            "stable-ID contact sheet; remaining images are authored style references. The "
            "contact sheet was locally alpha-composited from decoded RGBA sources onto "
            "checkerboards. Deterministic decoding proved true alpha, zero-alpha canvas "
            "borders, visible subject pixels, and exactly one connected subject per source. "
            "Judge alpha isolation from the checkerboard composition and these deterministic "
            "facts, and do not claim the expected manifest is missing. Judge, for every "
            "entry: authored identity fidelity, style coherence, and above all whether the "
            "drawn subject matches its stated axis, because the consumer scales, mirrors and "
            "rotates these along that axis and a reversed or tilted subject flies backwards. "
            "Report concrete visible defects. Uncertainty must not be called accept."
        )
    authored_directions = [
        {"asset_id": entity, "prompt": str(getattr(entry, "prompt"))}  # noqa: B009
        for entity, entry in entries
    ]
    return (
        f"Review the complete generated {family} catalog. The exact complete stable-ID "
        f"list is {expected_ids}. Authored directions are {authored_directions}. Image 1 "
        "is a locally labeled stable-ID contact sheet; remaining images are authored "
        "style/scene references. The contact sheet was locally alpha-composited from "
        "decoded RGBA sources onto checkerboards. Deterministic decoding proved true "
        "alpha, zero-alpha canvas borders, and visible subject pixels for every source. "
        "Hidden RGB behind fully transparent pixels is not visible game content. Judge "
        "alpha isolation from the checkerboard composition and these deterministic facts, "
        "and do not claim the expected manifest is missing. Judge authored identity "
        "fidelity, style coherence, unique readable silhouettes, "
        "side-view gameplay framing, native-alpha isolation, scale consistency within the "
        "catalog, and complete catalog coverage. Report concrete visible defects. "
        "Uncertainty must not be called accept."
    )


# --------------------------------------------------------------------- shapes


def _review_schema(checks: Sequence[str]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["accept", "reject", "uncertain"]},
            "confidence": {"type": "number"},
            "checks": {
                "type": "object",
                "properties": {key: {"type": "boolean"} for key in checks},
            },
            "issues": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "string"},
        },
    }


__all__ = [
    "CONTEXT_SPAN",
    "EDITABLE_SPAN",
    "MAP_REVIEW_SYSTEM",
    "REVIEW_MAX_TOKENS",
    "REVIEW_SYSTEM",
    "ActorContent",
    "CatalogFamily",
    "actor_review_prompt",
    "catalog_prompt",
    "catalog_review_prompt",
    "climbable_prompt",
    "concept_prompt",
    "content_review_schema",
    "dialogue_prompt",
    "entity_id",
    "layer_prompt",
    "loop_prompt",
    "map_prompt",
    "map_review_prompt",
    "map_review_schema",
    "material_direction",
    "motion_prompt",
    "portal_prompt",
    "visual_prompt",
]

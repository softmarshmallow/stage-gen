"""The runner recipe's prompt composition over the container's visual direction.

The container's style, proportion, and universe digest ride every generation
node's identity exactly as they do in the platformer: one style edit re-keys
the whole generative graph on purpose. Prompts stay short - the authored
member prompts carry the content; this module carries only the shared framing
each node family needs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stage_gen.canonical import canonical_sha256
from stage_gen.components.platformer_content import projectile_silhouette_art
from stage_gen.components.runner_track import (
    RunnerStructuralGround,
    structural_ground_generation_prompt,
)
from stage_gen.components.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from stage_gen.components.sideview_terrain import terrain_atlas_generation_prompt

if TYPE_CHECKING:
    from stage_gen.components.runner_content import RunnerAvatar, RunnerBoss
    from stage_gen.components.runner_track import RunnerSegmentChunk, RunnerTrack
    from stage_gen.recipes.sideview_runner.runner_request import ResolvedRunnerPackage


def visual_direction(resolved: ResolvedRunnerPackage) -> dict[str, object]:
    package = resolved.package
    return {
        "universe_sha256": package.file(package.game.universe.source).sha256,
        "style": package.game.style.model_dump(mode="json"),
        "proportion": package.game.proportion.model_dump(mode="json"),
        # Runtime contact shadows are deliberately absent: changing them must not
        # invalidate any paid generation node.
        "presentation": {
            "view_profile": resolved.runner.member.presentation.view_profile,
            "gameplay_space": resolved.runner.member.presentation.gameplay_space,
        },
    }


def visual_direction_digest(resolved: ResolvedRunnerPackage) -> str:
    return canonical_sha256(visual_direction(resolved))


def _style_clause(resolved: ResolvedRunnerPackage) -> str:
    style = resolved.package.game.style
    clause = f"Art direction: {style.label}. " + " ".join(f"{word}." for word in style.keywords)
    if style.avoid:
        clause += " Avoid: " + "; ".join(style.avoid) + "."
    return clause


def fx_plate_prompt(resolved: ResolvedRunnerPackage, task: str) -> str:
    """One screen-FX plate task under the container's art direction."""

    return f"{task}\n\n{_style_clause(resolved)}"


def _avatar_contract_clause(
    avatar: RunnerAvatar,
    *,
    proportion_heads: float,
) -> str:
    facts = (
        f"Contract facts: age {avatar.age}; body_kind {avatar.body_kind}; "
        f"silhouette_mode {avatar.silhouette_mode}; "
        f"proportion_basis {avatar.proportion_basis}; approximately "
        f"{proportion_heads} declared-basis heads tall. "
    )
    if avatar.silhouette_mode == "visible_rider_machine_v1":
        return facts + (
            "The visible rider and machine are one connected runtime actor and one whole "
            "silhouette, never two subjects. Measure proportion from the visible rider's head, "
            "but frame and preserve the complete combined rider-and-machine silhouette. "
            "Collision, duck clearance, draw scale, and motion rebase all apply to that whole "
            "combined silhouette."
        )
    return facts + (
        "Draw one single character and one whole connected character silhouette. Measure "
        "proportion from that character's head; collision, duck clearance, draw scale, and "
        "motion rebase all apply to the whole character silhouette."
    )


def ground_prompt(resolved: ResolvedRunnerPackage, track: RunnerTrack) -> str:
    # Style rides inside the material-direction slot so the atlas HARD CONTRACT
    # stays the prompt's final word; appended trailing style text measurably
    # erodes locked-topology adherence past the 0.1 mismatch gate.
    style = resolved.package.game.style
    material_direction = (
        f"{track.ground.prompt.strip()} Target style: {style.label}; {', '.join(style.keywords)}."
    )
    return terrain_atlas_generation_prompt(material_direction)


def structural_ground_prompt(
    resolved: ResolvedRunnerPackage,
    track: RunnerTrack,
    chunk: RunnerSegmentChunk,
) -> str:
    """Bind one bespoke chunk painting to the shared material and style."""

    if not isinstance(track.ground, RunnerStructuralGround):
        raise ValueError("structural ground prompts require the structural ground mode")
    style = resolved.package.game.style
    material_direction = (
        f"{track.ground.prompt.strip()} Target style: {style.label}; {', '.join(style.keywords)}."
    )
    return structural_ground_generation_prompt(
        material_direction,
        segment_id=chunk.segment_id,
        columns=len(chunk.occupancy[0]),
        rows=len(chunk.occupancy),
        projection=track.ground.projection_mode(),
    )


def layer_prompt(
    resolved: ResolvedRunnerPackage, layer_prompt_text: str, *, transparent: bool
) -> str:
    prompt = (
        f"{layer_prompt_text}\n{_style_clause(resolved)}\n"
        "Output one horizontally seamless repeat unit. The left and right edges must join "
        "without a visible seam. "
    )
    prompt += (
        "Isolate only this layer on a fully transparent background with true alpha."
        if transparent
        else "Output a completely opaque sky plate with no transparency."
    )
    return prompt


def layer_loop_prompt(layer_prompt_text: str) -> str:
    """Compile the exact masked-edit instruction for a generative layer loop."""

    return (
        f"{layer_prompt_text}\nContinue this artwork seamlessly across the masked span so the "
        "far left and far right edges of the original image join perfectly. Match the existing "
        "palette, lighting, and level of detail exactly. Paint only inside the masked span."
    )


def avatar_concept_prompt(resolved: ResolvedRunnerPackage, avatar: RunnerAvatar) -> str:
    proportion = resolved.package.game.proportion.heads_for(avatar.body_kind)
    return (
        f"A single full-body identity concept of {avatar.display_name}: {avatar.prompt}\n"
        f"{_avatar_contract_clause(avatar, proportion_heads=proportion)}\n"
        "Draw in strict side view facing right, "
        "isolated on a fully transparent background with true alpha, no text or watermark.\n"
        + _style_clause(resolved)
    )


def avatar_motion_prompt(resolved: ResolvedRunnerPackage, avatar: RunnerAvatar, state: str) -> str:
    geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
    proportion = resolved.package.game.proportion.heads_for(avatar.body_kind)
    if avatar.silhouette_mode == "visible_rider_machine_v1":
        slide_direction = (
            "four isolated right-facing cells of one fast low-clearance chassis slide, in this "
            "exact order: drop, compress, fully-low undercarriage skid, fully-low held skid. "
            "Never begin to rise in the fourth cell: it is the pose held indefinitely while "
            "the player ducks. In cells three and four, keep every painted pixel of the complete "
            "connected rider-and-machine silhouette below 45 percent of standing run height, "
            "including antenna, backpack, rider hair, and arms. The machine's legs compress and "
            "tuck beneath the chassis; the rider remains visibly secured in the harness, folds "
            "safely with the chassis, and keeps both hands on the controls. Add no glow, shadow, "
            "or effect outside the low envelope; never detach, eject, stretch, or contort the rider"
        )
        hurt_direction = (
            "four right-facing cells of one brief recoil that ends back in the run: a hit "
            "flinch with the chassis rocked back, the deepest recoil, a recovering stride, and "
            "an upright running pose matching the run cycle. The fourth cell must be able to cut "
            "straight back to the run: the machine is upright and powered, the flower reactor and "
            "headlamp are lit, and the rider is secured with both hands on the controls. This is "
            "a survivable blow, not a defeat - never collapse, kneel, power down, detach, eject, "
            "or show gore or injury detail"
        )
        death_direction = (
            "four fully disconnected right-facing cells whose height strictly descends: a "
            "running stumble, knees buckling, a controlled forward kneel, and the lowest compact "
            "powered-down failure pose. The fourth cell is held indefinitely: keep the chassis "
            "collapsed or kneeling, the rider secured and visibly worried or exhausted with mouth "
            "closed, and the flower reactor and headlamp visibly dark. Never recover, rise, reset, "
            "smile, celebrate, or power back up. Center every complete figure inside its own "
            "quarter with a wide band of completely empty zero-alpha pixels between neighbors; "
            "add no glow, aura, dust, motion streak, cast shadow, lighting pool, or backdrop that "
            "could bridge cells, and show no gore or injury detail"
        )
    else:
        slide_direction = (
            "four sequential key poses of one fast forward baseball-style slide under a low "
            "obstacle: dropping from the run into the slide, then gliding low with the legs "
            "leading forward, the torso laid far back, and the head tucked so the whole "
            "figure stays below half its standing height, then beginning to rise back up"
        )
        hurt_direction = (
            "four sequential key poses of one brief recoil that ends back in the run: a hit "
            "flinch with the torso rocked back, the deepest recoil, a recovering stride, and an "
            "upright running pose matching the run cycle. The fourth cell must be able to cut "
            "straight back to the run. This is a survivable blow, not a defeat - never collapse, "
            "come to rest, or show gore or injury detail"
        )
        death_direction = (
            "four fully disconnected sequential key poses of the run ending: a stumble, knees "
            "buckling, a controlled forward collapse, and the lowest motionless final rest, "
            "without gore or injury detail. The fourth cell is held indefinitely: never recover, "
            "rise, reset, smile, celebrate, or return to idle. Center every complete figure inside "
            "its own quarter with a wide band of completely empty zero-alpha transparent pixels "
            "between every neighboring pose. Add no glow, aura, dust, motion streak, cast shadow, "
            "lighting pool, or backdrop that could bridge cells"
        )
    # Sustained thrust, not a jump: the cells are phases of one held climb that
    # loops, so none of them may read as a takeoff or a landing. Named
    # explicitly because the generic fallback ("poses that communicate fly")
    # reliably produces a jump.
    fly_direction = (
        "four sequential phases of one seamless sustained hovering thrust cycle, looping "
        "cleanly from the fourth cell back to the first: the body held level and airborne "
        "throughout with both feet clear of any ground, riding a steady lift with only a small "
        "rise-and-settle bob and a slight forward lean. Never a takeoff, never a landing, never "
        "a crouch, and never a ballistic jump arc"
    )
    direction = {
        "run": "four sequential phases of one seamless full-speed run cycle",
        "jump": "four sequential key poses of one forward jump arc: takeoff, rise, apex, fall",
        "slide": slide_direction,
        "fly": fly_direction,
        "hurt": hurt_direction,
        "death": death_direction,
    }.get(state, f"four clear game-animation key poses that communicate {state}")
    return (
        f"A {geometry.columns}x{geometry.rows} sprite motion strip of {avatar.display_name}: "
        f"{avatar.prompt}\n"
        f"{_avatar_contract_clause(avatar, proportion_heads=proportion)}\n"
        f"Exactly {geometry.frame_word} evenly spaced cells left to right, each one full-body "
        f"figure in strict side view facing right, showing {direction}. Every cell is one "
        "connected figure isolated on a fully transparent background with true alpha; nothing "
        "trails outside its own cell, no ground, no shadow, no text.\n" + _style_clause(resolved)
    )


def catalog_asset_prompt(
    resolved: ResolvedRunnerPackage,
    *,
    family: str,
    prompt_text: str,
    silhouette: str | None = None,
) -> str:
    if family == "projectile":
        if silhouette is None:
            raise ValueError("a projectile prompt requires its declared silhouette")
        art = projectile_silhouette_art(silhouette)
        # The axis directive leads, before the subject is even named: a thrown
        # object is the one catalog family the runtime moves, so which way it
        # was drawn is load-bearing rather than cosmetic.
        return (
            f"{art.axis_directive}\n{prompt_text}\nOne single subject, {art.shape_clause}, in "
            "strict side view, isolated on a fully transparent background with true alpha, no "
            "text or watermark.\n" + _style_clause(resolved)
        )
    framing = "strict side view" if family == "prop" else "clean collectible icon framing"
    return (
        f"{prompt_text}\nOne single subject, {framing}, isolated on a fully transparent "
        "background with true alpha, no text or watermark.\n" + _style_clause(resolved)
    )


def _boss_contract_clause(resolved: ResolvedRunnerPackage, boss: RunnerBoss) -> str:
    proportion = resolved.package.game.proportion.heads_for(boss.body_kind)
    heads = "" if proportion is None else f"Built to about {proportion} heads tall. "
    return (
        f"{heads}It is one connected machine of a single piece, drawn at roughly "
        f"{boss.height_units} times the height of the player character it faces."
    )


def boss_concept_prompt(resolved: ResolvedRunnerPackage, boss: RunnerBoss) -> str:
    return (
        f"A single full-body identity concept of {boss.display_name}: {boss.prompt}\n"
        f"{_boss_contract_clause(resolved, boss)}\n"
        "Draw in strict side view facing LEFT, isolated on a fully transparent background with "
        "true alpha, no text or watermark.\n" + _style_clause(resolved)
    )


def boss_motion_prompt(resolved: ResolvedRunnerPackage, boss: RunnerBoss, state: str) -> str:
    geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
    direction = {
        "hover": (
            "four sequential phases of one seamless hovering idle that loops cleanly from the "
            "fourth cell back to the first: the whole machine held aloft with a slow "
            "rise-and-settle bob, lift fans turning, trailing growth swaying slightly. It never "
            "touches ground and never changes its facing"
        ),
        "attack": (
            "four sequential key poses of one throw toward the LEFT: a gathering wind-up that "
            "draws mass back to the right, the release with the throwing head snapped forward "
            "to the left, the recoil rocked back, and a return to the level hovering pose. The "
            "fourth cell must be able to cut straight back to the hover. Show no projectile, "
            "no muzzle flash, and no beam"
        ),
        "death": (
            "four fully disconnected sequential key poses of the machine giving out: lift "
            "failing with a lurch, tipping nose-down, a slumping fall, and the lowest "
            "motionless final rest with its fans stopped. The fourth cell is held indefinitely: "
            "never recover, rise, or reset. This is equipment shutting down, never a creature "
            "dying: no gore, no wound, no death throes. Add no glow, aura, dust, motion streak, "
            "or lighting pool that could bridge one cell to the next"
        ),
    }.get(state, f"four clear game-animation key poses that communicate {state}")
    # The separation clause LEADS, before the subject is even named.
    #
    # A boss is the one runner actor whose silhouette is defined by trailing
    # growth, and the first pass proved the point: as a trailing sub-clause
    # ("nothing trails outside its own cell") the roots bridged neighbouring
    # cells anyway, merging four poses into three and failing the exact-slot
    # repack. This recipe has already watched facing, isolated-view framing,
    # and reach each fail as trailing sub-clauses and succeed as leading
    # labelled ones; separation is the same shape of instruction.
    separation = (
        "SEPARATION, before anything else: this subject trails roots, vines and hoses, and every "
        f"one of them must be gathered in close. Draw exactly {geometry.frame_word} cells left to "
        "right, each holding ONE single connected island of pixels, with a wide vertical band of "
        "completely empty zero-alpha transparent pixels between every neighbouring pair. No root, "
        "vine, leaf, flower, hose, cable, water droplet, spark, glow, shadow or debris may cross "
        "into a neighbouring cell or float free of the machine with empty space between it and "
        "the body. Nothing dangles below the machine far enough to reach the bottom edge."
    )
    return (
        f"{separation}\n"
        f"A {geometry.columns}x{geometry.rows} sprite motion strip of {boss.display_name}: "
        f"{boss.prompt}\n"
        f"{_boss_contract_clause(resolved, boss)}\n"
        f"Each cell is one complete machine in strict side view facing LEFT, showing "
        f"{direction}. Isolate every cell on a fully transparent background with true alpha; no "
        "ground, no cast shadow, no backdrop, no text.\n" + _style_clause(resolved)
    )


def soundtrack_direction() -> str:
    """The runner-specific staging omitted by the shared music compiler."""

    return (
        "Endless-runner staging: establish the full rhythmic engine on the first beat and "
        "maintain an urgent, even forward pulse throughout. Favor short repeating action cells, "
        "clear percussion transients, and bass motion that supports rapid player reactions. "
        "Do not drift into RPG exploration, town-theme, pastoral, cinematic, rubato, ambient, "
        "or long-form orchestral development."
    )


__all__ = [
    "avatar_concept_prompt",
    "fx_plate_prompt",
    "avatar_motion_prompt",
    "catalog_asset_prompt",
    "ground_prompt",
    "layer_loop_prompt",
    "layer_prompt",
    "structural_ground_prompt",
    "soundtrack_direction",
    "visual_direction",
    "visual_direction_digest",
]

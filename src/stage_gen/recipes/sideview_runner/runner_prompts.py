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
from stage_gen.components.runner_track import structural_ground_generation_prompt
from stage_gen.components.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from stage_gen.components.sideview_terrain import terrain_atlas_generation_prompt

if TYPE_CHECKING:
    from stage_gen.components.runner_content import RunnerAvatar
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

    style = resolved.package.game.style
    material_direction = (
        f"{track.ground.prompt.strip()} Target style: {style.label}; {', '.join(style.keywords)}."
    )
    return structural_ground_generation_prompt(
        material_direction,
        segment_id=chunk.segment_id,
        columns=len(chunk.occupancy[0]),
        rows=len(chunk.occupancy),
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
        death_direction = (
            "four fully disconnected sequential key poses of the run ending: a stumble, knees "
            "buckling, a controlled forward collapse, and the lowest motionless final rest, "
            "without gore or injury detail. The fourth cell is held indefinitely: never recover, "
            "rise, reset, smile, celebrate, or return to idle. Center every complete figure inside "
            "its own quarter with a wide band of completely empty zero-alpha transparent pixels "
            "between every neighboring pose. Add no glow, aura, dust, motion streak, cast shadow, "
            "lighting pool, or backdrop that could bridge cells"
        )
    direction = {
        "run": "four sequential phases of one seamless full-speed run cycle",
        "jump": "four sequential key poses of one forward jump arc: takeoff, rise, apex, fall",
        "slide": slide_direction,
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


def catalog_asset_prompt(resolved: ResolvedRunnerPackage, *, family: str, prompt_text: str) -> str:
    framing = "strict side view" if family == "prop" else "clean collectible icon framing"
    return (
        f"{prompt_text}\nOne single subject, {framing}, isolated on a fully transparent "
        "background with true alpha, no text or watermark.\n" + _style_clause(resolved)
    )


__all__ = [
    "avatar_concept_prompt",
    "avatar_motion_prompt",
    "catalog_asset_prompt",
    "ground_prompt",
    "layer_loop_prompt",
    "layer_prompt",
    "structural_ground_prompt",
    "visual_direction",
    "visual_direction_digest",
]

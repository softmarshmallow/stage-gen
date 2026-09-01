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
from stage_gen.components.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from stage_gen.components.sideview_terrain import terrain_atlas_generation_prompt

if TYPE_CHECKING:
    from stage_gen.components.runner_content import RunnerAvatar
    from stage_gen.components.runner_track import RunnerTrack
    from stage_gen.orchestration.game_package import ResolvedGamePackage
    from stage_gen.recipes.sideview_runner.runner_request import ResolvedRunnerPackage


def visual_direction(resolved: ResolvedRunnerPackage) -> dict[str, object]:
    package: ResolvedGamePackage = resolved.package
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


def ground_prompt(resolved: ResolvedRunnerPackage, track: RunnerTrack) -> str:
    # Style rides inside the material-direction slot so the atlas HARD CONTRACT
    # stays the prompt's final word; appended trailing style text measurably
    # erodes locked-topology adherence past the 0.1 mismatch gate.
    style = resolved.package.game.style
    material_direction = (
        f"{track.ground.prompt.strip()} Target style: {style.label}; {', '.join(style.keywords)}."
    )
    return terrain_atlas_generation_prompt(material_direction)


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


def avatar_concept_prompt(resolved: ResolvedRunnerPackage, avatar: RunnerAvatar) -> str:
    proportion = resolved.package.game.proportion.heads_for(avatar.body_kind)
    return (
        f"A single full-body identity concept of {avatar.display_name}: {avatar.prompt}\n"
        f"Drawn at approximately {proportion} heads tall, in strict side view facing right, "
        "isolated on a fully transparent background with true alpha, no text or watermark.\n"
        + _style_clause(resolved)
    )


def avatar_motion_prompt(resolved: ResolvedRunnerPackage, avatar: RunnerAvatar, state: str) -> str:
    geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
    direction = {
        "run": "four sequential phases of one seamless full-speed run cycle",
        "jump": "four sequential key poses of one forward jump arc: takeoff, rise, apex, fall",
        "death": (
            "four sequential key poses of the run ending: a stumble, a collapse forward, and a "
            "final rest, without gore or injury detail"
        ),
    }.get(state, f"four clear game-animation key poses that communicate {state}")
    return (
        f"A {geometry.columns}x{geometry.rows} sprite motion strip of {avatar.display_name}: "
        f"{avatar.prompt}\n"
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
    "layer_prompt",
    "visual_direction",
    "visual_direction_digest",
]

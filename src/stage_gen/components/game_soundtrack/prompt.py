"""Compile provider-neutral authored track intent into one music prompt.

This sits with the intent it compiles rather than in a recipe, because every
consumer of a generated track needs the same two guarantees and neither is a
matter of genre taste: the performance and ending must follow the authored
`instrumental` and `seamless_loop` flags rather than a prompt writer's habit,
and the output must be original. A recipe that composed its own prompt could
silently drop the originality clause - which is exactly what happened once.

What stays a recipe decision is the *medium* the track is for and any staging
direction it needs; both are parameters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stage_gen.components.game_soundtrack.models import TrackGenerationIntent

#: Non-negotiable regardless of medium: see `docs/oss-ip.md`.
ORIGINALITY_CLAUSE = (
    "Do not reference or imitate any artist, performer, franchise, brand, or identifiable "
    "composition. Do not quote an existing melody."
)


def music_track_prompt(
    *,
    medium: str,
    game_id: str,
    track_id: str,
    creative_brief: str,
    generation: TrackGenerationIntent,
    direction: str | None = None,
) -> str:
    """One original-music prompt from authored intent.

    `medium` names what the track plays under ("a 2D game", "a visual novel
    scene"); `direction` is optional staging the medium needs and the catalog
    does not model.
    """

    performance = (
        "Instrumental only; do not include vocals, speech, or spoken words."
        if generation.instrumental
        else "Use vocals only when the creative brief explicitly calls for them."
    )
    ending = (
        "The ending must reconnect naturally to the opening harmony and rhythm, with no fade-out."
        if generation.seamless_loop
        else "Give the track a deliberate musical ending rather than an abrupt cutoff."
    )
    lines = [
        f"Generate an original music track for {medium}.",
        f"Game ID: {game_id}.",
        f"Track ID: {track_id}.",
        f"Creative brief: {creative_brief}",
        f"Target duration: approximately {generation.target_duration_seconds} seconds.",
        performance,
        ending,
    ]
    if direction is not None:
        lines.append(direction)
    lines.append(ORIGINALITY_CLAUSE)
    return "\n".join(lines)


__all__ = ["ORIGINALITY_CLAUSE", "music_track_prompt"]

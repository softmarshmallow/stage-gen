"""Recipe-owned compilation of an authored soundtrack track into a music prompt.

The authored catalog owns stable track identities and provider-neutral creative intent.
Turning that intent into the one string a music provider is asked for is a recipe decision,
so it lives here rather than in the shared `game_soundtrack` component.
"""

from __future__ import annotations

from stage_gen.components.game_soundtrack import SoundtrackTrack


def soundtrack_track_prompt(game_id: str, track: SoundtrackTrack) -> str:
    """Compile provider-neutral authored intent into one original-music prompt."""

    generation = track.generation
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
    return (
        "Generate an original music track for a 2D game.\n"
        f"Game ID: {game_id}.\n"
        f"Track ID: {track.track_id}.\n"
        f"Creative brief: {track.creative_brief}\n"
        f"Target duration: approximately {generation.target_duration_seconds} seconds.\n"
        f"{performance}\n"
        f"{ending}\n"
        "Do not reference or imitate any artist, performer, franchise, brand, or identifiable "
        "composition. Do not quote an existing melody."
    )

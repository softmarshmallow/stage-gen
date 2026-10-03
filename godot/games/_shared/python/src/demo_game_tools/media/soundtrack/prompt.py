"""Legacy prompt spelling retained so existing generated-track cache keys stay stable."""

from demo_game_tools.kits.music.models import TrackGenerationIntent
from demo_game_tools.kits.music.prompt import ORIGINALITY_CLAUSE
from demo_game_tools.kits.music.prompt import music_track_prompt as _asset_prompt


def music_track_prompt(
    *,
    medium: str,
    game_id: str,
    track_id: str,
    creative_brief: str,
    generation: TrackGenerationIntent,
    direction: str | None = None,
) -> str:
    return _asset_prompt(
        medium=medium,
        track_id=track_id,
        creative_brief=creative_brief,
        generation=generation,
        direction=direction,
        asset_id=game_id,
    ).replace(f"Asset ID: {game_id}.", f"Game ID: {game_id}.", 1)


__all__ = ["ORIGINALITY_CLAUSE", "music_track_prompt"]

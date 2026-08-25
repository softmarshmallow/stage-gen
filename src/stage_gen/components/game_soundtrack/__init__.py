"""Provider-neutral authored game-soundtrack API."""

from .library import (
    GAME_SOUNDTRACK_LIBRARY_RESOLUTION_VERSION,
    ResolvedGameSoundtrack,
    resolve_game_soundtrack_binding,
)
from .loader import (
    GameSoundtrackLoadError,
    canonical_game_soundtrack_json,
    game_soundtrack_sha256,
    load_game_soundtrack,
    load_game_soundtrack_bytes,
    load_game_soundtrack_mapping,
)
from .models import (
    GAME_SOUNDTRACK_SCHEMA_VERSION,
    GameSoundtrack,
    GameSoundtrackBinding,
    SoundtrackPlaybackPolicy,
    SoundtrackTrack,
    TrackGenerationIntent,
)

__all__ = [
    "GAME_SOUNDTRACK_LIBRARY_RESOLUTION_VERSION",
    "GAME_SOUNDTRACK_SCHEMA_VERSION",
    "GameSoundtrack",
    "GameSoundtrackBinding",
    "GameSoundtrackLoadError",
    "ResolvedGameSoundtrack",
    "SoundtrackPlaybackPolicy",
    "SoundtrackTrack",
    "TrackGenerationIntent",
    "canonical_game_soundtrack_json",
    "game_soundtrack_sha256",
    "load_game_soundtrack",
    "load_game_soundtrack_bytes",
    "load_game_soundtrack_mapping",
    "resolve_game_soundtrack_binding",
]

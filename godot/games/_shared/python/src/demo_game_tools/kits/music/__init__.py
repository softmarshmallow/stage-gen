"""Independent music asset definitions and the prompt a track is composed from."""

from .models import MusicTrack, SoundtrackTrack, TrackGenerationIntent
from .prompt import music_track_prompt

__all__ = [
    "MusicTrack",
    "SoundtrackTrack",
    "TrackGenerationIntent",
    "music_track_prompt",
]

"""Independent music asset definitions, prompts, and composable node families."""

from .models import MusicTrack, SoundtrackTrack, TrackGenerationIntent
from .nodes import SoundtrackHandlers, SoundtrackHost, add_soundtrack_nodes, soundtrack_node_types
from .prompt import music_track_prompt

__all__ = [
    "MusicTrack",
    "SoundtrackTrack",
    "TrackGenerationIntent",
    "SoundtrackHandlers",
    "SoundtrackHost",
    "add_soundtrack_nodes",
    "soundtrack_node_types",
    "music_track_prompt",
]

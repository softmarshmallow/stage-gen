"""Immutable resources owned by the historical demo builders."""

from pathlib import Path

_RESOURCE_ROOT = Path(__file__).resolve().parent


def bundled_music_path() -> Path:
    """Return the approved game preview loop, with its unchanged adjacent provenance."""
    return _RESOURCE_ROOT / "music" / "preview-loop.mp3"


def game_vocabulary_path() -> Path:
    """Return the historical game vocabulary; it is not an SDK authoring contract."""
    return _RESOURCE_ROOT / "prompting" / "game_vocabulary_v1.json"


__all__ = ["bundled_music_path", "game_vocabulary_path"]

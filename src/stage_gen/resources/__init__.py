"""Filesystem paths for immutable resources shipped in the stage-gen wheel."""

from __future__ import annotations

from pathlib import Path

_RESOURCE_ROOT = Path(__file__).resolve().parent
_REQUIRED_RELATIVE_PATHS = (
    "fixtures/image_gen_templates/character_template.png",
    "fixtures/image_gen_templates/character_template_combined.png",
    "fixtures/image_gen_templates/inventory_template.png",
    "fixtures/image_gen_templates/obstacle_template.png",
    "fixtures/image_gen_templates/wireframe.png",
    "fixtures/loading.gif",
    "fixtures/prompts.txt",
    "fixtures/styles.txt",
    "music/preview-loop.mp3",
    "music/preview-loop.mp3.meta.json",
    "music/preview-loop.LICENSE.md",
)


def image_template_dir() -> Path:
    """Return the installed directory containing reference layout templates."""

    return _RESOURCE_ROOT / "fixtures" / "image_gen_templates"


def bundled_music_path() -> Path:
    """Return the installed fallback music artifact; metadata stays adjacent."""

    return _RESOURCE_ROOT / "music" / "preview-loop.mp3"


def required_resource_paths() -> tuple[Path, ...]:
    """Return every fixture/resource that the distribution promises to ship."""

    return tuple(_RESOURCE_ROOT / relative for relative in _REQUIRED_RELATIVE_PATHS)


__all__ = ["bundled_music_path", "image_template_dir", "required_resource_paths"]

"""Filesystem paths for immutable resources shipped in the stage-gen wheel."""

from __future__ import annotations

from hashlib import sha256
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
    "prompting/image_style_vocabulary_v1.json",
    "prompting/game_vocabulary_v1.json",
    "skills/anchor-image-style/SKILL.md",
    "skills/compile-theme-art-direction/SKILL.md",
)


def image_template_dir() -> Path:
    """Return the installed directory containing reference layout templates."""

    return _RESOURCE_ROOT / "fixtures" / "image_gen_templates"


def bundled_music_path() -> Path:
    """Return the installed fallback music artifact; metadata stays adjacent."""

    return _RESOURCE_ROOT / "music" / "preview-loop.mp3"


def theme_compiler_skill_path() -> Path:
    """Return the tracked art-direction skill consumed by the theme compiler."""

    return _RESOURCE_ROOT / "skills" / "compile-theme-art-direction" / "SKILL.md"


def image_style_skill_path() -> Path:
    """Return the tracked image-style selection skill."""

    return _RESOURCE_ROOT / "skills" / "anchor-image-style" / "SKILL.md"


def image_style_vocabulary_path() -> Path:
    """Return the versioned canonical image-style vocabulary."""

    return _RESOURCE_ROOT / "prompting" / "image_style_vocabulary_v1.json"


def game_vocabulary_path() -> Path:
    """Return the versioned closed vocabulary an authored game contract draws from."""

    return _RESOURCE_ROOT / "prompting" / "game_vocabulary_v1.json"


def image_style_resource_digests() -> dict[str, str]:
    """Hash the exact packaged bytes consumed by the image-style compiler."""

    return {
        "skill_sha256": sha256(image_style_skill_path().read_bytes()).hexdigest(),
        "vocabulary_sha256": sha256(image_style_vocabulary_path().read_bytes()).hexdigest(),
    }


def required_resource_paths() -> tuple[Path, ...]:
    """Return every fixture/resource that the distribution promises to ship."""

    return tuple(_RESOURCE_ROOT / relative for relative in _REQUIRED_RELATIVE_PATHS)


__all__ = [
    "bundled_music_path",
    "image_style_resource_digests",
    "image_style_skill_path",
    "image_style_vocabulary_path",
    "image_template_dir",
    "required_resource_paths",
    "theme_compiler_skill_path",
    "game_vocabulary_path",
]

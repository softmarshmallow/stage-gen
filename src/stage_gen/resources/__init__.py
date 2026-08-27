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
    "fixtures/image_gen_templates/terrain_atlas_12x4_template.png",
    "fixtures/image_gen_templates/terrain_atlas_godot_topology_reference.png",
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
    "terrain/godot_3x3_minimal_lookup_v1.json",
)


def image_template_dir() -> Path:
    """Return the installed directory containing reference layout templates."""

    return _RESOURCE_ROOT / "fixtures" / "image_gen_templates"


def inventory_template_path() -> Path:
    """Return the immutable V1 inventory layout reference."""

    return image_template_dir() / "inventory_template.png"


def terrain_atlas_template_path() -> Path:
    """Return the locked local 12-by-4 terrain topology-silhouette template."""

    return image_template_dir() / "terrain_atlas_12x4_template.png"


def terrain_atlas_topology_reference_path() -> Path:
    """Return the attributed Godot terrain-grid reference used as redundant topology input."""

    return image_template_dir() / "terrain_atlas_godot_topology_reference.png"


def terrain_atlas_lookup_path() -> Path:
    """Return the locked 47-mask 3x3-minimal lookup contract."""

    return _RESOURCE_ROOT / "terrain" / "godot_3x3_minimal_lookup_v1.json"


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
    "inventory_template_path",
    "required_resource_paths",
    "terrain_atlas_lookup_path",
    "terrain_atlas_template_path",
    "terrain_atlas_topology_reference_path",
    "theme_compiler_skill_path",
    "game_vocabulary_path",
]

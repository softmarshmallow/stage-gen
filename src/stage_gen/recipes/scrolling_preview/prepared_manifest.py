"""Assemble one portable runtime manifest from accepted prepared-package artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from stage_gen.components.game_content import MotionPresentation, PropContent
from stage_gen.components.game_ui import inventory_panel_layout_contract
from stage_gen.media import measure_alpha_ground_contact
from stage_gen.orchestration.game_package import ResolvedGamePackage
from stage_gen.recipes.scrolling_preview.motion_contract import (
    MOTION_ATLAS_COLUMNS,
    MOTION_ATLAS_REQUIRED_CELLS,
    MOTION_ATLAS_ROWS,
    dialogue_atlas_grid,
    motion_source_facing,
    runtime_mirrors_source,
)
from stage_gen.reliability import atomic_write_json

PREPARED_RUNTIME_MANIFEST_SCHEMA_VERSION = 5
PREPARED_RUNTIME_MANIFEST_KIND = "prepared-game-runtime-v5"


class PreparedManifestError(ValueError):
    """Reject an incomplete, ambiguous, or unsafe integration input."""


@dataclass(frozen=True, slots=True)
class PreparedManifestResult:
    manifest: dict[str, object]
    output_dir: Path
    artifact_count: int


def assemble_prepared_runtime(
    package: ResolvedGamePackage,
    *,
    artifact_roots: Sequence[Path],
    output_dir: Path,
) -> PreparedManifestResult:
    """Publish the exact runtime closure without invoking a provider.

    Roots are searched in caller order. This lets a narrow corrective run override an older
    complete run while every selected byte remains digest-bound in the emitted manifest.
    """

    if not artifact_roots:
        raise PreparedManifestError("integration requires at least one artifact root")
    roots = tuple(_validated_root(path) for path in artifact_roots)
    if output_dir.exists():
        raise PreparedManifestError(f"integration output already exists: {output_dir}")
    for relative_path in runtime_artifact_paths(package):
        _find_artifact(roots, relative_path)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.assembling-", dir=output_dir.parent)
    )
    try:
        staged = _assemble_prepared_runtime(
            package,
            artifact_roots=roots,
            output_dir=staging,
        )
        staging.rename(output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return PreparedManifestResult(
        manifest=staged.manifest,
        output_dir=output_dir,
        artifact_count=staged.artifact_count,
    )


def _assemble_prepared_runtime(
    package: ResolvedGamePackage,
    *,
    artifact_roots: Sequence[Path],
    output_dir: Path,
) -> PreparedManifestResult:
    roots = tuple(artifact_roots)

    artifacts: dict[str, dict[str, object]] = {}

    def publish(relative_path: str) -> dict[str, object]:
        existing = artifacts.get(relative_path)
        if existing is not None:
            return existing
        source = _find_artifact(roots, relative_path)
        target = _safe_output_path(output_dir, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        record = _artifact_record(target, relative_path)
        artifacts[relative_path] = record
        return record

    def prop_manifest(prop: PropContent) -> dict[str, object]:
        relative_path = f"content/props/{prop.prop_id}.png"
        asset = publish(relative_path)
        contact = measure_alpha_ground_contact(
            _safe_output_path(output_dir, relative_path).read_bytes()
        )
        normalized = contact["ground_contact_y_normalized"]
        if not isinstance(normalized, (int, float)):
            raise PreparedManifestError("prop ground contact measurement is invalid")
        return {
            "prop_id": prop.prop_id,
            "display_name": prop.display_name,
            "ground_contact_y_normalized": float(normalized),
            "asset": asset,
        }

    map_uses = {entry.map_id: entry for entry in package.gameplay.map_uses}
    maps: list[dict[str, object]] = []
    for game_map in package.maps:
        map_use = map_uses[game_map.map_id]
        map_manifest: dict[str, object] = {
            "map_id": game_map.map_id,
            "revision": game_map.revision,
            "display_name": game_map.display_name,
            "view": game_map.view.model_dump(mode="json"),
            "continuity": game_map.continuity.model_dump(mode="json"),
            "role": map_use.role,
            "hostile_population_enabled": map_use.hostile_population_enabled,
            "track_ids": list(map_use.track_ids),
            "layers": [
                {
                    "layer_id": layer.layer_id,
                    "plane": layer.plane,
                    "order": layer.order,
                    "parallax": layer.parallax,
                    "alpha_mode": layer.alpha_mode,
                    "asset": publish(f"maps/{game_map.map_id}/layers/{layer.layer_id}.png"),
                }
                for layer in game_map.layers
            ],
            "ground": {
                "mode": game_map.ground.mode,
                "occupancy": list(game_map.ground.occupancy),
                "asset": publish(f"maps/{game_map.map_id}/ground.png"),
            },
        }
        if game_map.ladder is not None:
            map_manifest["ladder"] = {
                "mode": game_map.ladder.mode,
                "placements": [
                    entry.model_dump(mode="json") for entry in game_map.ladder.placements
                ],
                "asset": publish(f"maps/{game_map.map_id}/ladder.png"),
            }
        if game_map.portal is not None:
            map_manifest["portal"] = {
                "mode": game_map.portal.mode,
                "endpoints": [entry.model_dump(mode="json") for entry in game_map.portal.endpoints],
                "asset": publish(f"maps/{game_map.map_id}/portal.png"),
            }
        maps.append(map_manifest)

    player = package.player.players[0]
    player_manifest = {
        "player_id": player.player_id,
        "display_name": player.display_name,
        "body_kind": player.body_kind,
        "concept": publish(f"content/players/{player.player_id}/concept.png"),
        "states": {
            motion.state: _motion_binding(
                publish(f"content/players/{player.player_id}/states/{motion.state}.png"),
                motion,
                actor_kind="player",
            )
            for motion in player.motions
        },
        "dialogue": _dialogue_binding(
            publish(f"content/players/{player.player_id}/dialogue.png"),
            player.dialogue_art.expressions,
        ),
    }

    mobs = [
        {
            "mob_id": mob.mob_id,
            "display_name": mob.display_name,
            "body_kind": mob.body_kind,
            "rank": mob.rank,
            "concept": publish(f"content/mobs/{mob.mob_id}/concept.png"),
            "states": {
                motion.state: _motion_binding(
                    publish(f"content/mobs/{mob.mob_id}/states/{motion.state}.png"),
                    motion,
                    actor_kind="mob",
                )
                for motion in mob.motions
            },
        }
        for mob in package.mobs.mobs
    ]

    npcs = [
        {
            "npc_id": npc.npc_id,
            "display_name": npc.display_name,
            "role": npc.role,
            "body_kind": npc.body_kind,
            "world": _motion_binding(
                publish(f"content/npcs/{npc.npc_id}/world.png"),
                npc.world_motions[0],
                actor_kind="npc",
            ),
            "dialogue": _dialogue_binding(
                publish(f"content/npcs/{npc.npc_id}/dialogue.png"),
                npc.dialogue_expressions,
            ),
        }
        for npc in package.npcs.npcs
    ]

    props = [prop_manifest(prop) for prop in package.props.props]
    items = [
        {
            "item_id": item.item_id,
            "display_name": item.display_name,
            "item_kind": item.item_kind,
            "asset": publish(f"content/items/{item.item_id}.png"),
        }
        for item in package.items.items
    ]
    tracks = [
        {
            "track_id": track.track_id,
            "display_name": track.display_name,
            "instrumental": track.generation.instrumental,
            "seamless_loop": track.generation.seamless_loop,
            "target_duration_seconds": track.generation.target_duration_seconds,
            "asset": publish(f"soundtrack/{track.track_id}.mp3"),
        }
        for track in package.soundtrack.tracks
    ]
    ui = {
        "inventory_panel": {
            **inventory_panel_layout_contract(),
            "asset": publish("ui/inventory_panel.png"),
        }
    }

    artifact_records = [artifacts[path] for path in sorted(artifacts)]
    closure_sha256 = _canonical_sha256(artifact_records)
    manifest: dict[str, object] = {
        "schema_version": PREPARED_RUNTIME_MANIFEST_SCHEMA_VERSION,
        "kind": PREPARED_RUNTIME_MANIFEST_KIND,
        "game_id": package.game.game_id,
        "revision": package.game.revision,
        "display_name": package.game.display_name,
        "package_sha256": package.package_sha256,
        "canonical_game_sha256": package.canonical_game_sha256,
        "universe": package.file(package.game.universe.source).data.decode("utf-8"),
        "presentation": package.game.presentation.model_dump(mode="json"),
        "style": package.game.style.model_dump(mode="json"),
        "proportion": package.game.proportion.model_dump(mode="json"),
        "entry_map_id": package.gameplay.entry_map_id,
        "entry_spawn_id": package.gameplay.entry_spawn_id,
        "maps": maps,
        "player": player_manifest,
        "mobs": mobs,
        "npcs": npcs,
        "props": props,
        "items": items,
        "ui": ui,
        "soundtrack": {
            "playback": package.soundtrack.playback.model_dump(mode="json"),
            "tracks": tracks,
        },
        "gameplay": package.gameplay.model_dump(mode="json"),
        "sequences": [sequence.model_dump(mode="json") for sequence in package.sequences],
        "closure": {
            "artifact_count": len(artifact_records),
            "artifacts_sha256": closure_sha256,
            "artifacts": artifact_records,
        },
    }
    atomic_write_json(output_dir / "manifest.json", manifest)
    return PreparedManifestResult(
        manifest=manifest,
        output_dir=output_dir,
        artifact_count=len(artifact_records),
    )


def _motion_binding(
    artifact: dict[str, object],
    motion: MotionPresentation,
    *,
    actor_kind: Literal["player", "mob", "npc"],
) -> dict[str, object]:
    invalid = [
        index for index in motion.canonical_frame_indices if index >= MOTION_ATLAS_REQUIRED_CELLS
    ]
    if invalid:
        raise PreparedManifestError(
            f"{actor_kind} motion {motion.state} selects unavailable canonical frames: {invalid}"
        )
    source_facing = motion_source_facing(actor_kind, motion.state)
    playback: dict[str, object] = {
        "mode": motion.playback_mode,
        "canonical_frame_indices": list(motion.canonical_frame_indices),
    }
    if motion.frames_per_second is not None:
        playback["frames_per_second"] = motion.frames_per_second
    return {
        "source_facing": source_facing,
        "runtime_mirror": runtime_mirrors_source(source_facing),
        "columns": MOTION_ATLAS_COLUMNS,
        "rows": MOTION_ATLAS_ROWS,
        "source_frame_count": MOTION_ATLAS_REQUIRED_CELLS,
        "playback": playback,
        "asset": artifact,
    }


def _dialogue_binding(artifact: dict[str, object], expressions: Sequence[str]) -> dict[str, object]:
    columns, rows = dialogue_atlas_grid(len(expressions))
    return {
        "columns": columns,
        "rows": rows,
        "index_order": "row_major",
        "expressions": list(expressions),
        "asset": artifact,
    }


def _validated_root(path: Path) -> Path:
    root = path.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise PreparedManifestError(f"artifact root must be a real directory: {path}")
    return root


def _find_artifact(roots: Sequence[Path], relative_path: str) -> Path:
    for root in roots:
        candidate = root.joinpath(*relative_path.split("/"))
        if not candidate.exists():
            continue
        if candidate.is_symlink() or not candidate.is_file():
            raise PreparedManifestError(f"runtime artifact must be a regular file: {relative_path}")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise PreparedManifestError(f"runtime artifact escapes its root: {relative_path}")
        return resolved
    raise PreparedManifestError(f"missing accepted runtime artifact: {relative_path}")


def _safe_output_path(output_dir: Path, relative_path: str) -> Path:
    parts = relative_path.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise PreparedManifestError(f"invalid runtime artifact path: {relative_path}")
    target = output_dir.joinpath(*parts)
    if not target.absolute().is_relative_to(output_dir.absolute()):
        raise PreparedManifestError(f"runtime artifact escapes output: {relative_path}")
    return target


def _artifact_record(path: Path, relative_path: str) -> dict[str, object]:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    record: dict[str, object] = {
        "path": relative_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "media_type": _media_type(suffix),
    }
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            record["width"] = image.width
            record["height"] = image.height
    return record


def _media_type(suffix: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp3": "audio/mpeg",
    }.get(suffix, "application/octet-stream")


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def runtime_artifact_paths(package: ResolvedGamePackage) -> tuple[str, ...]:
    """Return the deterministic expected media closure for tests and reporting."""

    paths: list[str] = []
    for game_map in package.maps:
        paths.extend(
            f"maps/{game_map.map_id}/layers/{layer.layer_id}.png" for layer in game_map.layers
        )
        paths.append(f"maps/{game_map.map_id}/ground.png")
        if game_map.ladder is not None:
            paths.append(f"maps/{game_map.map_id}/ladder.png")
        if game_map.portal is not None:
            paths.append(f"maps/{game_map.map_id}/portal.png")
    for player in package.player.players:
        paths.append(f"content/players/{player.player_id}/concept.png")
        paths.extend(
            f"content/players/{player.player_id}/states/{motion.state}.png"
            for motion in player.motions
        )
        paths.append(f"content/players/{player.player_id}/dialogue.png")
    for mob in package.mobs.mobs:
        paths.append(f"content/mobs/{mob.mob_id}/concept.png")
        paths.extend(
            f"content/mobs/{mob.mob_id}/states/{motion.state}.png" for motion in mob.motions
        )
    for npc in package.npcs.npcs:
        paths.extend(
            (
                f"content/npcs/{npc.npc_id}/world.png",
                f"content/npcs/{npc.npc_id}/dialogue.png",
            )
        )
    paths.extend(f"content/props/{entry.prop_id}.png" for entry in package.props.props)
    paths.extend(f"content/items/{entry.item_id}.png" for entry in package.items.items)
    paths.append("ui/inventory_panel.png")
    paths.extend(f"soundtrack/{track.track_id}.mp3" for track in package.soundtrack.tracks)
    return tuple(sorted(paths))


def verify_prepared_runtime(run_dir: Path) -> dict[str, object]:
    """Revalidate one published run from bytes without trusting path existence."""

    root = _validated_root(run_dir)
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PreparedManifestError("prepared runtime is missing a regular manifest.json")
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise PreparedManifestError(f"prepared runtime manifest is invalid: {error}") from error
    if not isinstance(manifest, dict):
        raise PreparedManifestError("prepared runtime manifest must be an object")
    if (
        manifest.get("schema_version") != PREPARED_RUNTIME_MANIFEST_SCHEMA_VERSION
        or manifest.get("kind") != PREPARED_RUNTIME_MANIFEST_KIND
    ):
        raise PreparedManifestError("prepared runtime manifest identity is invalid")
    closure = manifest.get("closure")
    if not isinstance(closure, dict) or not isinstance(closure.get("artifacts"), list):
        raise PreparedManifestError("prepared runtime manifest closure is invalid")
    declared = closure["artifacts"]
    paths: list[str] = []
    verified: list[dict[str, object]] = []
    for index, raw_record in enumerate(declared):
        if not isinstance(raw_record, dict) or not isinstance(raw_record.get("path"), str):
            raise PreparedManifestError(f"runtime closure artifact {index} is invalid")
        relative_path = raw_record["path"]
        target = _safe_output_path(root, relative_path)
        if target.is_symlink() or not target.is_file():
            raise PreparedManifestError(f"runtime closure artifact is not a file: {relative_path}")
        if not target.resolve(strict=True).is_relative_to(root):
            raise PreparedManifestError(f"runtime closure artifact escapes run: {relative_path}")
        actual = _artifact_record(target, relative_path)
        if actual != raw_record:
            raise PreparedManifestError(f"runtime closure artifact drifted: {relative_path}")
        paths.append(relative_path)
        verified.append(actual)
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        raise PreparedManifestError("runtime closure artifact paths must be unique and sorted")
    if closure.get("artifact_count") != len(verified):
        raise PreparedManifestError("runtime closure artifact_count disagrees")
    if closure.get("artifacts_sha256") != _canonical_sha256(verified):
        raise PreparedManifestError("runtime closure digest disagrees")
    actual_files = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )
    expected_files = sorted(["manifest.json", *paths])
    if actual_files != expected_files:
        raise PreparedManifestError("runtime directory contains undeclared or missing files")
    return {
        "schema_version": 1,
        "kind": "prepared-runtime-verification-v1",
        "valid": True,
        "game_id": manifest.get("game_id"),
        "package_sha256": manifest.get("package_sha256"),
        "artifact_count": len(verified),
        "artifacts_sha256": closure.get("artifacts_sha256"),
    }


__all__ = [
    "PREPARED_RUNTIME_MANIFEST_KIND",
    "PREPARED_RUNTIME_MANIFEST_SCHEMA_VERSION",
    "PreparedManifestError",
    "PreparedManifestResult",
    "assemble_prepared_runtime",
    "runtime_artifact_paths",
    "verify_prepared_runtime",
]

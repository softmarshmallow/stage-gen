"""Assemble one portable runtime manifest from accepted prepared-package artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from gnode import atomic_write_json
from stage_gen.components.game_contract.package import PreparedScale
from stage_gen.components.game_ui import inventory_panel_layout_contract
from stage_gen.components.game_ui.nodes import (
    document_roles,
    ui_atlas_manifest_block,
)
from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_CELL_PX,
    PaintedTerrainGround,
    painted_silhouette_tolerance,
    painted_terrain_segments,
)
from stage_gen.components.platformer_content import MotionPresentation, PropContent
from stage_gen.components.platformer_map import PreparedGameMap, PreparedMapLayer
from stage_gen.components.platformer_map.prepared import (
    PreparedMapTerrain,
    load_prepared_map_terrain_bytes,
    validate_generated_terrain,
)
from stage_gen.components.sideview_actor.asset_unit import (
    ResolvedMagnitude,
    SubjectExtentAxis,
    calibrate_subject,
    measure_subject_extent,
    resolve_declared_magnitude,
    resolve_player_magnitude,
)
from stage_gen.components.sideview_actor.motion_geometry import (
    dialogue_atlas_grid,
    runtime_mirrors_source,
)
from stage_gen.media import measure_alpha_ground_contact
from stage_gen.media.sprite_sheets import split_atlas_columns
from stage_gen.recipes.manifest_blocks import (
    ManifestBlock,
    block_table,
    build_blocks,
    present_blocks,
)
from stage_gen.recipes.sideview_platformer.asset_unit import (
    admit_rank_ladder,
    resolve_rank_magnitude,
)
from stage_gen.recipes.sideview_platformer.motion_contract import (
    motion_atlas_geometry,
    motion_source_facing,
)
from stage_gen.recipes.sideview_platformer.package_types import (
    PREPARED_RUNTIME_MANIFEST_KIND,
    PREPARED_RUNTIME_MANIFEST_SCHEMA_VERSION,
)
from stage_gen.recipes.sideview_platformer.terrain_design import terrain_artifact_path
from stage_gen.recipes.sideview_platformer.validation import ResolvedGamePackage

#: The render projection the scrolling-preview consumer draws at. This is the only place
#: the asset unit meets pixels, and a consumer multiplies through it exactly once.
RUNTIME_TILE_PX = 64

#: The state the asset unit measures. Every other state reaches its scale through a rebase
#: multiplier, so measuring a second one would create a second authority for one quantity.
_BASELINE_STATE = "idle"
#:
#: ``asset`` names media this package publishes as its own content. Every one of them is bound
#: by name somewhere in the manifest, so a consumer enumerating what the game is made of must
#: account for all of them. ``provenance`` names the records and judged plates a run ships so it
#: can be re-derived and audited; their readable values are already inlined in the manifest, so
#: nothing has to fetch them to present the game.
#:
#: The role is declared where an artifact is published and never inferred downstream. Neither a
#: filename, a directory, nor a media type can carry it: a judged comparison plate is a PNG under
#: `content/` exactly like the artwork it was composed from. Before this was declared, every
#: consumer that enumerated the closure had to guess, and each new provenance artifact silently
#: broke the ones that guessed wrong.
RuntimeArtifactRole = Literal["asset", "provenance"]
RUNTIME_ARTIFACT_ROLES: tuple[RuntimeArtifactRole, ...] = ("asset", "provenance")


class PreparedManifestError(ValueError):
    """Reject an incomplete, ambiguous, or unsafe integration input."""


PreparedManifestDisposition = Literal["created", "unchanged", "replaced"]


@dataclass(frozen=True, slots=True)
class PreparedManifestResult:
    manifest: dict[str, object]
    output_dir: Path
    artifact_count: int
    #: What publishing did to ``output_dir``. ``unchanged`` means an existing run already held
    #: exactly these bytes, so nothing was written.
    disposition: PreparedManifestDisposition = "created"
    #: Digest of the manifest a replacement destroyed. Recorded because a run tag is cited by
    #: digest elsewhere, so a citation invalidated by a replacement stays traceable.
    replaced_manifest_sha256: str | None = None


def assemble_prepared_runtime(
    package: ResolvedGamePackage,
    *,
    artifact_roots: Sequence[Path],
    output_dir: Path,
    replace_output: bool = False,
) -> PreparedManifestResult:
    """Publish the exact runtime closure without invoking a provider.

    Roots are searched in caller order. This lets a narrow corrective run override an older
    complete run while every selected byte remains digest-bound in the emitted manifest.

    A published run tag names exactly one byte set, so publishing stays immutable by default.
    Because integration is deterministic, republishing the identical closure over an existing tag
    is a no-op rather than an error. Replacing a tag with *different* bytes changes what that tag
    means to everything that cites it, so it requires ``replace_output``.
    """

    if not artifact_roots:
        raise PreparedManifestError("integration requires at least one artifact root")
    roots = tuple(_validated_root(path) for path in artifact_roots)
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
        disposition, replaced_sha256 = _install_prepared_runtime(
            staging, output_dir, replace_output=replace_output
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return PreparedManifestResult(
        manifest=staged.manifest,
        output_dir=output_dir,
        artifact_count=staged.artifact_count,
        disposition=disposition,
        replaced_manifest_sha256=replaced_sha256,
    )


def _install_prepared_runtime(
    staging: Path,
    output_dir: Path,
    *,
    replace_output: bool,
) -> tuple[PreparedManifestDisposition, str | None]:
    """Move one fully assembled run into place, or prove the published run already matches it.

    The staging directory is consumed either way: renamed into place, or removed once an existing
    run is shown to hold the same bytes. A replacement retires the previous run to a sibling
    temporary directory first, so a failed install can put it back.
    """

    if not output_dir.exists():
        staging.rename(output_dir)
        return "created", None
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise PreparedManifestError(f"integration output is not a directory: {output_dir}")
    if _published_runs_match(staging, output_dir):
        shutil.rmtree(staging, ignore_errors=True)
        return "unchanged", None
    if not replace_output:
        raise PreparedManifestError(
            f"integration output already exists with different content: {output_dir}"
        )
    replaced_sha256 = _file_sha256(output_dir / "manifest.json")
    retired = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.retired-", dir=output_dir.parent))
    retired_output = retired / output_dir.name
    output_dir.rename(retired_output)
    try:
        staging.rename(output_dir)
    except BaseException:
        retired_output.rename(output_dir)
        raise
    finally:
        shutil.rmtree(retired, ignore_errors=True)
    return "replaced", replaced_sha256


def _published_runs_match(left: Path, right: Path) -> bool:
    """Compare two published runs by relative path and content digest."""

    left_digests = _published_run_digests(left)
    return left_digests is not None and left_digests == _published_run_digests(right)


def _published_run_digests(root: Path) -> dict[str, str] | None:
    """Digest every regular file under ``root``, or return ``None`` if anything else is present.

    A tree carrying a symlink or a device node is never treated as equal to a freshly assembled
    run, so an unexpected published directory is replaced explicitly rather than silently kept.
    """

    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            return None
        if path.is_dir():
            continue
        if not path.is_file():
            return None
        digests[path.relative_to(root).as_posix()] = _file_sha256(path)
    return digests


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(slots=True)
class _Publication:
    """Where artifacts come from, where they go, and the records the manifest binds them by."""

    package: ResolvedGamePackage
    roots: tuple[Path, ...]
    output_dir: Path
    artifacts: dict[str, dict[str, object]] = field(default_factory=dict)

    @property
    def scale(self) -> PreparedScale:
        return self.package.game.scale

    def _publish(self, relative_path: str, role: RuntimeArtifactRole) -> dict[str, object]:
        existing = self.artifacts.get(relative_path)
        if existing is not None:
            if existing["role"] != role:
                raise PreparedManifestError(
                    f"runtime artifact is published as both {existing['role']} and {role}: "
                    f"{relative_path}"
                )
            return existing
        source = _find_artifact(self.roots, relative_path)
        target = _safe_output_path(self.output_dir, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Integration restores into the directory it publishes from; the same file is
        # not copied onto itself.
        if not (target.exists() and target.resolve() == source):
            shutil.copyfile(source, target)
        record = _artifact_record(target, relative_path, role)
        self.artifacts[relative_path] = record
        return record

    def publish(self, relative_path: str) -> dict[str, object]:
        """Publish one asset and return the record the manifest binds it by."""

        return self._publish(relative_path, "asset")

    def publish_provenance(self, relative_path: str) -> None:
        """Publish one record or judged plate the run ships so it can be re-derived.

        Nothing is returned, because provenance is never bound as an asset. It reaches a
        consumer through the closure alone, where its declared role says not to present it.
        """

        self._publish(relative_path, "provenance")

    def read(self, relative_path: str) -> bytes:
        """The bytes of a published path, exactly as a consumer will load them."""

        return _safe_output_path(self.output_dir, relative_path).read_bytes()

    def find(self, relative_path: str) -> Path:
        return _find_artifact(self.roots, relative_path)

    def records(self) -> list[dict[str, object]]:
        return [self.artifacts[path] for path in sorted(self.artifacts)]


def _presentation_block(pub: _Publication) -> object:
    return pub.package.platformer.presentation.model_dump(mode="json")


def _scale_block(pub: _Publication) -> object:
    return pub.scale.model_dump(mode="json")


def _layer_manifest(pub: _Publication, map_id: str, layer: PreparedMapLayer) -> dict[str, object]:
    layer_id = layer.layer_id
    relative_path = f"maps/{map_id}/layers/{layer_id}.png"
    asset = pub.publish(relative_path)
    validation_path = f"maps/{map_id}/layers/{layer_id}.validation.json"
    pub.publish_provenance(validation_path)
    validation = json.loads(pub.read(validation_path))
    placement = validation.get("placement")
    if not isinstance(placement, dict):
        raise PreparedManifestError(
            f"map layer {map_id}/{layer_id} has no resolved vertical placement"
        )
    for field_name in ("vertical_anchor", "vertical_offset", "source_height", "trimmed_height"):
        if field_name not in placement:
            raise PreparedManifestError(
                f"map layer {map_id}/{layer_id} placement is missing {field_name}"
            )
    if placement["vertical_anchor"] != layer.vertical_anchor:
        raise PreparedManifestError(
            f"map layer {map_id}/{layer_id} placement does not match its authored anchor"
        )
    return {
        "layer_id": layer_id,
        "plane": layer.plane,
        "order": layer.order,
        "parallax": layer.parallax,
        "alpha_mode": layer.alpha_mode,
        # Resolved placement: the runtime applies it and never re-measures the raster.
        "placement": {
            "vertical_anchor": placement["vertical_anchor"],
            "vertical_offset": float(placement["vertical_offset"]),
            "vertical_offset_source": placement.get("vertical_offset_source", "measured"),
            # The painted frame stays the scale datum after empty rows are trimmed away.
            "source_height": int(placement["source_height"]),
            "trimmed_height": int(placement["trimmed_height"]),
            "trimmed_top": int(placement["trimmed_top"]),
        },
        "presentation": layer.presentation.model_dump(mode="json"),
        "asset": asset,
    }


def _climbable_manifest(
    pub: _Publication, game_map: PreparedGameMap, terrain: PreparedMapTerrain
) -> dict[str, object]:
    climbable = game_map.climbable
    assert climbable is not None
    # Atlas cell index is roster index: ladders left to right, then ropes. The binding is
    # positional, which is what lets the runtime address a variant without measuring it.
    #
    # Each variant's trimmed rectangle inside the repacked sheet travels with it, so the
    # consumer crops and sizes exactly rather than re-deriving geometry from alpha. A rope
    # is several times narrower than a ladder; without this the runtime has no way to draw
    # each at its own width.
    climbable_validation_path = f"maps/{game_map.map_id}/climbable.validation.json"
    pub.publish_provenance(climbable_validation_path)
    climbable_validation = json.loads(pub.read(climbable_validation_path))
    cells = climbable_validation.get("placements")
    if not isinstance(cells, list) or len(cells) != len(climbable.variants):
        raise PreparedManifestError(
            "climbable validation does not describe one cell per declared variant"
        )
    variants = []
    for index, entry in enumerate(climbable.variants):
        cell = cells[index]
        if not isinstance(cell, dict):
            raise PreparedManifestError("climbable validation cell is invalid")
        box = cell.get("target_bbox")
        if not isinstance(box, list) or len(box) != 4:
            raise PreparedManifestError("climbable validation cell geometry is invalid")
        left, top, right, bottom = (int(value) for value in box)
        if right <= left or bottom <= top:
            raise PreparedManifestError("climbable validation cell is empty")
        variants.append(
            {
                "variant_id": entry.variant_id,
                "role": climbable.role_of(entry.variant_id),
                "cell_index": index,
                "cell": {
                    "x": left,
                    "y": top,
                    "width": right - left,
                    "height": bottom - top,
                },
            }
        )
    return {
        "mode": climbable.mode,
        "index_order": "left_to_right",
        "variants": variants,
        "placements": [entry.model_dump(mode="json") for entry in terrain.climbable_placements],
        "asset": pub.publish(f"maps/{game_map.map_id}/climbable.png"),
    }


def _maps_block(pub: _Publication) -> object:
    package = pub.package
    map_uses = {entry.map_id: entry for entry in package.gameplay.map_uses}
    maps: list[dict[str, object]] = []
    for game_map in package.maps:
        map_use = map_uses[game_map.map_id]
        # Generated geometry, checked against what the map asked for before anything is written.
        terrain = load_prepared_map_terrain_bytes(
            pub.find(terrain_artifact_path(game_map.map_id)).read_bytes()
        )
        validate_generated_terrain(game_map, terrain)
        # The record the occupancy below was read from travels with the run so a consumer can
        # re-derive the world instead of trusting the inlined copy. Nothing fetches it to play:
        # it is provenance, not an asset.
        pub.publish_provenance(terrain_artifact_path(game_map.map_id))
        map_manifest: dict[str, object] = {
            "map_id": game_map.map_id,
            "revision": game_map.revision,
            "display_name": game_map.display_name,
            "view": game_map.view.model_dump(mode="json"),
            # Published so the consumer obeys the declaration instead of hardcoding it. A runtime
            # that cannot honour a declared axis must reject the map rather than ignore the field.
            "camera": game_map.camera.model_dump(mode="json"),
            "continuity": game_map.continuity.model_dump(mode="json"),
            "role": map_use.role,
            "hostile_population_enabled": map_use.hostile_population_enabled,
            "track_ids": list(map_use.track_ids),
            "layers": [_layer_manifest(pub, game_map.map_id, layer) for layer in game_map.layers],
            "ground": _ground_manifest(game_map, terrain, pub.publish),
        }
        if game_map.climbable is not None:
            map_manifest["climbable"] = _climbable_manifest(pub, game_map, terrain)
        if game_map.portal is not None:
            map_manifest["portal"] = {
                "mode": game_map.portal.mode,
                "endpoints": [entry.model_dump(mode="json") for entry in game_map.portal.endpoints],
                "asset": pub.publish(f"maps/{game_map.map_id}/portal.png"),
            }
        maps.append(map_manifest)
    return maps


def _player_block(pub: _Publication) -> object:
    player = pub.package.player.players[0]
    scale = pub.scale
    return {
        "player_id": player.player_id,
        "display_name": player.display_name,
        "body_kind": player.body_kind,
        "concept": pub.publish(f"content/players/{player.player_id}/concept.png"),
        "states": {
            motion.state: _motion_binding(
                pub.publish(f"content/players/{player.player_id}/states/{motion.state}.png"),
                motion,
                actor_kind="player",
            )
            for motion in player.motions
        },
        "dialogue": _dialogue_binding(
            pub.publish(f"content/players/{player.player_id}/dialogue.png"),
            player.dialogue_art.expressions,
        ),
        "calibration": {
            # The magnitude the unit is defined by, measured on the baseline frame alone, and the
            # per-state ratios that bring every other atlas onto it. The pair is deliberate: the
            # first is authored input and its measurement, the second is derived output.
            **_subject_calibration(
                pub.output_dir,
                f"content/players/{player.player_id}/states/{_BASELINE_STATE}.png",
                resolve_player_magnitude(None),
                scale,
                subject=player.player_id,
                columns=motion_atlas_geometry("player", _BASELINE_STATE).columns,
            ),
            **_motion_rebase_binding(
                pub.output_dir,
                pub.publish_provenance,
                player.player_id,
                [motion.state for motion in player.motions],
            ),
        },
    }


def _mobs_block(pub: _Publication) -> object:
    scale = pub.scale
    return [
        {
            "mob_id": mob.mob_id,
            "display_name": mob.display_name,
            "body_kind": mob.body_kind,
            "rank": mob.rank,
            "aggression": mob.aggression,
            "concept": pub.publish(f"content/mobs/{mob.mob_id}/concept.png"),
            "states": {
                motion.state: _motion_binding(
                    pub.publish(f"content/mobs/{mob.mob_id}/states/{motion.state}.png"),
                    motion,
                    actor_kind="mob",
                )
                for motion in mob.motions
            },
            "calibration": _subject_calibration(
                pub.output_dir,
                f"content/mobs/{mob.mob_id}/states/{mob.motions[0].state}.png",
                resolve_rank_magnitude(scale, mob.rank),
                scale,
                subject=mob.mob_id,
                columns=motion_atlas_geometry("mob", mob.motions[0].state).columns,
            ),
        }
        for mob in pub.package.mobs.mobs
    ]


def _npcs_block(pub: _Publication) -> object:
    package = pub.package
    scale = pub.scale
    return [
        {
            "npc_id": npc.npc_id,
            "display_name": npc.display_name,
            "role": npc.role,
            "body_kind": npc.body_kind,
            "world": _motion_binding(
                pub.publish(f"content/npcs/{npc.npc_id}/world.png"),
                npc.motions[0],
                actor_kind="npc",
                npc_world_orientation=package.npcs.world_orientation,
            ),
            "dialogue": _dialogue_binding(
                pub.publish(f"content/npcs/{npc.npc_id}/dialogue.png"),
                npc.dialogue_expressions,
            ),
            "calibration": _subject_calibration(
                pub.output_dir,
                f"content/npcs/{npc.npc_id}/world.png",
                resolve_declared_magnitude(scale, npc.height_units, subject=npc.npc_id),
                scale,
                subject=npc.npc_id,
                columns=motion_atlas_geometry("npc", npc.motions[0].state).columns,
            ),
        }
        for npc in package.npcs.npcs
    ]


def _prop_manifest(pub: _Publication, prop: PropContent) -> dict[str, object]:
    relative_path = f"content/props/{prop.prop_id}.png"
    asset = pub.publish(relative_path)
    contact = measure_alpha_ground_contact(pub.read(relative_path))
    normalized = contact["ground_contact_y_normalized"]
    if not isinstance(normalized, (int, float)):
        raise PreparedManifestError("prop ground contact measurement is invalid")
    return {
        "prop_id": prop.prop_id,
        "display_name": prop.display_name,
        "ground_contact_y_normalized": float(normalized),
        "calibration": _subject_calibration(
            pub.output_dir,
            relative_path,
            resolve_declared_magnitude(pub.scale, prop.height_units, subject=prop.prop_id),
            pub.scale,
            subject=prop.prop_id,
        ),
        "asset": asset,
    }


def _props_block(pub: _Publication) -> object:
    return [_prop_manifest(pub, prop) for prop in pub.package.props.props]


def _items_block(pub: _Publication) -> object:
    scale = pub.scale
    return [
        {
            "item_id": item.item_id,
            "display_name": item.display_name,
            "item_kind": item.item_kind,
            # Published before it is measured: the calibration describes the bytes a consumer
            # will load, not the bytes the run happened to produce.
            "asset": pub.publish(f"content/items/{item.item_id}.png"),
            "calibration": _subject_calibration(
                pub.output_dir,
                f"content/items/{item.item_id}.png",
                resolve_declared_magnitude(scale, item.height_units, subject=item.item_id),
                scale,
                subject=item.item_id,
            ),
        }
        for item in pub.package.items.items
    ]


def _projectiles_block(pub: _Publication) -> object:
    package = pub.package
    scale = pub.scale
    return [
        {
            "projectile_id": entry.projectile_id,
            "display_name": entry.display_name,
            "silhouette": entry.silhouette,
            "flight": entry.flight,
            "impact": entry.impact,
            "asset": pub.publish(f"content/projectiles/{entry.projectile_id}.png"),
            # Measured across, not up: the subject is drawn lying along its own travel axis, so
            # its width is the dimension `length_units` declares. The record names the axis.
            "calibration": _subject_calibration(
                pub.output_dir,
                f"content/projectiles/{entry.projectile_id}.png",
                resolve_declared_magnitude(scale, entry.length_units, subject=entry.projectile_id),
                scale,
                subject=entry.projectile_id,
                extent_axis="width",
            ),
        }
        for entry in ([] if package.projectiles is None else package.projectiles.projectiles)
    ]


def _ui_block(pub: _Publication) -> object:
    try:
        atlas_block = ui_atlas_manifest_block(
            read_validation=pub.read,
            publish=pub.publish,
            publish_provenance=pub.publish_provenance,
            roles=document_roles(pub.package.ui),
        )
    except ValueError as error:
        raise PreparedManifestError(str(error)) from error
    return {
        "inventory_panel": {
            **inventory_panel_layout_contract(),
            "asset": pub.publish("ui/inventory_panel.png"),
        },
        **atlas_block,
    }


def _soundtrack_block(pub: _Publication) -> object:
    package = pub.package
    return {
        "playback": package.soundtrack.playback.model_dump(mode="json"),
        "tracks": [
            {
                "track_id": track.track_id,
                "display_name": track.display_name,
                "instrumental": track.generation.instrumental,
                "seamless_loop": track.generation.seamless_loop,
                "target_duration_seconds": track.generation.target_duration_seconds,
                "asset": pub.publish(f"soundtrack/{track.track_id}.mp3"),
            }
            for track in package.soundtrack.tracks
        ],
    }


def _gameplay_block(pub: _Publication) -> object:
    # The score and the timers are their own blocks, parsed by their own families.
    return pub.package.gameplay.model_dump(mode="json", exclude={"score", "timers"})


def _score_block(pub: _Publication) -> object:
    score = pub.package.gameplay.score
    return None if score is None else score.model_dump(mode="json")


def _timers_block(pub: _Publication) -> object:
    timers = pub.package.gameplay.timers
    return None if timers is None else timers.model_dump(mode="json")


def _scenarios_block(pub: _Publication) -> object:
    # The compiled program, not the authored declarations: the consumer walks a
    # graph, and re-deriving it in TypeScript would be a second compiler that
    # could disagree with the proof.
    return [
        scenario.program.model_dump(mode="json", exclude_none=True)
        for scenario in pub.package.scenarios
    ]


def _closure_block(pub: _Publication) -> object:
    records = pub.records()
    return {
        "artifact_count": len(records),
        "artifacts_sha256": _canonical_sha256(records),
        "artifacts": records,
    }


#: The manifest's blocks, in publication order, each at its own version. The closure is
#: last because it records what every earlier block published. A block whose shape moves
#: bumps its version here and the parser that reads it; nothing else moves.
PLATFORMER_MANIFEST_BLOCKS: tuple[ManifestBlock[_Publication], ...] = (
    ManifestBlock("presentation", "platformer-presentation-block-v1", _presentation_block),
    ManifestBlock("scale", "platformer-scale-block-v1", _scale_block),
    ManifestBlock("maps", "platformer-maps-block-v1", _maps_block),
    ManifestBlock("player", "platformer-player-block-v1", _player_block),
    ManifestBlock("mobs", "platformer-mobs-block-v1", _mobs_block),
    ManifestBlock("npcs", "platformer-npcs-block-v1", _npcs_block),
    ManifestBlock("props", "platformer-props-block-v1", _props_block),
    ManifestBlock("items", "platformer-items-block-v1", _items_block),
    ManifestBlock("projectiles", "platformer-projectiles-block-v1", _projectiles_block),
    ManifestBlock("ui", "platformer-ui-block-v1", _ui_block),
    ManifestBlock("soundtrack", "platformer-soundtrack-block-v1", _soundtrack_block),
    ManifestBlock("gameplay", "platformer-gameplay-block-v1", _gameplay_block),
    # Optional: published only when authored, so a game without them carries no entry.
    ManifestBlock("score", "platformer-score-block-v1", _score_block),
    ManifestBlock("timers", "platformer-timers-block-v1", _timers_block),
    ManifestBlock("scenarios", "platformer-scenarios-block-v1", _scenarios_block),
    ManifestBlock("closure", "platformer-closure-block-v1", _closure_block),
)
PLATFORMER_MANIFEST_BLOCK_VERSIONS: dict[str, str] = block_table(PLATFORMER_MANIFEST_BLOCKS)


def _assemble_prepared_runtime(
    package: ResolvedGamePackage,
    *,
    artifact_roots: Sequence[Path],
    output_dir: Path,
) -> PreparedManifestResult:
    pub = _Publication(package, tuple(artifact_roots), output_dir)
    # Silhouette height carries threat, so the ladder is admitted before anything reads it.
    admit_rank_ladder(pub.scale, {mob.mob_id: mob.rank for mob in package.mobs.mobs})
    # An optional block a package did not author is built as None: absent from the table
    # and absent from the document, so a consumer reads its absence as absence.
    blocks = build_blocks(PLATFORMER_MANIFEST_BLOCKS, pub)
    manifest: dict[str, object] = {
        "schema_version": PREPARED_RUNTIME_MANIFEST_SCHEMA_VERSION,
        "kind": PREPARED_RUNTIME_MANIFEST_KIND,
        "blocks": present_blocks(PLATFORMER_MANIFEST_BLOCK_VERSIONS, blocks),
        "game_id": package.game.game_id,
        "revision": package.game.revision,
        "display_name": package.game.display_name,
        "package_sha256": package.package_sha256,
        # C-R6: the root publishes only what a consumer reads. The universe text, the style
        # and proportion tables and the canonical game digest left in v12; nothing read them.
        "entry_map_id": package.gameplay.entry_map_id,
        "entry_spawn_id": package.gameplay.entry_spawn_id,
        **{key: value for key, value in blocks.items() if value is not None},
    }
    _validate_closure_roles(manifest, pub.artifacts)
    atomic_write_json(output_dir / "manifest.json", manifest)
    return PreparedManifestResult(
        manifest=manifest,
        output_dir=output_dir,
        artifact_count=len(pub.artifacts),
    )


def _motion_binding(
    artifact: dict[str, object],
    motion: MotionPresentation,
    *,
    actor_kind: Literal["player", "mob", "npc"],
    npc_world_orientation: Literal["front"] | None = None,
) -> dict[str, object]:
    geometry = motion_atlas_geometry(actor_kind, motion.state)
    invalid = [
        index for index in motion.canonical_frame_indices if index >= geometry.required_cells
    ]
    if invalid:
        raise PreparedManifestError(
            f"{actor_kind} motion {motion.state} selects unavailable canonical frames: {invalid}"
        )
    source_facing = motion_source_facing(
        actor_kind,
        motion.state,
        npc_world_orientation=npc_world_orientation,
    )
    playback: dict[str, object] = {
        "mode": motion.playback_mode,
        "canonical_frame_indices": list(motion.canonical_frame_indices),
    }
    if motion.frames_per_second is not None:
        playback["frames_per_second"] = motion.frames_per_second
    return {
        "source_facing": source_facing,
        "runtime_mirror": runtime_mirrors_source(source_facing),
        "columns": geometry.columns,
        "rows": geometry.rows,
        "source_frame_count": geometry.required_cells,
        "anchor": motion.anchor,
        "playback": playback,
        "asset": artifact,
    }


def _subject_calibration(
    output_dir: Path,
    relative_path: str,
    magnitude: ResolvedMagnitude,
    scale: PreparedScale,
    *,
    subject: str,
    columns: int = 1,
    extent_axis: SubjectExtentAxis = "height",
) -> dict[str, object]:
    """Measure one published subject and republish what its artwork spent on a unit.

    The manifest re-derives this from the published bytes rather than reading a declaration and
    trusting it: a record a consumer cannot reproduce from the artifact is a record that can go
    stale without any signal.
    """

    data = _safe_output_path(output_dir, relative_path).read_bytes()
    if columns > 1:
        data = split_atlas_columns(data, columns)[0]
    extent = measure_subject_extent(data, subject=subject, axis=extent_axis)
    calibration = calibrate_subject(
        magnitude=magnitude,
        subject_extent_px=extent,
        measured_sha256=hashlib.sha256(data).hexdigest(),
        scale=scale,
        tile_px=RUNTIME_TILE_PX,
        subject=subject,
        extent_axis=extent_axis,
    )
    return calibration.as_record()


def _motion_rebase_binding(
    output_dir: Path,
    publish_provenance: Callable[[str], None],
    player_id: str,
    states: Sequence[str],
) -> dict[str, object]:
    """Republish the judged rebase, re-derived from the run artifact rather than trusted.

    A per-state multiplier is a property of the artwork and changes whenever the artwork does,
    so it is never authored by hand and never copied forward: the manifest reads the record the
    judging stage wrote, checks it still covers exactly the states this actor publishes, and
    fails rather than shipping a stale reading.
    """

    relative_path = f"content/players/{player_id}/motion-rebase.json"
    publish_provenance(relative_path)
    publish_provenance(f"content/players/{player_id}/motion-rebase-first-pass.json")
    publish_provenance(f"content/players/{player_id}/motion-rebase-plate.png")
    publish_provenance(f"content/players/{player_id}/motion-rebase-verification-plate.png")
    record = json.loads(_safe_output_path(output_dir, relative_path).read_bytes())
    if not isinstance(record, dict):
        raise PreparedManifestError(f"player {player_id} motion rebase record is not an object")
    baseline_state = record.get("baseline_state")
    multipliers = record.get("states")
    plate_sha256 = record.get("plate_sha256")
    verification_plate_sha256 = record.get("verification_plate_sha256")
    if not isinstance(baseline_state, str) or not isinstance(multipliers, dict):
        raise PreparedManifestError(f"player {player_id} motion rebase record is incomplete")
    if not isinstance(plate_sha256, str) or len(plate_sha256) != 64:
        raise PreparedManifestError(f"player {player_id} motion rebase record has no plate digest")
    if not isinstance(verification_plate_sha256, str) or len(verification_plate_sha256) != 64:
        raise PreparedManifestError(
            f"player {player_id} motion rebase record has no verification plate digest; a record "
            "without one predates the closed-loop judgement and is stale"
        )
    if set(multipliers) != set(states):
        raise PreparedManifestError(
            f"player {player_id} motion rebase covers {sorted(multipliers)}, "
            f"but the actor publishes {sorted(states)}"
        )
    resolved: dict[str, float] = {}
    for state, multiplier in multipliers.items():
        if not isinstance(multiplier, (int, float)) or isinstance(multiplier, bool):
            raise PreparedManifestError(
                f"player {player_id} motion rebase multiplier for {state} is not a number"
            )
        resolved[state] = float(multiplier)
    if resolved.get(baseline_state) != 1.0:
        raise PreparedManifestError(
            f"player {player_id} baseline {baseline_state} must rebase to 1.0"
        )
    return {
        "baseline_state": baseline_state,
        "state_rebase": {state: resolved[state] for state in sorted(resolved)},
        "plate_sha256": plate_sha256,
        "verification_plate_sha256": verification_plate_sha256,
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


def _artifact_record(
    path: Path, relative_path: str, role: RuntimeArtifactRole
) -> dict[str, object]:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    record: dict[str, object] = {
        "path": relative_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "media_type": _media_type(suffix),
        # Declared at publication, because nothing about the bytes reveals it.
        "role": role,
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
        # Generated geometry and measurement records are published like any other artifact.
        ".json": "application/json",
    }.get(suffix, "application/octet-stream")


def _is_artifact_record(value: dict[str, object]) -> bool:
    """Recognise a published artifact record wherever it is bound in the manifest."""

    return isinstance(value.get("path"), str) and {"sha256", "bytes", "media_type", "role"} <= set(
        value
    )


def _bound_artifact_paths(manifest: dict[str, object]) -> set[str]:
    """Collect every artifact the manifest binds by name, ignoring the closure listing itself."""

    bound: set[str] = set()
    pending: list[object] = [value for key, value in manifest.items() if key != "closure"]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            if _is_artifact_record(current):
                path = current["path"]
                assert isinstance(path, str)
                bound.add(path)
                continue
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return bound


def _validate_closure_roles(
    manifest: dict[str, object], artifacts: dict[str, dict[str, object]]
) -> None:
    """Prove the published closure and the manifest's bindings say the same thing.

    This is the producer's job, not a consumer's. A consumer handed a valid manifest can present
    every asset without guessing, and the run that would have made it guess fails here instead of
    at somebody's page load.
    """

    bound = _bound_artifact_paths(manifest)
    assets = {path for path, record in artifacts.items() if record["role"] == "asset"}
    unbound = sorted(assets - bound)
    if unbound:
        raise PreparedManifestError(
            "assets are published without a manifest binding: " + ", ".join(unbound)
        )
    unpublished = sorted(bound - assets)
    if unpublished:
        raise PreparedManifestError(
            "the manifest binds artifacts that are not published as assets: "
            + ", ".join(unpublished)
        )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def runtime_artifact_closure(
    package: ResolvedGamePackage,
) -> tuple[tuple[str, RuntimeArtifactRole], ...]:
    """Return the deterministic expected closure, each path beside the role it is published as.

    This is the same declaration the assembler makes, stated once where tests, the execution
    graph, and reporting can all read it. A new artifact has to choose a role here, so growing
    the closure is a decision rather than an accident.
    """

    closure: list[tuple[str, RuntimeArtifactRole]] = []
    for game_map in package.maps:
        for layer in game_map.layers:
            closure.append((f"maps/{game_map.map_id}/layers/{layer.layer_id}.png", "asset"))
            # The measured placement travels with the raster so a published runtime stays usable
            # as an artifact root for a later corrective run.
            closure.append(
                (f"maps/{game_map.map_id}/layers/{layer.layer_id}.validation.json", "provenance")
            )
        if isinstance(game_map.ground, PaintedTerrainGround):
            for segment in painted_terrain_segments(
                game_map.terrain.columns, game_map.terrain.rows
            ):
                closure.append((f"maps/{game_map.map_id}/ground/{segment.segment_id}.png", "asset"))
                # Each segment's own measurements travel with its raster, the way a layer's
                # measured placement travels with its own.
                closure.append(
                    (
                        f"maps/{game_map.map_id}/ground/{segment.segment_id}.validation.json",
                        "provenance",
                    )
                )
            closure.append((f"maps/{game_map.map_id}/ground.validation.json", "provenance"))
        else:
            closure.append((f"maps/{game_map.map_id}/ground.png", "asset"))
        # Generated geometry travels with the run, but the manifest already inlines what a
        # consumer reads from it.
        closure.append((terrain_artifact_path(game_map.map_id), "provenance"))
        if game_map.climbable is not None:
            closure.append((f"maps/{game_map.map_id}/climbable.png", "asset"))
            # The measured per-variant cell geometry travels with the sheet, exactly as a layer's
            # measured placement travels with its raster.
            closure.append((f"maps/{game_map.map_id}/climbable.validation.json", "provenance"))
        if game_map.portal is not None:
            closure.append((f"maps/{game_map.map_id}/portal.png", "asset"))
    for player in package.player.players:
        closure.append((f"content/players/{player.player_id}/concept.png", "asset"))
        closure.extend(
            (f"content/players/{player.player_id}/states/{motion.state}.png", "asset")
            for motion in player.motions
        )
        closure.append((f"content/players/{player.player_id}/dialogue.png", "asset"))
        # The judged rebase and the plates it was read from travel with the run: the multipliers
        # are a property of this artwork, so a consumer must be able to re-derive them rather
        # than trust a value copied forward. Both passes ship - the first-pass record and its
        # plate, then the verification plate the residual was read from.
        closure.append((f"content/players/{player.player_id}/motion-rebase.json", "provenance"))
        closure.append(
            (f"content/players/{player.player_id}/motion-rebase-first-pass.json", "provenance")
        )
        closure.append(
            (f"content/players/{player.player_id}/motion-rebase-plate.png", "provenance")
        )
        closure.append(
            (
                f"content/players/{player.player_id}/motion-rebase-verification-plate.png",
                "provenance",
            )
        )
    for mob in package.mobs.mobs:
        closure.append((f"content/mobs/{mob.mob_id}/concept.png", "asset"))
        closure.extend(
            (f"content/mobs/{mob.mob_id}/states/{motion.state}.png", "asset")
            for motion in mob.motions
        )
    for npc in package.npcs.npcs:
        closure.extend(
            (
                (f"content/npcs/{npc.npc_id}/world.png", "asset"),
                (f"content/npcs/{npc.npc_id}/dialogue.png", "asset"),
            )
        )
    closure.extend((f"content/props/{entry.prop_id}.png", "asset") for entry in package.props.props)
    closure.extend((f"content/items/{entry.item_id}.png", "asset") for entry in package.items.items)
    if package.projectiles is not None:
        closure.extend(
            (f"content/projectiles/{entry.projectile_id}.png", "asset")
            for entry in package.projectiles.projectiles
        )
    closure.append(("ui/inventory_panel.png", "asset"))
    for role in document_roles(package.ui):
        closure.append((f"ui/{role.role}.png", "asset"))
        closure.append((f"ui/{role.role}.validation.json", "provenance"))
    closure.extend(
        (f"soundtrack/{track.track_id}.mp3", "asset") for track in package.soundtrack.tracks
    )
    return tuple(sorted(closure))


def runtime_artifact_paths(package: ResolvedGamePackage) -> tuple[str, ...]:
    """Return the deterministic expected media closure for tests and reporting."""

    return tuple(path for path, _ in runtime_artifact_closure(package))


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
        role = raw_record.get("role")
        if role not in RUNTIME_ARTIFACT_ROLES:
            raise PreparedManifestError(
                f"runtime closure artifact declares no known role: {relative_path}"
            )
        # Every other field is re-derived from the bytes. A role cannot be, so it is read back
        # from the declaration and checked against the vocabulary instead.
        actual = _artifact_record(target, relative_path, role)
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
    "RUNTIME_ARTIFACT_ROLES",
    "RuntimeArtifactRole",
    "PreparedManifestError",
    "PreparedManifestResult",
    "assemble_prepared_runtime",
    "runtime_artifact_closure",
    "runtime_artifact_paths",
    "verify_prepared_runtime",
]


def _ground_manifest(
    game_map: PreparedGameMap,
    terrain: PreparedMapTerrain,
    publish: Callable[[str], dict[str, object]],
) -> dict[str, object]:
    """Project either ground discipline into runtime shape.

    Everything the geometry needs is mode-independent and stays on both arms: occupancy,
    the vertical fit and the walk-surface row are what the consumer computes collision,
    the world box and every layer datum from, and none of them knows how the ground is
    drawn. Only the raster differs -- one repeating atlas, or one bespoke plate per
    segment -- so a consumer that already reads a map keeps reading it.

    Occupancy is inlined so the consumer can read the world without a second fetch, the
    same treatment portal endpoints already get. The generated record itself is in the
    closure as provenance, which is where its digest and lineage live.
    """

    common: dict[str, object] = {
        "mode": game_map.ground.mode,
        "occupancy": list(terrain.occupancy),
        "vertical_fit": game_map.ground.vertical_fit,
        "walk_surface_row": terrain.walk_surface_row,
    }
    if not isinstance(game_map.ground, PaintedTerrainGround):
        return {**common, "asset": publish(f"maps/{game_map.map_id}/ground.png")}
    segments = painted_terrain_segments(game_map.terrain.columns, game_map.terrain.rows)
    return {
        **common,
        "cell_px": PAINTED_TERRAIN_CELL_PX,
        # Published rather than implied. Collision is occupancy and nothing samples the
        # image at any stage, so this band changes no rule of play -- but a consumer
        # drawing a debug overlay needs the number rather than a description of it.
        "silhouette_tolerance": painted_silhouette_tolerance().model_dump(mode="json"),
        # One texture per segment, never one stitched raster: fifty-six columns fit inside a
        # 4096-pixel texture and sixty-five do not, so segment textures keep the runtime
        # bounded by construction rather than by luck.
        "segments": [
            {
                "segment_id": segment.segment_id,
                "start_column": segment.start_column,
                "columns": segment.columns,
                "asset": publish(f"maps/{game_map.map_id}/ground/{segment.segment_id}.png"),
            }
            for segment in segments
        ],
    }

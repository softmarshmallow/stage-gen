"""Game-global soundtrack resolution, generation, and manifest projection.

The authored catalog owns stable track identities.  This recipe turns those
definitions into normalized run artifacts, while maps and other future
consumers remain free to select tracks by ``track_id`` without owning them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol, cast

from stage_gen.components.game_contract import GameContractBinding
from stage_gen.components.game_soundtrack import (
    GAME_SOUNDTRACK_LIBRARY_RESOLUTION_VERSION,
    GameSoundtrack,
    GameSoundtrackBinding,
    ResolvedGameSoundtrack,
    SoundtrackTrack,
    canonical_game_soundtrack_json,
    resolve_game_soundtrack_binding,
)
from stage_gen.contracts import (
    ArtifactProvenance,
    BinaryArtifact,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.media import assert_audio_signature
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.cache import valid_artifact_pair
from stage_gen.reliability import sha256_hex, write_artifact_with_provenance_async

if TYPE_CHECKING:
    from stage_gen.capabilities import CapabilityArtifactResult

SOUNDTRACK_RESOLUTION_VERSION = "scrolling-game-soundtrack-resolution-v1"
SOUNDTRACK_MANIFEST_KIND = "game-soundtrack-manifest-v2"

_RECIPE_COMPONENT = SoftwareIdentity(name="@stage-gen/stage-gen", version="0.0.0")
_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")


class _MusicRuntime(Protocol):
    async def generate_music(
        self,
        *,
        prompt: str,
        output_path: str,
        output_format: str,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult: ...


@dataclass(frozen=True, slots=True)
class CollectedSoundtrack:
    manifest: dict[str, object]
    artifact_paths: tuple[str, ...]
    default_music: dict[str, Any]


def parse_game_soundtrack_binding(value: object) -> dict[str, object]:
    """Validate the shared binding without adding recipe-local aliases."""

    return GameSoundtrackBinding.model_validate(value).model_dump(mode="json")


def assert_soundtrack_matches_game(
    soundtrack_value: object,
    game_value: object,
) -> None:
    """Require the soundtrack and game bindings to name the same game directory."""

    soundtrack = GameSoundtrackBinding.model_validate(soundtrack_value)
    game = GameContractBinding.model_validate(game_value)
    soundtrack_parts = PurePosixPath(soundtrack.ref).parts
    game_parts = PurePosixPath(game.ref).parts
    if soundtrack_parts[:3] != game_parts[:3]:
        raise ValueError("scrolling-preview soundtrack and game must belong to the same game_id")


def soundtrack_contract_path(run_dir: Path, tag: str) -> Path:
    return run_dir / f"soundtrack_{tag}.json"


def soundtrack_track_path(run_dir: Path, tag: str, track_id: str) -> Path:
    return run_dir / f"music_{tag}_{track_id}.mp3"


def soundtrack_track_prompt(game_id: str, track: SoundtrackTrack) -> str:
    """Compile provider-neutral authored intent into one original-music prompt."""

    generation = track.generation
    performance = (
        "Instrumental only; do not include vocals, speech, or spoken words."
        if generation.instrumental
        else "Use vocals only when the creative brief explicitly calls for them."
    )
    ending = (
        "The ending must reconnect naturally to the opening harmony and rhythm, with no fade-out."
        if generation.seamless_loop
        else "Give the track a deliberate musical ending rather than an abrupt cutoff."
    )
    return (
        "Generate an original music track for a 2D game.\n"
        f"Game ID: {game_id}.\n"
        f"Track ID: {track.track_id}.\n"
        f"Creative brief: {track.creative_brief}\n"
        f"Target duration: approximately {generation.target_duration_seconds} seconds.\n"
        f"{performance}\n"
        f"{ending}\n"
        "Do not reference or imitate any artist, performer, franchise, brand, or identifiable "
        "composition. Do not quote an existing melody."
    )


async def resolve_scrolling_soundtrack(context: StageContext) -> tuple[str, ...]:
    """Resolve and persist the exact authored catalog that directs this run."""

    resolved = await _resolve_from_context(context)
    output = soundtrack_contract_path(context.run_dir, context.tag)
    identity = _resolved_identity(resolved)
    force = "soundtrack-resolve" in context.affected_stages
    if valid_artifact_pair(
        output,
        validator=lambda path, sidecar: _valid_resolved_cache(path, sidecar, resolved, identity),
        force=force,
    ):
        return (str(output), f"{output}.meta.json")
    sidecar = await write_artifact_with_provenance_async(
        output,
        BinaryArtifact(data=resolved.canonical_bytes, media_type="application/json"),
        ProvenanceInput(
            provider="local",
            model=SOUNDTRACK_RESOLUTION_VERSION,
            prompt="resolve authored game soundtrack",
            refs=[resolved.binding.ref],
            inputs=[resolved.source_provenance],
            params={"stage": "soundtrack-resolve", "soundtrack": identity},
            validation={
                "source_digest_verified": True,
                "canonical_digest_verified": True,
                "game_id_verified": True,
                "track_ids_unique": True,
                "playback_policy_verified": True,
            },
            component=_RECIPE_COMPONENT,
            tool=_TOOL,
            attempts=1,
        ),
    )
    return (str(output), str(sidecar))


async def generate_scrolling_soundtrack(context: StageContext) -> tuple[str, ...]:
    """Generate or reuse every declared track; partial catalogs never reach the manifest."""

    resolved = await _read_resolved_soundtrack(context)
    runtime = _music_runtime(context)
    force = "soundtrack-generate" in context.affected_stages
    artifacts: list[str] = []
    for track in resolved.soundtrack.tracks:
        output = soundtrack_track_path(context.run_dir, context.tag, track.track_id)
        prompt = soundtrack_track_prompt(resolved.soundtrack.game_id, track)
        metadata = _track_metadata(resolved, track)
        if not valid_artifact_pair(
            output,
            validator=partial(
                _valid_track_artifact,
                prompt=prompt,
                model=context.config.music_model,
                metadata=metadata,
            ),
            force=force,
        ):
            await runtime.generate_music(
                prompt=prompt,
                output_path=str(output),
                output_format="mp3",
                metadata=metadata,
            )
        if not valid_artifact_pair(
            output,
            validator=partial(
                _valid_track_artifact,
                prompt=prompt,
                model=context.config.music_model,
                metadata=metadata,
            ),
            force=False,
        ):
            raise ValueError(f"generated soundtrack track is missing or invalid: {track.track_id}")
        artifacts.extend((str(output), f"{output}.meta.json"))
    return tuple(artifacts)


def collect_scrolling_soundtrack(run_dir: Path, tag: str) -> CollectedSoundtrack:
    """Build a strict manifest block from a complete resolved soundtrack."""

    contract_path = soundtrack_contract_path(run_dir, tag)
    if not valid_artifact_pair(
        contract_path,
        validator=lambda path, sidecar: _valid_collected_contract(path, sidecar),
        force=False,
    ):
        raise ValueError("resolved soundtrack artifact pair is missing, stale, or invalid")
    contract_bytes = contract_path.read_bytes()
    soundtrack = GameSoundtrack.model_validate_json(contract_bytes)
    contract_sidecar = ArtifactProvenance.model_validate_json(
        Path(f"{contract_path}.meta.json").read_bytes()
    )
    identity = cast(dict[str, object], contract_sidecar.params["soundtrack"])
    tracks: list[dict[str, object]] = []
    artifact_paths = [contract_path.name, f"{contract_path.name}.meta.json"]
    for track in soundtrack.tracks:
        output = soundtrack_track_path(run_dir, tag, track.track_id)
        expected_prompt = soundtrack_track_prompt(soundtrack.game_id, track)
        metadata = _track_metadata_from_identity(identity, track)
        if not valid_artifact_pair(
            output,
            validator=partial(
                _valid_track_artifact,
                prompt=expected_prompt,
                model=None,
                metadata=metadata,
            ),
            force=False,
        ):
            raise ValueError(
                f"soundtrack track artifact pair is missing or invalid: {track.track_id}"
            )
        raw = output.read_bytes()
        provenance = ArtifactProvenance.model_validate_json(
            Path(f"{output}.meta.json").read_bytes()
        )
        if provenance.artifact is None or provenance.rights is None:
            raise ValueError(f"soundtrack track provenance is incomplete: {track.track_id}")
        if provenance.rights.status == "restricted":
            raise ValueError(f"soundtrack track is restricted: {track.track_id}")
        postprocess = provenance.validation.get("postprocess")
        duration = postprocess.get("duration_seconds") if isinstance(postprocess, Mapping) else None
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
            raise ValueError(f"soundtrack track duration is missing: {track.track_id}")
        tracks.append(
            {
                "track_id": track.track_id,
                "display_name": track.display_name,
                "path": output.name,
                "provenance_path": f"{output.name}.meta.json",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "media_type": provenance.artifact.media_type,
                "rights_status": provenance.rights.status,
                "generation_capability": "generate-music",
                "seamless_loop": track.generation.seamless_loop,
                "target_duration_seconds": track.generation.target_duration_seconds,
                "duration_seconds": duration,
            }
        )
        artifact_paths.extend((output.name, f"{output.name}.meta.json"))
    first = tracks[0]
    return CollectedSoundtrack(
        manifest={
            "schema_version": 2,
            "kind": SOUNDTRACK_MANIFEST_KIND,
            "game_id": soundtrack.game_id,
            "revision": soundtrack.revision,
            "source": {
                "path": contract_path.name,
                "provenance_path": f"{contract_path.name}.meta.json",
                "source_sha256": identity["source_sha256"],
                "canonical_sha256": identity["canonical_sha256"],
            },
            "playback": soundtrack.playback.model_dump(mode="json"),
            "tracks": tracks,
        },
        artifact_paths=tuple(artifact_paths),
        default_music={
            "path": str(first["path"]),
            "provenance_path": str(first["provenance_path"]),
            "source": "per-run",
            "rights_status": str(first["rights_status"]),
        },
    )


async def _resolve_from_context(context: StageContext) -> ResolvedGameSoundtrack:
    if "soundtrack" not in context.input:
        raise ValueError("soundtrack-resolve requires a game soundtrack binding")
    if "game" not in context.input:
        raise ValueError("a game soundtrack requires a game contract binding")
    assert_soundtrack_matches_game(context.input["soundtrack"], context.input["game"])
    root = context.config.game_library_root
    if root is None:
        raise ValueError("soundtrack-directed scrolling generation requires game_library_root")
    resolved = await asyncio.to_thread(
        resolve_game_soundtrack_binding,
        context.input["soundtrack"],
        game_library_root=root,
    )
    game = GameContractBinding.model_validate(context.input["game"])
    if resolved.soundtrack.game_id != PurePosixPath(game.ref).parts[2]:
        raise ValueError("resolved soundtrack game_id does not match the bound game")
    return resolved


async def _read_resolved_soundtrack(context: StageContext) -> ResolvedGameSoundtrack:
    resolved = await _resolve_from_context(context)
    path = soundtrack_contract_path(context.run_dir, context.tag)
    identity = _resolved_identity(resolved)
    if not valid_artifact_pair(
        path,
        validator=lambda artifact, sidecar: _valid_resolved_cache(
            artifact, sidecar, resolved, identity
        ),
        force=False,
    ):
        raise ValueError("resolved soundtrack is missing, stale, or invalid")
    return resolved


def _resolved_identity(resolved: ResolvedGameSoundtrack) -> dict[str, object]:
    return {
        **resolved.identity(),
        "recipe_resolution_version": SOUNDTRACK_RESOLUTION_VERSION,
        "artifact_ref": f"sha256:{resolved.canonical_sha256}",
        "artifact_sha256": resolved.canonical_sha256,
        "artifact_bytes": len(resolved.canonical_bytes),
    }


def _valid_resolved_cache(
    path: Path,
    sidecar: dict[str, Any],
    resolved: ResolvedGameSoundtrack,
    identity: Mapping[str, object],
) -> bool:
    try:
        if path.read_bytes() != resolved.canonical_bytes:
            return False
        soundtrack = GameSoundtrack.model_validate_json(resolved.canonical_bytes)
        if canonical_game_soundtrack_json(soundtrack) != resolved.canonical_bytes:
            return False
    except (OSError, ValueError):
        return False
    params = sidecar.get("params")
    return (
        sidecar.get("provider") == "local"
        and sidecar.get("model") == SOUNDTRACK_RESOLUTION_VERSION
        and sidecar.get("refs") == [resolved.binding.ref]
        and isinstance(params, Mapping)
        and params.get("stage") == "soundtrack-resolve"
        and params.get("soundtrack") == dict(identity)
    )


def _valid_collected_contract(path: Path, sidecar: dict[str, Any]) -> bool:
    try:
        raw = path.read_bytes()
        soundtrack = GameSoundtrack.model_validate_json(raw)
        if canonical_game_soundtrack_json(soundtrack) != raw:
            return False
        provenance = ArtifactProvenance.model_validate(sidecar)
        params = provenance.params
        identity = params.get("soundtrack")
        if not isinstance(identity, Mapping):
            return False
        binding = GameSoundtrackBinding.model_validate(identity.get("binding"))
    except (OSError, ValueError):
        return False

    canonical_sha256 = sha256_hex(raw)
    source_input = provenance.inputs[0] if len(provenance.inputs) == 1 else None
    return (
        provenance.provider == "local"
        and provenance.model == SOUNDTRACK_RESOLUTION_VERSION
        and provenance.prompt == "resolve authored game soundtrack"
        and set(params) == {"stage", "soundtrack"}
        and params.get("stage") == "soundtrack-resolve"
        and set(identity)
        == {
            "schema_version",
            "kind",
            "resolution_version",
            "binding",
            "game_id",
            "revision",
            "track_ids",
            "playback",
            "source_sha256",
            "canonical_sha256",
            "canonical_bytes",
            "recipe_resolution_version",
            "artifact_ref",
            "artifact_sha256",
            "artifact_bytes",
        }
        and identity.get("schema_version") == 1
        and identity.get("kind") == "resolved-game-soundtrack-v1"
        and identity.get("resolution_version") == GAME_SOUNDTRACK_LIBRARY_RESOLUTION_VERSION
        and identity.get("recipe_resolution_version") == SOUNDTRACK_RESOLUTION_VERSION
        and identity.get("binding") == binding.model_dump(mode="json")
        and identity.get("game_id") == soundtrack.game_id
        and identity.get("revision") == soundtrack.revision
        and identity.get("track_ids") == list(soundtrack.track_ids)
        and identity.get("playback") == soundtrack.playback.model_dump(mode="json")
        and binding.ref == f"library/games/{soundtrack.game_id}/soundtrack.toml"
        and identity.get("source_sha256") == binding.source_sha256
        and identity.get("canonical_sha256") == canonical_sha256
        and identity.get("canonical_bytes") == len(raw)
        and identity.get("artifact_ref") == f"sha256:{canonical_sha256}"
        and identity.get("artifact_sha256") == canonical_sha256
        and identity.get("artifact_bytes") == len(raw)
        and provenance.refs == [binding.ref]
        and source_input is not None
        and source_input.ref == binding.ref
        and source_input.sha256 == binding.source_sha256
        and source_input.source == "content"
        and isinstance(source_input.bytes, int)
        and not isinstance(source_input.bytes, bool)
        and source_input.bytes > 0
        and source_input.media_type == "application/toml"
    )


def _track_metadata(
    resolved: ResolvedGameSoundtrack,
    track: SoundtrackTrack,
) -> dict[str, object]:
    return {
        "source": "scrolling-preview-soundtrack",
        "game_id": resolved.soundtrack.game_id,
        "track_id": track.track_id,
        "soundtrack_source_sha256": resolved.source_sha256,
        "soundtrack_canonical_sha256": resolved.canonical_sha256,
        "track_sha256": _track_sha256(track),
    }


def _track_metadata_from_identity(
    identity: Mapping[str, object],
    track: SoundtrackTrack,
) -> dict[str, object]:
    return {
        "source": "scrolling-preview-soundtrack",
        "game_id": identity["game_id"],
        "track_id": track.track_id,
        "soundtrack_source_sha256": identity["source_sha256"],
        "soundtrack_canonical_sha256": identity["canonical_sha256"],
        "track_sha256": _track_sha256(track),
    }


def _track_sha256(track: SoundtrackTrack) -> str:
    payload = json.dumps(
        track.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _valid_track_sidecar(
    sidecar: Mapping[str, Any],
    *,
    prompt: str,
    model: str | None,
    metadata: Mapping[str, object],
) -> bool:
    try:
        provenance = ArtifactProvenance.model_validate(sidecar)
    except ValueError:
        return False
    generation = provenance.params.get("generation")
    postprocess = provenance.params.get("postprocess")
    validation = provenance.validation.get("postprocess")
    return (
        provenance.prompt == prompt
        and (model is None or provenance.model == model)
        and provenance.artifact is not None
        and provenance.artifact.media_type == "audio/mpeg"
        and provenance.rights is not None
        and provenance.rights.status in {"unreviewed", "redistribution-approved"}
        and isinstance(generation, Mapping)
        and generation.get("metadata") == dict(metadata)
        and isinstance(postprocess, Mapping)
        and postprocess.get("processor") == "ffmpeg"
        and postprocess.get("output_format") == "mp3"
        and isinstance(validation, Mapping)
        and validation.get("non_silent") is True
        and validation.get("signature") == "matched"
    )


def _valid_track_artifact(
    path: Path,
    sidecar: dict[str, Any],
    *,
    prompt: str,
    model: str | None,
    metadata: Mapping[str, object],
) -> bool:
    try:
        assert_audio_signature(path.read_bytes(), "audio/mpeg")
    except (OSError, ValueError):
        return False
    return _valid_track_sidecar(
        sidecar,
        prompt=prompt,
        model=model,
        metadata=metadata,
    )


def _music_runtime(context: StageContext) -> _MusicRuntime:
    runtime = context.runtime
    if runtime is None or not callable(getattr(runtime, "generate_music", None)):
        raise RuntimeError("soundtrack generation requires the headless music capability")
    return cast(_MusicRuntime, runtime)


__all__ = [
    "SOUNDTRACK_MANIFEST_KIND",
    "SOUNDTRACK_RESOLUTION_VERSION",
    "CollectedSoundtrack",
    "assert_soundtrack_matches_game",
    "collect_scrolling_soundtrack",
    "generate_scrolling_soundtrack",
    "parse_game_soundtrack_binding",
    "resolve_scrolling_soundtrack",
    "soundtrack_contract_path",
    "soundtrack_track_path",
    "soundtrack_track_prompt",
]

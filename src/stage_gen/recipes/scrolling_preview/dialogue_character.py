"""Bind a reviewed dialogue-character bundle into one scrolling runtime manifest."""

from __future__ import annotations

import json
import stat
from pathlib import Path, PurePosixPath
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from stage_gen.components._secure_fs import read_absolute_regular_file
from stage_gen.contracts import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.recipes.dialogue_scene.character_bundle import (
    DialogueCharacterBundle,
    DialogueCharacterIndependentReview,
    load_reviewed_dialogue_character_bundle,
)
from stage_gen.recipes.dialogue_scene.identity import content_sha256
from stage_gen.recipes.dialogue_scene.models import EXPRESSION_STATES, DialogueBeat
from stage_gen.recipes.scrolling_preview.manifest import _lower_snake_case_manifest
from stage_gen.reliability import build_artifact_provenance, resolve_relative_path_within_root
from stage_gen.reliability.atomic import (
    AtomicBundleFile,
    atomic_write_bundle,
    serialize_provenance,
)

_COMPONENT = SoftwareIdentity(name="@stage-gen/scrolling-dialogue-character-import", version="1")
_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")
_SCROLLING_MANIFEST_SCHEMA_VERSION = 7


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DialogueCharacterRuntimeAsset(_StrictModel):
    state: Literal["neutral", "delighted", "flustered", "concerned"]
    path: str = Field(pattern=r"^dialogue-character-[a-f0-9]{64}\.png$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=1)
    media_type: Literal["image/png"]
    width: Literal[1024]
    height: Literal[1536]
    alpha: Literal[True]
    provenance_path: str = Field(pattern=r"^dialogue-character-[a-f0-9]{64}\.png\.meta\.json$")
    provenance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def content_addressed_name(self) -> DialogueCharacterRuntimeAsset:
        expected = f"dialogue-character-{self.sha256}.png"
        if self.path != expected or self.provenance_path != f"{expected}.meta.json":
            raise ValueError("dialogue character runtime asset path must be content-addressed")
        return self


class DialogueCharacterRuntimeReview(_StrictModel):
    status: Literal["pass"]
    usage: Literal["local-demo"]
    source_review_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class DialogueCharacterRuntimeRights(_StrictModel):
    aggregate: Literal["restricted"]
    publication_authorized: Literal[False]


class DialogueCharacterRuntime(_StrictModel):
    schema_version: Literal[1]
    kind: Literal["dialogue-character-runtime-v1"]
    npc_slot: int = Field(ge=0, le=3)
    npc_name: str = Field(min_length=1, max_length=96)
    character_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    source_bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    available_states: list[Literal["neutral", "delighted", "flustered", "concerned"]]
    assets: list[DialogueCharacterRuntimeAsset]
    dialogue: list[DialogueBeat] = Field(min_length=1, max_length=12)
    review: DialogueCharacterRuntimeReview
    rights: DialogueCharacterRuntimeRights

    @model_validator(mode="after")
    def locked_states(self) -> DialogueCharacterRuntime:
        if tuple(self.available_states) != EXPRESSION_STATES:
            raise ValueError("runtime available_states must use the locked taxonomy and order")
        if tuple(asset.state for asset in self.assets) != EXPRESSION_STATES:
            raise ValueError("runtime assets must bind all four states in locked order")
        return self


def _dialogue_manifest_bind_mode(
    version: int,
    manifest: dict[str, object],
) -> Literal["add", "idempotent"]:
    """Classify composition within the one current scrolling envelope."""

    _dialogue_manifest_output_version(version)
    if "dialogue_characters" not in manifest:
        return "add"
    return "idempotent"


def _dialogue_manifest_output_version(version: int) -> int:
    """Accept and preserve only the current scrolling envelope."""

    if isinstance(version, bool) or version != _SCROLLING_MANIFEST_SCHEMA_VERSION:
        raise ValueError("scrolling manifest schema_version must be 7")
    return _SCROLLING_MANIFEST_SCHEMA_VERSION


def bind_dialogue_character_to_scrolling_manifest(
    bundle_path: str | Path,
    *,
    manifest_path: str | Path,
    npc_slot: int,
) -> dict[str, object]:
    """Import a reviewed character into a current scrolling envelope."""

    bundle_path, bundle_bytes, bundle, _bundle_provenance = load_reviewed_dialogue_character_bundle(
        bundle_path
    )
    bundle_sha256 = content_sha256(bundle_bytes)
    npc_name = bundle.character.label
    identity_sha256 = bundle.character.identity_reference.sha256

    manifest_path = Path(manifest_path).absolute()
    run_dir = manifest_path.parent
    base_bytes = _read_regular(manifest_path, "scrolling manifest")
    base_provenance_path = Path(f"{manifest_path}.meta.json")
    base_provenance_bytes = _read_regular(base_provenance_path, "scrolling manifest provenance")
    base_provenance = _validate_provenance(
        base_provenance_bytes,
        base_bytes,
        "scrolling manifest",
        "application/json",
    )
    try:
        raw_manifest = json.loads(base_bytes)
    except json.JSONDecodeError as error:
        raise ValueError("scrolling manifest is not valid JSON") from error
    if not isinstance(raw_manifest, dict):
        raise ValueError("scrolling manifest must be an object")
    normalized = _lower_snake_case_manifest(raw_manifest)
    if normalized != raw_manifest:
        raise ValueError("scrolling manifest must use lower_snake_case keys")
    version = normalized.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValueError("scrolling manifest schema_version must be an integer")
    output_version = _dialogue_manifest_output_version(version)
    bind_mode = _dialogue_manifest_bind_mode(version, normalized)
    tag = normalized.get("tag")
    if not isinstance(tag, str) or not tag:
        raise ValueError("scrolling manifest tag is missing")
    if manifest_path.name != f"manifest_{tag}.json":
        raise ValueError("scrolling manifest filename does not match its tag")

    _verify_target_identity(
        run_dir,
        normalized,
        tag=tag,
        bundle=bundle,
        npc_slot=npc_slot,
        npc_name=npc_name,
        identity_sha256=identity_sha256,
    )
    review, review_bytes = _review_record(bundle_path.parent, bundle)
    imports = _build_imports(
        bundle_path.parent,
        bundle,
        bundle_sha256=bundle_sha256,
        source_review_sha256=content_sha256(review_bytes),
        tag=tag,
        npc_slot=npc_slot,
        npc_name=npc_name,
        identity_sha256=identity_sha256,
        reviewed_at=review.reviewed_at,
    )
    runtime = DialogueCharacterRuntime(
        schema_version=1,
        kind="dialogue-character-runtime-v1",
        npc_slot=npc_slot,
        npc_name=npc_name,
        character_id=bundle.character.id,
        source_bundle_sha256=bundle_sha256,
        identity_sha256=identity_sha256,
        available_states=list(EXPRESSION_STATES),
        assets=[item.runtime for item in imports],
        dialogue=bundle.dialogue,
        review=DialogueCharacterRuntimeReview(
            status="pass",
            usage="local-demo",
            source_review_sha256=content_sha256(review_bytes),
        ),
        rights=DialogueCharacterRuntimeRights(aggregate="restricted", publication_authorized=False),
    )

    if bind_mode == "idempotent":
        _validate_idempotent_provenance(
            base_provenance,
            bundle_bytes=bundle_bytes,
            bundle=bundle,
            review_bytes=review_bytes,
            review=review,
            imports=imports,
            tag=tag,
            npc_slot=npc_slot,
            npc_name=npc_name,
            identity_sha256=identity_sha256,
        )
        _validate_idempotent_manifest(
            run_dir,
            normalized,
            runtime,
            imports,
        )
        return _result(manifest_path, base_bytes, bundle_sha256, npc_slot, idempotent=True)

    updated = dict(normalized)
    updated["schema_version"] = output_version
    updated["dialogue_characters"] = [runtime.model_dump(mode="json")]
    updated["artifacts"] = _updated_artifacts(updated, imports)
    updated["canonical_artifacts"] = _updated_canonical_artifacts(updated, imports)
    updated["runtime_assets"] = _updated_runtime_assets(updated, imports, npc_slot, bundle)
    payload = f"{json.dumps(updated, indent=2, ensure_ascii=False)}\n".encode()

    manifest_provenance = ProvenanceInput(
        schema_version=2,
        provider="local",
        model="deterministic-scrolling-dialogue-character-bind-v1",
        prompt="Bind one reviewed dialogue character to a verified scrolling NPC slot.",
        refs=[
            f"scrolling-base-manifest:sha256:{content_sha256(base_bytes)}",
            f"dialogue-character-bundle:sha256:{bundle_sha256}",
            f"dialogue-character-review:sha256:{content_sha256(review_bytes)}",
        ],
        inputs=[
            _input(
                f"scrolling-base-manifest:sha256:{content_sha256(base_bytes)}",
                base_bytes,
                "application/json",
            ),
            _input(
                f"scrolling-base-manifest-provenance:sha256:{content_sha256(base_provenance_bytes)}",
                base_provenance_bytes,
                "application/json",
            ),
            _input(
                f"dialogue-character-bundle:sha256:{bundle_sha256}",
                bundle_bytes,
                "application/json",
            ),
            _input(
                f"dialogue-character-review:sha256:{content_sha256(review_bytes)}",
                review_bytes,
                "application/json",
            ),
            *[
                _input(
                    f"dialogue-character-import:{item.state}:sha256:{item.sha256}",
                    item.data,
                    "image/png",
                )
                for item in imports
            ],
        ],
        params={
            "base_manifest_schema_version": version,
            "base_manifest_sha256": content_sha256(base_bytes),
            "base_manifest_provenance_sha256": content_sha256(base_provenance_bytes),
            "source_bundle_sha256": bundle_sha256,
            "source_run_identity_sha256": bundle.run_identity_sha256,
            "source_review_sha256": content_sha256(review_bytes),
            "target_tag": tag,
            "npc_slot": npc_slot,
            "npc_name": npc_name,
            "identity_sha256": identity_sha256,
        },
        validation={
            "target_npc_name_verified": True,
            "target_identity_digest_verified": True,
            "assets_imported": 4,
            "manifest_schema_version": output_version,
            "review_status": "pass",
            "usage": "local-demo",
            "publication_authorized": False,
        },
        component=_COMPONENT,
        tool=_TOOL,
        timestamp=review.reviewed_at,
        attempts=1,
        rights=_restricted_rights(review.reviewed_at),
    )
    manifest_record = build_artifact_provenance(
        BinaryArtifact(data=payload, media_type="application/json"), manifest_provenance
    )
    _preflight_import_destinations(run_dir, imports)
    _assert_unchanged(manifest_path, base_bytes, "scrolling manifest")
    _assert_unchanged(
        base_provenance_path,
        base_provenance_bytes,
        "scrolling manifest provenance",
    )
    publication: list[AtomicBundleFile] = []
    for item in imports:
        publication.extend(
            (
                AtomicBundleFile(run_dir / item.path, item.data),
                AtomicBundleFile(run_dir / item.provenance_path, item.provenance_bytes),
            )
        )
    publication.extend(
        (
            AtomicBundleFile(manifest_path, payload),
            AtomicBundleFile(base_provenance_path, serialize_provenance(manifest_record)),
        )
    )
    atomic_write_bundle(tuple(publication))
    return _result(manifest_path, payload, bundle_sha256, npc_slot, idempotent=False)


def _preflight_import_destinations(run_dir: Path, imports: list[_Import]) -> None:
    for item in imports:
        _preflight_destination(
            run_dir / item.path,
            item.data,
            f"dialogue character {item.state} import",
        )
        _preflight_destination(
            run_dir / item.provenance_path,
            item.provenance_bytes,
            f"dialogue character {item.state} import provenance",
        )


def _preflight_destination(path: Path, expected: bytes, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as error:
        raise ValueError(f"{label} destination cannot be inspected") from error
    if not stat.S_ISREG(mode):
        raise ValueError(f"{label} destination must be a regular non-symlink file")
    if _read_regular(path, f"existing {label}") != expected:
        raise ValueError(f"conflicting existing {label} destination")


def _assert_unchanged(path: Path, expected: bytes, label: str) -> None:
    if _read_regular(path, label) != expected:
        raise RuntimeError(f"{label} changed during dialogue character bind")


class _Import:
    __slots__ = (
        "data",
        "path",
        "provenance_bytes",
        "provenance_path",
        "runtime",
        "sha256",
        "state",
    )

    def __init__(
        self,
        *,
        state: str,
        path: str,
        provenance_path: str,
        data: bytes,
        provenance_bytes: bytes,
        sha256: str,
        runtime: DialogueCharacterRuntimeAsset,
    ) -> None:
        self.state = state
        self.path = path
        self.provenance_path = provenance_path
        self.data = data
        self.provenance_bytes = provenance_bytes
        self.sha256 = sha256
        self.runtime = runtime


def _build_imports(
    source_root: Path,
    bundle: DialogueCharacterBundle,
    *,
    bundle_sha256: str,
    source_review_sha256: str,
    tag: str,
    npc_slot: int,
    npc_name: str,
    identity_sha256: str,
    reviewed_at: str,
) -> list[_Import]:
    result: list[_Import] = []
    paths: set[str] = set()
    for asset in bundle.assets:
        data = _read_relative(source_root, asset.path, f"dialogue character {asset.state} asset")
        source_provenance = _read_relative(
            source_root,
            asset.provenance_path,
            f"dialogue character {asset.state} provenance",
        )
        if content_sha256(data) != asset.sha256 or len(data) != asset.bytes:
            raise ValueError(
                f"dialogue character {asset.state} source asset digest or size mismatch"
            )
        if content_sha256(source_provenance) != asset.provenance_sha256:
            raise ValueError(f"dialogue character {asset.state} source provenance digest mismatch")
        _validate_provenance(
            source_provenance,
            data,
            f"dialogue character {asset.state} source",
            "image/png",
        )
        path = f"dialogue-character-{asset.sha256}.png"
        provenance_path = f"{path}.meta.json"
        if path in paths:
            raise ValueError("dialogue character assets must have distinct content digests")
        paths.add(path)
        provenance = ProvenanceInput(
            schema_version=2,
            provider="local",
            model="deterministic-dialogue-character-import-v1",
            prompt="Import a reviewed dialogue character state into a scrolling run.",
            refs=[
                f"dialogue-character-bundle:sha256:{bundle_sha256}",
                f"dialogue-character-review:sha256:{source_review_sha256}",
                f"dialogue-character-source:{asset.state}:sha256:{asset.sha256}",
            ],
            inputs=[
                _input(
                    f"dialogue-character-source:{asset.state}:sha256:{asset.sha256}",
                    data,
                    "image/png",
                ),
                _input(
                    "dialogue-character-source-provenance:"
                    f"{asset.state}:sha256:{asset.provenance_sha256}",
                    source_provenance,
                    "application/json",
                ),
            ],
            params={
                "source_bundle_sha256": bundle_sha256,
                "source_run_identity_sha256": bundle.run_identity_sha256,
                "source_review_sha256": source_review_sha256,
                "target_tag": tag,
                "npc_slot": npc_slot,
                "npc_name": npc_name,
                "identity_sha256": identity_sha256,
                "state": asset.state,
            },
            validation={
                "source_asset_digest_verified": True,
                "source_provenance_digest_verified": True,
                "width": asset.width,
                "height": asset.height,
                "alpha": asset.alpha,
                "review_status": "pass",
                "usage": "local-demo",
                "publication_authorized": False,
            },
            component=_COMPONENT,
            tool=_TOOL,
            timestamp=reviewed_at,
            attempts=1,
            rights=_restricted_rights(reviewed_at),
        )
        record = build_artifact_provenance(
            BinaryArtifact(data=data, media_type="image/png"), provenance
        )
        provenance_bytes = serialize_provenance(record)
        runtime = DialogueCharacterRuntimeAsset(
            state=asset.state,
            path=path,
            sha256=asset.sha256,
            bytes=asset.bytes,
            media_type="image/png",
            width=1024,
            height=1536,
            alpha=True,
            provenance_path=provenance_path,
            provenance_sha256=content_sha256(provenance_bytes),
        )
        result.append(
            _Import(
                state=asset.state,
                path=path,
                provenance_path=provenance_path,
                data=data,
                provenance_bytes=provenance_bytes,
                sha256=asset.sha256,
                runtime=runtime,
            )
        )
    return result


def _verify_target_identity(
    run_dir: Path,
    manifest: dict[str, object],
    *,
    tag: str,
    bundle: DialogueCharacterBundle,
    npc_slot: int,
    npc_name: str,
    identity_sha256: str,
) -> None:
    village = manifest.get("village")
    if not isinstance(village, dict):
        raise ValueError("scrolling manifest does not contain a village")
    npcs = village.get("npcs")
    if not isinstance(npcs, list):
        raise ValueError("scrolling village NPC list is missing")
    matches = [item for item in npcs if isinstance(item, dict) and item.get("slot") == npc_slot]
    if len(matches) != 1 or matches[0].get("name") != npc_name:
        raise ValueError("target scrolling NPC slot/name binding mismatch")

    identity_ref = PurePosixPath(bundle.character.identity_reference.ref)
    if len(identity_ref.parts) < 2 or identity_ref.parts[-2:] != (
        tag,
        identity_ref.name,
    ):
        raise ValueError("bundle identity reference does not name the target scrolling run")
    runtime_assets = manifest.get("runtime_assets")
    if not isinstance(runtime_assets, list):
        raise ValueError("scrolling runtime_assets are missing")
    candidates = []
    for item in runtime_assets:
        if not isinstance(item, dict) or item.get("path") != identity_ref.name:
            continue
        binding = item.get("binding")
        if isinstance(binding, dict) and binding.get("slot") == npc_slot:
            candidates.append(item)
    if len(candidates) != 1:
        raise ValueError("target NPC identity runtime asset is missing or ambiguous")
    identity_path = candidates[0].get("path")
    provenance_path = candidates[0].get("provenance_path")
    if not isinstance(identity_path, str) or not isinstance(provenance_path, str):
        raise ValueError("target NPC identity runtime paths are invalid")
    identity_data = _read_relative(run_dir, identity_path, "target NPC identity asset")
    if content_sha256(identity_data) != identity_sha256:
        raise ValueError("target NPC identity asset digest mismatch")
    identity_provenance = _read_relative(run_dir, provenance_path, "target NPC identity provenance")
    _validate_provenance(
        identity_provenance,
        identity_data,
        "target NPC identity",
        "image/png",
    )


def _review_record(
    root: Path, bundle: DialogueCharacterBundle
) -> tuple[DialogueCharacterIndependentReview, bytes]:
    if bundle.review.status != "pass":
        raise ValueError("dialogue character bundle review is not passing")
    data = _read_relative(root, bundle.review.path, "dialogue character review")
    if content_sha256(data) != bundle.review.sha256:
        raise ValueError("dialogue character review digest mismatch")
    try:
        review = DialogueCharacterIndependentReview.model_validate_json(data)
    except ValidationError as error:
        raise ValueError(f"invalid dialogue character review: {error}") from None
    return review, data


def _updated_artifacts(manifest: dict[str, object], imports: list[_Import]) -> list[str]:
    value = manifest.get("artifacts")
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("scrolling manifest artifacts must be a string list")
    names = cast(list[str], value)
    imported = [item.path for item in imports] + [item.provenance_path for item in imports]
    if set(names) & set(imported):
        raise ValueError("dialogue character import filename collides with a target artifact")
    return sorted([*names, *imported])


def _updated_canonical_artifacts(
    manifest: dict[str, object], imports: list[_Import]
) -> list[object]:
    value = manifest.get("canonical_artifacts")
    if not isinstance(value, list):
        raise ValueError("scrolling manifest canonical_artifacts must be a list")
    paths = {
        item.get("path")
        for item in value
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    if any(item.path in paths for item in imports):
        raise ValueError("dialogue character canonical path collides with a target artifact")
    added = [{"path": item.path, "provenance_path": item.provenance_path} for item in imports]
    return sorted(
        [*value, *added],
        key=lambda item: str(item.get("path", "")) if isinstance(item, dict) else "",
    )


def _updated_runtime_assets(
    manifest: dict[str, object],
    imports: list[_Import],
    npc_slot: int,
    bundle: DialogueCharacterBundle,
) -> list[object]:
    value = manifest.get("runtime_assets")
    if not isinstance(value, list):
        raise ValueError("scrolling manifest runtime_assets must be a list")
    roles = {
        item.get("runtime_slot")
        for item in value
        if isinstance(item, dict) and isinstance(item.get("runtime_slot"), str)
    }
    added: list[dict[str, object]] = []
    for item in imports:
        role = f"dialogue-character-{npc_slot}-{item.state}"
        if role in roles:
            raise ValueError("dialogue character runtime role collides with a target role")
        added.append(
            _runtime_asset_projection(
                item,
                npc_slot=npc_slot,
                character_id=bundle.character.id,
            )
        )
    return [*value, *added]


def _runtime_asset_projection(
    item: _Import,
    *,
    npc_slot: int,
    character_id: str,
) -> dict[str, object]:
    role = f"dialogue-character-{npc_slot}-{item.state}"
    return {
        "id": role,
        "runtime_slot": role,
        "path": item.path,
        "provenance_path": item.provenance_path,
        "alpha_expectation": "transparent",
        "layout": {
            "topology": "single",
            "rows": 1,
            "columns": 1,
            "cell_width": 1024,
            "cell_height": 1536,
            "gutter": 0,
        },
        "geometry_validation": {
            "exact_dimensions": True,
            "alpha_contract": True,
        },
        "binding": {
            "npc_slot": npc_slot,
            "state": item.state,
            "character_id": character_id,
        },
    }


def _validate_idempotent_manifest(
    run_dir: Path,
    manifest: dict[str, object],
    runtime: DialogueCharacterRuntime,
    imports: list[_Import],
) -> None:
    existing = manifest.get("dialogue_characters")
    desired = [runtime.model_dump(mode="json")]
    if existing != desired:
        raise ValueError(
            "a composed manifest may only be rebound with the identical bundle and NPC slot"
        )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or any(not isinstance(item, str) for item in artifacts):
        raise ValueError("composed manifest artifacts must be a string list")
    required_artifacts = [
        relative for item in imports for relative in (item.path, item.provenance_path)
    ]
    if any(artifacts.count(relative) != 1 for relative in required_artifacts):
        raise ValueError(
            "composed manifest dialogue character artifacts are incomplete or ambiguous"
        )

    canonical_artifacts = manifest.get("canonical_artifacts")
    if not isinstance(canonical_artifacts, list):
        raise ValueError("composed manifest canonical_artifacts must be a list")
    for item in imports:
        expected_canonical = {
            "path": item.path,
            "provenance_path": item.provenance_path,
        }
        matches = [
            entry
            for entry in canonical_artifacts
            if isinstance(entry, dict) and entry.get("path") == item.path
        ]
        if matches != [expected_canonical]:
            raise ValueError(
                "composed manifest dialogue character canonical_artifacts projection mismatch"
            )

    runtime_assets = manifest.get("runtime_assets")
    if not isinstance(runtime_assets, list):
        raise ValueError("composed manifest runtime_assets must be a list")
    for item in imports:
        expected_runtime = _runtime_asset_projection(
            item,
            npc_slot=runtime.npc_slot,
            character_id=runtime.character_id,
        )
        role = expected_runtime["runtime_slot"]
        matches = [
            entry
            for entry in runtime_assets
            if isinstance(entry, dict)
            and (
                entry.get("id") == role
                or entry.get("runtime_slot") == role
                or entry.get("path") == item.path
            )
        ]
        if matches != [expected_runtime]:
            raise ValueError(
                "composed manifest dialogue character runtime_assets projection mismatch"
            )

    for item in imports:
        if _read_relative(run_dir, item.path, "imported dialogue character asset") != item.data:
            raise ValueError("existing dialogue character asset is not byte-identical")
        if (
            _read_relative(run_dir, item.provenance_path, "imported dialogue character provenance")
            != item.provenance_bytes
        ):
            raise ValueError("existing dialogue character import provenance is not byte-identical")


def _validate_idempotent_provenance(
    provenance: ArtifactProvenance,
    *,
    bundle_bytes: bytes,
    bundle: DialogueCharacterBundle,
    review_bytes: bytes,
    review: DialogueCharacterIndependentReview,
    imports: list[_Import],
    tag: str,
    npc_slot: int,
    npc_name: str,
    identity_sha256: str,
) -> None:
    bundle_sha256 = content_sha256(bundle_bytes)
    review_sha256 = content_sha256(review_bytes)
    base_manifest_sha256 = provenance.params.get("base_manifest_sha256")
    base_provenance_sha256 = provenance.params.get("base_manifest_provenance_sha256")
    if not _is_sha256(base_manifest_sha256) or not _is_sha256(base_provenance_sha256):
        raise ValueError("composed manifest dialogue character provenance lineage mismatch")
    expected_refs = [
        f"scrolling-base-manifest:sha256:{base_manifest_sha256}",
        f"dialogue-character-bundle:sha256:{bundle_sha256}",
        f"dialogue-character-review:sha256:{review_sha256}",
    ]
    expected_params = {
        "base_manifest_schema_version": _SCROLLING_MANIFEST_SCHEMA_VERSION,
        "base_manifest_sha256": base_manifest_sha256,
        "base_manifest_provenance_sha256": base_provenance_sha256,
        "source_bundle_sha256": bundle_sha256,
        "source_run_identity_sha256": bundle.run_identity_sha256,
        "source_review_sha256": review_sha256,
        "target_tag": tag,
        "npc_slot": npc_slot,
        "npc_name": npc_name,
        "identity_sha256": identity_sha256,
    }
    expected_validation = {
        "target_npc_name_verified": True,
        "target_identity_digest_verified": True,
        "assets_imported": 4,
        "manifest_schema_version": _SCROLLING_MANIFEST_SCHEMA_VERSION,
        "review_status": "pass",
        "usage": "local-demo",
        "publication_authorized": False,
    }
    if (
        provenance.provider != "local"
        or provenance.model != "deterministic-scrolling-dialogue-character-bind-v1"
        or provenance.seed is not None
        or provenance.prompt
        != "Bind one reviewed dialogue character to a verified scrolling NPC slot."
        or provenance.references != expected_refs
        or provenance.refs != expected_refs
        or provenance.params != expected_params
        or provenance.validation != expected_validation
        or provenance.component != _COMPONENT
        or provenance.tool != _TOOL
        or provenance.rights != _restricted_rights(review.reviewed_at)
        or provenance.ts != review.reviewed_at
        or provenance.attempts != 1
        or provenance.retries != 0
        or provenance.response is not None
        or len(provenance.inputs) != 8
    ):
        raise ValueError("composed manifest dialogue character provenance lineage mismatch")
    base_manifest_ref = expected_refs[0]
    base_provenance_ref = f"scrolling-base-manifest-provenance:sha256:{base_provenance_sha256}"
    if not _content_input_matches(
        provenance.inputs[0],
        ref=base_manifest_ref,
        sha256=base_manifest_sha256,
        media_type="application/json",
    ) or not _content_input_matches(
        provenance.inputs[1],
        ref=base_provenance_ref,
        sha256=base_provenance_sha256,
        media_type="application/json",
    ):
        raise ValueError("composed manifest dialogue character provenance lineage mismatch")
    expected_known_inputs = [
        _input(expected_refs[1], bundle_bytes, "application/json"),
        _input(expected_refs[2], review_bytes, "application/json"),
        *[
            _input(
                f"dialogue-character-import:{item.state}:sha256:{item.sha256}",
                item.data,
                "image/png",
            )
            for item in imports
        ],
    ]
    if provenance.inputs[2:] != expected_known_inputs:
        raise ValueError("composed manifest dialogue character provenance lineage mismatch")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _content_input_matches(
    value: InputProvenance,
    *,
    ref: str,
    sha256: object,
    media_type: str,
) -> bool:
    return (
        value.ref == ref
        and value.sha256 == sha256
        and value.source == "content"
        and value.bytes is not None
        and value.bytes > 0
        and value.media_type == media_type
    )


def _result(
    manifest_path: Path,
    payload: bytes,
    bundle_sha256: str,
    npc_slot: int,
    *,
    idempotent: bool,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "scrolling-dialogue-character-bind-result-v1",
        "manifest_path": str(manifest_path),
        "manifest_sha256": content_sha256(payload),
        "source_bundle_sha256": bundle_sha256,
        "npc_slot": npc_slot,
        "idempotent": idempotent,
        "publication_authorized": False,
    }


def _input(ref: str, data: bytes, media_type: str) -> InputProvenance:
    return InputProvenance(
        ref=ref,
        sha256=content_sha256(data),
        source="content",
        bytes=len(data),
        media_type=media_type,
    )


def _restricted_rights(reviewed_at: str) -> ArtifactRights:
    return ArtifactRights(
        status="restricted",
        attribution=[],
        basis=["Independent digest-bound dialogue character review passed."],
        reviewed_at=reviewed_at,
    )


def _read_regular(path: Path, label: str) -> bytes:
    return read_absolute_regular_file(path, label=label)


def _read_relative(root: Path, relative: str, label: str) -> bytes:
    path = resolve_relative_path_within_root(root, relative, label)
    return _read_regular(path, label)


def _validate_provenance(
    data: bytes, artifact: bytes, label: str, media_type: str
) -> ArtifactProvenance:
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label} provenance: {error}") from None
    if isinstance(payload, dict) and payload.get("schema_version") != 2:
        raise ValueError(f"{label} provenance must use schema_version 2")
    try:
        provenance = ArtifactProvenance.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"invalid {label} provenance: {error}") from None
    expected = (content_sha256(artifact), len(artifact), media_type)
    actual = (
        (
            provenance.artifact.sha256,
            provenance.artifact.bytes,
            provenance.artifact.media_type,
        )
        if provenance.artifact is not None
        else None
    )
    if actual != expected:
        raise ValueError(f"{label} provenance artifact digest mismatch")
    return provenance

"""Deterministic, local-only independent-review transition for dialogue bundles."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from gnode import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
    atomic_write_bytes,
    build_artifact_provenance,
    resolve_relative_path_within_root,
    serialize_provenance,
    write_artifact_with_provenance,
)
from stage_gen.components import CharacterProfile, canonical_character_profile_json
from stage_gen.recipes.dialogue_scene.identity import canonical_json_bytes, content_sha256
from stage_gen.recipes.dialogue_scene.models import (
    DialogueBundle,
    IndependentReview,
    PersistedContractModel,
    ReviewState,
    RightsState,
)

_COMPONENT = SoftwareIdentity(name="@stage-gen/dialogue-scene-review", version="2")
_COMPONENT_V3 = SoftwareIdentity(name="@stage-gen/dialogue-scene-review", version="3")
_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")


class _ReviewActionRequest(PersistedContractModel):
    bundle_path: str = Field(min_length=1)
    review_path: str = Field(min_length=1)
    acceptance_spec_path: str = Field(min_length=1)
    usage: Literal["local-demo"]


async def transition_dialogue_review(input_value: Mapping[str, object]) -> dict[str, object]:
    """Derive an immutable reviewed bundle without changing generation artifacts."""

    return await asyncio.to_thread(_transition_dialogue_review_sync, input_value)


def _transition_dialogue_review_sync(input_value: Mapping[str, object]) -> dict[str, object]:
    """Perform the filesystem transition off the caller's event loop."""

    try:
        action = _ReviewActionRequest.model_validate(dict(input_value))
    except ValidationError as error:
        raise ValueError(f"invalid dialogue review action: {error}") from None
    source_path = _regular_input(Path(action.bundle_path), "source bundle")
    if source_path.name != "bundle.json":
        raise ValueError("source bundle must be the original bundle.json")
    review_input_path = _regular_input(Path(action.review_path), "independent review")
    acceptance_path = _regular_input(Path(action.acceptance_spec_path), "acceptance spec")
    root = source_path.parent
    review_output_path = root / "review.json"
    if review_input_path == review_output_path:
        raise ValueError("independent review input must be outside the derived review path")

    source_bytes = source_path.read_bytes()
    acceptance_bytes = acceptance_path.read_bytes()
    if not acceptance_bytes:
        raise ValueError("acceptance spec must be non-empty")
    return _transition_dialogue_review(
        action=action,
        source_path=source_path,
        source_bytes=source_bytes,
        review_input_path=review_input_path,
        review_output_path=review_output_path,
        acceptance_bytes=acceptance_bytes,
        root=root,
    )


def _transition_dialogue_review(
    *,
    action: _ReviewActionRequest,
    source_path: Path,
    source_bytes: bytes,
    review_input_path: Path,
    review_output_path: Path,
    acceptance_bytes: bytes,
    root: Path,
) -> dict[str, object]:
    try:
        bundle = DialogueBundle.model_validate_json(source_bytes)
        review = IndependentReview.model_validate_json(review_input_path.read_bytes())
    except ValidationError as error:
        raise ValueError(f"invalid dialogue review contract: {error}") from None
    _validate_source_state(bundle)
    source_sha256 = content_sha256(source_bytes)
    acceptance_sha256 = content_sha256(acceptance_bytes)
    if review.source_bundle_sha256 != source_sha256:
        raise ValueError("review source_bundle_sha256 does not match bundle.json")
    if review.acceptance_spec_sha256 != acceptance_sha256:
        raise ValueError("review acceptance_spec_sha256 does not match the acceptance spec")
    if review.character_profile_source_sha256 != (bundle.character_profile_binding.source_sha256):
        raise ValueError("review character_profile_source_sha256 does not match bundle.json")
    if review.character_profile_sha256 != bundle.character_profile_sha256:
        raise ValueError("review character_profile_sha256 does not match bundle.json")
    expected_asset_sha256 = [asset.sha256 for asset in bundle.assets]
    if Counter(review.asset_sha256) != Counter(expected_asset_sha256):
        raise ValueError("review asset_sha256 must bind every selected asset digest exactly once")
    _validate_selected_assets(root, bundle)
    _validate_profile_artifact(root, bundle)
    canonical_review = review.model_copy(update={"asset_sha256": expected_asset_sha256})
    review_bytes = canonical_json_bytes(canonical_review) + b"\n"
    provenance_input = ProvenanceInput(
        schema_version=2,
        provider="local",
        model="deterministic-dialogue-review-v3",
        prompt="Record a profile-bound independent review for local demo use only.",
        refs=["bundle.json", "character-profile.json"],
        inputs=[
            InputProvenance(
                ref="bundle.json",
                sha256=source_sha256,
                source="content",
                bytes=len(source_bytes),
                media_type="application/json",
            ),
            InputProvenance(
                ref="acceptance-spec",
                sha256=acceptance_sha256,
                source="content",
                bytes=len(acceptance_bytes),
                media_type="application/json",
            ),
            InputProvenance(
                ref="character-profile.json",
                sha256=bundle.character_profile_sha256,
                source="content",
                bytes=(root / bundle.character_profile.path).stat().st_size,
                media_type="application/json",
            ),
        ],
        params={
            "usage": action.usage,
            "source_bundle_sha256": source_sha256,
            "acceptance_spec_sha256": acceptance_sha256,
            "character_profile_ref": bundle.character_profile_binding.ref,
            "character_profile_source_sha256": (bundle.character_profile_binding.source_sha256),
            "character_profile_sha256": bundle.character_profile_sha256,
            "asset_sha256": expected_asset_sha256,
        },
        validation={
            "status": "pass",
            "independent_reviewer": True,
            "selected_assets": len(expected_asset_sha256),
            "profile_binding_verified": True,
            "publication_authorized": False,
        },
        component=_COMPONENT_V3,
        tool=_TOOL,
        timestamp=canonical_review.reviewed_at,
        attempts=1,
        rights=ArtifactRights(
            status="restricted",
            attribution=[],
            basis=["Independent digest-bound review passed for local demo use."],
            reviewed_at=canonical_review.reviewed_at,
        ),
    )
    review_provenance_path = Path(f"{review_output_path}.meta.json")
    _persist_review_pair_immutable(
        review_output_path, review_bytes, provenance_input, review_provenance_path
    )
    reviewed_bundle = DialogueBundle.model_validate(
        {
            **bundle.model_dump(mode="json", exclude_none=True),
            "review": ReviewState(
                status="pass",
                path="review.json",
                sha256=content_sha256(review_bytes),
                provenance_path="review.json.meta.json",
                provenance_sha256=content_sha256(review_provenance_path.read_bytes()),
            ).model_dump(mode="json"),
            "rights": RightsState(aggregate="restricted", publication_authorized=False).model_dump(
                mode="json"
            ),
        }
    )
    reviewed_bytes = canonical_json_bytes(reviewed_bundle) + b"\n"
    reviewed_path = root / "bundle.reviewed.json"
    _persist_immutable(reviewed_path, reviewed_bytes, "reviewed bundle")
    if source_path.read_bytes() != source_bytes:
        raise RuntimeError("source bundle changed during review transition")
    return {
        "schema_version": 3,
        "kind": "dialogue-review-transition-result-v3",
        "usage": action.usage,
        "source_bundle_sha256": source_sha256,
        "reviewed_bundle_sha256": content_sha256(reviewed_bytes),
        "character_profile_source_sha256": bundle.character_profile_binding.source_sha256,
        "character_profile_sha256": bundle.character_profile_sha256,
        "bundle_path": str(reviewed_path),
        "review_path": str(review_output_path),
        "review_provenance_path": str(review_provenance_path),
        "publication_authorized": False,
    }


def _validate_source_state(bundle: DialogueBundle) -> None:
    if bundle.review.status != "pending":
        raise ValueError("source bundle review must be pending")
    if bundle.rights.aggregate != "unreviewed" or bundle.rights.publication_authorized:
        raise ValueError("source bundle rights must be unreviewed and publication-disabled")


def _validate_selected_assets(root: Path, bundle: DialogueBundle) -> None:
    for asset in bundle.assets:
        path = resolve_relative_path_within_root(root, asset.path, "selected asset path")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"selected asset is missing or unsafe: {asset.id}")
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(root.resolve(strict=True))
        except ValueError as error:
            raise ValueError(f"selected asset escapes the bundle root: {asset.id}") from error
        if content_sha256(resolved.read_bytes()) != asset.sha256:
            raise ValueError(f"selected asset digest mismatch: {asset.id}")


def _validate_profile_artifact(root: Path, bundle: DialogueBundle) -> None:
    binding = bundle.character_profile
    path = resolve_relative_path_within_root(root, binding.path, "character profile path")
    provenance = resolve_relative_path_within_root(
        root, binding.provenance_path, "character profile provenance path"
    )
    for candidate, label in ((path, "character profile"), (provenance, "profile provenance")):
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError(f"{label} is missing or unsafe")
    profile_bytes = path.read_bytes()
    provenance_bytes = provenance.read_bytes()
    if content_sha256(profile_bytes) != binding.sha256:
        raise ValueError("character profile artifact digest mismatch")
    if binding.sha256 != bundle.character_profile_sha256:
        raise ValueError("character profile canonical digest mismatch")
    if content_sha256(provenance_bytes) != binding.provenance_sha256:
        raise ValueError("character profile provenance digest mismatch")
    try:
        profile = CharacterProfile.model_validate_json(profile_bytes)
    except ValidationError as error:
        raise ValueError(f"invalid canonical character profile artifact: {error}") from None
    if canonical_character_profile_json(profile) != profile_bytes:
        raise ValueError("character profile artifact is not canonical")
    # The binding names a package member by relative path; the run cannot prove
    # what that path meant, only that the bytes it shipped are the ones bound.
    ref = bundle.character_profile_binding.ref
    ref_parts = ref.split("/")
    if not ref.endswith(".toml") or any(part in {"", ".", ".."} for part in ref_parts):
        raise ValueError("character profile artifact binding ref is invalid")
    try:
        record = ArtifactProvenance.model_validate_json(provenance_bytes)
    except ValidationError as error:
        raise ValueError(f"invalid character profile provenance: {error}") from None
    if record.schema_version != 2:
        raise ValueError("character profile provenance must use schema version 2")
    if record.artifact is None or (
        record.artifact.sha256,
        record.artifact.bytes,
        record.artifact.media_type,
    ) != (binding.sha256, len(profile_bytes), "application/json"):
        raise ValueError("character profile provenance artifact binding mismatch")
    if (
        record.provider,
        record.model,
        record.component.name,
        record.component.version,
        record.refs,
    ) != (
        "local",
        "deterministic-dialogue-scene-v5",
        "@stage-gen/dialogue-scene",
        "5",
        [bundle.character_profile_binding.ref],
    ):
        raise ValueError("character profile provenance producer lineage mismatch")
    expected_source_input = InputProvenance(
        ref=bundle.character_profile_binding.ref,
        sha256=bundle.character_profile_binding.source_sha256,
        source="content",
        bytes=None,
        media_type="application/toml",
    )
    if (
        len(record.inputs) != 1
        or (
            record.inputs[0].ref,
            record.inputs[0].sha256,
            record.inputs[0].source,
            record.inputs[0].media_type,
        )
        != (
            expected_source_input.ref,
            expected_source_input.sha256,
            expected_source_input.source,
            expected_source_input.media_type,
        )
        or record.inputs[0].bytes is None
    ):
        raise ValueError("character profile provenance source input binding mismatch")
    expected_params = {
        "character_profile_ref": bundle.character_profile_binding.ref,
        "character_profile_source_sha256": bundle.character_profile_binding.source_sha256,
        "character_profile_sha256": bundle.character_profile_sha256,
        "profile_id": profile.profile_id,
        "revision": profile.revision,
    }
    if record.params != expected_params:
        raise ValueError("character profile provenance params mismatch")
    if record.rights is None or record.rights.model_dump(mode="json") != (
        profile.rights.model_dump(mode="json")
    ):
        raise ValueError("character profile provenance rights mismatch")


def _regular_input(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    return path.resolve(strict=True)


def _persist_review_pair_immutable(
    path: Path,
    data: bytes,
    provenance: ProvenanceInput,
    provenance_path: Path,
) -> None:
    expected_provenance = serialize_provenance(
        build_artifact_provenance(
            BinaryArtifact(data=data, media_type="application/json"), provenance
        )
    )
    if path.exists() or provenance_path.exists():
        if (
            path.is_file()
            and not path.is_symlink()
            and provenance_path.is_file()
            and not provenance_path.is_symlink()
            and path.read_bytes() == data
            and provenance_path.read_bytes() == expected_provenance
        ):
            return
        raise ValueError("derived review artifact already exists with different content")
    write_artifact_with_provenance(
        path, BinaryArtifact(data=data, media_type="application/json"), provenance
    )


def _persist_immutable(path: Path, data: bytes, label: str) -> None:
    if path.exists():
        if path.is_file() and not path.is_symlink() and path.read_bytes() == data:
            return
        raise ValueError(f"{label} already exists with different content")
    atomic_write_bytes(path, data)

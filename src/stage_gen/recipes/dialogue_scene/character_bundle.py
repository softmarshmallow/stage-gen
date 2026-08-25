"""First-class portable dialogue-character bundle and local review transition."""

from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from stage_gen.components._secure_fs import read_absolute_regular_file
from stage_gen.contracts import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.media import (
    MAGENTA_EDGE_DECONTAMINATION_VERSION,
    decontaminate_magenta_edges,
    inspect_image,
)
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
    content_sha256,
)
from stage_gen.recipes.dialogue_scene.models import (
    EXPRESSION_STATES,
    DialogueBeat,
    DialogueScenePlan,
    DialogueThemeRequest,
    PersistedContractModel,
    ReuseSource,
    RightsState,
)
from stage_gen.reliability import build_artifact_provenance, resolve_relative_path_within_root
from stage_gen.reliability.atomic import (
    AtomicBundleFile,
    atomic_write_bundle,
    serialize_provenance,
)

_COMPONENT = SoftwareIdentity(name="@stage-gen/dialogue-character-bundle", version="1")
_REVIEW_COMPONENT = SoftwareIdentity(
    name="@stage-gen/dialogue-character-bundle-review", version="1"
)
_SANITIZE_COMPONENT = SoftwareIdentity(name="@stage-gen/dialogue-character-sanitize", version="1")
_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_SANITIZE_ASSET_MODEL = "deterministic-dialogue-character-magenta-edge-sanitize-v1"
_SANITIZE_SPIKE_MODEL = "deterministic-dialogue-character-sanitized-spike-v1"
_DERIVED_REVIEW_OUTPUTS = (
    "dialogue-character.bundle.json",
    "dialogue-character.bundle.json.meta.json",
    "dialogue-character.bundle.reviewed.json",
    "dialogue-character.bundle.reviewed.json.meta.json",
    "dialogue-character.review.json",
    "dialogue-character.review.json.meta.json",
)


class _StrictModel(PersistedContractModel):
    """Strict dialogue-local model with the shared trimmed-string invariant."""


def _portable(value: str, label: str) -> str:
    parts = value.split("/")
    if (
        not value
        or "\x00" in value
        or value.startswith(("/", "~", "http://", "https://"))
        or "\\" in value
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"{label} must be a portable relative path")
    return value


class DialogueCharacterIdentityReference(_StrictModel):
    ref: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("ref")
    @classmethod
    def portable_ref(cls, value: str) -> str:
        return _portable(value, "identity reference")


class DialogueCharacterIdentity(_StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    label: str = Field(min_length=1, max_length=96)
    age: int = Field(ge=21, le=120)
    identity_reference: DialogueCharacterIdentityReference


class DialogueCharacterAsset(_StrictModel):
    state: Literal["neutral", "delighted", "flustered", "concerned"]
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=1)
    media_type: Literal["image/png"]
    width: Literal[1024]
    height: Literal[1536]
    alpha: Literal[True]
    provenance_path: str
    provenance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path", "provenance_path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        return _portable(value, "dialogue character asset path")


class DialogueCharacterFile(_StrictModel):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance_path: str
    provenance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path", "provenance_path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        return _portable(value, "dialogue character file path")


class _PendingSpikeReview(_StrictModel):
    status: Literal["pending"]


class DialogueCharacterOnlySpike(_StrictModel):
    schema_version: Literal[1]
    kind: Literal["dialogue-character-only-spike-v1"]
    status: Literal["ready-for-local-demo"]
    character: DialogueCharacterIdentity
    available_states: list[Literal["neutral", "delighted", "flustered", "concerned"]]
    assets: list[DialogueCharacterAsset]
    source_plan: str
    source_request: str
    background: None
    review: _PendingSpikeReview
    publication_authorized: Literal[False]
    note: str = Field(min_length=1)

    @field_validator("source_plan", "source_request")
    @classmethod
    def portable_source_path(cls, value: str) -> str:
        return _portable(value, "spike source path")

    @model_validator(mode="after")
    def locked_assets(self) -> DialogueCharacterOnlySpike:
        if tuple(self.available_states) != EXPRESSION_STATES:
            raise ValueError("spike available_states must use the locked taxonomy and order")
        if tuple(asset.state for asset in self.assets) != EXPRESSION_STATES:
            raise ValueError("spike assets must bind every locked state in order")
        return self


class DialogueCharacterBundlePendingReview(_StrictModel):
    status: Literal["pending"] = "pending"


class DialogueCharacterBundlePassedReview(_StrictModel):
    status: Literal["pass"]
    usage: Literal["local-demo"]
    path: Literal["dialogue-character.review.json"]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance_path: Literal["dialogue-character.review.json.meta.json"]
    provenance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptance_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


DialogueCharacterBundleReviewState = Annotated[
    DialogueCharacterBundlePendingReview | DialogueCharacterBundlePassedReview,
    Field(discriminator="status"),
]


class DialogueCharacterBundle(_StrictModel):
    schema_version: Literal[1]
    kind: Literal["dialogue-character-bundle-v1"]
    recipe: Literal["dialogue-scene"]
    recipe_version: Literal["dialogue-scene-v3"]
    tag: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,199}$")
    run_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    character: DialogueCharacterIdentity
    source_spike: DialogueCharacterFile
    request: DialogueCharacterFile
    plan: DialogueCharacterFile
    available_states: list[Literal["neutral", "delighted", "flustered", "concerned"]]
    assets: list[DialogueCharacterAsset]
    dialogue: list[DialogueBeat] = Field(min_length=1, max_length=12)
    review: DialogueCharacterBundleReviewState
    rights: RightsState

    @model_validator(mode="after")
    def locked_projection(self) -> DialogueCharacterBundle:
        if tuple(self.available_states) != EXPRESSION_STATES:
            raise ValueError("bundle available_states must use the locked taxonomy and order")
        if tuple(asset.state for asset in self.assets) != EXPRESSION_STATES:
            raise ValueError("bundle assets must bind every locked state in order")
        if any(beat.expression_state not in self.available_states for beat in self.dialogue):
            raise ValueError("bundle dialogue references an unavailable state")
        if self.review.status == "pending" and self.rights != RightsState(
            aggregate="unreviewed", publication_authorized=False
        ):
            raise ValueError("pending bundle rights must remain unreviewed and unpublished")
        if self.review.status == "pass" and self.rights != RightsState(
            aggregate="restricted", publication_authorized=False
        ):
            raise ValueError("reviewed bundle rights must be restricted to local demo use")
        return self


class DialogueCharacterIndependentReview(_StrictModel):
    schema_version: Literal[1]
    kind: Literal["dialogue-character-review-v1"]
    status: Literal["pass"]
    usage: Literal["local-demo"]
    source_bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptance_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    independent_reviewer: Literal[True]
    asset_sha256: list[str] = Field(min_length=4, max_length=4)
    publication_authorized: Literal[False]
    reviewed_at: str

    @field_validator("asset_sha256")
    @classmethod
    def valid_asset_digests(cls, value: list[str]) -> list[str]:
        if any(re.fullmatch(r"[a-f0-9]{64}", item) is None for item in value):
            raise ValueError("asset_sha256 entries must be SHA-256 digests")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def valid_reviewed_at(cls, value: str) -> str:
        if _UTC_TIMESTAMP.fullmatch(value) is None:
            raise ValueError("reviewed_at must be a UTC ISO-8601 timestamp")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as error:
            raise ValueError("reviewed_at must be a valid UTC ISO-8601 timestamp") from error
        offset = parsed.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("reviewed_at must be a UTC ISO-8601 timestamp")
        return value


@dataclass(frozen=True, slots=True)
class _LoadedSpikeAsset:
    contract: DialogueCharacterAsset
    data: bytes
    provenance_bytes: bytes
    provenance: ArtifactProvenance


@dataclass(frozen=True, slots=True)
class _SanitizedSpikeAsset:
    source: _LoadedSpikeAsset
    contract: DialogueCharacterAsset
    data: bytes
    provenance_bytes: bytes
    transform: dict[str, object]


def sanitize_dialogue_character_spike(spike_path: str | Path) -> dict[str, object]:
    """Derive sanitized siblings and atomically rebind one pending local spike."""

    path, root = _validated_spike_path(spike_path)
    _refuse_derived_dialogue_character_outputs(root)
    spike_bytes, spike, spike_provenance_bytes, spike_provenance, assets = (
        _load_pending_dialogue_character_spike(path, root)
    )
    expected_paths = [
        f"spike-assets/expression-{state}.sanitized.png" for state in EXPRESSION_STATES
    ]
    current_paths = [asset.contract.path for asset in assets]
    if current_paths == expected_paths:
        return _validate_idempotent_sanitized_spike(
            path,
            root,
            spike_bytes,
            spike,
            spike_provenance,
            assets,
        )
    if any(item in expected_paths for item in current_paths):
        raise ValueError("dialogue character spike contains a partial sanitized asset set")

    source_spike_sha256 = content_sha256(spike_bytes)
    source_spike_provenance_sha256 = content_sha256(spike_provenance_bytes)
    sanitized = [
        _sanitize_spike_asset(
            root,
            source,
            output_relative=expected_paths[index],
            source_spike_sha256=source_spike_sha256,
            source_spike_provenance_sha256=source_spike_provenance_sha256,
        )
        for index, source in enumerate(assets)
    ]
    updated = DialogueCharacterOnlySpike.model_validate(
        {
            **spike.model_dump(mode="json"),
            "assets": [item.contract.model_dump(mode="json") for item in sanitized],
        }
    )
    updated_bytes = (
        canonical_json_bytes(updated.model_dump(mode="json", exclude_none=False)) + b"\n"
    )
    updated_provenance = ProvenanceInput(
        schema_version=2,
        provider="local",
        model=_SANITIZE_SPIKE_MODEL,
        prompt="Bind four deterministic magenta-edge-sanitized assets to a pending spike.",
        refs=[item.contract.path for item in sanitized],
        inputs=[_input(item.contract.path, item.data, "image/png") for item in sanitized],
        params={
            "source_spike_sha256": source_spike_sha256,
            "source_spike_provenance_sha256": source_spike_provenance_sha256,
            "transform_version": MAGENTA_EDGE_DECONTAMINATION_VERSION,
            "source_asset_sha256": [item.source.contract.sha256 for item in sanitized],
            "sanitized_asset_sha256": [item.contract.sha256 for item in sanitized],
        },
        validation={
            "status": "ready-for-local-demo",
            "review_status": "pending",
            "rights": "unreviewed",
            "asset_count": 4,
            "locked_states": list(EXPRESSION_STATES),
            "publication_authorized": False,
        },
        component=_SANITIZE_COMPONENT,
        tool=_TOOL,
        timestamp=spike_provenance.ts,
        attempts=1,
        rights=_unreviewed_rights(),
    )
    updated_record = build_artifact_provenance(
        BinaryArtifact(data=updated_bytes, media_type="application/json"),
        updated_provenance,
    )
    updated_provenance_bytes = serialize_provenance(updated_record)

    for item in sanitized:
        _preflight_sanitize_destination(
            root / item.contract.path,
            item.data,
            f"sanitized {item.contract.state} asset",
        )
        _preflight_sanitize_destination(
            root / item.contract.provenance_path,
            item.provenance_bytes,
            f"sanitized {item.contract.state} asset provenance",
        )
    _assert_unchanged(path, spike_bytes, "dialogue character spike")
    _assert_unchanged(
        Path(f"{path}.meta.json"),
        spike_provenance_bytes,
        "dialogue character spike provenance",
    )
    for item in sanitized:
        _assert_unchanged(
            root / item.source.contract.path,
            item.source.data,
            f"source {item.contract.state} asset",
        )
        _assert_unchanged(
            root / item.source.contract.provenance_path,
            item.source.provenance_bytes,
            f"source {item.contract.state} asset provenance",
        )

    publication = [
        entry
        for item in sanitized
        for entry in (
            AtomicBundleFile(root / item.contract.path, item.data),
            AtomicBundleFile(root / item.contract.provenance_path, item.provenance_bytes),
        )
    ]
    publication.extend(
        (
            AtomicBundleFile(path, updated_bytes),
            AtomicBundleFile(f"{path}.meta.json", updated_provenance_bytes),
        )
    )
    atomic_write_bundle(tuple(publication))
    return _sanitize_result(
        path,
        updated_bytes,
        sanitized,
        source_spike_sha256=source_spike_sha256,
        idempotent=False,
    )


def _validated_spike_path(spike_path: str | Path) -> tuple[Path, Path]:
    path = Path(spike_path).absolute()
    if path.name != "character-only.json" or path.parent.name != "spike-assets":
        raise ValueError("spike must equal RUN/spike-assets/character-only.json")
    root = path.parent.parent
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,199}", root.name) is None:
        raise ValueError("dialogue character run directory must use a safe run tag")
    return path, root


def _refuse_derived_dialogue_character_outputs(root: Path) -> None:
    for name in _DERIVED_REVIEW_OUTPUTS:
        path = root / name
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ValueError("derived dialogue character outputs cannot be inspected") from error
        raise ValueError(
            "dialogue character sanitize requires package and review outputs to be absent"
        )


def _load_pending_dialogue_character_spike(
    path: Path, root: Path
) -> tuple[
    bytes,
    DialogueCharacterOnlySpike,
    bytes,
    ArtifactProvenance,
    list[_LoadedSpikeAsset],
]:
    data = _read_regular(path, "dialogue character spike")
    spike = _parse(DialogueCharacterOnlySpike, data, "dialogue character spike")
    provenance_path = Path(f"{path}.meta.json")
    provenance_bytes = _read_regular(provenance_path, "dialogue character spike provenance")
    provenance = _validate_provenance_bytes(
        provenance_bytes,
        data,
        "dialogue character spike",
        "application/json",
    )
    _validate_unreviewed_provenance(
        provenance,
        label="dialogue character spike",
        require_explicit_publication_false=True,
    )

    request_path, request_bytes, _request_provenance_path, _request_provenance = (
        _read_bound_relative(root, spike.source_request, "dialogue request")
    )
    plan_path, plan_bytes, _plan_provenance_path, _plan_provenance = _read_bound_relative(
        root, spike.source_plan, "dialogue plan"
    )
    request = _parse(DialogueThemeRequest, request_bytes, "dialogue request")
    plan = _parse(DialogueScenePlan, plan_bytes, "dialogue plan")
    if plan.request_sha256 != canonical_sha256(request):
        raise ValueError("dialogue plan request digest mismatch")
    concept = request.appearance.concept
    if not isinstance(concept, ReuseSource):
        raise ValueError("dialogue character spike requires a reused identity reference")
    expected_identity = (request.appearance.id, request.appearance.label, request.appearance.age)
    actual_identity = (spike.character.id, spike.character.label, spike.character.age)
    if actual_identity != expected_identity:
        raise ValueError("spike character identity does not match the dialogue request")
    if (spike.character.identity_reference.ref, spike.character.identity_reference.sha256) != (
        concept.ref,
        concept.sha256,
    ):
        raise ValueError("spike identity reference does not match the dialogue request")
    if request_path != root / spike.source_request or plan_path != root / spike.source_plan:
        raise ValueError("dialogue character source paths must remain confined to the run")

    assets = [_load_spike_asset(root, asset) for asset in spike.assets]
    if len({asset.contract.path for asset in assets}) != len(assets):
        raise ValueError("dialogue character spike asset paths must be unique")
    expected_inputs = {
        asset.contract.path: _content_tuple(asset.data, "image/png") for asset in assets
    }
    if _provenance_input_tuples(provenance, label="dialogue character spike") != (expected_inputs):
        raise ValueError("dialogue character spike provenance input bindings mismatch")
    expected_refs = [asset.contract.path for asset in assets]
    if provenance.refs != expected_refs:
        raise ValueError("dialogue character spike provenance refs mismatch")
    return data, spike, provenance_bytes, provenance, assets


def _load_spike_asset(root: Path, asset: DialogueCharacterAsset) -> _LoadedSpikeAsset:
    path = PurePosixPath(asset.path)
    if path.parent != PurePosixPath("spike-assets"):
        raise ValueError("dialogue character spike assets must be siblings of the spike")
    if asset.provenance_path != f"{asset.path}.meta.json":
        raise ValueError("dialogue character spike asset provenance must be adjacent")
    data = _read_relative(root, asset.path, f"dialogue character {asset.state} asset")
    if content_sha256(data) != asset.sha256 or len(data) != asset.bytes:
        raise ValueError(f"dialogue character {asset.state} asset digest or size mismatch")
    facts = inspect_image(data, expected_media_type="image/png")
    if (facts.width, facts.height, facts.has_alpha) != (1024, 1536, True):
        raise ValueError(f"dialogue character {asset.state} asset media contract mismatch")
    provenance_bytes = _read_relative(
        root,
        asset.provenance_path,
        f"dialogue character {asset.state} provenance",
    )
    if content_sha256(provenance_bytes) != asset.provenance_sha256:
        raise ValueError(f"dialogue character {asset.state} provenance digest mismatch")
    provenance = _validate_provenance_bytes(
        provenance_bytes,
        data,
        f"dialogue character {asset.state}",
        "image/png",
    )
    _validate_unreviewed_provenance(
        provenance,
        label=f"dialogue character {asset.state}",
        require_explicit_publication_false=False,
    )
    return _LoadedSpikeAsset(asset, data, provenance_bytes, provenance)


def _validate_unreviewed_provenance(
    provenance: ArtifactProvenance,
    *,
    label: str,
    require_explicit_publication_false: bool,
) -> None:
    if provenance.rights is None or provenance.rights.status != "unreviewed":
        raise ValueError(f"{label} provenance rights must remain unreviewed")
    publication = provenance.validation.get("publication_authorized")
    if publication is True or (require_explicit_publication_false and publication is not False):
        raise ValueError(f"{label} provenance must not authorize publication")


def _sanitize_spike_asset(
    root: Path,
    source: _LoadedSpikeAsset,
    *,
    output_relative: str,
    source_spike_sha256: str,
    source_spike_provenance_sha256: str,
) -> _SanitizedSpikeAsset:
    output_relative = _portable(output_relative, "sanitized asset path")
    if PurePosixPath(output_relative).parent != PurePosixPath("spike-assets"):
        raise ValueError("sanitized assets must be siblings of the spike")
    output, facts = decontaminate_magenta_edges(source.data)
    image = inspect_image(output, expected_media_type="image/png")
    if (image.width, image.height, image.has_alpha) != (1024, 1536, True):
        raise ValueError("sanitized dialogue character asset media contract mismatch")
    transform: dict[str, object] = {
        "version": MAGENTA_EDGE_DECONTAMINATION_VERSION,
        **facts.as_dict(),
    }
    provenance_input = ProvenanceInput(
        schema_version=2,
        provider="local",
        model=_SANITIZE_ASSET_MODEL,
        prompt="Remove transparency-connected hot-magenta edge contamination deterministically.",
        refs=[source.contract.path, source.contract.provenance_path],
        inputs=[
            _input(source.contract.path, source.data, "image/png"),
            _input(
                source.contract.provenance_path,
                source.provenance_bytes,
                "application/json",
            ),
        ],
        params={
            "state": source.contract.state,
            "source_asset": source.contract.model_dump(mode="json"),
            "source_spike_sha256": source_spike_sha256,
            "source_spike_provenance_sha256": source_spike_provenance_sha256,
            "transform": transform,
        },
        validation={
            "width": image.width,
            "height": image.height,
            "alpha": image.has_alpha,
            "removed_pixels": facts.removed_pixels,
            "output_hot_magenta_pixels": facts.output_hot_magenta_pixels,
            "review_status": "pending",
            "rights": "unreviewed",
            "publication_authorized": False,
        },
        component=_SANITIZE_COMPONENT,
        tool=_TOOL,
        timestamp=source.provenance.ts,
        attempts=1,
        rights=_unreviewed_rights(),
    )
    record = build_artifact_provenance(
        BinaryArtifact(data=output, media_type="image/png"), provenance_input
    )
    provenance_bytes = serialize_provenance(record)
    contract = DialogueCharacterAsset(
        state=source.contract.state,
        path=output_relative,
        sha256=content_sha256(output),
        bytes=len(output),
        media_type="image/png",
        width=1024,
        height=1536,
        alpha=True,
        provenance_path=f"{output_relative}.meta.json",
        provenance_sha256=content_sha256(provenance_bytes),
    )
    return _SanitizedSpikeAsset(source, contract, output, provenance_bytes, transform)


def _validate_idempotent_sanitized_spike(
    path: Path,
    root: Path,
    spike_bytes: bytes,
    spike: DialogueCharacterOnlySpike,
    spike_provenance: ArtifactProvenance,
    assets: list[_LoadedSpikeAsset],
) -> dict[str, object]:
    if (
        spike_provenance.model != _SANITIZE_SPIKE_MODEL
        or spike_provenance.component != _SANITIZE_COMPONENT
        or spike_provenance.validation.get("publication_authorized") is not False
    ):
        raise ValueError("sanitized spike provenance transition marker mismatch")
    source_spike_sha256 = spike_provenance.params.get("source_spike_sha256")
    source_spike_provenance_sha256 = spike_provenance.params.get("source_spike_provenance_sha256")
    if (
        not isinstance(source_spike_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", source_spike_sha256) is None
        or not isinstance(source_spike_provenance_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", source_spike_provenance_sha256) is None
    ):
        raise ValueError("sanitized spike source lineage digests are invalid")

    expected: list[_SanitizedSpikeAsset] = []
    for current in assets:
        if (
            current.provenance.model != _SANITIZE_ASSET_MODEL
            or current.provenance.component != _SANITIZE_COMPONENT
            or current.provenance.validation.get("publication_authorized") is not False
        ):
            raise ValueError("sanitized asset provenance transition marker mismatch")
        try:
            source_contract = DialogueCharacterAsset.model_validate(
                current.provenance.params["source_asset"]
            )
        except (KeyError, ValidationError):
            raise ValueError("sanitized asset source binding is invalid") from None
        source = _load_spike_asset(root, source_contract)
        rebuilt = _sanitize_spike_asset(
            root,
            source,
            output_relative=current.contract.path,
            source_spike_sha256=source_spike_sha256,
            source_spike_provenance_sha256=source_spike_provenance_sha256,
        )
        if (
            rebuilt.contract != current.contract
            or rebuilt.data != current.data
            or rebuilt.provenance_bytes != current.provenance_bytes
        ):
            raise ValueError("sanitized asset is not the deterministic source derivation")
        expected.append(rebuilt)
    if [item.contract for item in expected] != spike.assets:
        raise ValueError("sanitized spike asset projection mismatch")
    return _sanitize_result(
        path,
        spike_bytes,
        expected,
        source_spike_sha256=source_spike_sha256,
        idempotent=True,
    )


def _preflight_sanitize_destination(path: Path, expected: bytes, label: str) -> None:
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
        raise RuntimeError(f"{label} changed during sanitize")


def _sanitize_result(
    path: Path,
    spike_bytes: bytes,
    assets: list[_SanitizedSpikeAsset],
    *,
    source_spike_sha256: str,
    idempotent: bool,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "dialogue-character-sanitize-result-v1",
        "spike_path": str(path),
        "source_spike_sha256": source_spike_sha256,
        "sanitized_spike_sha256": content_sha256(spike_bytes),
        "asset_sha256": [item.contract.sha256 for item in assets],
        "removed_pixels": {
            item.contract.state: item.transform["removed_pixels"] for item in assets
        },
        "transform_version": MAGENTA_EDGE_DECONTAMINATION_VERSION,
        "idempotent": idempotent,
        "review_status": "pending",
        "publication_authorized": False,
    }


def package_dialogue_character_spike(
    spike_path: str | Path, *, output_path: str | Path | None = None
) -> dict[str, object]:
    """Validate and package one local four-state spike without changing its assets."""

    spike_path = Path(spike_path).absolute()
    if spike_path.name != "character-only.json" or spike_path.parent.name != "spike-assets":
        raise ValueError("spike must equal RUN/spike-assets/character-only.json")
    root = spike_path.parent.parent
    tag = root.name
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,199}", tag) is None:
        raise ValueError("dialogue character run directory must use a safe run tag")
    output = (
        Path(output_path).absolute()
        if output_path is not None
        else root / ("dialogue-character.bundle.json")
    )
    if output.parent != root or output.name != "dialogue-character.bundle.json":
        raise ValueError("character bundle output must equal RUN/dialogue-character.bundle.json")

    spike_bytes = _read_regular(spike_path, "dialogue character spike")
    spike = _parse(DialogueCharacterOnlySpike, spike_bytes, "dialogue character spike")
    spike_provenance_path = Path(f"{spike_path}.meta.json")
    spike_provenance = _read_bound_provenance(
        spike_provenance_path, spike_bytes, "dialogue character spike"
    )
    _validate_provenance_bytes(
        spike_provenance,
        spike_bytes,
        "dialogue character spike",
        "application/json",
    )
    spike_relative = spike_path.relative_to(root).as_posix()

    request_path, request_bytes, request_provenance_path, request_provenance = _read_bound_relative(
        root, spike.source_request, "dialogue request"
    )
    plan_path, plan_bytes, plan_provenance_path, plan_provenance = _read_bound_relative(
        root, spike.source_plan, "dialogue plan"
    )
    request = _parse(DialogueThemeRequest, request_bytes, "dialogue request")
    plan = _parse(DialogueScenePlan, plan_bytes, "dialogue plan")
    if plan.request_sha256 != canonical_sha256(request):
        raise ValueError("dialogue plan request digest mismatch")
    concept = request.appearance.concept
    if not isinstance(concept, ReuseSource):
        raise ValueError("dialogue character spike requires a reused identity reference")
    expected_identity = (request.appearance.id, request.appearance.label, request.appearance.age)
    actual_identity = (spike.character.id, spike.character.label, spike.character.age)
    if actual_identity != expected_identity:
        raise ValueError("spike character identity does not match the dialogue request")
    if (spike.character.identity_reference.ref, spike.character.identity_reference.sha256) != (
        concept.ref,
        concept.sha256,
    ):
        raise ValueError("spike identity reference does not match the dialogue request")

    assets = [_validate_asset(root, asset) for asset in spike.assets]
    run_identity_sha256 = canonical_sha256(
        {
            "domain": "stage-gen/dialogue-character-bundle/run-identity/v1",
            "recipe": "dialogue-scene-v3",
            "tag": tag,
            "request_sha256": canonical_sha256(request),
            "plan_sha256": canonical_sha256(plan),
            "identity_reference_sha256": spike.character.identity_reference.sha256,
            "selected_assets": [{"state": asset.state, "sha256": asset.sha256} for asset in assets],
        }
    )
    bundle = DialogueCharacterBundle(
        schema_version=1,
        kind="dialogue-character-bundle-v1",
        recipe="dialogue-scene",
        recipe_version="dialogue-scene-v3",
        tag=tag,
        run_identity_sha256=run_identity_sha256,
        character=spike.character,
        source_spike=_file_binding(
            spike_relative,
            spike_bytes,
            f"{spike_relative}.meta.json",
            spike_provenance,
        ),
        request=_file_binding(
            request_path.relative_to(root).as_posix(),
            request_bytes,
            request_provenance_path.relative_to(root).as_posix(),
            request_provenance,
        ),
        plan=_file_binding(
            plan_path.relative_to(root).as_posix(),
            plan_bytes,
            plan_provenance_path.relative_to(root).as_posix(),
            plan_provenance,
        ),
        available_states=list(EXPRESSION_STATES),
        assets=assets,
        dialogue=request.dialogue,
        review=DialogueCharacterBundlePendingReview(),
        rights=RightsState(aggregate="unreviewed", publication_authorized=False),
    )
    bundle_bytes = canonical_json_bytes(bundle) + b"\n"
    if _existing_immutable_pair(output, bundle_bytes, "dialogue character package"):
        return {
            "schema_version": 1,
            "kind": "dialogue-character-package-result-v1",
            "bundle_path": str(output),
            "bundle_sha256": content_sha256(bundle_bytes),
            "publication_authorized": False,
        }
    inputs = [
        _input(spike_relative, spike_bytes, "application/json"),
        _input(request_path.relative_to(root).as_posix(), request_bytes, "application/json"),
        _input(plan_path.relative_to(root).as_posix(), plan_bytes, "application/json"),
        *[
            item
            for asset in bundle.assets
            for item in (
                _input(
                    asset.path,
                    _read_relative(root, asset.path, "character asset"),
                    "image/png",
                ),
                _input(
                    asset.provenance_path,
                    _read_relative(root, asset.provenance_path, "character asset provenance"),
                    "application/json",
                ),
            )
        ],
    ]
    provenance = ProvenanceInput(
        schema_version=2,
        provider="local",
        model="deterministic-dialogue-character-package-v1",
        prompt="Package four validated dialogue character states into a portable bundle.",
        refs=[spike_relative, request_path.name, plan_path.name],
        inputs=inputs,
        params={
            "source_spike_sha256": content_sha256(spike_bytes),
            "request_sha256": content_sha256(request_bytes),
            "plan_sha256": content_sha256(plan_bytes),
            "identity_sha256": spike.character.identity_reference.sha256,
            "run_identity_sha256": run_identity_sha256,
            "asset_sha256": [asset.sha256 for asset in bundle.assets],
        },
        validation={
            "strict_contract": True,
            "locked_states": list(EXPRESSION_STATES),
            "assets_verified": 4,
            "publication_authorized": False,
        },
        component=_COMPONENT,
        tool=_TOOL,
        attempts=1,
        rights=_unreviewed_rights(),
    )
    _write_pair(output, bundle_bytes, provenance)
    return {
        "schema_version": 1,
        "kind": "dialogue-character-package-result-v1",
        "bundle_path": str(output),
        "bundle_sha256": content_sha256(bundle_bytes),
        "publication_authorized": False,
    }


def review_dialogue_character_bundle(
    bundle_path: str | Path,
    *,
    review_path: str | Path,
    acceptance_spec_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, object]:
    """Apply one exact independent local-demo review and derive a reviewed bundle."""

    bundle_path = Path(bundle_path).absolute()
    if bundle_path.name != "dialogue-character.bundle.json":
        raise ValueError("source bundle must be dialogue-character.bundle.json")
    root = bundle_path.parent
    output = (
        Path(output_path).absolute()
        if output_path is not None
        else root / ("dialogue-character.bundle.reviewed.json")
    )
    if output.parent != root or output.name != "dialogue-character.bundle.reviewed.json":
        raise ValueError(
            "reviewed bundle output must equal RUN/dialogue-character.bundle.reviewed.json"
        )
    bundle_bytes = _read_regular(bundle_path, "dialogue character bundle")
    _read_bound_provenance(
        Path(f"{bundle_path}.meta.json"), bundle_bytes, "dialogue character bundle"
    )
    bundle = _parse(DialogueCharacterBundle, bundle_bytes, "dialogue character bundle")
    if bundle.review.status != "pending":
        raise ValueError("source dialogue character bundle review must be pending")
    _validate_bundle_files(root, bundle)

    review_input_path = Path(review_path).absolute()
    review_output = root / "dialogue-character.review.json"
    if review_input_path in {review_output, output}:
        raise ValueError("independent review input must be outside derived review outputs")
    supplied_review = _parse(
        DialogueCharacterIndependentReview,
        _read_regular(review_input_path, "independent dialogue character review"),
        "independent dialogue character review",
    )
    acceptance_bytes = _read_regular(Path(acceptance_spec_path).absolute(), "acceptance spec")
    if not acceptance_bytes:
        raise ValueError("acceptance spec must be non-empty")
    source_sha256 = content_sha256(bundle_bytes)
    acceptance_sha256 = content_sha256(acceptance_bytes)
    if supplied_review.source_bundle_sha256 != source_sha256:
        raise ValueError("review source_bundle_sha256 does not match the character bundle")
    if supplied_review.acceptance_spec_sha256 != acceptance_sha256:
        raise ValueError("review acceptance_spec_sha256 does not match the acceptance spec")
    expected_assets = [asset.sha256 for asset in bundle.assets]
    if supplied_review.asset_sha256 != expected_assets:
        raise ValueError("review asset_sha256 must bind all four assets in locked state order")

    review_bytes = canonical_json_bytes(supplied_review) + b"\n"
    review_provenance = ProvenanceInput(
        schema_version=2,
        provider="local",
        model="deterministic-dialogue-character-review-v1",
        prompt="Record an independent digest-bound dialogue character review for local demo use.",
        refs=[bundle_path.name],
        inputs=[
            _input(bundle_path.name, bundle_bytes, "application/json"),
            _input("acceptance-spec", acceptance_bytes, "application/json"),
        ],
        params={
            "usage": "local-demo",
            "source_bundle_sha256": source_sha256,
            "acceptance_spec_sha256": acceptance_sha256,
            "asset_sha256": expected_assets,
        },
        validation={
            "status": "pass",
            "independent_reviewer": True,
            "assets_verified": 4,
            "publication_authorized": False,
        },
        component=_REVIEW_COMPONENT,
        tool=_TOOL,
        timestamp=supplied_review.reviewed_at,
        attempts=1,
        rights=_restricted_rights(supplied_review.reviewed_at),
    )
    review_record = build_artifact_provenance(
        BinaryArtifact(data=review_bytes, media_type="application/json"), review_provenance
    )
    review_provenance_bytes = serialize_provenance(review_record)

    reviewed = DialogueCharacterBundle.model_validate(
        {
            **bundle.model_dump(mode="json", exclude_none=True),
            "review": DialogueCharacterBundlePassedReview(
                status="pass",
                usage="local-demo",
                path="dialogue-character.review.json",
                sha256=content_sha256(review_bytes),
                provenance_path="dialogue-character.review.json.meta.json",
                provenance_sha256=content_sha256(review_provenance_bytes),
                acceptance_spec_sha256=acceptance_sha256,
            ).model_dump(mode="json"),
            "rights": RightsState(aggregate="restricted", publication_authorized=False).model_dump(
                mode="json"
            ),
        }
    )
    reviewed_bytes = canonical_json_bytes(reviewed) + b"\n"
    reviewed_provenance = ProvenanceInput(
        schema_version=2,
        provider="local",
        model="deterministic-dialogue-character-reviewed-bundle-v1",
        prompt="Bind the passing local-demo review to the dialogue character bundle.",
        refs=[bundle_path.name, review_output.name],
        inputs=[
            _input(bundle_path.name, bundle_bytes, "application/json"),
            _input(review_output.name, review_bytes, "application/json"),
            _input(
                f"{review_output.name}.meta.json",
                review_provenance_bytes,
                "application/json",
            ),
            _input("acceptance-spec", acceptance_bytes, "application/json"),
        ],
        params={
            "source_bundle_sha256": source_sha256,
            "source_review_sha256": content_sha256(review_bytes),
            "acceptance_spec_sha256": acceptance_sha256,
        },
        validation={
            "status": "pass",
            "usage": "local-demo",
            "rights": "restricted",
            "publication_authorized": False,
        },
        component=_REVIEW_COMPONENT,
        tool=_TOOL,
        timestamp=supplied_review.reviewed_at,
        attempts=1,
        rights=_restricted_rights(supplied_review.reviewed_at),
    )
    reviewed_record = build_artifact_provenance(
        BinaryArtifact(data=reviewed_bytes, media_type="application/json"),
        reviewed_provenance,
    )
    _persist_immutable(
        (
            AtomicBundleFile(review_output, review_bytes),
            AtomicBundleFile(f"{review_output}.meta.json", review_provenance_bytes),
            AtomicBundleFile(output, reviewed_bytes),
            AtomicBundleFile(f"{output}.meta.json", serialize_provenance(reviewed_record)),
        ),
        label="dialogue character review transition",
    )
    if _read_regular(bundle_path, "dialogue character bundle") != bundle_bytes:
        raise RuntimeError("source dialogue character bundle changed during review")
    return {
        "schema_version": 1,
        "kind": "dialogue-character-review-result-v1",
        "source_bundle_sha256": source_sha256,
        "reviewed_bundle_path": str(output),
        "reviewed_bundle_sha256": content_sha256(reviewed_bytes),
        "review_path": str(review_output),
        "source_review_sha256": content_sha256(review_bytes),
        "publication_authorized": False,
    }


def load_reviewed_dialogue_character_bundle(
    bundle_path: str | Path,
) -> tuple[Path, bytes, DialogueCharacterBundle, ArtifactProvenance]:
    """Load and fully validate one reviewed bundle for a downstream adapter."""

    path = Path(bundle_path).absolute()
    if path.name != "dialogue-character.bundle.reviewed.json":
        raise ValueError("reviewed bundle must be dialogue-character.bundle.reviewed.json")
    data = _read_regular(path, "reviewed dialogue character bundle")
    provenance_bytes = _read_bound_provenance(
        Path(f"{path}.meta.json"), data, "reviewed dialogue character bundle"
    )
    provenance = _validate_provenance_bytes(
        provenance_bytes,
        data,
        "reviewed dialogue character bundle",
        "application/json",
    )
    bundle = _parse(DialogueCharacterBundle, data, "reviewed dialogue character bundle")
    if bundle.review.status != "pass" or bundle.rights != RightsState(
        aggregate="restricted", publication_authorized=False
    ):
        raise ValueError("dialogue character bundle is not approved for restricted local demo use")
    _validate_bundle_files(path.parent, bundle)
    assert bundle.review.status == "pass"
    review_bytes = _read_relative(path.parent, bundle.review.path, "character review")
    review = _parse(
        DialogueCharacterIndependentReview,
        review_bytes,
        "dialogue character review",
    )
    source_bundle_bytes = _read_regular(
        path.parent / "dialogue-character.bundle.json",
        "source dialogue character bundle",
    )
    source_bundle = _parse(
        DialogueCharacterBundle,
        source_bundle_bytes,
        "source dialogue character bundle",
    )
    if source_bundle.review.status != "pending" or source_bundle.rights != RightsState(
        aggregate="unreviewed", publication_authorized=False
    ):
        raise ValueError("source dialogue character bundle must remain pending and unpublished")
    if review.source_bundle_sha256 != content_sha256(source_bundle_bytes):
        raise ValueError("review source bundle digest does not match the original bundle")
    source_projection = source_bundle.model_dump(mode="json")
    reviewed_projection = bundle.model_dump(mode="json")
    for projection in (source_projection, reviewed_projection):
        projection.pop("review")
        projection.pop("rights")
    if reviewed_projection != source_projection:
        raise ValueError("reviewed dialogue character bundle changes the source projection")
    if review.acceptance_spec_sha256 != bundle.review.acceptance_spec_sha256:
        raise ValueError("review acceptance digest does not match the reviewed bundle")

    review_provenance_bytes = _read_relative(
        path.parent,
        bundle.review.provenance_path,
        "dialogue character review provenance",
    )
    review_provenance = _validate_provenance_bytes(
        review_provenance_bytes,
        review_bytes,
        "dialogue character review",
        "application/json",
    )
    _validate_restricted_provenance(
        review_provenance,
        reviewed_at=review.reviewed_at,
        label="dialogue character review",
    )
    review_inputs = _provenance_input_tuples(review_provenance, label="dialogue character review")
    if set(review_inputs) != {"dialogue-character.bundle.json", "acceptance-spec"}:
        raise ValueError("dialogue character review provenance input bindings mismatch")
    source_tuple = _content_tuple(source_bundle_bytes, "application/json")
    if review_inputs["dialogue-character.bundle.json"] != source_tuple:
        raise ValueError("dialogue character review provenance input bindings mismatch")
    acceptance_tuple = review_inputs["acceptance-spec"]
    if (
        acceptance_tuple[0] != review.acceptance_spec_sha256
        or acceptance_tuple[2] != "application/json"
    ):
        raise ValueError("dialogue character review provenance input bindings mismatch")

    _validate_restricted_provenance(
        provenance,
        reviewed_at=review.reviewed_at,
        label="reviewed dialogue character bundle",
    )
    input_tuples = _provenance_input_tuples(provenance, label="reviewed dialogue character bundle")
    expected_inputs = {
        "dialogue-character.bundle.json": source_tuple,
        "dialogue-character.review.json": _content_tuple(review_bytes, "application/json"),
        "dialogue-character.review.json.meta.json": _content_tuple(
            review_provenance_bytes, "application/json"
        ),
        "acceptance-spec": acceptance_tuple,
    }
    if input_tuples != expected_inputs:
        raise ValueError("reviewed bundle provenance input bindings mismatch")
    if provenance.params.get("source_bundle_sha256") != review.source_bundle_sha256:
        raise ValueError("reviewed bundle provenance source digest mismatch")
    if provenance.params.get("source_review_sha256") != bundle.review.sha256:
        raise ValueError("reviewed bundle provenance review digest mismatch")
    if provenance.params.get("acceptance_spec_sha256") != review.acceptance_spec_sha256:
        raise ValueError("reviewed bundle provenance acceptance digest mismatch")
    return path, data, bundle, provenance


def _content_tuple(data: bytes, media_type: str) -> tuple[str, int, str]:
    return content_sha256(data), len(data), media_type


def _provenance_input_tuples(
    provenance: ArtifactProvenance, *, label: str
) -> dict[str, tuple[str, int, str]]:
    result: dict[str, tuple[str, int, str]] = {}
    for item in provenance.inputs:
        if (
            item.ref in result
            or item.source != "content"
            or item.bytes is None
            or item.media_type is None
        ):
            raise ValueError(f"{label} provenance input bindings mismatch")
        result[item.ref] = (item.sha256, item.bytes, item.media_type)
    return result


def _validate_restricted_provenance(
    provenance: ArtifactProvenance, *, reviewed_at: str, label: str
) -> None:
    if provenance.rights != _restricted_rights(reviewed_at):
        raise ValueError(f"{label} provenance rights must be restricted to local demo use")
    if provenance.validation.get("publication_authorized") is not False:
        raise ValueError(f"{label} provenance must not authorize publication")


def _validate_bundle_files(root: Path, bundle: DialogueCharacterBundle) -> None:
    for binding, label in (
        (bundle.source_spike, "source spike"),
        (bundle.request, "request"),
        (bundle.plan, "plan"),
    ):
        data = _read_relative(root, binding.path, label)
        if content_sha256(data) != binding.sha256:
            raise ValueError(f"dialogue character {label} digest mismatch")
        provenance = _read_relative(root, binding.provenance_path, f"{label} provenance")
        if content_sha256(provenance) != binding.provenance_sha256:
            raise ValueError(f"dialogue character {label} provenance digest mismatch")
        _validate_provenance_bytes(provenance, data, label, "application/json")
    for asset in bundle.assets:
        _validate_asset(root, asset)
    if bundle.review.status == "pass":
        review_data = _read_relative(root, bundle.review.path, "character review")
        if content_sha256(review_data) != bundle.review.sha256:
            raise ValueError("dialogue character review digest mismatch")
        review_provenance = _read_relative(
            root, bundle.review.provenance_path, "character review provenance"
        )
        if content_sha256(review_provenance) != bundle.review.provenance_sha256:
            raise ValueError("dialogue character review provenance digest mismatch")
        _validate_provenance_bytes(
            review_provenance, review_data, "character review", "application/json"
        )
        review = _parse(
            DialogueCharacterIndependentReview, review_data, "dialogue character review"
        )
        if review.asset_sha256 != [asset.sha256 for asset in bundle.assets]:
            raise ValueError("dialogue character review asset bindings mismatch")


def _validate_asset(root: Path, asset: DialogueCharacterAsset) -> DialogueCharacterAsset:
    data = _read_relative(root, asset.path, f"dialogue character {asset.state} asset")
    if content_sha256(data) != asset.sha256 or len(data) != asset.bytes:
        raise ValueError(f"dialogue character {asset.state} asset digest or size mismatch")
    facts = inspect_image(data, expected_media_type="image/png")
    if (facts.width, facts.height, facts.has_alpha) != (1024, 1536, True):
        raise ValueError(f"dialogue character {asset.state} asset media contract mismatch")
    provenance = _read_relative(
        root, asset.provenance_path, f"dialogue character {asset.state} provenance"
    )
    if content_sha256(provenance) != asset.provenance_sha256:
        raise ValueError(f"dialogue character {asset.state} provenance digest mismatch")
    _validate_provenance_bytes(provenance, data, f"dialogue character {asset.state}", "image/png")
    return asset


def _read_bound_relative(root: Path, relative: str, label: str) -> tuple[Path, bytes, Path, bytes]:
    path = resolve_relative_path_within_root(root, relative, label)
    data = _read_regular(path, label)
    provenance_path = Path(f"{path}.meta.json")
    provenance = _read_bound_provenance(provenance_path, data, label)
    return path, data, provenance_path, provenance


def _read_bound_provenance(path: Path, artifact: bytes, label: str) -> bytes:
    data = _read_regular(path, f"{label} provenance")
    _validate_provenance_bytes(data, artifact, label, "application/json")
    return data


def _validate_provenance_bytes(
    data: bytes, artifact: bytes, label: str, media_type: str
) -> ArtifactProvenance:
    try:
        record = ArtifactProvenance.model_validate_json(data)
    except ValidationError as error:
        raise ValueError(f"invalid {label} provenance: {error}") from None
    if record.schema_version != 2:
        raise ValueError(f"{label} provenance must use schema_version 2")
    expected = (content_sha256(artifact), len(artifact), media_type)
    actual = (
        (
            record.artifact.sha256,
            record.artifact.bytes,
            record.artifact.media_type,
        )
        if record.artifact is not None
        else None
    )
    if actual != expected:
        raise ValueError(f"{label} provenance artifact digest mismatch")
    return record


def _read_regular(path: Path, label: str) -> bytes:
    return read_absolute_regular_file(path, label=label)


def _read_relative(root: Path, relative: str, label: str) -> bytes:
    path = resolve_relative_path_within_root(root, relative, label)
    return _read_regular(path, label)


def _file_binding(
    path: str, data: bytes, provenance_path: str, provenance: bytes
) -> DialogueCharacterFile:
    return DialogueCharacterFile(
        path=path,
        sha256=content_sha256(data),
        provenance_path=provenance_path,
        provenance_sha256=content_sha256(provenance),
    )


def _input(ref: str, data: bytes, media_type: str) -> InputProvenance:
    return InputProvenance(
        ref=ref,
        sha256=content_sha256(data),
        source="content",
        bytes=len(data),
        media_type=media_type,
    )


def _unreviewed_rights() -> ArtifactRights:
    return ArtifactRights(
        status="unreviewed",
        license_id=None,
        notice="Independent review and a separate rights decision are required before use.",
        attribution=[],
        basis=[],
        reviewed_at=None,
    )


def _restricted_rights(reviewed_at: str) -> ArtifactRights:
    return ArtifactRights(
        status="restricted",
        license_id=None,
        notice="Restricted to local demo use; publication is not authorized.",
        attribution=[],
        basis=["Independent digest-bound review passed for local demo use."],
        reviewed_at=reviewed_at,
    )


def _write_pair(path: Path, data: bytes, provenance: ProvenanceInput) -> None:
    record = build_artifact_provenance(
        BinaryArtifact(data=data, media_type="application/json"), provenance
    )
    _persist_immutable(
        (
            AtomicBundleFile(path, data),
            AtomicBundleFile(f"{path}.meta.json", serialize_provenance(record)),
        ),
        label="dialogue character package",
    )


def _persist_immutable(entries: tuple[AtomicBundleFile, ...], *, label: str) -> None:
    existing: list[bool] = []
    for entry in entries:
        path = Path(entry.path)
        try:
            current = _read_regular(path, label)
        except ValueError:
            if path.exists() or path.is_symlink():
                raise
            existing.append(False)
            continue
        existing.append(True)
        if current != entry.data:
            raise ValueError(f"conflicting immutable {label} output: {path.name}")
    if all(existing):
        return
    if any(existing):
        raise ValueError(f"partial immutable {label} output already exists")
    atomic_write_bundle(entries)


def _existing_immutable_pair(path: Path, data: bytes, label: str) -> bool:
    sidecar = Path(f"{path}.meta.json")
    states = (path.exists() or path.is_symlink(), sidecar.exists() or sidecar.is_symlink())
    if not any(states):
        return False
    if not all(states):
        raise ValueError(f"partial immutable {label} output already exists")
    current = _read_regular(path, label)
    if current != data:
        raise ValueError(f"conflicting immutable {label} output: {path.name}")
    provenance = _read_regular(sidecar, f"{label} provenance")
    _validate_provenance_bytes(provenance, current, label, "application/json")
    return True


def _parse[ModelT: BaseModel](model: type[ModelT], data: bytes, label: str) -> ModelT:
    try:
        return model.model_validate_json(data)
    except ValidationError as error:
        raise ValueError(f"invalid {label}: {error}") from None

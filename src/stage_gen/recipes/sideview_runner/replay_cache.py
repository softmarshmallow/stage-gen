"""Audited, provider-free migration of an accepted runner run into today's cache.

This is deliberately narrower than a general replay facility.  It exists for the case where
provider bytes have already passed independent semantic review, while the recipe's cache
contract subsequently tightened.  The migration replays every current request against the
recorded response, runs today's caller validators, reconstructs mixed local/provider nodes with
today's handler, and seeds only provider-node cache records.  A second ordinary handler run then
proves those records are hits while every local node executes normally.

No provider adapter is constructed.  A request mismatch is terminal; this module never falls
through to a live route and never weakens a current validator to admit historical output.
"""

from __future__ import annotations

import base64
import json
import os
import re
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from gnode import (
    ArtifactProvenance,
    BinaryArtifact,
    CacheDisposition,
    JsonlTraceSink,
    NodeExecutionResult,
    Scheduler,
    assert_audio_signature,
    assert_image_signature,
    atomic_write_bytes,
    atomic_write_json,
    resolve_relative_path_within_root,
    run_validator,
    serialize_provenance,
    write_graph,
    write_run_summary,
)
from stage_gen.components._secure_fs import SecurePathError, read_absolute_regular_file
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_runner.prepared_runner import (
    RUNNER_HANDLER_VERSION,
    SideviewRunnerNodeHandler,
)
from stage_gen.recipes.sideview_runner.runner_executor import (
    SideviewRunnerExecutor,
    SideviewRunnerPlan,
)
from stage_gen.recipes.sideview_runner.runner_graph import (
    RUNNER_CACHE_NAMESPACE,
    RunnerOperationKind,
    SideviewRunnerGraph,
    runner_graph_profile,
)
from stage_gen.recipes.sideview_runner.runner_types import runner_type_index

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gnode import (
        ImageGenerationRequest,
        MusicGenerationRequest,
        Node,
        NodeExecutionContext,
        RunSummary,
        SoundEffectGenerationRequest,
        StructuredGenerationRequest,
    )

REPLAY_AUDIT_KIND = "sideview-runner-provider-cache-replay-audit-v1"
REPLAY_LINK_KIND = "sideview-runner-listening-review-link-v1"
_PROVIDER_IDENTITY_FIELDS = (
    "schema_version",
    "provider",
    "model",
    "seed",
    "prompt",
    "prompt_sha256",
    "references",
    "refs",
    "inputs",
    "params",
    "validation",
    "component",
    "tool",
    "rights",
)
_HISTORICAL_PROVIDER_FIELDS = (
    "artifact",
    "response",
    "attempts",
    "retries",
    "ts",
    "rights",
)


class ProviderReplayMismatch(ValueError):
    """A recorded result did not describe the exact current provider request."""


@dataclass(frozen=True, slots=True)
class ProviderReplayResult:
    """The completed cache migration and its provider-free current-graph run."""

    staging_run: Path
    cache_dir: Path
    output_run: Path
    audit_path: Path
    seed_summary: RunSummary
    output_summary: RunSummary


def _json_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return sha256(encoded).hexdigest()


def _json_value(value: object, label: str) -> object:
    try:
        return json.loads(
            json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProviderReplayMismatch(f"{label} is not standards-compliant JSON") from error


def _same_resolved_path(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def _paths_overlap(left: Path, right: Path) -> bool:
    resolved_left = left.resolve()
    resolved_right = right.resolve()
    return (
        resolved_left == resolved_right
        or resolved_left in resolved_right.parents
        or resolved_right in resolved_left.parents
    )


def _assert_disjoint_replay_paths(
    *,
    source_run: Path,
    structured_sidecar_run: Path,
    staging_run: Path,
    cache_dir: Path,
    output_run: Path,
) -> None:
    destinations = {
        "staging run": staging_run,
        "cache directory": cache_dir,
        "output run": output_run,
    }
    sources = {
        "source run": source_run,
        "structured-sidecar source run": structured_sidecar_run,
    }
    for destination_label, destination in destinations.items():
        for source_label, source in sources.items():
            if _paths_overlap(destination, source):
                raise ProviderReplayMismatch(
                    f"{destination_label} must not overlap immutable {source_label}"
                )
    destination_items = list(destinations.items())
    for index, (left_label, left) in enumerate(destination_items):
        for right_label, right in destination_items[index + 1 :]:
            if _paths_overlap(left, right):
                raise ProviderReplayMismatch(f"{left_label} and {right_label} must not overlap")


def _bytes_record(ref: str, data: bytes, *, media_type: str | None = None) -> dict[str, object]:
    record: dict[str, object] = {
        "ref": ref,
        "sha256": sha256(data).hexdigest(),
        "bytes": len(data),
    }
    if media_type is not None:
        record["media_type"] = media_type
    return record


def _decode_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderReplayMismatch(f"{label} is not readable JSON") from error
    if not isinstance(value, dict):
        raise ProviderReplayMismatch(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _read_confined_file(root: Path, ref: str, label: str) -> bytes:
    """Read one immutable bundle member without following any symlink."""

    try:
        path = resolve_relative_path_within_root(root, ref, label)
        return read_absolute_regular_file(path, label=label)
    except (OSError, SecurePathError, ValueError) as error:
        raise ProviderReplayMismatch(
            f"{label} must be a confined regular non-symlink file"
        ) from error


def _read_confined_object(root: Path, ref: str, label: str) -> tuple[dict[str, Any], bytes]:
    data = _read_confined_file(root, ref, label)
    return _decode_object(data, label), data


def _confined_ref_for_path(root: Path, path: Path, label: str) -> str:
    """Turn a caller path into a portable ref while rejecting lexical traversal."""

    if any(part in {".", ".."} for part in path.parts):
        raise ProviderReplayMismatch(f"{label} must not contain dot or parent path segments")
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as error:
        raise ProviderReplayMismatch(
            f"{label} must remain inside its immutable source run"
        ) from error
    ref = relative.as_posix()
    try:
        resolve_relative_path_within_root(root, ref, label)
    except ValueError as error:
        raise ProviderReplayMismatch(
            f"{label} must remain inside its immutable source run"
        ) from error
    return ref


def _require_equal(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ProviderReplayMismatch(
            f"{label} differs (actual={_json_digest(actual)}, expected={_json_digest(expected)})"
        )


def _provider_identity(record: ArtifactProvenance) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "provider": record.provider,
        "model": record.model,
        "seed": record.seed,
        "prompt": record.prompt,
        "prompt_sha256": record.prompt_sha256,
        "references": record.references,
        "refs": record.refs,
        "inputs": [item.model_dump(mode="json", exclude_none=True) for item in record.inputs],
        "params": record.params,
        "validation": record.validation,
        "component": record.component.model_dump(mode="json"),
        "tool": record.tool.model_dump(mode="json"),
        "rights": None if record.rights is None else record.rights.model_dump(mode="json"),
    }


def _historical_provider_fields(record: ArtifactProvenance) -> dict[str, object]:
    return {
        "artifact": (None if record.artifact is None else record.artifact.model_dump(mode="json")),
        "response": record.response,
        "attempts": record.attempts,
        "retries": record.retries,
        "ts": record.ts,
        "rights": None if record.rights is None else record.rights.model_dump(mode="json"),
    }


def _migrate_provider_sidecar(
    *,
    node_id: str,
    sidecar_ref: str,
    historical_data: bytes,
    artifact_data: bytes,
    expected_identity: Mapping[str, object],
    equivalent_ref_label_normalizations: list[dict[str, object]],
    historical_loop_mask_omission_reconstruction: dict[str, object] | None,
) -> tuple[bytes, dict[str, object]]:
    """Rewrite only request identity while retaining the accepted provider response facts."""

    historical_raw = _decode_object(historical_data, f"{node_id} historical provider sidecar")
    try:
        historical = ArtifactProvenance.model_validate(historical_raw)
    except ValueError as error:
        raise ProviderReplayMismatch(
            f"{node_id} historical provider sidecar fails provenance-v2"
        ) from error
    _require_equal(
        f"{node_id} current provider identity field set",
        sorted(expected_identity),
        sorted(_PROVIDER_IDENTITY_FIELDS),
    )
    historical_fields = _historical_provider_fields(historical)
    artifact = historical_fields["artifact"]
    if not isinstance(artifact, dict):
        raise ProviderReplayMismatch(f"{node_id} historical sidecar has no artifact binding")
    exact_artifact = {
        "sha256": sha256(artifact_data).hexdigest(),
        "bytes": len(artifact_data),
        "media_type": artifact.get("media_type"),
    }
    _require_equal(f"{node_id} historical artifact binding", artifact, exact_artifact)
    _require_equal(
        f"{node_id} historical rights",
        historical_fields["rights"],
        expected_identity.get("rights"),
    )

    migrated_raw = {
        **expected_identity,
        "artifact": exact_artifact,
        "response": historical.response,
        "attempts": historical.attempts,
        "retries": historical.retries,
        "ts": historical.ts,
    }
    try:
        migrated = ArtifactProvenance.model_validate(migrated_raw)
    except ValueError as error:
        raise ProviderReplayMismatch(
            f"{node_id} migrated provider sidecar fails current provenance-v2"
        ) from error
    migrated_data = serialize_provenance(migrated)
    reparsed_raw = _decode_object(migrated_data, f"{node_id} migrated provider sidecar")
    try:
        reparsed = ArtifactProvenance.model_validate(reparsed_raw)
    except ValueError as error:
        raise ProviderReplayMismatch(
            f"{node_id} serialized migrated sidecar fails current provenance-v2"
        ) from error
    migrated_identity = _provider_identity(reparsed)
    for field in _PROVIDER_IDENTITY_FIELDS:
        _require_equal(
            f"{node_id} migrated provider identity field {field}",
            migrated_identity[field],
            expected_identity[field],
        )
    _require_equal(f"{node_id} migrated provider identity", migrated_identity, expected_identity)
    migrated_fields = _historical_provider_fields(reparsed)
    for field in _HISTORICAL_PROVIDER_FIELDS:
        _require_equal(
            f"{node_id} preserved historical sidecar field {field}",
            migrated_fields[field],
            historical_fields[field],
        )

    historical_identity = _provider_identity(historical)
    exact_field_migration: list[dict[str, object]] = []
    for field in _PROVIDER_IDENTITY_FIELDS:
        historical_value = historical_identity[field]
        current_value = migrated_identity[field]
        reasons: list[str] = []
        if field in {"references", "refs", "inputs"}:
            if equivalent_ref_label_normalizations:
                reasons.append("equivalent_non_provider_ref_label_normalization")
            if historical_loop_mask_omission_reconstruction is not None:
                reasons.append("historical_loop_mask_omission_deterministically_reconstructed")
        if historical_value != current_value and not reasons:
            reasons.append("current_request_identity_revalidation")
        if historical_value == current_value:
            reasons.append("unchanged")
        exact_field_migration.append(
            {
                "field": field,
                "historical_value_sha256": _json_digest(historical_value),
                "current_value_sha256": _json_digest(current_value),
                "changed": historical_value != current_value,
                "reasons": reasons,
            }
        )

    preserved_fields = {
        field: {
            "historical_value_sha256": _json_digest(historical_fields[field]),
            "current_value_sha256": _json_digest(migrated_fields[field]),
            "exact": True,
        }
        for field in _HISTORICAL_PROVIDER_FIELDS
    }
    return (
        migrated_data,
        {
            "classification": "current_request_identity_migration",
            "historical_sidecar": _bytes_record(
                sidecar_ref, historical_data, media_type="application/json"
            ),
            "migrated_sidecar": _bytes_record(
                sidecar_ref, migrated_data, media_type="application/json"
            ),
            "historical_identity_sha256": _json_digest(historical_identity),
            "current_expected_identity_sha256": _json_digest(expected_identity),
            "migrated_identity_sha256": _json_digest(migrated_identity),
            "exact_field_migration": exact_field_migration,
            "preserved_historical_fields": preserved_fields,
            "equivalent_ref_label_normalizations": equivalent_ref_label_normalizations,
            "historical_loop_mask_omission_reconstruction": (
                historical_loop_mask_omission_reconstruction
            ),
        },
    )


def _data_reference_record(
    url: str,
    provenance_ref: str | None,
    *,
    role: str,
) -> tuple[dict[str, object], bytes]:
    header, separator, payload = url.partition(",")
    if not separator or not header.startswith("data:") or not header.endswith(";base64"):
        raise ProviderReplayMismatch("replay accepts only embedded base64 provider inputs")
    media_type = header[5:-7]
    try:
        data = base64.b64decode(payload, validate=True)
    except ValueError as error:
        raise ProviderReplayMismatch("provider input is not strict base64") from error
    if not media_type:
        raise ProviderReplayMismatch("provider input has no media type")
    ref = provenance_ref
    if ref is None or not ref.strip():
        raise ProviderReplayMismatch("provider input has no portable provenance reference")
    return (
        {
            **_bytes_record(ref, data, media_type=media_type),
            "role": role,
        },
        data,
    )


def _sidecar_input_shape(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "ref": record["ref"],
            "sha256": record["sha256"],
            "bytes": record["bytes"],
            "media_type": record["media_type"],
            "source": "content",
        }
        for record in records
    ]


def _primary_provider_port(node: Node) -> tuple[str, str]:
    if node.operation == RunnerOperationKind.IMAGE_GENERATION:
        port_id = (
            "edit_image" if any(port.port_id == "edit_image" for port in node.ports) else "image"
        )
    elif node.operation == RunnerOperationKind.STRUCTURED_GENERATION:
        port_id = (
            "verification"
            if any(port.port_id == "verification" for port in node.ports)
            else "reading"
        )
    elif node.operation in {
        RunnerOperationKind.MUSIC_GENERATION,
        RunnerOperationKind.SOUND_EFFECT_GENERATION,
    }:
        port_id = "audio"
    else:
        raise ProviderReplayMismatch(f"{node.node_id} is not a provider node")
    port = node.port(port_id)
    if port.sidecar_ref is None:
        raise ProviderReplayMismatch(f"{node.node_id}/{port_id} has no provenance sidecar")
    return port.artifact_ref, port.sidecar_ref


class _RecordedProviderCatalog:
    """Match current in-memory requests to immutable accepted provider records."""

    def __init__(
        self,
        plan: SideviewRunnerPlan,
        *,
        run_dir: Path,
        source_run: Path,
        structured_sidecar_run: Path,
        config: StageGenConfig,
    ) -> None:
        self._plan = plan
        self._run_dir = run_dir
        self._source_run = source_run
        self._structured_sidecar_run = structured_sidecar_run
        self._source_plan, self._source_plan_data = _read_confined_object(
            source_run, "execution-plan.json", "source plan"
        )
        self._structured_plan, self._structured_plan_data = _read_confined_object(
            structured_sidecar_run,
            "execution-plan.json",
            "structured-sidecar source plan",
        )
        try:
            self._source_graph = SideviewRunnerGraph.model_validate_json(self._source_plan_data)
            self._structured_graph = SideviewRunnerGraph.model_validate_json(
                self._structured_plan_data
            )
        except ValueError as error:
            raise ProviderReplayMismatch(
                "a source execution plan failed its sealed graph contract"
            ) from error
        self._source_nodes = self._index_plan_nodes(self._source_plan, "source plan")
        self._structured_nodes = self._index_plan_nodes(
            self._structured_plan, "structured-sidecar source plan"
        )
        self._nodes_by_output: dict[str, Node] = {}
        self._entries: dict[str, dict[str, object]] = {}
        self._completed: set[str] = set()
        self._source_card_gaps: set[str] = set()
        self._provider_service_calls = 0
        self._handler: SideviewRunnerNodeHandler | None = None
        self._migrated_sidecars: dict[str, bytes] = {}
        self._profile = {
            binding.operation: binding for binding in runner_graph_profile(config).bindings
        }
        self._types = runner_type_index()
        self._validate_plan_compatibility()

    def bind_current_handler(self, handler: SideviewRunnerNodeHandler) -> None:
        if self._handler is not None:
            raise ProviderReplayMismatch("replay catalog handler may be bound only once")
        self._handler = handler

    @property
    def source_plan_data(self) -> bytes:
        return self._source_plan_data

    @property
    def structured_plan_data(self) -> bytes:
        return self._structured_plan_data

    def migrated_sidecar_data(self, node_id: str) -> bytes:
        try:
            return self._migrated_sidecars[node_id]
        except KeyError as error:
            raise ProviderReplayMismatch(
                f"provider node {node_id} has no admitted migrated sidecar"
            ) from error

    @staticmethod
    def _index_plan_nodes(plan: Mapping[str, object], label: str) -> dict[str, dict[str, Any]]:
        raw = plan.get("nodes")
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise ProviderReplayMismatch(f"{label} has no node list")
        nodes = {cast(str, item.get("node_id")): cast(dict[str, Any], item) for item in raw}
        if None in nodes or len(nodes) != len(raw):
            raise ProviderReplayMismatch(f"{label} node ids must be present and unique")
        return nodes

    def _validate_plan_compatibility(self) -> None:
        current = [node for node in self._plan.graph.nodes if not node.is_local]
        source_ids = {
            node_id
            for node_id, node in self._source_nodes.items()
            if node.get("operation") != RunnerOperationKind.LOCAL
        }
        current_ids = {node.node_id for node in current}
        _require_equal("provider node id set", sorted(source_ids), sorted(current_ids))
        for node in current:
            source = self._source_nodes[node.node_id]
            current_document = node.model_dump(mode="json")
            for key in (
                "type_id",
                "operation",
                "resource_id",
                "provider",
                "model",
                "template_id",
                "params",
                "depends_on",
                "barrier_only",
                "retry_owner",
                "max_attempts",
            ):
                _require_equal(
                    f"{node.node_id} source {key}", source.get(key), current_document.get(key)
                )
            current_card = None if node.card is None else node.card.model_dump(mode="json")
            if source.get("card") is None and current_card is not None:
                # Several old plans omitted an executable card whose exact prompt was still
                # persisted by the provider sidecar.  Request replay below is authoritative.
                self._source_card_gaps.add(node.node_id)
            else:
                _require_equal(f"{node.node_id} source card", source.get("card"), current_card)
            artifact_ref, _sidecar_ref = _primary_provider_port(node)
            if artifact_ref in self._nodes_by_output:
                raise ProviderReplayMismatch(f"provider output ref is duplicated: {artifact_ref}")
            self._nodes_by_output[artifact_ref] = node
            if node.operation == RunnerOperationKind.STRUCTURED_GENERATION:
                structured_source = self._structured_nodes.get(node.node_id)
                if structured_source is None:
                    raise ProviderReplayMismatch(
                        f"structured-sidecar source plan has no {node.node_id}"
                    )
                for key in (
                    "type_id",
                    "operation",
                    "resource_id",
                    "provider",
                    "model",
                    "template_id",
                    "params",
                    "retry_owner",
                    "max_attempts",
                ):
                    _require_equal(
                        f"{node.node_id} structured-sidecar source {key}",
                        structured_source.get(key),
                        current_document.get(key),
                    )

    @property
    def provider_service_calls(self) -> int:
        return self._provider_service_calls

    @property
    def entries(self) -> list[dict[str, object]]:
        return [
            self._entries[node.node_id]
            for node in self._plan.graph.nodes
            if node.node_id in self._entries
        ]

    def assert_complete(self) -> None:
        expected = {node.node_id for node in self._plan.graph.nodes if not node.is_local}
        _require_equal("replayed provider node set", sorted(self._completed), sorted(expected))
        if self._provider_service_calls != len(expected):
            raise ProviderReplayMismatch("each provider node must be replayed exactly once")

    def finalize_cache_entry(
        self,
        node: Node,
        context: NodeExecutionContext,
        result: NodeExecutionResult,
        *,
        cache_record: dict[str, Any],
        cache_record_bytes: bytes,
    ) -> None:
        entry = self._entries[node.node_id]
        ledger_ref = next(
            port.artifact_ref for port in node.ports if port.kind == "attempt-ledger-v2"
        )
        ledger, ledger_data = _read_confined_object(
            self._run_dir, ledger_ref, f"{node.node_id} staged attempt ledger"
        )
        attempt_records = ledger.get("attempts", [])
        if not isinstance(attempt_records, list):
            raise ProviderReplayMismatch(f"{node.node_id} ledger attempts are not a list")
        selected = [item for item in attempt_records if item.get("outcome") == "selected"]
        not_selected = [item for item in attempt_records if item.get("outcome") == "not_selected"]
        _require_equal(
            f"{node.node_id} ledger provider operations", ledger.get("provider_operations"), 1
        )
        _require_equal(f"{node.node_id} ledger attempts", len(attempt_records), 1)
        output_selection = ledger.get("output_selection")
        if output_selection == "provider_output":
            _require_equal(f"{node.node_id} ledger selected entries", len(selected), 1)
            _require_equal(f"{node.node_id} ledger rejected entries", len(not_selected), 0)
        elif output_selection == "fallback_output":
            _require_equal(f"{node.node_id} ledger selected entries", len(selected), 0)
            _require_equal(f"{node.node_id} ledger rejected entries", len(not_selected), 1)
            if not any(port.port_id == "loop_report" for port in node.ports):
                raise ProviderReplayMismatch(
                    f"{node.node_id} claims fallback output outside a mixed loop node"
                )
            report, _report_document_data = _read_confined_object(
                self._run_dir,
                node.port("loop_report").artifact_ref,
                f"{node.node_id} loop report",
            )
            _require_equal(
                f"{node.node_id} rejected construction",
                report.get("rejected_construction"),
                node.params.get("construction"),
            )
            _require_equal(
                f"{node.node_id} fallback provider operations",
                report.get("provider_operations"),
                1,
            )
            attempt = not_selected[0]
            _require_equal(
                f"{node.node_id} rejected attempt prompt hash",
                attempt.get("prompt_sha256"),
                ledger.get("prompt_sha256"),
            )
            _require_equal(
                f"{node.node_id} rejected attempt reason",
                attempt.get("reason"),
                "provider attempt did not produce the selected output",
            )
            rejection = report.get("rejection")
            if not isinstance(rejection, str):
                raise ProviderReplayMismatch(f"{node.node_id} fallback has no rejection reason")
            offset_match = re.search(
                r"vertical offset \((-?\d+) vs (-?\d+), tolerance (\d+)\)", rejection
            )
            if offset_match is None:
                raise ProviderReplayMismatch(
                    f"{node.node_id} fallback lacks the expected registration-offset facts"
                )
            loop_port = node.port("loop_image")
            if loop_port.sidecar_ref is None:
                raise ProviderReplayMismatch(f"{node.node_id} loop output has no sidecar")
            loop_data = _read_confined_file(
                self._run_dir, loop_port.artifact_ref, f"{node.node_id} loop output"
            )
            loop_sidecar_data = _read_confined_file(
                self._run_dir,
                loop_port.sidecar_ref,
                f"{node.node_id} loop output sidecar",
            )
            report_data = _read_confined_file(
                self._run_dir,
                node.port("loop_report").artifact_ref,
                f"{node.node_id} loop output report",
            )
            entry["provider_output_rejection"] = {
                "classification": "current_validator_selected_deterministic_fallback",
                "requested_construction": node.params.get("construction"),
                "published_construction": report.get("construction"),
                "reason": rejection,
                "registration_facts": {
                    "left_context_vertical_offset": int(offset_match.group(1)),
                    "right_context_vertical_offset": int(offset_match.group(2)),
                    "tolerance": int(offset_match.group(3)),
                },
                "algorithm_identity": {
                    "provider_assembly": "assemble_generated_bridge@generated-bridge-v1",
                    "fallback": "mirror_repeat@mirror-repeat-v1",
                    "repeat_validator_version": cast(
                        dict[str, object], report.get("repeat", {})
                    ).get("validator_version"),
                    "node_contract_version": self._types[node.type_id].contract_version,
                },
                "published_fallback_bundle": {
                    "image": _bytes_record(
                        loop_port.artifact_ref, loop_data, media_type="image/png"
                    ),
                    "sidecar": _bytes_record(
                        loop_port.sidecar_ref,
                        loop_sidecar_data,
                        media_type="application/json",
                    ),
                    "report": _bytes_record(
                        node.port("loop_report").artifact_ref,
                        report_data,
                        media_type="application/json",
                    ),
                },
            }
        else:
            raise ProviderReplayMismatch(
                f"{node.node_id} ledger has unsupported output selection {output_selection!r}"
            )
        entry["attempt_ledger"] = _bytes_record(
            ledger_ref, ledger_data, media_type="application/json"
        )
        cast(dict[str, object], entry["migration"])["output_selection"] = output_selection
        entry["current_lineage"] = cache_record.get("lineage")
        entry["cache_record"] = {
            "sha256": sha256(cache_record_bytes).hexdigest(),
            "bytes": len(cache_record_bytes),
            "artifact_bundle": [item.model_dump(mode="json") for item in result.artifacts],
        }
        entry["dependency_result_sha256"] = {
            dependency: [
                artifact.sha256 for artifact in context.dependency_results[dependency].artifacts
            ]
            for dependency in node.depends_on
        }

    def _node_for_request(self, artifact_path: str | Path, operation: RunnerOperationKind) -> Node:
        path = Path(artifact_path)
        try:
            ref = path.relative_to(self._run_dir).as_posix()
        except ValueError as error:
            raise ProviderReplayMismatch("replay artifact path escaped the staging run") from error
        node = self._nodes_by_output.get(ref)
        if node is None or node.operation != operation:
            raise ProviderReplayMismatch(f"no current {operation} node owns provider output {ref}")
        if node.node_id in self._completed:
            raise ProviderReplayMismatch(f"provider node replayed twice: {node.node_id}")
        return node

    def _recorded(self, node: Node) -> tuple[bytes, bytes, dict[str, Any], str, str]:
        artifact_ref, sidecar_ref = _primary_provider_port(node)
        sidecar_root = (
            self._structured_sidecar_run
            if node.operation == RunnerOperationKind.STRUCTURED_GENERATION
            else self._source_run
        )
        artifact_data = _read_confined_file(
            self._source_run,
            artifact_ref,
            f"{node.node_id} historical provider artifact",
        )
        sidecar, sidecar_data = _read_confined_object(
            sidecar_root,
            sidecar_ref,
            f"{node.node_id} historical provider sidecar",
        )
        artifact = sidecar.get("artifact")
        expected_artifact = {
            "sha256": sha256(artifact_data).hexdigest(),
            "bytes": len(artifact_data),
            "media_type": artifact.get("media_type") if isinstance(artifact, dict) else None,
        }
        _require_equal(f"{node.node_id} sidecar artifact", artifact, expected_artifact)
        _require_equal(f"{node.node_id} recorded attempts", sidecar.get("attempts"), 1)
        return artifact_data, sidecar_data, sidecar, artifact_ref, sidecar_ref

    def _migrate_recorded_sidecar(
        self,
        node: Node,
        *,
        artifact_data: bytes,
        historical_sidecar_data: bytes,
        historical_sidecar: Mapping[str, Any],
        sidecar_ref: str,
        bundle: Mapping[str, bytes] | None = None,
        equivalent_ref_label_normalizations: list[dict[str, object]],
        historical_loop_mask_omission_reconstruction: dict[str, object] | None,
    ) -> tuple[bytes, dict[str, object], dict[str, object]]:
        if self._handler is None:
            raise ProviderReplayMismatch("current replay handler was not bound")
        response = historical_sidecar.get("response")
        if response is not None and not isinstance(response, dict):
            raise ProviderReplayMismatch(
                f"{node.node_id} historical provider response is not an object"
            )
        try:
            expected_identity = self._handler.expected_provider_provenance_identity(
                node,
                artifact_data,
                bundle=bundle,
                provider_response=cast("Mapping[str, object] | None", response),
            )
        except (OSError, ValueError) as error:
            raise ProviderReplayMismatch(
                f"{node.node_id} current provider provenance identity was not reproducible"
            ) from error
        migrated_data, migration = _migrate_provider_sidecar(
            node_id=node.node_id,
            sidecar_ref=sidecar_ref,
            historical_data=historical_sidecar_data,
            artifact_data=artifact_data,
            expected_identity=expected_identity,
            equivalent_ref_label_normalizations=equivalent_ref_label_normalizations,
            historical_loop_mask_omission_reconstruction=(
                historical_loop_mask_omission_reconstruction
            ),
        )
        if node.node_id in self._migrated_sidecars:
            raise ProviderReplayMismatch(f"provider sidecar migrated twice: {node.node_id}")
        self._migrated_sidecars[node.node_id] = migrated_data
        return migrated_data, expected_identity, migration

    def _compare_ordered_inputs(
        self,
        node: Node,
        historical: object,
        current: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Compare provider input content and prove any authored-ref identity hardening.

        ``provenance_ref`` is never transmitted to the provider.  Historical runner plans used
        the authored card label there; current plans use a portable package URI.  That one
        metadata-only change is admitted only when both names resolve through their respective
        plan cards to the same package path and digest.  Every transmitted byte fact stays exact.
        """

        if not isinstance(historical, list) or len(historical) != len(current):
            raise ProviderReplayMismatch(f"{node.node_id} ordered provider input count differs")
        source_card = self._source_nodes[node.node_id].get("card")
        source_authored = (
            source_card.get("authored_inputs", []) if isinstance(source_card, dict) else []
        )
        current_authored = () if node.card is None else node.card.authored_inputs
        migrations: list[dict[str, object]] = []
        for index, (old, new) in enumerate(zip(historical, current, strict=True)):
            if not isinstance(old, dict):
                raise ProviderReplayMismatch(
                    f"{node.node_id} historical provider input {index} is not an object"
                )
            expected_content = {
                "sha256": new["sha256"],
                "source": "content",
                "bytes": new["bytes"],
                "media_type": new["media_type"],
            }
            _require_equal(
                f"{node.node_id} provider input {index} bytes and MIME",
                {key: old.get(key) for key in expected_content},
                expected_content,
            )
            old_ref = old.get("ref")
            new_ref = new["ref"]
            if old_ref == new_ref:
                continue
            if not isinstance(old_ref, str) or not isinstance(new_ref, str):
                raise ProviderReplayMismatch(
                    f"{node.node_id} provider input {index} ref is not portable text"
                )
            old_binding = next(
                (
                    item
                    for item in source_authored
                    if isinstance(item, dict)
                    and item.get("label") == old_ref
                    and item.get("sha256") == new["sha256"]
                ),
                None,
            )
            current_binding = next(
                (
                    item
                    for item in current_authored
                    if item.ref == (old_binding or {}).get("ref") and item.sha256 == new["sha256"]
                ),
                None,
            )
            expected_new_ref = (
                None
                if current_binding is None
                else (
                    f"package://{self._plan.graph.game_id}/{current_binding.ref}"
                    f"#sha256={current_binding.sha256}"
                )
            )
            if old_binding is None or current_binding is None or new_ref != expected_new_ref:
                raise ProviderReplayMismatch(
                    f"{node.node_id} provider input {index} provenance ref changed without "
                    "an exact historical-card-to-current-package binding"
                )
            migrations.append(
                {
                    "index": index,
                    "classification": "non_provider_transmitted_provenance_identity_hardening",
                    "historical_ref": old_ref,
                    "current_ref": new_ref,
                    "package_member": current_binding.ref,
                    "sha256": current_binding.sha256,
                }
            )
        return migrations

    def _base_request_entry(
        self,
        node: Node,
        sidecar: Mapping[str, Any],
        *,
        artifact_ref: str,
        sidecar_ref: str,
        artifact_data: bytes,
        historical_sidecar_data: bytes,
        migrated_sidecar_data: bytes,
        sidecar_migration: Mapping[str, object],
        request_identity: dict[str, object],
        current_validation: Mapping[str, object],
    ) -> dict[str, object]:
        node_type = self._types[node.type_id]
        binding = self._profile[node.operation]
        source = self._source_nodes[node.node_id]
        route = {
            "operation": node.operation,
            "resource_id": node.resource_id,
            "provider": node.provider,
            "model": node.model,
            "features": sorted(node_type.features),
            "binding_features": sorted(binding.features),
            "verified_on": binding.verified_on,
            "retry_owner": str(node.retry_owner),
            "max_attempts": node.max_attempts,
        }
        _require_equal(f"{node.node_id} sidecar provider", sidecar.get("provider"), node.provider)
        _require_equal(f"{node.node_id} sidecar model", sidecar.get("model"), node.model)
        return {
            "node_id": node.node_id,
            "type_id": node.type_id,
            "type_contract_version": node_type.contract_version,
            "handler_version": RUNNER_HANDLER_VERSION,
            "template_id": node.template_id,
            "capability_route": route,
            "source_cache_key": source.get("cache_key"),
            "historical_plan_card_omission": node.node_id in self._source_card_gaps,
            "current_cache_key": node.cache_key,
            "current_node_input_sha256": list(node.input_sha256),
            "request_identity": request_identity,
            "request_identity_sha256": _json_digest(request_identity),
            "provider_artifact": _bytes_record(
                artifact_ref,
                artifact_data,
                media_type=cast(str, cast(dict[str, object], sidecar["artifact"])["media_type"]),
            ),
            "historical_provider_sidecar": _bytes_record(
                sidecar_ref, historical_sidecar_data, media_type="application/json"
            ),
            "migrated_provider_sidecar": _bytes_record(
                sidecar_ref, migrated_sidecar_data, media_type="application/json"
            ),
            "sidecar_identity_migration": dict(sidecar_migration),
            "current_validation": dict(current_validation),
            "current_validation_sha256": _json_digest(current_validation),
            "historical_validation_sha256": _json_digest(sidecar.get("validation")),
            "migration": {
                "provider_calls": 0,
                "recorded_provider_attempts": 1,
                "provider_bytes_preserved": True,
                "provider_sidecar_identity_migrated": True,
            },
        }

    async def replay_image(self, request: ImageGenerationRequest) -> SimpleNamespace:
        node = self._node_for_request(request.artifact_path, RunnerOperationKind.IMAGE_GENERATION)
        artifact_data, sidecar_data, sidecar, artifact_ref, sidecar_ref = self._recorded(node)
        assert_image_signature(artifact_data, cast(str, sidecar["artifact"]["media_type"]))
        _require_equal(f"{node.node_id} prompt", request.prompt, sidecar.get("prompt"))
        _require_equal(
            f"{node.node_id} prompt sha256",
            sha256(request.prompt.encode()).hexdigest(),
            sidecar.get("prompt_sha256"),
        )

        reference_records: list[dict[str, object]] = []
        for reference in request.input_references:
            record, _data = _data_reference_record(
                reference.url, reference.provenance_ref, role="reference"
            )
            reference_records.append(record)
        mask_record: dict[str, object] | None = None
        if request.mask_reference is not None:
            mask_record, _mask = _data_reference_record(
                request.mask_reference.url,
                request.mask_reference.provenance_ref,
                role="mask",
            )
        all_inputs = reference_records + ([] if mask_record is None else [mask_record])
        historical_inputs = sidecar.get("inputs")
        legacy_mask_omission = False
        if isinstance(historical_inputs, list) and len(historical_inputs) == len(all_inputs):
            ref_migrations = self._compare_ordered_inputs(node, historical_inputs, all_inputs)
        elif (
            mask_record is not None
            and isinstance(historical_inputs, list)
            and len(historical_inputs) == len(reference_records)
        ):
            # ImageGenerationService now records mask lineage.  Historical v5 predates that
            # provenance fix, so the deterministic mask is bound in this migration envelope.
            legacy_mask_omission = True
            ref_migrations = self._compare_ordered_inputs(
                node, historical_inputs, reference_records
            )
        else:
            raise ProviderReplayMismatch(f"{node.node_id} ordered provider input count differs")
        historical_refs = sidecar.get("refs")
        historical_expected_refs = [
            item["ref"] for item in cast(list[dict[str, object]], historical_inputs)
        ]
        _require_equal(
            f"{node.node_id} ordered provider refs", historical_refs, historical_expected_refs
        )
        _require_equal(
            f"{node.node_id} references alias", sidecar.get("references"), historical_refs
        )

        expected_params: dict[str, object] = {
            "n": 1,
            "validated": request.validate is not None,
            "operation": "edit"
            if request.input_references or request.mask_reference
            else "generation",
        }
        for key in (
            "aspect_ratio",
            "resolution",
            "quality",
            "background",
            "output_format",
            "output_compression",
            "size",
            "moderation",
        ):
            value = getattr(request, key)
            if value is not None:
                expected_params[key] = value
        if request.metadata:
            expected_params["metadata"] = dict(request.metadata)
        _require_equal(f"{node.node_id} image params", sidecar.get("params"), expected_params)
        current_validation = await run_validator(
            request.validate,
            BinaryArtifact(
                data=artifact_data,
                media_type=cast(str, sidecar["artifact"]["media_type"]),
            ),
        )
        mask_gap: dict[str, object] | None = (
            {
                "classification": "historical_sidecar_omission_deterministically_reconstructed",
                "algorithm_identity": (
                    f"loop_conditioning@{node.params.get('construction')}/"
                    f"{self._types[node.type_id].contract_version}"
                ),
                "conditioning_inputs": reference_records,
                "mask_input": mask_record,
            }
            if legacy_mask_omission
            else None
        )
        migrated_sidecar_data, expected_identity, sidecar_migration = (
            self._migrate_recorded_sidecar(
                node,
                artifact_data=artifact_data,
                historical_sidecar_data=sidecar_data,
                historical_sidecar=sidecar,
                sidecar_ref=sidecar_ref,
                equivalent_ref_label_normalizations=ref_migrations,
                historical_loop_mask_omission_reconstruction=mask_gap,
            )
        )
        _require_equal(
            f"{node.node_id} current sidecar inputs",
            expected_identity.get("inputs"),
            _sidecar_input_shape(all_inputs),
        )
        _require_equal(
            f"{node.node_id} current sidecar refs",
            expected_identity.get("refs"),
            [record["ref"] for record in all_inputs],
        )
        _require_equal(
            f"{node.node_id} current sidecar params",
            expected_identity.get("params"),
            expected_params,
        )
        expected_current_validation = _json_value(
            {
                "output_nonempty": True,
                "base64": "strict",
                "media_type": cast(str, sidecar["artifact"]["media_type"]),
                "signature": "matched",
                "caller": request.validate is not None,
                **current_validation,
            },
            f"{node.node_id} current image validation",
        )
        _require_equal(
            f"{node.node_id} current sidecar validation",
            expected_identity.get("validation"),
            expected_current_validation,
        )
        request_identity: dict[str, object] = {
            "prompt_sha256": sha256(request.prompt.encode()).hexdigest(),
            "params": expected_params,
            "ordered_inputs": all_inputs,
            "legacy_sidecar_mask_omission": legacy_mask_omission,
            "historical_mask_provenance_gap": mask_gap,
            "historical_provenance_ref_migrations": ref_migrations,
            "provenance_schema_version": request.provenance_schema_version,
        }
        self._entries[node.node_id] = self._base_request_entry(
            node,
            sidecar,
            artifact_ref=artifact_ref,
            sidecar_ref=sidecar_ref,
            artifact_data=artifact_data,
            historical_sidecar_data=sidecar_data,
            migrated_sidecar_data=migrated_sidecar_data,
            sidecar_migration=sidecar_migration,
            request_identity=request_identity,
            current_validation=cast("Mapping[str, object]", expected_identity["validation"]),
        )
        output = Path(request.artifact_path)
        atomic_write_bytes(output, artifact_data)
        atomic_write_bytes(self._run_dir / sidecar_ref, migrated_sidecar_data)
        self._completed.add(node.node_id)
        self._provider_service_calls += 1
        return SimpleNamespace(attempts=1, provenance_path=str(self._run_dir / sidecar_ref))

    async def replay_structured(self, request: StructuredGenerationRequest[Any]) -> SimpleNamespace:
        node = self._node_for_request(
            request.artifact_path, RunnerOperationKind.STRUCTURED_GENERATION
        )
        artifact_data, sidecar_data, sidecar, artifact_ref, sidecar_ref = self._recorded(node)
        _require_equal(f"{node.node_id} prompt", request.prompt, sidecar.get("prompt"))
        _require_equal(
            f"{node.node_id} prompt sha256",
            sha256(request.prompt.encode()).hexdigest(),
            sidecar.get("prompt_sha256"),
        )
        references: list[dict[str, object]] = []
        for reference in request.references:
            record, _data = _data_reference_record(
                reference.url, reference.provenance_ref, role="reference"
            )
            references.append(record)
        _require_equal(
            f"{node.node_id} ordered structured inputs",
            sidecar.get("inputs"),
            _sidecar_input_shape(references),
        )
        _require_equal(
            f"{node.node_id} ordered structured refs",
            sidecar.get("refs"),
            [record["ref"] for record in references],
        )
        _require_equal(
            f"{node.node_id} references alias", sidecar.get("references"), sidecar.get("refs")
        )

        expected_params: dict[str, object] = {
            "schema_name": request.schema.name,
            "schema": dict(request.schema.json_schema),
            "strict": request.schema.strict,
            "require_parameters": True,
        }
        if request.system:
            expected_params["system"] = request.system
            expected_params["system_sha256"] = sha256(request.system.encode()).hexdigest()
        if request.temperature is not None:
            expected_params["temperature"] = request.temperature
        if request.max_tokens is not None:
            expected_params["max_tokens"] = request.max_tokens
        if request.seed is not None:
            expected_params["seed"] = request.seed
        if request.metadata:
            expected_params["metadata"] = dict(request.metadata)
        if request.artifact_value is not None:
            expected_params["artifact_value"] = "caller-canonicalized"
        if request.validate is not None:
            expected_params["validated"] = True
        _require_equal(
            f"{node.node_id} historical structured params",
            sidecar.get("params"),
            expected_params,
        )
        expected_params["schema_description"] = request.schema.description

        published = json.loads(artifact_data)
        if not isinstance(published, dict) or not isinstance(published.get("evidence"), dict):
            raise ProviderReplayMismatch(
                f"{node.node_id} recorded structured artifact is malformed"
            )
        states = request.metadata.get("states")
        if not isinstance(states, list) or not all(isinstance(state, str) for state in states):
            raise ProviderReplayMismatch(f"{node.node_id} request has no ordered state vocabulary")
        multiplier_key = "correction" if "correction" in published else "states"
        multipliers = published.get(multiplier_key)
        if not isinstance(multipliers, dict):
            raise ProviderReplayMismatch(f"{node.node_id} artifact has no replayable multipliers")
        decoded = {
            "baseline_state": published.get("baseline_state"),
            "states": [
                {
                    "state": state,
                    "multiplier": multipliers[state],
                    "evidence": published["evidence"][state],
                }
                for state in states
            ],
        }
        value = request.parse(decoded)
        canonical = request.artifact_value(value) if request.artifact_value is not None else decoded
        serialized = (
            json.dumps(canonical, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        ).encode()
        _require_equal(
            f"{node.node_id} current structured canonicalization",
            sha256(serialized).hexdigest(),
            sha256(artifact_data).hexdigest(),
        )
        caller_validation = (
            dict(request.validate(value) or {}) if request.validate is not None else {}
        )
        current_validation = {
            "output_nonempty": True,
            "json": "parsed",
            "schema": "caller-validated",
            **caller_validation,
        }
        _require_equal(
            f"{node.node_id} structured validation",
            sidecar.get("validation"),
            current_validation,
        )
        plate_ref = node.port("plate").artifact_ref
        plate_data = _read_confined_file(
            self._run_dir, plate_ref, f"{node.node_id} staged structured plate"
        )
        migrated_sidecar_data, expected_identity, sidecar_migration = (
            self._migrate_recorded_sidecar(
                node,
                artifact_data=artifact_data,
                historical_sidecar_data=sidecar_data,
                historical_sidecar=sidecar,
                sidecar_ref=sidecar_ref,
                bundle={plate_ref: plate_data, artifact_ref: artifact_data},
                equivalent_ref_label_normalizations=[],
                historical_loop_mask_omission_reconstruction=None,
            )
        )
        _require_equal(
            f"{node.node_id} current structured sidecar inputs",
            expected_identity.get("inputs"),
            _sidecar_input_shape(references),
        )
        _require_equal(
            f"{node.node_id} current structured sidecar refs",
            expected_identity.get("refs"),
            [record["ref"] for record in references],
        )
        _require_equal(
            f"{node.node_id} current structured sidecar params",
            expected_identity.get("params"),
            expected_params,
        )
        _require_equal(
            f"{node.node_id} current structured sidecar validation",
            expected_identity.get("validation"),
            current_validation,
        )
        request_identity: dict[str, object] = {
            "prompt_sha256": sha256(request.prompt.encode()).hexdigest(),
            "system_sha256": None
            if request.system is None
            else sha256(request.system.encode()).hexdigest(),
            "schema_name": request.schema.name,
            "schema_description": request.schema.description,
            "schema_sha256": _json_digest(dict(request.schema.json_schema)),
            "params": expected_params,
            "ordered_inputs": references,
            "provenance_schema_version": request.provenance_schema_version,
            "historical_schema_description_provenance_gap": {
                "classification": "historical_sidecar_omission_current_request_reconstructed",
                "description": request.schema.description,
                "provider_transport_field": "response_format.json_schema.description",
            },
        }
        self._entries[node.node_id] = self._base_request_entry(
            node,
            sidecar,
            artifact_ref=artifact_ref,
            sidecar_ref=sidecar_ref,
            artifact_data=artifact_data,
            historical_sidecar_data=sidecar_data,
            migrated_sidecar_data=migrated_sidecar_data,
            sidecar_migration=sidecar_migration,
            request_identity=request_identity,
            current_validation=cast("Mapping[str, object]", expected_identity["validation"]),
        )
        atomic_write_bytes(Path(request.artifact_path), artifact_data)
        atomic_write_bytes(self._run_dir / sidecar_ref, migrated_sidecar_data)
        self._completed.add(node.node_id)
        self._provider_service_calls += 1
        return SimpleNamespace(attempts=1, provenance_path=str(self._run_dir / sidecar_ref))

    async def replay_music(self, request: MusicGenerationRequest) -> SimpleNamespace:
        node = self._node_for_request(request.artifact_path, RunnerOperationKind.MUSIC_GENERATION)
        artifact_data, sidecar_data, sidecar, artifact_ref, sidecar_ref = self._recorded(node)
        media_type = cast(str, sidecar["artifact"]["media_type"])
        assert_audio_signature(artifact_data, media_type)
        _require_equal(f"{node.node_id} prompt", request.prompt, sidecar.get("prompt"))
        _require_equal(
            f"{node.node_id} prompt sha256",
            sha256(request.prompt.encode()).hexdigest(),
            sidecar.get("prompt_sha256"),
        )
        references: list[dict[str, object]] = []
        for reference in request.references:
            record, _data = _data_reference_record(
                reference.url, reference.provenance_ref, role="reference"
            )
            references.append(record)
        _require_equal(
            f"{node.node_id} ordered music inputs",
            sidecar.get("inputs"),
            _sidecar_input_shape(references),
        )
        _require_equal(
            f"{node.node_id} ordered music refs",
            sidecar.get("refs"),
            [record["ref"] for record in references],
        )
        expected_params: dict[str, object] = {
            "output_format": request.output_format,
            "modalities": ["text", "audio"],
            "stream": True,
            "validated": request.validate is not None,
        }
        for key in ("temperature", "top_p", "seed", "max_tokens"):
            value = getattr(request, key)
            if value is not None:
                expected_params[key] = value
        if request.metadata:
            expected_params["metadata"] = dict(request.metadata)
        _require_equal(f"{node.node_id} music params", sidecar.get("params"), expected_params)
        current_validation = await run_validator(
            request.validate, BinaryArtifact(data=artifact_data, media_type=media_type)
        )
        migrated_sidecar_data, expected_identity, sidecar_migration = (
            self._migrate_recorded_sidecar(
                node,
                artifact_data=artifact_data,
                historical_sidecar_data=sidecar_data,
                historical_sidecar=sidecar,
                sidecar_ref=sidecar_ref,
                equivalent_ref_label_normalizations=[],
                historical_loop_mask_omission_reconstruction=None,
            )
        )
        _require_equal(
            f"{node.node_id} current music sidecar inputs",
            expected_identity.get("inputs"),
            _sidecar_input_shape(references),
        )
        _require_equal(
            f"{node.node_id} current music sidecar refs",
            expected_identity.get("refs"),
            [record["ref"] for record in references],
        )
        _require_equal(
            f"{node.node_id} current music sidecar params",
            expected_identity.get("params"),
            expected_params,
        )
        expected_current_validation = _json_value(
            {
                "output_nonempty": True,
                "base64": "strict",
                "media_type": media_type,
                "signature": "matched",
                "source_shape": cast(dict[str, Any], sidecar["response"])["source_shape"],
                "caller": request.validate is not None,
                **current_validation,
            },
            f"{node.node_id} current music validation",
        )
        _require_equal(
            f"{node.node_id} current music sidecar validation",
            expected_identity.get("validation"),
            expected_current_validation,
        )
        request_identity: dict[str, object] = {
            "prompt_sha256": sha256(request.prompt.encode()).hexdigest(),
            "params": expected_params,
            "ordered_inputs": references,
        }
        self._entries[node.node_id] = self._base_request_entry(
            node,
            sidecar,
            artifact_ref=artifact_ref,
            sidecar_ref=sidecar_ref,
            artifact_data=artifact_data,
            historical_sidecar_data=sidecar_data,
            migrated_sidecar_data=migrated_sidecar_data,
            sidecar_migration=sidecar_migration,
            request_identity=request_identity,
            current_validation=cast("Mapping[str, object]", expected_identity["validation"]),
        )
        atomic_write_bytes(Path(request.artifact_path), artifact_data)
        atomic_write_bytes(self._run_dir / sidecar_ref, migrated_sidecar_data)
        self._completed.add(node.node_id)
        self._provider_service_calls += 1
        return SimpleNamespace(attempts=1, provenance_path=str(self._run_dir / sidecar_ref))

    async def replay_sound_effect(self, request: SoundEffectGenerationRequest) -> SimpleNamespace:
        node = self._node_for_request(
            request.artifact_path, RunnerOperationKind.SOUND_EFFECT_GENERATION
        )
        artifact_data, sidecar_data, sidecar, artifact_ref, sidecar_ref = self._recorded(node)
        media_type = cast(str, sidecar["artifact"]["media_type"])
        assert_audio_signature(artifact_data, media_type)
        _require_equal(f"{node.node_id} prompt", request.prompt, sidecar.get("prompt"))
        _require_equal(
            f"{node.node_id} prompt sha256",
            sha256(request.prompt.encode()).hexdigest(),
            sidecar.get("prompt_sha256"),
        )
        _require_equal(f"{node.node_id} sound effect inputs", sidecar.get("inputs"), [])
        _require_equal(f"{node.node_id} sound effect refs", sidecar.get("refs"), [])
        expected_params: dict[str, object] = {
            "output_format": request.output_format,
            "loop": request.loop,
            "validated": request.validate is not None,
        }
        if request.duration_seconds is not None:
            expected_params["duration_seconds"] = request.duration_seconds
        if request.prompt_influence is not None:
            expected_params["prompt_influence"] = request.prompt_influence
        if request.metadata:
            expected_params["metadata"] = dict(request.metadata)
        _require_equal(
            f"{node.node_id} sound effect params", sidecar.get("params"), expected_params
        )
        current_validation = await run_validator(
            request.validate, BinaryArtifact(data=artifact_data, media_type=media_type)
        )
        migrated_sidecar_data, expected_identity, sidecar_migration = (
            self._migrate_recorded_sidecar(
                node,
                artifact_data=artifact_data,
                historical_sidecar_data=sidecar_data,
                historical_sidecar=sidecar,
                sidecar_ref=sidecar_ref,
                equivalent_ref_label_normalizations=[],
                historical_loop_mask_omission_reconstruction=None,
            )
        )
        _require_equal(
            f"{node.node_id} current sound effect sidecar params",
            expected_identity.get("params"),
            expected_params,
        )
        expected_current_validation = _json_value(
            {
                "output_nonempty": True,
                "media_type": media_type,
                "signature": "matched",
                "source_shape": cast(dict[str, Any], sidecar["response"])["source_shape"],
                "caller": request.validate is not None,
                **current_validation,
            },
            f"{node.node_id} current sound effect validation",
        )
        _require_equal(
            f"{node.node_id} current sound effect sidecar validation",
            expected_identity.get("validation"),
            expected_current_validation,
        )
        request_identity: dict[str, object] = {
            "prompt_sha256": sha256(request.prompt.encode()).hexdigest(),
            "params": expected_params,
            "ordered_inputs": [],
        }
        self._entries[node.node_id] = self._base_request_entry(
            node,
            sidecar,
            artifact_ref=artifact_ref,
            sidecar_ref=sidecar_ref,
            artifact_data=artifact_data,
            historical_sidecar_data=sidecar_data,
            migrated_sidecar_data=migrated_sidecar_data,
            sidecar_migration=sidecar_migration,
            request_identity=request_identity,
            current_validation=cast("Mapping[str, object]", expected_identity["validation"]),
        )
        atomic_write_bytes(Path(request.artifact_path), artifact_data)
        atomic_write_bytes(self._run_dir / sidecar_ref, migrated_sidecar_data)
        self._completed.add(node.node_id)
        self._provider_service_calls += 1
        return SimpleNamespace(attempts=1, provenance_path=str(self._run_dir / sidecar_ref))


class _ReplayImageService:
    def __init__(self, catalog: _RecordedProviderCatalog) -> None:
        self._catalog = catalog

    async def generate(self, request: ImageGenerationRequest) -> SimpleNamespace:
        return await self._catalog.replay_image(request)


class _ReplayStructuredService:
    def __init__(self, catalog: _RecordedProviderCatalog) -> None:
        self._catalog = catalog

    async def generate(self, request: StructuredGenerationRequest[Any]) -> SimpleNamespace:
        return await self._catalog.replay_structured(request)


class _ReplayMusicService:
    def __init__(self, catalog: _RecordedProviderCatalog) -> None:
        self._catalog = catalog

    async def generate(self, request: MusicGenerationRequest) -> SimpleNamespace:
        return await self._catalog.replay_music(request)


class _ReplaySoundEffectService:
    def __init__(self, catalog: _RecordedProviderCatalog) -> None:
        self._catalog = catalog

    async def generate(self, request: SoundEffectGenerationRequest) -> SimpleNamespace:
        return await self._catalog.replay_sound_effect(request)


class _DenyProviderService:
    """A cache-only run trips immediately if even one provider record is not admitted."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, _request: object) -> object:
        self.calls += 1
        raise ProviderReplayMismatch("cache-only verification attempted a provider operation")


class _ProviderSeedHandler:
    """Run local dependencies, but persist cache records only for provider nodes."""

    def __init__(
        self,
        handler: SideviewRunnerNodeHandler,
        catalog: _RecordedProviderCatalog,
        *,
        cache_root: Path,
    ) -> None:
        self._handler = handler
        self._catalog = catalog
        self._cache_root = cache_root

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        # The registry is the current handler's uncached dispatch surface.  Bypassing __call__
        # here is intentional: local results establish lineage but must not be seeded.
        result = await self._handler._registry(node, context)
        if node.is_local:
            return result
        self._handler._cache.write(node, context, result)
        record_path = (
            self._cache_root
            / RUNNER_CACHE_NAMESPACE
            / node.cache_key[:2]
            / node.cache_key
            / "record.json"
        )
        record_ref = record_path.relative_to(self._cache_root).as_posix()
        record, record_bytes = _read_confined_object(
            self._cache_root, record_ref, f"{node.node_id} cache record"
        )
        self._catalog.finalize_cache_entry(
            node, context, result, cache_record=record, cache_record_bytes=record_bytes
        )
        # The attempt ledger describes the historical operation that made the selected bytes.
        # This execution trace describes the migration itself, which made zero provider calls.
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=1,
            provider_operations=0,
            artifacts=result.artifacts,
            known_cost_usd=0.0,
        )


def _open_current_run(plan: SideviewRunnerPlan, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=False)
    write_graph(run_dir / "execution-plan.json", plan.graph)
    atomic_write_json(
        run_dir / "execution-projection.json", plan.projection.model_dump(mode="json")
    )
    atomic_write_json(run_dir / "runner-identity.json", plan.resolved.identity())


async def _schedule(
    plan: SideviewRunnerPlan,
    handler: Any,
    *,
    run_dir: Path,
    invocation_id: str,
    timeout_seconds: float,
) -> RunSummary:
    trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
    scheduler = Scheduler(plan.graph.resources, node_timeout_seconds=timeout_seconds, secrets=())
    try:
        summary = await scheduler.run(
            plan.graph, handler, invocation_id=invocation_id, trace_sink=trace
        )
    finally:
        trace.close()
    write_run_summary(run_dir / "execution-summary.json", summary)
    if not summary.ok:
        raise ProviderReplayMismatch(f"provider replay run failed: {invocation_id}")
    return summary


def _plan_identity(
    document: Mapping[str, object], *, run_name: str, plan_data: bytes
) -> dict[str, object]:
    return {
        "run_id": run_name,
        "graph_sha256": document.get("graph_sha256"),
        "topology_sha256": document.get("topology_sha256"),
        "execution_plan_sha256": sha256(plan_data).hexdigest(),
        "execution_plan_bytes": len(plan_data),
    }


def _validate_listening_review(
    review_root: Path,
    review_ref: str,
    *,
    output_run: Path,
    source_run_name: str,
    expected_tracks: tuple[tuple[str, str], ...],
) -> tuple[dict[str, object], bytes]:
    review, data = _read_confined_object(review_root, review_ref, "external listening review")
    _require_equal(
        "listening review kind", review.get("kind"), "sideview-runner-external-listening-review-v1"
    )
    _require_equal("listening review source run", review.get("run_id"), source_run_name)
    _require_equal("listening review verdict", review.get("overall_verdict"), "pass")
    tracks = review.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise ProviderReplayMismatch("listening review carries no tracks")
    if len(expected_tracks) != len(set(expected_tracks)) or len(
        {ref for _track, ref in expected_tracks}
    ) != len(expected_tracks):
        raise ProviderReplayMismatch("current soundtrack bindings must be exact and unique")
    bound: list[dict[str, object]] = []
    observed_bindings: list[tuple[str, str]] = []
    for item in tracks:
        if not isinstance(item, dict) or item.get("verdict") != "pass":
            raise ProviderReplayMismatch("listening review has a non-passing track")
        track_id = item.get("track_id")
        ref = item.get("artifact_ref")
        if not isinstance(track_id, str) or not isinstance(ref, str):
            raise ProviderReplayMismatch("listening review track has no exact id and artifact ref")
        try:
            audio_path = resolve_relative_path_within_root(
                output_run, ref, "listening review artifact ref"
            )
            audio = read_absolute_regular_file(
                audio_path, label="listening review soundtrack artifact"
            )
        except (OSError, SecurePathError, ValueError) as error:
            raise ProviderReplayMismatch(
                "listening review artifact ref must resolve to a confined regular output file"
            ) from error
        _require_equal(
            f"listening review {ref} sha256", item.get("artifact_sha256"), sha256(audio).hexdigest()
        )
        _require_equal(f"listening review {ref} bytes", item.get("artifact_bytes"), len(audio))
        observed_bindings.append((track_id, ref))
        bound.append(_bytes_record(ref, audio, media_type="audio/mpeg"))
    if len(observed_bindings) != len(set(observed_bindings)) or len(
        {ref for _track, ref in observed_bindings}
    ) != len(observed_bindings):
        raise ProviderReplayMismatch("listening review soundtrack bindings must be unique")
    _require_equal(
        "listening review current soundtrack bindings",
        sorted([list(binding) for binding in observed_bindings]),
        sorted([list(binding) for binding in expected_tracks]),
    )
    return (
        {
            "source_run_id": source_run_name,
            "review_sha256": sha256(data).hexdigest(),
            "review_bytes": len(data),
            "reviewer_identity": review.get("reviewer_identity"),
            "recorded_at": review.get("recorded_at"),
            "binding_mode": "exact_audio_sha256_reuse",
            "tracks": bound,
        },
        data,
    )


async def revalidate_runner_provider_cache(
    *,
    input_path: Path,
    source_run: Path,
    structured_sidecar_run: Path,
    staging_run: Path,
    cache_dir: Path,
    output_run: Path,
    listening_review: Path,
    invocation_id: str,
    config: StageGenConfig | None = None,
) -> ProviderReplayResult:
    """Revalidate accepted provider bytes and prove a zero-call current-graph cache run.

    All output paths must be absent.  The cache is assembled under a unique sibling and renamed
    into place only after every current request and validator passes.
    """

    config = config or StageGenConfig()
    for path, label in (
        (staging_run, "staging run"),
        (cache_dir, "cache directory"),
        (output_run, "output run"),
    ):
        if path.exists():
            raise ProviderReplayMismatch(f"{label} must not already exist")
    if _same_resolved_path(source_run, structured_sidecar_run):
        raise ProviderReplayMismatch(
            "structured replay must name its independently complete sidecar run"
        )
    _assert_disjoint_replay_paths(
        source_run=source_run,
        structured_sidecar_run=structured_sidecar_run,
        staging_run=staging_run,
        cache_dir=cache_dir,
        output_run=output_run,
    )
    listening_review_ref = _confined_ref_for_path(
        source_run, listening_review, "external listening review"
    )
    # Refuse a symlinked or non-regular review before any staging work.  It is read again for
    # the final audio binding so an in-place replacement cannot bypass descriptor-safe admission.
    _read_confined_file(source_run, listening_review_ref, "external listening review")
    executor = SideviewRunnerExecutor(config)
    plan = executor.plan(input_path)
    _open_current_run(plan, staging_run)

    scratch_cache = cache_dir.with_name(f".{cache_dir.name}.replay-{uuid.uuid4().hex}")
    scratch_cache.parent.mkdir(parents=True, exist_ok=True)
    scratch_cache.mkdir(exist_ok=False)
    catalog = _RecordedProviderCatalog(
        plan,
        run_dir=staging_run,
        source_run=source_run,
        structured_sidecar_run=structured_sidecar_run,
        config=config,
    )
    replay_handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=staging_run,
        cache_dir=scratch_cache,
        image_service=cast(Any, _ReplayImageService(catalog)),
        structured_service=cast(Any, _ReplayStructuredService(catalog)),
        music_service=cast(Any, _ReplayMusicService(catalog)),
        sound_effect_service=cast(Any, _ReplaySoundEffectService(catalog)),
        capability_timeout_s=config.capability_timeout_s,
    )
    catalog.bind_current_handler(replay_handler)
    seed_summary = await _schedule(
        plan,
        _ProviderSeedHandler(replay_handler, catalog, cache_root=scratch_cache),
        run_dir=staging_run,
        invocation_id=f"{invocation_id}-seed",
        timeout_seconds=max(config.stage_timeout_s, 900),
    )
    catalog.assert_complete()
    _require_equal(
        "seed provider operation counts",
        seed_summary.provider_operation_counts,
        {operation: 0 for operation in plan.graph.provider_operation_vocabulary()},
    )
    provider_record_count = len(
        list(scratch_cache.glob(f"{RUNNER_CACHE_NAMESPACE}/*/*/record.json"))
    )
    _require_equal(
        "seeded provider cache record count", provider_record_count, len(catalog.entries)
    )
    _open_current_run(plan, output_run)
    denied_image = _DenyProviderService()
    denied_structured = _DenyProviderService()
    denied_music = _DenyProviderService()
    denied_sound_effect = _DenyProviderService()
    output_handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=output_run,
        cache_dir=scratch_cache,
        image_service=cast(Any, denied_image),
        structured_service=cast(Any, denied_structured),
        music_service=cast(Any, denied_music),
        sound_effect_service=cast(Any, denied_sound_effect),
        capability_timeout_s=config.capability_timeout_s,
    )
    output_summary = await _schedule(
        plan,
        output_handler,
        run_dir=output_run,
        invocation_id=invocation_id,
        timeout_seconds=max(config.stage_timeout_s, 900),
    )
    _require_equal(
        "cache-only provider service calls",
        denied_image.calls
        + denied_structured.calls
        + denied_music.calls
        + denied_sound_effect.calls,
        0,
    )
    provider_ids = {node.node_id for node in plan.graph.nodes if not node.is_local}
    local_ids = {node.node_id for node in plan.graph.nodes if node.is_local}
    hits = {trace.node_id for trace in output_summary.nodes if trace.cache == CacheDisposition.HIT}
    misses = {
        trace.node_id for trace in output_summary.nodes if trace.cache == CacheDisposition.MISS
    }
    _require_equal("cache-only provider hits", sorted(hits & provider_ids), sorted(provider_ids))
    _require_equal("cache-only local misses", sorted(misses & local_ids), sorted(local_ids))
    _require_equal("cache-only unexpected hits", sorted(hits - provider_ids), [])
    _require_equal(
        "cache-only provider operation counts",
        output_summary.provider_operation_counts,
        {operation: 0 for operation in plan.graph.provider_operation_vocabulary()},
    )
    final_cache_record_count = len(
        list(scratch_cache.glob(f"{RUNNER_CACHE_NAMESPACE}/*/*/record.json"))
    )
    _require_equal(
        "cache-only final cache record count", final_cache_record_count, len(plan.graph.nodes)
    )

    expected_listening_tracks = tuple(
        (str(node.params["track_id"]), node.port("audio").artifact_ref)
        for node in plan.graph.nodes
        if node.operation == RunnerOperationKind.MUSIC_GENERATION
    )
    listening, review_data = _validate_listening_review(
        source_run,
        listening_review_ref,
        output_run=output_run,
        source_run_name=source_run.name,
        expected_tracks=expected_listening_tracks,
    )
    review_output = output_run / "soundtrack/external-listening-review.json"
    atomic_write_bytes(review_output, review_data)
    link = {
        "schema_version": 1,
        "kind": REPLAY_LINK_KIND,
        "target_run_id": output_run.name,
        "review_ref": "soundtrack/external-listening-review.json",
        **listening,
    }
    link_path = output_run / "soundtrack/external-listening-review-link.json"
    atomic_write_json(link_path, link)

    source_plan = _decode_object(catalog.source_plan_data, "source plan")
    structured_plan = _decode_object(catalog.structured_plan_data, "structured-sidecar source plan")
    entries_by_node = {cast(str, entry["node_id"]): entry for entry in catalog.entries}
    for node_id in provider_ids:
        migration = cast(dict[str, object], entries_by_node[node_id]["migration"])
        migration["current_cache_admission"] = "passed_exact_current_handler_cache_hit"
    provider_output_records: list[dict[str, object]] = []
    for node in plan.graph.nodes:
        if node.is_local:
            continue
        artifact_ref, sidecar_ref = _primary_provider_port(node)
        source_sidecar_root = (
            structured_sidecar_run
            if node.operation == RunnerOperationKind.STRUCTURED_GENERATION
            else source_run
        )
        output_artifact = _read_confined_file(
            output_run, artifact_ref, f"{node.node_id} final provider artifact"
        )
        output_sidecar = _read_confined_file(
            output_run, sidecar_ref, f"{node.node_id} final migrated provider sidecar"
        )
        source_artifact = _read_confined_file(
            source_run, artifact_ref, f"{node.node_id} historical provider artifact"
        )
        historical_sidecar = _read_confined_file(
            source_sidecar_root,
            sidecar_ref,
            f"{node.node_id} historical provider sidecar",
        )
        migrated_sidecar = catalog.migrated_sidecar_data(node.node_id)
        _require_equal(
            f"{node.node_id} output provider bytes",
            _bytes_record(artifact_ref, output_artifact),
            _bytes_record(artifact_ref, source_artifact),
        )
        _require_equal(
            f"{node.node_id} output migrated provider sidecar",
            _bytes_record(sidecar_ref, output_sidecar),
            _bytes_record(sidecar_ref, migrated_sidecar),
        )
        _require_equal(
            f"{node.node_id} audited historical provider sidecar",
            entries_by_node[node.node_id]["historical_provider_sidecar"],
            _bytes_record(sidecar_ref, historical_sidecar, media_type="application/json"),
        )
        _require_equal(
            f"{node.node_id} audited migrated provider sidecar",
            entries_by_node[node.node_id]["migrated_provider_sidecar"],
            _bytes_record(sidecar_ref, migrated_sidecar, media_type="application/json"),
        )
        provider_output_records.append(
            {
                "node_id": node.node_id,
                "artifact": _bytes_record(artifact_ref, output_artifact),
                "historical_sidecar": _bytes_record(sidecar_ref, historical_sidecar),
                "migrated_sidecar": _bytes_record(sidecar_ref, output_sidecar),
            }
        )

    provider_selections = [
        entry["node_id"]
        for entry in catalog.entries
        if cast(dict[str, object], entry["migration"]).get("output_selection") == "provider_output"
    ]
    deterministic_fallbacks = [
        entry["node_id"]
        for entry in catalog.entries
        if cast(dict[str, object], entry["migration"]).get("output_selection") == "fallback_output"
    ]
    _require_equal(
        "reused provider result accounting",
        len(provider_selections) + len(deterministic_fallbacks),
        len(provider_ids),
    )

    audit = {
        "schema_version": 1,
        "kind": REPLAY_AUDIT_KIND,
        "status": "pass",
        "provider_calls": 0,
        "semantic_regenerations": 0,
        "reuse_summary": {
            "reused_provider_nodes": len(provider_ids),
            "provider_output_selections": len(provider_selections),
            "deterministic_fallbacks": len(deterministic_fallbacks),
            "fallback_node_ids": deterministic_fallbacks,
        },
        "package": {
            "game_id": plan.graph.game_id,
            "track_id": plan.graph.track_id,
            "package_sha256": plan.graph.package_sha256,
        },
        "sources": {
            "provider_artifacts": _plan_identity(
                source_plan,
                run_name=source_run.name,
                plan_data=catalog.source_plan_data,
            ),
            "structured_sidecars": _plan_identity(
                structured_plan,
                run_name=structured_sidecar_run.name,
                plan_data=catalog.structured_plan_data,
            ),
        },
        "current_graph": {
            "graph_sha256": plan.graph.graph_sha256,
            "topology_sha256": plan.graph.topology_sha256,
            "node_count": len(plan.graph.nodes),
            "provider_node_count": len(provider_ids),
            "local_node_count": len(local_ids),
        },
        "seed_execution": {
            "run_id": staging_run.name,
            "summary_sha256": sha256(
                _read_confined_file(staging_run, "execution-summary.json", "seed execution summary")
            ).hexdigest(),
            "provider_operation_counts": seed_summary.provider_operation_counts,
            "provider_cache_records": provider_record_count,
            "local_cache_records": 0,
        },
        "cache_only_execution": {
            "run_id": output_run.name,
            "summary_sha256": sha256(
                _read_confined_file(
                    output_run, "execution-summary.json", "cache-only execution summary"
                )
            ).hexdigest(),
            "provider_operation_counts": output_summary.provider_operation_counts,
            "provider_cache_hits": len(hits & provider_ids),
            "local_cache_misses": len(misses & local_ids),
            "final_cache_records": final_cache_record_count,
        },
        "listening_review": {
            **listening,
            "link_ref": "soundtrack/external-listening-review-link.json",
            "link_sha256": sha256(
                _read_confined_file(
                    output_run,
                    "soundtrack/external-listening-review-link.json",
                    "listening review link",
                )
            ).hexdigest(),
        },
        "nodes": catalog.entries,
        "output_provider_bundles": provider_output_records,
    }
    audit_path = output_run / "provider-replay-audit.json"
    atomic_write_json(audit_path, audit)
    atomic_write_json(staging_run / "provider-replay-audit.json", audit)
    # The requested cache path remains absent until both the replay seed and the ordinary
    # cache-only current-graph run have passed, including their portable audit and review bind.
    os.replace(scratch_cache, cache_dir)
    return ProviderReplayResult(
        staging_run=staging_run,
        cache_dir=cache_dir,
        output_run=output_run,
        audit_path=audit_path,
        seed_summary=seed_summary,
        output_summary=output_summary,
    )


__all__ = [
    "ProviderReplayMismatch",
    "ProviderReplayResult",
    "REPLAY_AUDIT_KIND",
    "revalidate_runner_provider_cache",
]

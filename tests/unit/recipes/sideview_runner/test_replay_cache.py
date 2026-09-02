"""The accepted-run cache replay fails closed on request or lineage drift."""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from gnode import (
    ArtifactProvenance,
    CacheDisposition,
    NodeExecutionContext,
    NodeExecutionResult,
    serialize_provenance,
)
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_runner.replay_cache import (
    ProviderReplayMismatch,
    _assert_disjoint_replay_paths,
    _data_reference_record,
    _migrate_provider_sidecar,
    _primary_provider_port,
    _read_confined_file,
    _RecordedProviderCatalog,
    _validate_listening_review,
)
from stage_gen.recipes.sideview_runner.runner_executor import (
    SideviewRunnerExecutor,
    SideviewRunnerPlan,
)
from stage_gen.recipes.sideview_runner.runner_types import runner_type_index

from ..._runner_fixture import two_genre_package


def test_replay_destinations_cannot_overlap_sources_or_each_other(tmp_path: Path) -> None:
    source = tmp_path / "accepted-v5"
    structured = tmp_path / "accepted-v4"
    source.mkdir()
    structured.mkdir()

    with pytest.raises(ProviderReplayMismatch, match="overlap immutable source run"):
        _assert_disjoint_replay_paths(
            source_run=source,
            structured_sidecar_run=structured,
            staging_run=source / "staging",
            cache_dir=tmp_path / "cache",
            output_run=tmp_path / "v6",
        )

    with pytest.raises(ProviderReplayMismatch, match="cache directory and output run"):
        _assert_disjoint_replay_paths(
            source_run=source,
            structured_sidecar_run=structured,
            staging_run=tmp_path / "staging",
            cache_dir=tmp_path / "target",
            output_run=tmp_path / "target/v6",
        )

    _assert_disjoint_replay_paths(
        source_run=source,
        structured_sidecar_run=structured,
        staging_run=tmp_path / "staging",
        cache_dir=tmp_path / "cache",
        output_run=tmp_path / "v6",
    )


def _listening_review(track_id: str, ref: str, data: bytes) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "sideview-runner-external-listening-review-v1",
        "run_id": "accepted-v5",
        "reviewer_identity": "independent-reviewer",
        "recorded_at": "2026-09-02T07:42:11+09:00",
        "overall_verdict": "pass",
        "tracks": [
            {
                "track_id": track_id,
                "artifact_ref": ref,
                "artifact_sha256": sha256(data).hexdigest(),
                "artifact_bytes": len(data),
                "verdict": "pass",
            }
        ],
    }


def test_listening_transfer_rejects_unconfined_artifact_ref(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    escaped = tmp_path / "escape.mp3"
    escaped.write_bytes(b"reviewed audio")
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps(_listening_review("theme", "../escape.mp3", escaped.read_bytes())),
        encoding="utf-8",
    )

    with pytest.raises(ProviderReplayMismatch, match="confined regular output file"):
        _validate_listening_review(
            tmp_path,
            "review.json",
            output_run=output,
            source_run_name="accepted-v5",
            expected_tracks=(("theme", "soundtrack/theme.mp3"),),
        )


def test_listening_transfer_requires_exact_unique_current_soundtrack_refs(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    soundtrack = output / "soundtrack"
    soundtrack.mkdir(parents=True)
    audio = b"reviewed audio"
    (soundtrack / "theme.mp3").write_bytes(audio)
    review_document = _listening_review("theme", "soundtrack/theme.mp3", audio)
    review_document["tracks"] = [
        *review_document["tracks"],  # type: ignore[misc]
        {
            "track_id": "credits",
            "artifact_ref": "soundtrack/theme.mp3",
            "artifact_sha256": sha256(audio).hexdigest(),
            "artifact_bytes": len(audio),
            "verdict": "pass",
        },
    ]
    review = tmp_path / "review.json"
    review.write_text(json.dumps(review_document), encoding="utf-8")

    with pytest.raises(ProviderReplayMismatch, match="bindings must be unique"):
        _validate_listening_review(
            tmp_path,
            "review.json",
            output_run=output,
            source_run_name="accepted-v5",
            expected_tracks=(
                ("theme", "soundtrack/theme.mp3"),
                ("credits", "soundtrack/credits.mp3"),
            ),
        )


def _plan(tmp_path: Path, *, generated_loop: bool = False) -> SideviewRunnerPlan:
    package = two_genre_package(tmp_path / "package")
    if generated_loop:
        track = package / "runner/track.toml"
        track.write_text(
            track.read_text(encoding="utf-8").replace(
                'loop_construction = "mirror_repeat"',
                'loop_construction = "generated_bridge"',
                1,
            ),
            encoding="utf-8",
        )
    return SideviewRunnerExecutor(StageGenConfig()).plan(package)


def test_source_execution_plan_symlink_is_refused(tmp_path: Path) -> None:
    plan = _plan(tmp_path / "planning")
    source = tmp_path / "accepted-v5"
    structured = tmp_path / "accepted-v4"
    source.mkdir()
    structured.mkdir()
    outside = tmp_path / "outside-execution-plan.json"
    outside.write_text(plan.graph.model_dump_json(), encoding="utf-8")
    (source / "execution-plan.json").symlink_to(outside)
    (structured / "execution-plan.json").write_text(plan.graph.model_dump_json(), encoding="utf-8")

    with pytest.raises(ProviderReplayMismatch, match=r"source plan.*non-symlink"):
        _RecordedProviderCatalog(
            plan,
            run_dir=tmp_path / "staging",
            source_run=source,
            structured_sidecar_run=structured,
            config=StageGenConfig(),
        )


def test_historical_provider_artifact_symlink_is_refused(tmp_path: Path) -> None:
    plan = _plan(tmp_path / "planning")
    node = next(item for item in plan.graph.nodes if item.operation == "image_generation")
    artifact_ref, _sidecar_ref = _primary_provider_port(node)
    source = tmp_path / "accepted-v5"
    structured = tmp_path / "accepted-v4"
    structured.mkdir()
    artifact_path = source / artifact_ref
    artifact_path.parent.mkdir(parents=True)
    outside = tmp_path / "outside-provider.png"
    outside.write_bytes(b"provider bytes")
    artifact_path.symlink_to(outside)
    catalog = object.__new__(_RecordedProviderCatalog)
    catalog._source_run = source
    catalog._structured_sidecar_run = structured

    with pytest.raises(ProviderReplayMismatch, match=r"provider artifact.*non-symlink"):
        catalog._recorded(node)


def test_historical_provider_sidecar_symlink_and_traversal_are_refused(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path / "planning")
    node = next(item for item in plan.graph.nodes if item.operation == "image_generation")
    artifact_ref, sidecar_ref = _primary_provider_port(node)
    source = tmp_path / "accepted-v5"
    structured = tmp_path / "accepted-v4"
    structured.mkdir()
    artifact_path = source / artifact_ref
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"provider bytes")
    outside = tmp_path / "outside-sidecar.json"
    outside.write_text("{}", encoding="utf-8")
    sidecar_path = source / sidecar_ref
    sidecar_path.symlink_to(outside)
    catalog = object.__new__(_RecordedProviderCatalog)
    catalog._source_run = source
    catalog._structured_sidecar_run = structured

    with pytest.raises(ProviderReplayMismatch, match=r"provider sidecar.*non-symlink"):
        catalog._recorded(node)
    with pytest.raises(ProviderReplayMismatch, match="confined regular non-symlink"):
        _read_confined_file(source, "../outside-sidecar.json", "historical provider sidecar")


def test_data_reference_record_binds_exact_bytes_mime_role_and_ref() -> None:
    payload = b"\x89PNG\r\n\x1a\nproof"
    encoded = base64.b64encode(payload).decode()
    record, decoded = _data_reference_record(
        f"data:image/png;base64,{encoded}", "loop-mask", role="mask"
    )

    assert decoded == payload
    assert record == {
        "ref": "loop-mask",
        "sha256": "e88d1922d4b281dbc71d67ca2e98ae051c75953d3acbf9a45cd819e3ea77dc19",
        "bytes": 13,
        "media_type": "image/png",
        "role": "mask",
    }


def test_provider_sidecar_migration_rewrites_only_exact_current_identity() -> None:
    artifact_data = b"accepted provider result"
    old_ref = "authored-label"
    current_ref = "package://game/reference.png#sha256=" + "1" * 64
    prompt = "Generate the accepted original image."
    rights = {
        "status": "unreviewed",
        "attribution": [],
        "basis": ["provider output retained for private review"],
        "reviewed_at": None,
    }
    historical = ArtifactProvenance.model_validate(
        {
            "schema_version": 2,
            "provider": "provider",
            "model": "model",
            "seed": None,
            "prompt": prompt,
            "prompt_sha256": sha256(prompt.encode()).hexdigest(),
            "references": [old_ref],
            "refs": [old_ref],
            "inputs": [
                {
                    "ref": old_ref,
                    "sha256": "1" * 64,
                    "source": "content",
                    "bytes": 10,
                    "media_type": "image/png",
                }
            ],
            "params": {"n": 1, "operation": "edit"},
            "validation": {"output_nonempty": True},
            "component": {"name": "@stage-gen/image-generation", "version": "0.0.0"},
            "tool": {"name": "stage-gen", "version": "0.0.0"},
            "artifact": {
                "sha256": sha256(artifact_data).hexdigest(),
                "bytes": len(artifact_data),
                "media_type": "image/png",
            },
            "rights": rights,
            "ts": "2026-09-02T00:00:00Z",
            "attempts": 1,
            "retries": 0,
            "response": {"request_id": "historical-request", "usage": {"total": 7}},
        }
    )
    historical_data = serialize_provenance(historical)
    mask_input = {
        "ref": "loop-mask",
        "sha256": "2" * 64,
        "source": "content",
        "bytes": 11,
        "media_type": "image/png",
    }
    expected_identity: dict[str, object] = {
        "schema_version": 2,
        "provider": "provider",
        "model": "model",
        "seed": None,
        "prompt": prompt,
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "references": [current_ref, "loop-mask"],
        "refs": [current_ref, "loop-mask"],
        "inputs": [
            {
                "ref": current_ref,
                "sha256": "1" * 64,
                "source": "content",
                "bytes": 10,
                "media_type": "image/png",
            },
            mask_input,
        ],
        "params": {"n": 1, "operation": "edit"},
        "validation": {"output_nonempty": True},
        "component": {"name": "@stage-gen/image-generation", "version": "0.0.0"},
        "tool": {"name": "stage-gen", "version": "0.0.0"},
        "rights": rights,
    }
    ref_migration = {
        "index": 0,
        "classification": "non_provider_transmitted_provenance_identity_hardening",
        "historical_ref": old_ref,
        "current_ref": current_ref,
        "package_member": "reference.png",
        "sha256": "1" * 64,
    }
    mask_gap: dict[str, object] = {
        "classification": "historical_sidecar_omission_deterministically_reconstructed",
        "mask_input": mask_input,
    }

    migrated_data, audit = _migrate_provider_sidecar(
        node_id="provider-node",
        sidecar_ref="artifact.png.meta.json",
        historical_data=historical_data,
        artifact_data=artifact_data,
        expected_identity=expected_identity,
        equivalent_ref_label_normalizations=[ref_migration],
        historical_loop_mask_omission_reconstruction=mask_gap,
    )

    migrated = ArtifactProvenance.model_validate_json(migrated_data)
    assert migrated.references == [current_ref, "loop-mask"]
    assert [item.ref for item in migrated.inputs] == [current_ref, "loop-mask"]
    assert migrated.artifact == historical.artifact
    assert migrated.response == historical.response
    assert migrated.attempts == historical.attempts
    assert migrated.retries == historical.retries
    assert migrated.ts == historical.ts
    assert migrated.rights == historical.rights
    historical_audit = cast(dict[str, object], audit["historical_sidecar"])
    migrated_audit = cast(dict[str, object], audit["migrated_sidecar"])
    assert historical_audit["sha256"] == sha256(historical_data).hexdigest()
    assert migrated_audit["sha256"] == sha256(migrated_data).hexdigest()
    assert audit["equivalent_ref_label_normalizations"] == [ref_migration]
    assert audit["historical_loop_mask_omission_reconstruction"] == mask_gap
    preserved = cast(dict[str, Any], audit["preserved_historical_fields"])
    assert all(cast(dict[str, object], value)["exact"] for value in preserved.values())
    field_migrations = cast(list[dict[str, Any]], audit["exact_field_migration"])
    assert next(item for item in field_migrations if item["field"] == "inputs")["changed"]


def test_authored_label_to_package_ref_migration_requires_same_card_member(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    node = next(
        item
        for item in plan.graph.nodes
        if not item.is_local and item.card is not None and item.card.authored_inputs
    )
    assert node.card is not None
    authored = node.card.authored_inputs[0]
    source_node = node.model_dump(mode="json")
    catalog = object.__new__(_RecordedProviderCatalog)
    catalog._plan = plan
    catalog._source_nodes = {node.node_id: source_node}
    current_ref = f"package://{plan.graph.game_id}/{authored.ref}#sha256={authored.sha256}"
    current = [
        {
            "ref": current_ref,
            "sha256": authored.sha256,
            "bytes": 123,
            "media_type": "image/png",
            "role": "reference",
        }
    ]
    historical = [
        {
            "ref": authored.label,
            "sha256": authored.sha256,
            "source": "content",
            "bytes": 123,
            "media_type": "image/png",
        }
    ]

    assert catalog._compare_ordered_inputs(node, historical, current) == [
        {
            "index": 0,
            "classification": "non_provider_transmitted_provenance_identity_hardening",
            "historical_ref": authored.label,
            "current_ref": current_ref,
            "package_member": authored.ref,
            "sha256": authored.sha256,
        }
    ]

    historical[0]["ref"] = "unbound-label"
    with pytest.raises(ProviderReplayMismatch, match="exact historical-card-to-current-package"):
        catalog._compare_ordered_inputs(node, historical, current)


def test_authored_ref_migration_never_admits_byte_or_mime_drift(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    node = next(
        item
        for item in plan.graph.nodes
        if not item.is_local and item.card is not None and item.card.authored_inputs
    )
    assert node.card is not None
    authored = node.card.authored_inputs[0]
    catalog = object.__new__(_RecordedProviderCatalog)
    catalog._plan = plan
    catalog._source_nodes = {node.node_id: node.model_dump(mode="json")}
    current = [
        {
            "ref": f"package://{plan.graph.game_id}/{authored.ref}#sha256={authored.sha256}",
            "sha256": authored.sha256,
            "bytes": 123,
            "media_type": "image/png",
            "role": "reference",
        }
    ]
    historical = [
        {
            "ref": authored.label,
            "sha256": authored.sha256,
            "source": "content",
            "bytes": 124,
            "media_type": "image/png",
        }
    ]

    with pytest.raises(ProviderReplayMismatch, match="bytes and MIME"):
        catalog._compare_ordered_inputs(node, historical, current)


def test_rejected_loop_provider_attempt_records_truthful_fallback_ledger(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, generated_loop=True)
    node = next(
        item
        for item in plan.graph.nodes
        if any(port.port_id == "loop_report" for port in item.ports) and not item.is_local
    )
    run_dir = tmp_path / "run"
    attempt_ref = next(port.artifact_ref for port in node.ports if port.kind == "attempt-ledger-v2")
    attempt_path = run_dir / attempt_ref
    attempt_path.parent.mkdir(parents=True)
    attempt_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "kind": "sideview-runner-attempt-ledger-v2",
                "node_id": node.node_id,
                "cache_hit": False,
                "provider_operations": 1,
                "output_selection": "fallback_output",
                "prompt_sha256": "0" * 64,
                "attempts": [
                    {
                        "attempt": 1,
                        "outcome": "not_selected",
                        "prompt_sha256": "0" * 64,
                        "reason": "provider attempt did not produce the selected output",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report_path = run_dir / node.port("loop_report").artifact_ref
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "provider_operations": 1,
                "rejected_construction": node.params["construction"],
                "construction": "mirror_repeat",
                "rejection": (
                    "provider return context bands disagree on the vertical offset "
                    "(-64 vs -48, tolerance 6)"
                ),
                "repeat": {"validator_version": "single-axis-continuity-v2"},
            }
        ),
        encoding="utf-8",
    )
    loop_port = node.port("loop_image")
    assert loop_port.sidecar_ref is not None
    loop_path = run_dir / loop_port.artifact_ref
    loop_path.parent.mkdir(parents=True, exist_ok=True)
    loop_path.write_bytes(b"current mirror fallback")
    loop_sidecar_path = run_dir / loop_port.sidecar_ref
    loop_sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    loop_sidecar_path.write_bytes(b"{}")
    catalog = object.__new__(_RecordedProviderCatalog)
    catalog._run_dir = run_dir
    catalog._entries = {node.node_id: {"migration": {}}}
    catalog._types = runner_type_index()
    dependency_result = NodeExecutionResult(
        cache=CacheDisposition.MISS,
        attempts=1,
        provider_operations=0,
    )
    context = NodeExecutionContext(
        invocation_id="fallback-ledger",
        graph_sha256=plan.graph.graph_sha256,
        dependency_results={dependency: dependency_result for dependency in node.depends_on},
    )

    catalog.finalize_cache_entry(
        node,
        context,
        NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=1,
            provider_operations=1,
        ),
        cache_record={"lineage": []},
        cache_record_bytes=b"{}",
    )

    entry = catalog._entries[node.node_id]
    migration = cast(dict[str, Any], entry["migration"])
    assert migration["output_selection"] == "fallback_output"
    rejection = cast(dict[str, Any], entry["provider_output_rejection"])
    assert rejection["classification"] == "current_validator_selected_deterministic_fallback"
    assert rejection["registration_facts"] == {
        "left_context_vertical_offset": -64,
        "right_context_vertical_offset": -48,
        "tolerance": 6,
    }
    assert rejection["algorithm_identity"]["fallback"] == "mirror_repeat@mirror-repeat-v1"
    assert rejection["published_fallback_bundle"]["image"]["sha256"] == (
        "86f0e97fc85947b2c3e0b1e8e9fc9ab7973571f684d4820752bcd89225a0aa62"
    )

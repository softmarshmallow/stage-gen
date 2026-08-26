from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from PIL import Image

FIXTURES = Path(__file__).parents[2] / "docs/check-fixtures"


def _load_media_rights() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts/media_rights.py"
    spec = importlib.util.spec_from_file_location("stage_gen_media_rights", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MEDIA_RIGHTS = _load_media_rights()
check_generated_media_publication = MEDIA_RIGHTS.check_generated_media_publication
validate_published_media_copy = MEDIA_RIGHTS.validate_published_media_copy
validate_published_media_record = MEDIA_RIGHTS.validate_published_media_record


def _fixture(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return cast(dict[str, Any], value)


def test_accepts_an_artifact_specific_approval_record_without_decoding_media() -> None:
    assert validate_published_media_record(_fixture("media-rights-approved.json")) == []


def test_rejects_unreviewed_rights_mismatched_facts_and_temp_source_refs() -> None:
    failures = validate_published_media_record(_fixture("media-rights-unreviewed.json"))
    assert "inventory reviewStatus must be repository-approved" in failures
    assert "sidecar artifact digest does not match media bytes" in failures
    assert "sidecar artifact byte size does not match media bytes" in failures
    assert "sidecar.inputs[0].ref must be a stable non-file identifier" in failures
    assert "sidecar.rights is required for repository publication" in failures


def test_rejects_non_integer_and_out_of_range_media_byte_counts() -> None:
    cases: tuple[tuple[object, object], ...] = (
        (1, True),
        (1, 1.0),
        (-1, -1),
        (0, 0),
        (9_007_199_254_740_992, 9_007_199_254_740_992),
    )
    for observed_bytes, artifact_bytes in cases:
        value = _fixture("media-rights-approved.json")
        value["observed"]["bytes"] = observed_bytes
        value["sidecar"]["artifact"]["bytes"] = artifact_bytes
        failures = validate_published_media_record(value)
        assert "sidecar artifact byte size does not match media bytes" in failures

    valid = _fixture("media-rights-approved.json")
    valid["observed"]["bytes"] = 1
    valid["sidecar"]["artifact"]["bytes"] = 1
    assert validate_published_media_record(valid) == []


def test_rejects_non_positive_or_non_integer_observed_and_input_byte_counts() -> None:
    invalid_values: tuple[object, ...] = (
        True,
        1.0,
        -1,
        0,
        9_007_199_254_740_992,
    )
    for invalid in invalid_values:
        observed = _fixture("media-rights-approved.json")
        observed["observed"]["bytes"] = invalid
        assert (
            "observed media digest and byte size are required"
            in validate_published_media_record(observed)
        )

        source = _fixture("media-rights-approved.json")
        source["sidecar"]["inputs"][0]["bytes"] = invalid
        assert (
            "sidecar.inputs[0].bytes must be a positive integer"
            in validate_published_media_record(source)
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("license_id", "LicenseRef-Legacy"),
        ("notice", "example.LICENSE.md"),
        ("notice_sha256", "a" * 64),
        ("notice_bytes", 64),
    ),
)
def test_rejects_legacy_license_and_notice_fields(field: str, value: object) -> None:
    legacy = _fixture("media-rights-approved.json")
    legacy["sidecar"]["rights"][field] = value
    assert "sidecar.rights fields are incomplete or unsupported" in validate_published_media_record(
        legacy
    )


def test_rejects_provider_only_rights_basis() -> None:
    provenance_only = _fixture("media-rights-approved.json")
    provenance_only["sidecar"]["rights"]["basis"] = ["provider provenance only"]
    assert (
        "sidecar.rights.basis cannot rely only on provider provenance"
        in validate_published_media_record(provenance_only)
    )


def test_accepts_optional_stable_attribution_and_rejects_unsafe_values() -> None:
    attributed = _fixture("media-rights-approved.json")
    attributed["sidecar"]["rights"]["attribution"] = ["Example source author"]
    assert validate_published_media_record(attributed) == []

    attributed["sidecar"]["rights"]["attribution"] = ["source at /private/tmp/input.png"]
    assert (
        "sidecar.rights.attribution must contain stable reviewed values"
        in validate_published_media_record(attributed)
    )


def test_requires_role_based_listening_attestation_without_legal_name() -> None:
    value = _fixture("media-rights-approved.json")
    del value["entry"]["listeningReview"]["authorityBasis"]
    value["entry"]["listeningReview"]["result"] = "approved"
    failures = validate_published_media_record(value)
    assert "inventory listeningReview.authorityBasis is required" in failures
    assert "inventory listeningReview.result must record the protected-material finding" in failures


def test_requires_generated_media_copies_to_remain_byte_identical() -> None:
    digest = "a" * 64
    canonical_entry = {"path": "canonical/generated/audio.mp3"}
    entry = {"path": "copies/generated/audio.mp3", "copyOf": canonical_entry["path"]}
    observed = {
        "sha256": digest,
        "sidecarSha256": digest,
    }
    assert (
        validate_published_media_copy(
            {
                "entry": entry,
                "canonicalEntry": canonical_entry,
                "observed": observed,
                "canonicalObserved": copy.deepcopy(observed),
            }
        )
        == []
    )
    failures = validate_published_media_copy(
        {
            "entry": entry,
            "canonicalEntry": canonical_entry,
            "observed": {**observed, "sidecarSha256": "b" * 64},
            "canonicalObserved": observed,
        }
    )
    assert "provenance sidecar must match copyOf exactly" in failures


def _generated_derivative_record() -> dict[str, Any]:
    artifact_digest = "a" * 64
    review_digest = "b" * 64
    attestation = "independent-generated-derivative-review-a"
    skill_name = "compile-theme-art-direction"
    skill_digest = "f" * 64
    canonical_theme = json.dumps(
        {
            "schema_version": 1,
            "compiler_version": 6,
            "handles": {
                "sexual_content": 4,
                "nudity_exposure": 4,
                "hostile_action": 0,
                "injury_detail": 0,
                "substance_depiction": 0,
                "threat_disturbance": 0,
            },
        },
        separators=(",", ":"),
    )
    theme_digest = hashlib.sha256(
        json.dumps(
            {
                "canonical_theme_json": canonical_theme,
                "theme_skill_name": skill_name,
                "theme_skill_sha256": skill_digest,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    prompts = (
        "Original neutral shared-seed prompt with exact punctuation.",
        "Exact reference-edit prompt.\nIt preserves its final newline.\n",
    )
    inputs = []
    for index, (role, digest, prompt) in enumerate(
        zip(
            ("neutral_shared_seed", "compiled_maximum_candidate"),
            ("c" * 64, "d" * 64),
            prompts,
            strict=True,
        )
    ):
        reference = f"sha256:{digest}"
        inputs.append(
            {
                "role": role,
                "ref": reference,
                "sha256": digest,
                "bytes": 1024 + index,
                "media_type": "image/png",
                "width": 1024,
                "height": 1536,
                "original_prompt": prompt,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "prompt_hash_scope": "full_exact_utf8_string",
                "rights_basis": [
                    f"Artifact-specific source authorization for exact bytes {reference}"
                ],
            }
        )
    shared_review = {
        "status": "approved",
        "result": "pass",
        "independent": True,
        "reviewed_by": "independent visual-review subagent",
        "authority_basis": "reviewer independent from the derivative producer",
        "reviewed_at": "2026-08-20T00:00:00.000Z",
        "attestation_id": attestation,
        "attested_at": "2026-08-20T00:00:00.000Z",
        "artifact_sha256": artifact_digest,
        "artifact_bytes": 2048,
        "verification_report_path": "docs/media/example.visual-review.md",
        "verification_report_sha256": review_digest,
        "verification_report_bytes": 128,
    }
    return {
        "entry": {
            "path": "docs/media/example.webp",
            "provenance_kind": "generated_image_derivative",
            "lineage_kind": "theme_art_direction_comparison_v1",
            "kind": "image",
            "sidecar_sha256": "e" * 64,
            "review_status": "repository-approved",
            "synth_id_expected": False,
            "visual_review": copy.deepcopy(shared_review),
        },
        "observed": {
            "sha256": artifact_digest,
            "bytes": 2048,
        },
        "sidecar": {
            "schema_version": 1,
            "provenance_kind": "generated_image_derivative",
            "lineage_kind": "theme_art_direction_comparison_v1",
            "state": "redistribution-approved",
            "artifact": {
                "path": "docs/media/example.webp",
                "media_type": "image/webp",
                "width": 1200,
                "height": 1200,
                "sha256": artifact_digest,
                "bytes": 2048,
            },
            "inputs": inputs,
            "generation": {
                "shared_seed": {
                    "tool": "image_gen.imagegen",
                    "artifact_ref": inputs[0]["ref"],
                    "reference_refs": [],
                    "model": None,
                    "model_status": "unavailable_from_builtin_image_tool",
                    "numeric_seed": None,
                    "numeric_seed_status": "unavailable_from_builtin_image_tool",
                    "attempt_count": 1,
                },
                "compiled_variant": {
                    "artifact_ref": inputs[1]["ref"],
                    "reference_refs": [inputs[0]["ref"]],
                    "canonical_theme_json": canonical_theme,
                    "theme_digest": theme_digest,
                    "compiler_provider": "OpenRouter",
                    "compiler_model": "openai/gpt-5.6",
                    "compiler_version": 6,
                    "compiler_attempt_count": 5,
                    "skill_name": skill_name,
                    "skill_ref": f"sha256:{skill_digest}",
                    "skill_sha256": skill_digest,
                    "plan_ref": f"sha256:{'8' * 64}",
                    "plan_sha256": "8" * 64,
                    "image_tool": "image_gen.imagegen",
                    "image_model": None,
                    "image_model_status": "unavailable_from_builtin_image_tool",
                    "image_attempt_count": 1,
                    "numeric_seed": None,
                    "numeric_seed_status": "unavailable_from_builtin_image_tool",
                    "selected_candidate_attempt": 1,
                    "bounded_image_candidate_regenerations": 2,
                    "raw_selected_source_visual_status": "fail_readable_generated_signage",
                },
            },
            "transformation": {
                "tool": "ffmpeg+cwebp",
                "version": "ffmpeg 8.0.1; cwebp 1.6.0",
                "params": {
                    "operation": "crop_append_resize_encode",
                    "input_refs": [source["ref"] for source in inputs],
                    "output": {
                        "media_type": "image/webp",
                        "width": 1200,
                        "height": 1200,
                    },
                    "quality": 82,
                },
            },
            "visual_review": {
                **copy.deepcopy(shared_review),
                "acceptance_spec": "Exact derivative composition with no readable text.",
                "evidence": {
                    "path": shared_review["verification_report_path"],
                    "verdict": "pass",
                    "ref": f"sha256:{review_digest}",
                    "sha256": review_digest,
                    "bytes": shared_review["verification_report_bytes"],
                },
            },
            "rights": {
                "status": "redistribution-approved",
                "basis": ["Artifact-specific publication authorization", attestation],
                "reviewed_at": "2026-08-20T00:00:00.000Z",
            },
        },
    }


def _generated_concept_cover_record() -> dict[str, Any]:
    artifact_digest = "a" * 64
    concept_digest = "c" * 64
    review_digest = "b" * 64
    source_digest = "d" * 64
    attestation = "independent-game-concept-cover-review-a"
    prompt = (
        "Create original game concept cover art for a moonlit marsh adventure.\n"
        "No readable text, logo, signature, watermark, or protected character."
    )
    shared_review = {
        "status": "approved",
        "result": "pass",
        "independent": True,
        "reviewed_by": "independent visual-review subagent",
        "authority_basis": "reviewer independent from the concept-cover producer",
        "reviewed_at": "2026-08-25T00:00:00.000Z",
        "attestation_id": attestation,
        "attested_at": "2026-08-25T00:00:00.000Z",
        "artifact_sha256": artifact_digest,
        "artifact_bytes": 2048,
        "verification_report_path": (
            "concept-studio/gallery/moonlit-marsh/images/cover.visual-review.md"
        ),
        "verification_report_sha256": review_digest,
        "verification_report_bytes": 128,
    }
    return {
        "entry": {
            "path": "concept-studio/gallery/moonlit-marsh/images/cover.png",
            "provenance_kind": "generated_image",
            "lineage_kind": "game_concept_cover_v1",
            "kind": "image",
            "sidecar_sha256": "e" * 64,
            "review_status": "repository-approved",
            "synth_id_expected": False,
            "visual_review": copy.deepcopy(shared_review),
        },
        "observed": {
            "sha256": artifact_digest,
            "bytes": 2048,
        },
        "sidecar": {
            "schema_version": 1,
            "provenance_kind": "generated_image",
            "lineage_kind": "game_concept_cover_v1",
            "state": "redistribution-approved",
            "artifact": {
                "path": "concept-studio/gallery/moonlit-marsh/images/cover.png",
                "media_type": "image/png",
                "width": 1536,
                "height": 1024,
                "sha256": artifact_digest,
                "bytes": 2048,
            },
            "concept": {
                "path": "concept-studio/gallery/moonlit-marsh/concept.md",
                "sha256": concept_digest,
                "bytes": 512,
            },
            "generation": {
                "prompt": prompt,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "prompt_hash_scope": "full_exact_utf8_string",
                "provider": "OpenRouter",
                "model": "openai/gpt-image-2",
                "attempt_count": 2,
                "retry_count": 1,
                "n": 1,
                "input_references": [],
                "source": {
                    "media_type": "image/jpeg",
                    "sha256": source_digest,
                    "bytes": 4096,
                    "width": 1536,
                    "height": 1024,
                },
                "normalization": {
                    "tool": "Pillow",
                    "version": "12.0.0",
                    "operation": "exif_transpose_and_png_encode",
                    "input_sha256": source_digest,
                    "output_sha256": artifact_digest,
                    "output_media_type": "image/png",
                    "width": 1536,
                    "height": 1024,
                },
            },
            "visual_review": {
                **copy.deepcopy(shared_review),
                "acceptance_spec": (
                    "Exact selected concept cover; coherent game premise and original visual "
                    "direction; no readable text, protected mark, signature, or watermark."
                ),
                "evidence": {
                    "path": shared_review["verification_report_path"],
                    "verdict": "pass",
                    "ref": f"sha256:{review_digest}",
                    "sha256": review_digest,
                    "bytes": shared_review["verification_report_bytes"],
                },
            },
            "rights": {
                "status": "redistribution-approved",
                "basis": ["Artifact-specific publication authorization", attestation],
                "reviewed_at": "2026-08-25T00:00:00.000Z",
            },
        },
    }


def _generated_transformed_concept_cover_record() -> dict[str, Any]:
    value = _generated_concept_cover_record()
    published_digest = "f" * 64
    published_bytes = 1024
    published_path = "concept-studio/gallery/moonlit-marsh/images/cover.webp"
    value["entry"]["path"] = published_path
    value["observed"].update({"sha256": published_digest, "bytes": published_bytes})
    value["sidecar"]["artifact"].update(
        {
            "path": published_path,
            "media_type": "image/webp",
            "width": 960,
            "height": 540,
            "sha256": published_digest,
            "bytes": published_bytes,
        }
    )
    value["sidecar"]["generation"]["publication_transform"] = {
        "tool": "cwebp",
        "version": "1.6.0",
        "operation": "resize_and_webp_encode",
        "input_sha256": "a" * 64,
        "output_sha256": published_digest,
        "output_media_type": "image/webp",
        "width": 960,
        "height": 540,
        "settings": {
            "quality": 82,
            "resize_width": 960,
            "resize_height": 540,
            "metadata": "none",
        },
    }
    for review in (value["entry"]["visual_review"], value["sidecar"]["visual_review"]):
        review.update(
            {
                "artifact_sha256": published_digest,
                "artifact_bytes": published_bytes,
            }
        )
    return value


def test_accepts_generated_game_concept_cover() -> None:
    assert validate_published_media_record(_generated_concept_cover_record()) == []


def test_accepts_generated_game_concept_cover_with_publication_transform() -> None:
    assert validate_published_media_record(_generated_transformed_concept_cover_record()) == []


def test_generated_game_concept_cover_rejects_invalid_publication_transform() -> None:
    value = _generated_transformed_concept_cover_record()
    value["sidecar"]["generation"]["normalization"]["output_media_type"] = "image/jpeg"
    transform = value["sidecar"]["generation"]["publication_transform"]
    transform["tool"] = "x"
    transform["input_sha256"] = "1" * 64
    transform["output_sha256"] = "2" * 64
    transform["output_media_type"] = "image/png"
    transform["width"] = 959
    settings = transform["settings"]
    settings["quality"] = 101
    settings["resize_width"] = 958
    settings["resize_height"] = 0
    settings["metadata"] = "preserve"
    settings["extra"] = True

    failures = validate_published_media_record(value)

    expected = {
        (
            "sidecar.generation.normalization.output_media_type must be image/png when "
            "publication_transform is present"
        ),
        "sidecar.generation.publication_transform.tool must be a stable value",
        (
            "sidecar.generation.publication_transform.input_sha256 must match the "
            "normalization output"
        ),
        "sidecar.generation.publication_transform.output_sha256 must match the artifact",
        "sidecar.generation.publication_transform.output_media_type must match the artifact",
        "sidecar.generation.publication_transform.width must match the artifact",
        (
            "game_concept_cover_v1 publication_transform.settings fields are incomplete "
            "or unsupported"
        ),
        ("sidecar.generation.publication_transform.settings.quality must be within [0, 100]"),
        (
            "sidecar.generation.publication_transform.settings.resize_width must match "
            "publication_transform.width"
        ),
        (
            "sidecar.generation.publication_transform.settings.resize_height must be a "
            "positive integer"
        ),
        "sidecar.generation.publication_transform.settings.metadata must be none",
    }
    assert expected <= set(failures)


def test_generated_game_concept_cover_rejects_generation_and_lineage_mismatches() -> None:
    value = _generated_concept_cover_record()
    value["entry"]["lineage_kind"] = "unknown_concept_cover_v1"
    generation = value["sidecar"]["generation"]
    generation["prompt_sha256"] = "0" * 64
    generation["attempt_count"] = 7
    generation["retry_count"] = 0
    generation["n"] = 2
    generation["input_references"] = [f"sha256:{'f' * 64}"]
    generation["normalization"]["input_sha256"] = "1" * 64
    generation["normalization"]["output_sha256"] = "2" * 64

    failures = validate_published_media_record(value)

    expected = {
        "inventory lineage_kind must select supported game_concept_cover_v1",
        "sidecar.lineage_kind must match inventory lineage_kind",
        "sidecar.generation.prompt_sha256 must digest the full exact UTF-8 prompt",
        "sidecar.generation.attempt_count must be within [1, 6]",
        "sidecar.generation.retry_count must equal attempt_count minus one",
        "sidecar.generation.n must be exactly 1",
        "sidecar.generation.input_references must be empty for game_concept_cover_v1",
        "sidecar.generation.normalization.input_sha256 must match the source media",
        "sidecar.generation.normalization.output_sha256 must match the artifact",
    }
    assert expected <= set(failures)


def test_generated_game_concept_cover_rejects_unsafe_or_incomplete_records() -> None:
    value = _generated_concept_cover_record()
    value["entry"]["reviewStatus"] = value["entry"].pop("review_status")
    value["sidecar"]["concept"]["path"] = "/private/tmp/concept.md"
    value["sidecar"]["generation"]["source"]["bytes"] = 0
    value["sidecar"]["generation"]["normalization"]["working_path"] = "/private/tmp/cover.png"

    failures = validate_published_media_record(value)

    expected = {
        "generated-image inventory fields must use lower_snake_case",
        "generated-image records must not contain private, temporary, file, data, "
        "authorization, credential, or signed-URL material",
        "game_concept_cover_v1 inventory fields are incomplete or unsupported",
        "inventory review_status must be repository-approved",
        "sidecar.concept.path must be a distinct repository-relative path",
        "sidecar.generation.source.bytes must be a positive integer",
        "game_concept_cover_v1 normalization fields are incomplete or unsupported",
    }
    assert expected <= set(failures)


def test_generated_game_concept_cover_rejects_cross_package_bindings() -> None:
    value = _generated_concept_cover_record()
    other_root = "concept-studio/gallery/other-concept"
    value["sidecar"]["concept"]["path"] = f"{other_root}/concept.md"
    for review in (value["entry"]["visual_review"], value["sidecar"]["visual_review"]):
        review["verification_report_path"] = f"{other_root}/images/cover.visual-review.md"
    value["sidecar"]["visual_review"]["evidence"]["path"] = (
        f"{other_root}/images/cover.visual-review.md"
    )

    failures = validate_published_media_record(value)

    expected = {
        "sidecar.concept.path must stay inside the artifact concept gallery package",
        (
            "inventory visual_review.verification_report_path must stay inside the artifact "
            "concept gallery package"
        ),
        (
            "sidecar.visual_review.verification_report_path must stay inside the artifact "
            "concept gallery package"
        ),
        (
            "sidecar.visual_review.evidence.path must stay inside the artifact concept "
            "gallery package"
        ),
    }
    assert expected <= set(failures)


def test_generated_game_concept_cover_rejects_noncanonical_gallery_path() -> None:
    value = _generated_concept_cover_record()
    value["entry"]["path"] = "gallery/moonlit-marsh/images/cover.png"
    value["sidecar"]["artifact"]["path"] = value["entry"]["path"]

    failures = validate_published_media_record(value)

    assert "inventory artifact path must be inside concept-studio/gallery/<concept_id>" in failures


def test_generated_game_concept_cover_reuses_strict_review_bindings() -> None:
    value = _generated_concept_cover_record()
    value["entry"]["synth_id_expected"] = True
    value["entry"]["visual_review"]["independent"] = False
    value["sidecar"]["visual_review"]["verification_report_sha256"] = "1" * 64

    failures = validate_published_media_record(value)

    expected = {
        "inventory synth_id_expected must explicitly be false for generated image",
        "inventory visual_review.independent must be true",
        "inventory and sidecar visual_review.independent must match",
        "inventory and sidecar visual_review.verification_report_sha256 must match",
        "sidecar.visual_review.evidence.sha256 must match the review report",
    }
    assert expected <= set(failures)


def test_accepts_generated_image_derivative_without_tracked_raw_sources() -> None:
    assert validate_published_media_record(_generated_derivative_record()) == []


def test_generated_image_derivative_rejects_camel_case_temp_refs_and_missing_source_facts() -> None:
    value = _generated_derivative_record()
    value["entry"]["reviewStatus"] = value["entry"].pop("review_status")
    value["sidecar"]["visualReview"] = value["sidecar"].pop("visual_review")
    source = value["sidecar"]["inputs"][0]
    source["ref"] = "file:/private/tmp/seed.png"
    del source["original_prompt"]
    del source["rights_basis"]
    value["sidecar"]["capture"] = {}
    value["sidecar"]["transformation"]["params"]["working_path"] = "/private/tmp/output.webp"

    failures = validate_published_media_record(value)

    expected = {
        "generated-image derivative inventory fields must use lower_snake_case",
        "generated-image derivative sidecar fields must use lower_snake_case",
        "inventory review_status must be repository-approved",
        "sidecar.inputs[0].ref must match its sha256 content identifier",
        "sidecar.inputs[0].original_prompt must contain the full prompt",
        "sidecar.inputs[0].rights_basis must contain source-specific reviewed values",
        "generated-image derivative sidecar must use transformation, never capture",
        "sidecar.transformation.params must not contain private or temporary paths",
        "sidecar.visual_review is required for generated-image derivative",
    }
    assert expected <= set(failures)


def test_generated_image_derivative_rejects_prompt_digest_rights_and_review_mismatches() -> None:
    value = _generated_derivative_record()
    value["sidecar"]["inputs"][1]["prompt_sha256"] = "0" * 64
    value["sidecar"]["inputs"][1]["rights_basis"] = ["Generic provider provenance"]
    value["sidecar"]["visual_review"]["artifact_sha256"] = "1" * 64
    value["sidecar"]["visual_review"]["evidence"]["sha256"] = "2" * 64

    failures = validate_published_media_record(value)

    expected = {
        "sidecar.inputs[1].prompt_sha256 must digest the full exact UTF-8 prompt",
        "sidecar.inputs[1].rights_basis must bind the exact source content identifier",
        "sidecar.visual_review.artifact_sha256 must match the artifact",
        "inventory and sidecar visual_review.artifact_sha256 must match",
        "sidecar.visual_review.evidence.sha256 must match the review report",
        "sidecar.visual_review.evidence.ref must match its sha256",
    }
    assert expected <= set(failures)

    missing_rights = _generated_derivative_record()
    del missing_rights["sidecar"]["rights"]
    assert (
        "sidecar.rights is required for repository publication"
        in validate_published_media_record(missing_rights)
    )


def test_generated_image_derivative_rejects_unbound_generation_facts() -> None:
    value = _generated_derivative_record()
    compiled = value["sidecar"]["generation"]["compiled_variant"]
    compiled["reference_refs"] = []
    compiled["theme_digest"] = "0" * 64

    failures = validate_published_media_record(value)

    expected = {
        "sidecar.generation.compiled_variant.reference_refs must bind only the shared seed",
        (
            "sidecar.generation.compiled_variant.theme_digest must bind canonical theme "
            "and compiler skill identity"
        ),
    }
    assert expected <= set(failures)


def test_generated_image_derivative_accepts_a_stable_human_reviewer_identity() -> None:
    value = _generated_derivative_record()
    for review in (value["entry"]["visual_review"], value["sidecar"]["visual_review"]):
        review["reviewed_by"] = "Ada Reviewer, independent human reviewer"

    assert validate_published_media_record(value) == []


@pytest.mark.parametrize(
    "unsafe_value",
    (
        "private source at /home/alice/reference.png",
        "private key at /root/.ssh/id_ed25519",
        "system path /etc/passwd",
        "delimiter path source,/etc/passwd",
        "delimiter path source;/etc/passwd",
        "home path ~/.ssh/config",
        "home shorthand ~",
        "temporary source at tmp/reference.png",
        "relative URI file:relative.png",
        "Windows path C:/Users/alice/reference.png",
        r"Windows path C:\Users\alice\reference.png",
        "https://alice:supersecret@example.invalid/reference.png",
        "https://assets.example.invalid/image.png?X-Amz-Signature=secret",
        "https://assets.example.invalid/image.png?password=secret",
        "https://assets.example.invalid/image.png?client_secret=secret",
        "Authorization: Bearer abcdefghijklmnop",
        "Authorization: Basic YWxpY2U6c2VjcmV0",
        "data:image/png;base64,AAAA",
    ),
)
def test_generated_image_derivative_rejects_forbidden_material_anywhere(
    unsafe_value: str,
) -> None:
    value = _generated_derivative_record()
    value["sidecar"]["visual_review"]["acceptance_spec"] = unsafe_value

    assert (
        "generated-image derivative records must not contain private, temporary, file, "
        "data, authorization, credential, or signed-URL material"
        in validate_published_media_record(value)
    )


@pytest.mark.parametrize(
    "sensitive_key",
    (
        "openrouter_api_key",
        "api_token",
        "client_secret",
        "secret_key",
        "private_key",
        "authorization",
    ),
)
def test_generated_image_derivative_rejects_nested_sensitive_fields(
    sensitive_key: str,
) -> None:
    value = _generated_derivative_record()
    value["sidecar"]["visual_review"]["evidence"][sensitive_key] = "sensitive-value"

    assert (
        "generated-image derivative records must not contain private, temporary, file, "
        "data, authorization, credential, or signed-URL material"
        in validate_published_media_record(value)
    )


def test_generated_image_derivative_accepts_a_benign_public_https_url() -> None:
    value = _generated_derivative_record()
    value["sidecar"]["visual_review"]["acceptance_spec"] = (
        "Public reference https://example.invalid/reference.png?version=1"
    )

    assert validate_published_media_record(value) == []


def test_generated_image_derivative_accepts_benign_path_and_authorization_prose() -> None:
    value = _generated_derivative_record()
    value["sidecar"]["visual_review"]["acceptance_spec"] = (
        "Compare crop / framing treatments. Authorization: approved by project owner"
    )

    assert validate_published_media_record(value) == []


def test_generated_image_derivative_rejects_invalid_model_attempt_and_candidate_facts() -> None:
    value = _generated_derivative_record()
    seed = value["sidecar"]["generation"]["shared_seed"]
    compiled = value["sidecar"]["generation"]["compiled_variant"]
    seed["model"] = "reported-image-model"
    seed["model_status"] = "unavailable_from_builtin_image_tool"
    seed["attempt_count"] = 7
    compiled["compiler_attempt_count"] = 7
    compiled["image_attempt_count"] = 7
    compiled["selected_candidate_attempt"] = 4

    failures = validate_published_media_record(value)

    expected = {
        ("sidecar.generation.shared_seed.model must be stable and model_status must be reported"),
        "sidecar.generation.shared_seed.attempt_count must be within [1, 6]",
        ("sidecar.generation.compiled_variant.compiler_attempt_count must be within [1, 6]"),
        "sidecar.generation.compiled_variant.image_attempt_count must be within [1, 6]",
        (
            "sidecar.generation.compiled_variant.selected_candidate_attempt must not "
            "exceed the initial candidate plus regenerations"
        ),
    }
    assert expected <= set(failures)


def test_generated_image_derivative_rejects_bad_artifact_and_output_dimensions() -> None:
    value = _generated_derivative_record()
    value["sidecar"]["artifact"]["width"] = 0
    value["sidecar"]["transformation"]["params"]["output"]["width"] = 0

    failures = validate_published_media_record(value)

    assert "sidecar.artifact.width must be a positive integer" in failures
    assert "sidecar.transformation.params.output.width must be a positive integer" in failures


def test_generated_image_derivative_rejects_missing_or_unsupported_lineage_kind() -> None:
    missing = _generated_derivative_record()
    del missing["entry"]["lineage_kind"]
    del missing["sidecar"]["lineage_kind"]
    assert (
        "inventory lineage_kind must select supported theme_art_direction_comparison_v1"
        in validate_published_media_record(missing)
    )

    unsupported = _generated_derivative_record()
    unsupported["entry"]["lineage_kind"] = "unknown_derivative_v1"
    unsupported["sidecar"]["lineage_kind"] = "unknown_derivative_v1"
    assert (
        "inventory lineage_kind must select supported theme_art_direction_comparison_v1"
        in validate_published_media_record(unsupported)
    )


def test_theme_art_direction_subtype_rejects_unknown_top_level_fields() -> None:
    value = _generated_derivative_record()
    value["entry"]["extra_field"] = "unsupported"
    value["sidecar"]["extra_field"] = "unsupported"

    failures = validate_published_media_record(value)

    assert (
        "theme_art_direction_comparison_v1 inventory fields are incomplete or unsupported"
        in failures
    )
    assert (
        "theme_art_direction_comparison_v1 sidecar fields are incomplete or unsupported" in failures
    )


def _write_synthetic_publication(repo: Path) -> tuple[Path, Path]:
    media_root = repo / "media"
    media_root.mkdir()
    artifact = media_root / "clip.mp3"
    payload = b"synthetic publication bytes, not encoded media"
    artifact.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    fixture = _fixture("media-rights-approved.json")
    fixture["entry"]["path"] = "media/clip.mp3"
    fixture["observed"] = {"sha256": digest, "bytes": len(payload)}
    fixture["sidecar"]["artifact"] = {
        "sha256": digest,
        "bytes": len(payload),
        "media_type": "audio/mpeg",
    }
    sidecar = artifact.with_name(f"{artifact.name}.meta.json")
    sidecar.write_text(json.dumps(fixture["sidecar"]), encoding="utf-8")
    inventory = repo / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "roots": ["media"],
                "media": [fixture["entry"]],
            }
        ),
        encoding="utf-8",
    )
    return inventory, artifact


def _write_generated_derivative_publication(repo: Path) -> tuple[Path, Path, Path, Path]:
    record = _generated_derivative_record()
    media_root = repo / "docs/media"
    media_root.mkdir(parents=True)
    artifact = media_root / "example.webp"
    artifact_bytes = b"synthetic derivative bytes; not encoded media"
    artifact.write_bytes(artifact_bytes)
    artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()
    review_path = media_root / "example.visual-review.md"
    review_bytes = b"Artifact-bound independent review: pass."
    review_path.write_bytes(review_bytes)
    review_digest = hashlib.sha256(review_bytes).hexdigest()
    record["observed"] = {
        "sha256": artifact_digest,
        "bytes": len(artifact_bytes),
    }
    record["sidecar"]["artifact"].update({"sha256": artifact_digest, "bytes": len(artifact_bytes)})
    for review in (record["entry"]["visual_review"], record["sidecar"]["visual_review"]):
        review.update(
            {
                "artifact_sha256": artifact_digest,
                "artifact_bytes": len(artifact_bytes),
                "verification_report_sha256": review_digest,
                "verification_report_bytes": len(review_bytes),
            }
        )
    record["sidecar"]["visual_review"]["evidence"].update(
        {
            "ref": f"sha256:{review_digest}",
            "sha256": review_digest,
            "bytes": len(review_bytes),
        }
    )
    sidecar_path = Path(f"{artifact}.meta.json")
    sidecar_bytes = json.dumps(record["sidecar"], indent=2).encode("utf-8")
    sidecar_path.write_bytes(sidecar_bytes)
    record["entry"]["sidecar_sha256"] = hashlib.sha256(sidecar_bytes).hexdigest()
    inventory = repo / "docs/generated-media-inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "roots": ["docs/media"],
                "media": [record["entry"]],
            }
        ),
        encoding="utf-8",
    )
    return inventory, artifact, sidecar_path, review_path


def _encoded_concept_cover_png() -> bytes:
    output = BytesIO()
    with Image.new("RGB", (1536, 1024), color=(18, 35, 52)) as image:
        image.save(output, format="PNG")
    return output.getvalue()


def _write_generated_concept_cover_publication(
    repo: Path,
    *,
    artifact_bytes: bytes | None = None,
) -> tuple[Path, Path, Path, Path]:
    record = _generated_concept_cover_record()
    concept_root = repo / "concept-studio/gallery/moonlit-marsh"
    media_root = concept_root / "images"
    media_root.mkdir(parents=True)
    artifact = media_root / "cover.png"
    if artifact_bytes is None:
        artifact_bytes = _encoded_concept_cover_png()
    artifact.write_bytes(artifact_bytes)
    artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()
    concept = concept_root / "concept.md"
    concept_bytes = b"# Moonlit Marsh\n\nAn original game concept.\n"
    concept.write_bytes(concept_bytes)
    concept_digest = hashlib.sha256(concept_bytes).hexdigest()
    review_path = media_root / "cover.visual-review.md"
    review_bytes = b"Artifact-bound independent concept-cover review: pass."
    review_path.write_bytes(review_bytes)
    review_digest = hashlib.sha256(review_bytes).hexdigest()

    record["observed"] = {
        "sha256": artifact_digest,
        "bytes": len(artifact_bytes),
    }
    record["sidecar"]["artifact"].update({"sha256": artifact_digest, "bytes": len(artifact_bytes)})
    record["sidecar"]["concept"].update({"sha256": concept_digest, "bytes": len(concept_bytes)})
    record["sidecar"]["generation"]["normalization"]["output_sha256"] = artifact_digest
    for review in (record["entry"]["visual_review"], record["sidecar"]["visual_review"]):
        review.update(
            {
                "artifact_sha256": artifact_digest,
                "artifact_bytes": len(artifact_bytes),
                "verification_report_sha256": review_digest,
                "verification_report_bytes": len(review_bytes),
            }
        )
    record["sidecar"]["visual_review"]["evidence"].update(
        {
            "ref": f"sha256:{review_digest}",
            "sha256": review_digest,
            "bytes": len(review_bytes),
        }
    )
    sidecar_path = Path(f"{artifact}.meta.json")
    sidecar_bytes = json.dumps(record["sidecar"], indent=2).encode("utf-8")
    sidecar_path.write_bytes(sidecar_bytes)
    record["entry"]["sidecar_sha256"] = hashlib.sha256(sidecar_bytes).hexdigest()
    inventory = repo / "docs/generated-media-inventory.json"
    inventory.parent.mkdir(parents=True)
    inventory.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "roots": ["concept-studio/gallery"],
                "media": [record["entry"]],
            }
        ),
        encoding="utf-8",
    )
    return inventory, artifact, concept, sidecar_path


def test_publication_discovery_validates_bytes_sidecar_and_inventory(
    tmp_path: Path,
) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    assert check_generated_media_publication(tmp_path, inventory).failures == ()

    artifact.write_bytes(b"changed")
    failures = check_generated_media_publication(tmp_path, inventory).failures
    assert any("sidecar artifact digest does not match media bytes" in item for item in failures)
    assert any("sidecar artifact byte size does not match media bytes" in item for item in failures)


def test_generated_derivative_publication_binds_review_and_sidecar_without_raw_sources(
    tmp_path: Path,
) -> None:
    inventory, _artifact, sidecar, review = _write_generated_derivative_publication(tmp_path)
    assert check_generated_media_publication(tmp_path, inventory).failures == ()

    review.write_text("changed review evidence", encoding="utf-8")
    failures = check_generated_media_publication(tmp_path, inventory).failures
    assert any("visual review evidence digest does not match" in item for item in failures)
    assert any("visual review evidence byte size does not match" in item for item in failures)

    review.write_bytes(b"Artifact-bound independent review: pass.")
    sidecar.write_bytes(sidecar.read_bytes() + b"\n")
    failures = check_generated_media_publication(tmp_path, inventory).failures
    assert any(
        "inventory sidecar_sha256 does not match adjacent provenance sidecar" in item
        for item in failures
    )


def test_generated_concept_cover_publication_binds_concept_document(
    tmp_path: Path,
) -> None:
    inventory, _artifact, concept, _sidecar = _write_generated_concept_cover_publication(tmp_path)
    assert check_generated_media_publication(tmp_path, inventory).failures == ()

    concept.write_text("# Changed concept\n", encoding="utf-8")
    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert any("concept document digest does not match" in item for item in failures)
    assert any("concept document byte size does not match" in item for item in failures)


def test_generated_concept_cover_publication_rejects_undecodable_image_bytes(
    tmp_path: Path,
) -> None:
    inventory, _artifact, _concept, _sidecar = _write_generated_concept_cover_publication(
        tmp_path,
        artifact_bytes=b"not an encoded image",
    )

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert any("generated image artifact must be a decodable image" in item for item in failures)


@pytest.mark.parametrize(
    ("binding", "expected_failure"),
    (
        ("artifact", "generated-media roots cannot contain symlinks"),
        ("sidecar", "adjacent provenance sidecar must be a regular file"),
        ("concept", "sidecar.concept.path is unsafe"),
        ("review", "sidecar.visual_review.evidence.path is unsafe"),
    ),
)
def test_generated_concept_cover_publication_rejects_symlinked_package_bindings(
    tmp_path: Path,
    binding: str,
    expected_failure: str,
) -> None:
    inventory, artifact, concept, sidecar = _write_generated_concept_cover_publication(tmp_path)
    paths = {
        "artifact": artifact,
        "sidecar": sidecar,
        "concept": concept,
        "review": artifact.parent / "cover.visual-review.md",
    }
    selected = paths[binding]
    outside = tmp_path / "outside" / selected.name
    outside.parent.mkdir()
    outside.write_bytes(selected.read_bytes())
    selected.unlink()
    selected.symlink_to(outside)

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert any(expected_failure in item for item in failures)


def test_publication_discovery_rejects_unlisted_media_and_symlinks(tmp_path: Path) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    (artifact.parent / "unlisted.mp3").write_bytes(b"synthetic")
    (artifact.parent / "linked.mp3").symlink_to(artifact)

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert any("binary media is not enumerated" in item for item in failures)
    assert any("generated-media roots cannot contain symlinks" in item for item in failures)


def test_publication_discovery_rejects_unsafe_roots_and_missing_sidecars(
    tmp_path: Path,
) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    artifact.with_name(f"{artifact.name}.meta.json").unlink()
    value = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    value["roots"].append("../outside")
    inventory.write_text(json.dumps(value), encoding="utf-8")

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert any("inventory root is unsafe" in item for item in failures)
    assert any("adjacent provenance sidecar is missing" in item for item in failures)


def test_publication_inventory_rejects_repository_root_and_normalized_aliases(
    tmp_path: Path,
) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    original = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    unsafe_roots = (".", "./", ".//", "media/..", str(tmp_path.resolve()))
    for unsafe_root in unsafe_roots:
        value = copy.deepcopy(original)
        value["roots"] = [unsafe_root]
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert any("inventory root is unsafe" in item for item in failures)

    unsafe_entries = (
        ".",
        "./media/clip.mp3",
        "media/../media/clip.mp3",
        str(artifact.resolve()),
    )
    for unsafe_entry in unsafe_entries:
        value = copy.deepcopy(original)
        value["media"][0]["path"] = unsafe_entry
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory contains an unsafe media path" in failures


def test_publication_inventory_rejects_direct_and_indirect_symlink_loops(
    tmp_path: Path,
) -> None:
    inventory, _artifact = _write_synthetic_publication(tmp_path)
    original = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    (tmp_path / "direct-loop").symlink_to("direct-loop", target_is_directory=True)
    (tmp_path / "indirect-a").symlink_to("indirect-b", target_is_directory=True)
    (tmp_path / "indirect-b").symlink_to("indirect-a", target_is_directory=True)

    for unsafe_root in ("direct-loop", "indirect-a"):
        value = copy.deepcopy(original)
        value["roots"] = [unsafe_root]
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory root is unsafe" in failures
        assert str(tmp_path) not in "\n".join(failures)

    for unsafe_entry in ("direct-loop", "indirect-a/clip.mp3"):
        value = copy.deepcopy(original)
        value["media"][0]["path"] = unsafe_entry
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory contains an unsafe media path" in failures
        assert str(tmp_path) not in "\n".join(failures)


def test_publication_inventory_rejects_ordinary_and_broken_symlink_aliases(
    tmp_path: Path,
) -> None:
    inventory, artifact = _write_synthetic_publication(tmp_path)
    original = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    (tmp_path / "media-alias").symlink_to("media", target_is_directory=True)
    (tmp_path / "broken-root").symlink_to("missing-root", target_is_directory=True)
    (tmp_path / "clip-alias.mp3").symlink_to(artifact.relative_to(tmp_path))
    (tmp_path / "broken-entry.mp3").symlink_to("missing.mp3")

    for unsafe_root in ("media-alias", "broken-root"):
        value = copy.deepcopy(original)
        value["roots"] = [unsafe_root]
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory root is unsafe" in failures

    for unsafe_entry in ("clip-alias.mp3", "broken-entry.mp3"):
        value = copy.deepcopy(original)
        value["media"][0]["path"] = unsafe_entry
        inventory.write_text(json.dumps(value), encoding="utf-8")
        failures = check_generated_media_publication(tmp_path, inventory).failures
        assert "generated-media inventory contains an unsafe media path" in failures


def test_publication_inventory_sanitizes_path_resolution_os_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory, _artifact = _write_synthetic_publication(tmp_path)

    def fail_resolve(_path: Path, *, strict: bool = False) -> Path:
        del strict
        raise OSError(f"synthetic secret at {tmp_path}")

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert failures == (
        "generated-media inventory root is unsafe",
        "generated-media inventory contains an unsafe media path",
    )
    rendered = "\n".join(failures)
    assert "synthetic secret" not in rendered
    assert str(tmp_path) not in rendered


def test_publication_inventory_requires_exact_integer_schema_version(tmp_path: Path) -> None:
    inventory, _artifact = _write_synthetic_publication(tmp_path)
    original = cast(dict[str, Any], json.loads(inventory.read_text(encoding="utf-8")))
    for invalid in (True, False, 1.0, "1", 0, 2):
        value = copy.deepcopy(original)
        value["schemaVersion"] = invalid
        inventory.write_text(json.dumps(value), encoding="utf-8")
        assert check_generated_media_publication(tmp_path, inventory).failures == (
            "generated-media inventory schemaVersion must be 1",
        )

    inventory.write_text(json.dumps(original), encoding="utf-8")
    assert check_generated_media_publication(tmp_path, inventory).failures == ()


def _capture_record(kind: str) -> dict[str, Any]:
    extension, media_type = ("mp4", "video/mp4") if kind == "video" else ("png", "image/png")
    attestation = f"independent-visual-attestation-{kind}-2026-08-16"
    capture: dict[str, Any] = {
        "tool": "Playwright browser capture",
        "version": "1.55.0",
        "params": {
            "browser": "chromium",
            "viewport": {"width": 1280, "height": 720},
            "device_scale_factor": 1,
        },
        "source": {"path": "web/app/page.tsx", "sha256": "b" * 64},
        "generator": {
            "pathAtCapture": "web/tests/gameplay/harness.ts",
            "ref": f"sha256:{'e' * 64}",
            "sha256": "e" * 64,
        },
        "fixtureGenerator": {
            "pathAtCapture": "web/fixtures/showcase.json",
            "ref": f"sha256:{'c' * 64}",
            "sha256": "c" * 64,
        },
        "verifier": {"path": "web/tests/gameplay/harness.ts", "sha256": "f" * 64},
        "fixture": {"path": "web/fixtures/showcase.json", "sha256": "c" * 64},
        "timeline": {"path": "docs/showcase/timeline.json", "sha256": "d" * 64},
    }
    if kind == "video":
        capture["mp4"] = {
            "container": "mp4",
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "width": 1280,
            "height": 720,
            "frame_rate": 30,
            "duration_seconds": 30.0,
            "fast_start": True,
            "audio_codec": None,
        }
    return {
        "entry": {
            "path": f"docs/showcase/gameplay.{extension}",
            "kind": kind,
            "reviewStatus": "repository-approved",
            "synthIdExpected": False,
            "visualReview": {
                "status": "approved",
                "result": "pass",
                "independent": True,
                "reviewedBy": "independent verification subagent",
                "authorityBasis": "reviewer distinct from the browser capture producer",
                "reviewedAt": "2026-08-16T00:00:00.000Z",
                "attestationId": attestation,
                "attestedAt": "2026-08-16T00:00:00.000Z",
            },
        },
        "observed": {"sha256": "a" * 64, "bytes": 2048},
        "sidecar": {
            "schema_version": 1,
            "artifact": {"sha256": "a" * 64, "bytes": 2048, "media_type": media_type},
            "capture": capture,
            "rights": {
                "status": "redistribution-approved",
                "basis": ["Artifact-specific browser capture authorization", attestation],
                "reviewed_at": "2026-08-16T00:00:00.000Z",
            },
        },
    }


def test_accepts_strict_deterministic_video_and_poster_records() -> None:
    assert validate_published_media_record(_capture_record("video")) == []
    assert validate_published_media_record(_capture_record("image")) == []


def test_rejects_incomplete_or_unsafe_browser_capture_governance() -> None:
    video = _capture_record("video")
    del video["entry"]["kind"]
    video["entry"]["synthIdExpected"] = True
    video["entry"]["visualReview"]["independent"] = False
    video["entry"]["visualReview"]["result"] = "fail"
    video["sidecar"]["artifact"]["media_type"] = "video/webm"
    video["sidecar"]["capture"]["tool"] = ""
    video["sidecar"]["capture"]["params"] = {}
    video["sidecar"]["capture"]["source"] = {"path": "../private.ts", "sha256": "bad"}
    video["sidecar"]["capture"]["generator"] = {
        "pathAtCapture": "../private.ts",
        "ref": "file:private.ts",
        "sha256": "bad",
    }
    video["sidecar"]["capture"]["verifier"] = {
        "path": "/private/verify.ts",
        "sha256": "bad",
    }
    video["sidecar"]["capture"]["mp4"]["video_codec"] = "vp9"
    video["sidecar"]["capture"]["mp4"]["width"] = 1279
    video["sidecar"]["capture"]["mp4"]["fast_start"] = False
    video["sidecar"]["rights"]["basis"] = ["Artifact-specific browser capture authorization"]

    failures = validate_published_media_record(video)

    expected = {
        "inventory kind must explicitly declare video or image",
        "inventory synthIdExpected must explicitly be false for browser capture",
        "inventory visualReview.independent must be true",
        "inventory visualReview.result must be pass",
        "sidecar artifact media_type must match the artifact extension",
        "sidecar.capture.tool must be a stable value",
        "sidecar.capture.params must be a non-empty JSON object",
        "sidecar.capture.source.path must be repository-relative and canonical",
        "sidecar.capture.source.sha256 must be a content digest",
        "sidecar.capture.generator.pathAtCapture must be repository-relative and canonical",
        "sidecar.capture.generator.sha256 must be a content digest",
        "sidecar.capture.generator.ref must match its sha256 content identifier",
        "sidecar.capture.verifier.path must be repository-relative and canonical",
        "sidecar.capture.verifier.sha256 must be a content digest",
        "sidecar.capture.mp4.video_codec must be h264",
        "sidecar.capture.mp4.width must be a supported even integer",
        "sidecar.capture.mp4.fast_start must be true",
        "sidecar.rights.basis must include the visual attestation identifier",
    }
    assert expected <= set(failures)

    poster = _capture_record("image")
    poster["sidecar"]["capture"]["mp4"] = copy.deepcopy(
        _capture_record("video")["sidecar"]["capture"]["mp4"]
    )
    assert "sidecar.capture.mp4 is only valid for video" in validate_published_media_record(poster)


def _write_capture_publication(repo: Path) -> Path:
    source_paths = {
        "source": repo / "web/app/page.tsx",
        "verifier": repo / "web/tests/gameplay/harness.ts",
        "fixture": repo / "web/fixtures/showcase.json",
        "timeline": repo / "docs/showcase/timeline.json",
    }
    for label, path in source_paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"synthetic {label} input", encoding="utf-8")
    media_root = repo / "docs/showcase"
    entries: list[dict[str, Any]] = []
    for kind in ("video", "image"):
        record = _capture_record(kind)
        artifact = media_root / ("gameplay.mp4" if kind == "video" else "gameplay.png")
        payload = f"synthetic {kind} bytes; not encoded media".encode()
        artifact.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        record["entry"]["path"] = artifact.relative_to(repo).as_posix()
        record["observed"] = {"sha256": digest, "bytes": len(payload)}
        record["sidecar"]["artifact"].update({"sha256": digest, "bytes": len(payload)})
        for label, path in source_paths.items():
            record["sidecar"]["capture"][label] = {
                "path": path.relative_to(repo).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        sidecar_bytes = json.dumps(record["sidecar"]).encode()
        Path(f"{artifact}.meta.json").write_bytes(sidecar_bytes)
        record["entry"]["sidecarSha256"] = hashlib.sha256(sidecar_bytes).hexdigest()
        entries.append(record["entry"])
    inventory = repo / "docs/generated-media-inventory.json"
    inventory.parent.mkdir(exist_ok=True)
    inventory.write_text(
        json.dumps({"schemaVersion": 1, "roots": ["docs/showcase"], "media": entries}),
        encoding="utf-8",
    )
    return inventory


def test_capture_generator_is_historical_while_verifier_tracks_current_code() -> None:
    record = _capture_record("video")
    capture = record["sidecar"]["capture"]
    assert capture["generator"]["sha256"] != capture["verifier"]["sha256"]
    assert validate_published_media_record(record) == []

    capture["generator"]["ref"] = f"sha256:{'0' * 64}"
    assert (
        "sidecar.capture.generator.ref must match its sha256 content identifier"
        in validate_published_media_record(record)
    )


def test_capture_fixture_generator_preserves_historical_content_identity() -> None:
    record = _capture_record("video")
    capture = record["sidecar"]["capture"]
    assert capture["fixtureGenerator"]["sha256"] == capture["fixture"]["sha256"]
    assert validate_published_media_record(record) == []

    capture["fixtureGenerator"]["pathAtCapture"] = "../private-fixture.ts"
    capture["fixtureGenerator"]["ref"] = "sha256:not-a-digest"
    failures = validate_published_media_record(record)
    assert (
        "sidecar.capture.fixtureGenerator.pathAtCapture must be repository-relative and canonical"
        in failures
    )
    assert (
        "sidecar.capture.fixtureGenerator.ref must match its sha256 content identifier" in failures
    )


def test_browser_capture_publication_checks_hashes_and_symlinks(
    tmp_path: Path,
) -> None:
    inventory = _write_capture_publication(tmp_path)
    assert check_generated_media_publication(tmp_path, inventory).failures == ()

    timeline = tmp_path / "docs/showcase/timeline.json"
    timeline.write_text("changed timeline", encoding="utf-8")
    failures = check_generated_media_publication(tmp_path, inventory).failures
    assert sum("sidecar.capture.timeline digest does not match" in item for item in failures) == 2

    timeline.unlink()
    target = tmp_path / "timeline-target.json"
    target.write_text("synthetic target", encoding="utf-8")
    timeline.symlink_to(target)
    failures = check_generated_media_publication(tmp_path, inventory).failures
    assert sum("sidecar.capture.timeline.path is unsafe" in item for item in failures) == 2


def test_browser_capture_verifier_digest_tracks_current_hardened_code(tmp_path: Path) -> None:
    inventory = _write_capture_publication(tmp_path)
    verifier = tmp_path / "web/tests/gameplay/harness.ts"
    verifier.write_text("changed hardened verifier", encoding="utf-8")

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert sum("sidecar.capture.verifier digest does not match" in item for item in failures) == 2


def test_browser_capture_inventory_binds_exact_sidecar_bytes(tmp_path: Path) -> None:
    inventory = _write_capture_publication(tmp_path)
    sidecar = tmp_path / "docs/showcase/gameplay.mp4.meta.json"
    sidecar.write_bytes(sidecar.read_bytes() + b"\n")

    failures = check_generated_media_publication(tmp_path, inventory).failures

    assert (
        sum(
            "inventory sidecarSha256 does not match adjacent provenance sidecar" in item
            for item in failures
        )
        == 1
    )


def test_media_git_size_limits_are_enforced_without_large_fixtures() -> None:
    for kind, maximum in (("video", 25 * 1024 * 1024), ("image", 5 * 1024 * 1024)):
        value = _capture_record(kind)
        value["observed"]["bytes"] = maximum + 1
        value["sidecar"]["artifact"]["bytes"] = maximum + 1
        assert f"{kind} exceeds the Git publication size limit" in validate_published_media_record(
            value
        )


def test_current_theme_art_direction_derivative_is_exactly_bound() -> None:
    repository = Path(__file__).parents[2]
    inventory = cast(
        dict[str, Any],
        json.loads(
            (repository / "docs/generated-media-inventory.json").read_text(encoding="utf-8")
        ),
    )
    entry = next(
        item
        for item in cast(list[dict[str, Any]], inventory["media"])
        if item.get("provenance_kind") == "generated_image_derivative"
    )
    artifact = repository / cast(str, entry["path"])
    sidecar_path = Path(f"{artifact}.meta.json")
    sidecar_bytes = sidecar_path.read_bytes()
    sidecar = cast(dict[str, Any], json.loads(sidecar_bytes.decode("utf-8")))
    observed = {
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "bytes": artifact.stat().st_size,
    }

    assert entry["sidecar_sha256"] == hashlib.sha256(sidecar_bytes).hexdigest()
    assert (
        validate_published_media_record({"entry": entry, "observed": observed, "sidecar": sidecar})
        == []
    )
    report = repository / cast(str, sidecar["visual_review"]["evidence"]["path"])
    assert (
        sidecar["visual_review"]["evidence"]["sha256"]
        == hashlib.sha256(report.read_bytes()).hexdigest()
    )


def test_current_game_concept_cover_is_exactly_bound() -> None:
    repository = Path(__file__).parents[2]
    inventory = cast(
        dict[str, Any],
        json.loads(
            (repository / "docs/generated-media-inventory.json").read_text(encoding="utf-8")
        ),
    )
    entry = next(
        item
        for item in cast(list[dict[str, Any]], inventory["media"])
        if item.get("lineage_kind") == "game_concept_cover_v1"
    )
    artifact = repository / cast(str, entry["path"])
    sidecar_path = Path(f"{artifact}.meta.json")
    sidecar_bytes = sidecar_path.read_bytes()
    sidecar = cast(dict[str, Any], json.loads(sidecar_bytes.decode("utf-8")))
    observed = {
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "bytes": artifact.stat().st_size,
    }

    assert entry["sidecar_sha256"] == hashlib.sha256(sidecar_bytes).hexdigest()
    assert (
        validate_published_media_record({"entry": entry, "observed": observed, "sidecar": sidecar})
        == []
    )
    concept = repository / cast(str, sidecar["concept"]["path"])
    assert sidecar["concept"]["sha256"] == hashlib.sha256(concept.read_bytes()).hexdigest()
    assert sidecar["concept"]["bytes"] == concept.stat().st_size
    report = repository / cast(str, sidecar["visual_review"]["evidence"]["path"])
    assert (
        sidecar["visual_review"]["evidence"]["sha256"]
        == hashlib.sha256(report.read_bytes()).hexdigest()
    )


def test_current_repository_generated_media_inventory_remains_strictly_valid() -> None:
    repository = Path(__file__).parents[2]
    inventory_path = repository / "docs/generated-media-inventory.json"
    result = check_generated_media_publication(repository, inventory_path)
    assert result.failures == ()
    assert result.media_count == 7

    inventory = cast(dict[str, Any], json.loads(inventory_path.read_text(encoding="utf-8")))
    entries = {entry["path"]: entry for entry in cast(list[dict[str, Any]], inventory["media"])}
    expected = {
        "docs/media/gameplay-showcase.mp4": (
            "5ed3ba2648dc96d904bc38c9d98457aee2e66ebe08ff2d7921204d38fb9161b8",
            7_087_068,
        ),
        "docs/media/gameplay-showcase.poster.png": (
            "61c2e77b41df4e0fa28df060e831593312232ad84c05d81005e136867fc4554f",
            891_557,
        ),
    }
    approval_manifest = cast(
        dict[str, Any],
        json.loads(
            (repository / "fixtures/gameplay-demo/approval-manifest.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    approved_assets = cast(list[dict[str, Any]], approval_manifest["assets"])
    expected_asset_records = {
        (
            asset["id"],
            f"fixtures/gameplay-demo/{asset['path']}",
            asset["sha256"],
            asset["bytes"],
        )
        for asset in approved_assets
    }
    assets_promoted_after_capture = {
        (
            "ladder",
            "fixtures/gameplay-demo/ladder.png",
            "a89b1d865b651806b1457ab1fc37da4d0a54ff28daf5566ec4011483c732faa6",
            172_703,
        ),
        (
            "character-climb",
            "fixtures/gameplay-demo/character-climb.png",
            "782fcda99a7296ab746c21d05014214503d4af280541b1f115031cf4d70dc56e",
            39_677,
        ),
    }
    assert len(expected_asset_records) == 20
    assert assets_promoted_after_capture <= expected_asset_records
    assert all(asset["visualReview"]["status"] == "approved" for asset in approved_assets)
    assert all(asset["visualReview"]["result"] == "pass" for asset in approved_assets)
    assert all(asset["visualReview"]["independent"] is True for asset in approved_assets)
    assert all(asset["rights"]["status"] == "redistribution-approved" for asset in approved_assets)
    publication_text = inventory_path.read_text(encoding="utf-8")
    for path, (digest, byte_count) in expected.items():
        review = cast(dict[str, Any], entries[path]["visualReview"])
        assert review["artifactSha256"] == digest
        assert review["artifactBytes"] == byte_count
        assert review["verificationReportSha256"] == (
            "c312124fadd636ff510bd290db231b20523089f78d77b06a8e490c374377c2f8"
        )
        sidecar_path = repository / f"{path}.meta.json"
        assert (
            entries[path]["sidecarSha256"] == hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
        )
        sidecar = cast(dict[str, Any], json.loads(sidecar_path.read_text(encoding="utf-8")))
        assert sidecar["state"] == "redistribution-approved"
        assert sidecar["visualReview"]["artifactSha256"] == digest
        assert sidecar["visualReview"]["artifactBytes"] == byte_count
        assert sidecar["visualReview"]["evidence"]["sha256"] == (
            "c312124fadd636ff510bd290db231b20523089f78d77b06a8e490c374377c2f8"
        )
        capture = cast(dict[str, Any], sidecar["capture"])
        assert capture["producerManifest"] == {
            "path": "fixtures/gameplay-demo/asset-manifest.json",
            "sha256": "edf1b2913afeae906275588e745023ead6797ca7ed7839a72c0789243fd7b8ca",
            "bytes": 78_630,
        }
        assert capture["approvalManifest"] == {
            "path": "fixtures/gameplay-demo/approval-manifest.json",
            "sha256": "7818a18ea177ed47203e1d47d22b1d669055f13b4eb113801326c7cd86629048",
            "bytes": 16_869,
        }
        asset_set = cast(dict[str, Any], capture["assetSet"])
        assert asset_set["count"] == 18
        assert asset_set["aggregate"]["sha256"] == (
            "6bb9d428aead88df25e91dfe7761382e23673a77c5a1d2a1622019554184d30a"
        )
        historical_asset_records = {
            (asset["id"], asset["path"], asset["sha256"], asset["bytes"])
            for asset in cast(list[dict[str, Any]], asset_set["assets"])
        }
        assert historical_asset_records.isdisjoint(assets_promoted_after_capture)
        assert historical_asset_records == expected_asset_records - assets_promoted_after_capture
        publication_text += sidecar_path.read_text(encoding="utf-8")

    assert "6bb9d428aead88df25e91dfe7761382e23673a77c5a1d2a1622019554184d30a" in publication_text
    for retired in (
        "original synthetic fixture assets",
        "ec3c200b40ccd12521b5535ed46a3b7256ec1dc4fee1acfde2ec95c1540e694c",
        "6da7281ac29f91f20cb65099088af357420906946bdfde0df7974ec8e844bdec",
        "independent-visual-attestation-gameplay-showcase-2026-08-16",
    ):
        assert retired not in publication_text

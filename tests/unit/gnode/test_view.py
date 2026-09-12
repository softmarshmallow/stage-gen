from __future__ import annotations

from pydantic import JsonValue

from gnode import (
    LOCAL_OPERATION,
    Node,
    RetryOwner,
    RunViewArtifact,
    artifact_media_type,
    generic_artifact_annotation,
)


def _node() -> Node:
    return Node(
        node_id="entity-record-write",
        type_id="text/record.write",
        domain="entity",
        description="write one entity record",
        operation=LOCAL_OPERATION,
        resource_id="local",
        retry_owner=RetryOwner.NONE,
        max_attempts=1,
        cache_key="0" * 64,
        estimated_duration_seconds=0.0,
        estimated_cost_low_usd=0.0,
        estimated_cost_high_usd=0.0,
    )


def test_markdown_and_plain_text_suffixes_carry_their_own_media_types() -> None:
    assert artifact_media_type("production/records/wayfarer.md") == "text/markdown"
    assert artifact_media_type("production/records/wayfarer.txt") == "text/plain"
    assert artifact_media_type("production/records/wayfarer.bin") == "application/octet-stream"
    assert artifact_media_type("shell/opening_the_valley.raw.mp4") == "video/mp4"
    assert artifact_media_type("shell/opening_the_valley.clip.ogv") == "video/ogg"


def test_generic_annotation_displays_text_as_text() -> None:
    """The floor annotates prose as text; a renderer may still show it as data."""

    node = _node()
    assert generic_artifact_annotation("production/records/wayfarer.md", node).display == "text"
    assert generic_artifact_annotation("production/records/wayfarer.txt", node).display == "text"
    assert generic_artifact_annotation("production/records/wayfarer.json", node).display == "data"
    assert generic_artifact_annotation("content/players/idle.png", node).display == "image"
    # Both containers a clip passes through: what the route returned, and what
    # the host plays. A viewer that fell back to "data" would offer a download
    # link for something it could show.
    assert generic_artifact_annotation("shell/the_valley.raw.mp4", node).display == "video"
    assert generic_artifact_annotation("shell/the_valley.clip.ogv", node).display == "video"


def test_view_carries_consumer_preview_json_without_a_media_contract() -> None:
    preview: dict[str, JsonValue] = {"kind": "user-volume-v1", "shape": [32, 16, 8]}
    artifact = RunViewArtifact(
        artifact_ref="volume.bin",
        sha256="a" * 64,
        bytes=12,
        media_type="model/gltf-binary",
        present=True,
        display="user-volume",
        preview=preview,
        motion={"frame_count": 4},
    )
    restored = RunViewArtifact.model_validate_json(artifact.model_dump_json())
    assert restored.preview == preview
    assert restored.motion == {"frame_count": 4}
    assert restored.display == "user-volume"


def test_model_artifacts_retain_mime_without_implying_a_model_renderer() -> None:
    assert artifact_media_type("scene.glb") == "model/gltf-binary"
    assert artifact_media_type("scene.gltf") == "model/gltf+json"
    assert generic_artifact_annotation("scene.glb", _node()).display == "data"

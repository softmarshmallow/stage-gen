from __future__ import annotations

from pydantic import JsonValue

from gnode import RunViewArtifact, artifact_media_type


def test_markdown_and_plain_text_suffixes_carry_their_own_media_types() -> None:
    assert artifact_media_type("production/records/wayfarer.md") == "text/markdown"
    assert artifact_media_type("production/records/wayfarer.txt") == "text/plain"
    assert artifact_media_type("production/records/wayfarer.bin") == "application/octet-stream"
    assert artifact_media_type("shell/opening_the_valley.raw.mp4") == "video/mp4"
    assert artifact_media_type("shell/opening_the_valley.clip.ogv") == "video/ogg"


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

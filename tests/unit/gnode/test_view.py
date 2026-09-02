from __future__ import annotations

from gnode import (
    LOCAL_OPERATION,
    Node,
    RetryOwner,
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


def test_generic_annotation_displays_text_as_text() -> None:
    """The floor annotates prose as text; a renderer may still show it as data."""

    node = _node()
    assert generic_artifact_annotation("production/records/wayfarer.md", node).display == "text"
    assert generic_artifact_annotation("production/records/wayfarer.txt", node).display == "text"
    assert generic_artifact_annotation("production/records/wayfarer.json", node).display == "data"
    assert generic_artifact_annotation("content/players/idle.png", node).display == "image"

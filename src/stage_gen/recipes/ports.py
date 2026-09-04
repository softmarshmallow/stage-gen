"""Port and digest helpers every recipe's graph builder used to write for itself.

Five graph modules carried the same four functions under the same private names. They
are cache identity: a port's ``artifact_ref`` and ``kind`` and a node's input digests
are what ``build_node_cache_key`` hashes, so the one copy here must stay byte-for-byte
what the five copies were. ``object_digest`` in particular keeps ``json.dumps``'s
default ``ensure_ascii=True`` rather than ``stage_gen.canonical.canonical_json_bytes``
(``ensure_ascii=False``): the two agree on ASCII and differ on anything else, and every
shipped key was taken under the former.
"""

from __future__ import annotations

import hashlib
import json

from gnode import Port


def artifact_port(port_id: str, ref: str, kind: str) -> Port:
    """One artifact-plus-sidecar port; the pair stays visibly one payload."""

    return Port(port_id=port_id, artifact_ref=ref, kind=kind, sidecar_ref=f"{ref}.meta.json")


def record_port(port_id: str, ref: str, kind: str) -> Port:
    """A record written without a provenance sidecar: calibration, metadata, a ledger."""

    return Port(port_id=port_id, artifact_ref=ref, kind=kind)


def attempts_port(node_id: str, kind: str) -> Port:
    """The attempt ledger every provider node publishes beside its artifact.

    The ledger kind is the recipe's: the runner's is at v2, the universe's carries its own
    prefix, and a ledger's shape is part of what a run viewer reads.
    """

    return Port(port_id="attempts", artifact_ref=f"attempts/{node_id}.json", kind=kind)


def text_digest(text: str) -> str:
    """A node keyed on exactly the instruction it will send, so an edit re-bills one node."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def object_digest(value: object) -> str:
    """Digest of a JSON value in the compact, sorted, ASCII form every key was taken under."""

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["artifact_port", "attempts_port", "object_digest", "record_port", "text_digest"]

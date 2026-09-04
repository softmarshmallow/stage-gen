"""What every shared node family's kit needs from a host, and the helpers all of them write.

A node family exported from a component - the UI atlas triplet, the fx cut-in, the
soundtrack pair - is a set of node types plus the coroutines behind them, owned by
no recipe. Each kit used to carry its own copy of the same four helpers; they live
here once. Components import this module, and so may recipes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from gnode import (
    BinaryArtifact,
    CacheDisposition,
    InputProvenance,
    Node,
    NodeArtifact,
    NodeExecutionResult,
    Port,
    ProvenanceInput,
    SoftwareIdentity,
    write_artifact_with_provenance_async,
)
from stage_gen.identity import STAGE_GEN_TOOL

#: The seam for a recipe that keeps its own attempt ledger: it receives the node, a role
#: label, the exact prompt, and a thunk, and must return whatever the thunk returns.
ProviderCall = Callable[[Node, str, str, Callable[[], Awaitable[Any]]], Awaitable[Any]]


def artifact_port(port_id: str, ref: str, kind: str) -> Port:
    """One artifact-plus-sidecar port; the pair stays visibly one payload."""

    return Port(port_id=port_id, artifact_ref=ref, kind=kind, sidecar_ref=f"{ref}.meta.json")


def record_port(port_id: str, ref: str, kind: str) -> Port:
    """A record written without a provenance sidecar: calibration, metadata, a ledger."""

    return Port(port_id=port_id, artifact_ref=ref, kind=kind)


def attempts_port(node_id: str, kind: str) -> Port:
    """The attempt ledger a provider node publishes beside its artifact.

    The ledger kind is the recipe's: the runner's is at v2, the universe's carries its own
    prefix, and a ledger's shape is part of what a run viewer reads.
    """

    return Port(port_id="attempts", artifact_ref=f"attempts/{node_id}.json", kind=kind)


def card_prompt(node: Node) -> str:
    """The plan is the single source of a node's static instruction text."""

    if node.card is None or node.card.prompt is None:
        raise ValueError(f"node {node.node_id} declares no card prompt")
    return node.card.prompt


def text_digest(text: str) -> str:
    """A node keyed on exactly the instruction it will send, so an edit re-bills one node."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def object_digest(value: object) -> str:
    """Digest of a JSON value in the compact, sorted, ASCII form every key was taken under.

    Deliberately ``json.dumps``'s default ``ensure_ascii=True`` rather than the canonical
    encoder's ``False``: the two agree on ASCII and differ on anything else, and every
    shipped cache key was taken under the former.
    """

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def node_result(
    run_dir: Path,
    node: Node,
    *,
    attempts: int = 1,
    provider_operations: int = 0,
    known_cost_usd: float | None = None,
) -> NodeExecutionResult:
    """Every declared port that carries bytes this run, artifact then paired sidecar.

    A declared address that carries nothing is skipped rather than invented: a loop
    repaint intermediate exists only when admission escalated to a provider edit, and
    a record port has no sidecar to pair.
    """

    artifacts: list[NodeArtifact] = []
    for port in node.ports:
        for ref in (port.artifact_ref, port.sidecar_ref):
            if ref is None:
                continue
            path = run_dir / ref
            if not path.is_file():
                continue
            data = path.read_bytes()
            artifacts.append(
                NodeArtifact(
                    artifact_ref=ref, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)
                )
            )
    return NodeExecutionResult(
        cache=CacheDisposition.MISS,
        attempts=attempts,
        provider_operations=provider_operations,
        artifacts=tuple(artifacts),
        known_cost_usd=known_cost_usd,
    )


async def write_local_image(
    path: Path,
    data: bytes,
    *,
    prompt: str,
    inputs: Sequence[tuple[str, bytes]],
    validation: Mapping[str, object],
    model: str,
    component: SoftwareIdentity,
    handler_version: str,
) -> Path:
    """Publish a locally composed PNG with the provenance every kit writes the same way.

    ``inputs`` are the run-relative refs the composition read and their bytes; a
    ``.json`` input is recorded as such, everything else a kit composes from is a PNG.
    """

    return await write_artifact_with_provenance_async(
        path,
        BinaryArtifact(data=data, media_type="image/png"),
        ProvenanceInput(
            provider="local",
            model=model,
            prompt=prompt,
            refs=[ref for ref, _ in inputs],
            inputs=[
                InputProvenance(
                    ref=ref,
                    sha256=hashlib.sha256(payload).hexdigest(),
                    source="content",
                    bytes=len(payload),
                    media_type=(
                        "application/json"
                        if ref.split("#", 1)[0].endswith(".json")
                        else "image/png"
                    ),
                )
                for ref, payload in inputs
            ],
            params={"version": handler_version},
            validation=dict(validation),
            component=component,
            tool=STAGE_GEN_TOOL,
            attempts=1,
        ),
    )


__all__ = [
    "ProviderCall",
    "artifact_port",
    "attempts_port",
    "card_prompt",
    "node_result",
    "object_digest",
    "record_port",
    "text_digest",
    "write_local_image",
]

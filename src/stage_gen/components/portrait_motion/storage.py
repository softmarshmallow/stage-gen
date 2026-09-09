"""Confined run artifacts and complete, content-validated stage checkpoints."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from gnode import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    Node,
    ProvenanceInput,
    SoftwareIdentity,
    atomic_write_json,
    sha256_hex,
    write_artifact_with_provenance,
)

from .models import StageReceipt

COMPONENT = SoftwareIdentity(name="portrait-motion", version="1")


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def confined(root: Path, ref: str) -> Path:
    relative = PurePosixPath(ref)
    if (
        not ref
        or relative.is_absolute()
        or "\\" in ref
        or str(relative) != ref
        or any(part in {".", "..", ""} for part in ref.split("/"))
    ):
        raise ValueError("Artifact references must be normalized relative paths")
    root = root.absolute()
    if root.resolve() != root:
        raise ValueError("Run root must not traverse a symlink")
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Artifact path must not traverse a symlink")
    return path


class RunStore:
    def __init__(self, root: Path, *, tool: SoftwareIdentity) -> None:
        self.root = root.absolute()
        self.tool = tool
        confined(self.root, "plan.json")

    def path(self, ref: str) -> Path:
        return confined(self.root, ref)

    def digest(self, ref: str) -> str:
        return sha256_hex(self.path(ref).read_bytes())

    def read(self, ref: str) -> dict[str, Any]:
        value = json.loads(self.path(ref).read_bytes())
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    def write(
        self,
        ref: str,
        data: bytes,
        media_type: str,
        *,
        inputs: list[str],
        params: dict[str, Any],
        prompt: str,
        rights: ArtifactRights | None = None,
    ) -> None:
        write_artifact_with_provenance(
            self.path(ref),
            BinaryArtifact(data=data, media_type=media_type),
            ProvenanceInput(
                provider="local",
                model="portrait-motion-v1",
                prompt=prompt,
                refs=inputs,
                inputs=[
                    InputProvenance(ref=item, sha256=self.digest(item), source="reference")
                    for item in inputs
                ],
                params=params,
                component=COMPONENT,
                tool=self.tool,
                attempts=1,
                rights=rights,
            ),
        )

    def write_json(
        self, ref: str, value: object, *, inputs: list[str], params: dict[str, Any], prompt: str
    ) -> None:
        self.write(
            ref, json_bytes(value), "application/json", inputs=inputs, params=params, prompt=prompt
        )

    def verify_artifact(self, ref: str, *, node: Node | None = None) -> None:
        meta = ArtifactProvenance.model_validate_json(self.path(ref + ".meta.json").read_bytes())
        if meta.artifact is None or meta.artifact.sha256 != self.digest(ref):
            raise ValueError(f"Artifact and sidecar disagree: {ref}")
        if meta.artifact.bytes != self.path(ref).stat().st_size:
            raise ValueError(f"Artifact length changed: {ref}")
        for item in meta.inputs:
            if self.digest(item.ref) != item.sha256:
                raise ValueError(f"Artifact input lineage changed: {ref}")
        if node is not None:
            metadata = meta.params.get("metadata", meta.params)
            if metadata.get("node_cache_key") != node.cache_key:
                raise ValueError(f"Artifact belongs to a different node: {ref}")
            if meta.provider != "local" and (meta.provider, meta.model) != (
                node.provider,
                node.model,
            ):
                raise ValueError(f"Provider identity changed: {ref}")

    def receipt(self, node: Node) -> StageReceipt | None:
        ref = f"{node.node_id}/result.json"
        if not self.path(ref).exists():
            if self.path(ref + ".meta.json").exists():
                raise ValueError("Incomplete stage checkpoint")
            return None
        self.verify_artifact(ref, node=node)
        receipt = StageReceipt.model_validate_json(self.path(ref).read_bytes())
        if receipt.stage != node.node_id or receipt.node_cache_key != node.cache_key:
            raise ValueError("Stage checkpoint identity changed")
        expected = {
            f"{dep}/result.json": self.digest(f"{dep}/result.json") for dep in node.depends_on
        }
        if receipt.dependency_records != expected:
            raise ValueError("Stage dependency lineage changed")
        for artifact, digest in receipt.files.items():
            if self.digest(artifact) != digest:
                raise ValueError(f"Stage artifact changed: {artifact}")
            if not artifact.endswith(".meta.json"):
                self.verify_artifact(artifact, node=node)
        return receipt

    def finish(
        self,
        node: Node,
        *,
        status: str,
        reason: str,
        files: list[str],
        operations: int = 0,
        reported_cost: float | None = None,
    ) -> StageReceipt:
        records: dict[str, str] = {}
        for ref in files:
            self.verify_artifact(ref, node=node)
            for item in (ref, ref + ".meta.json"):
                records[item] = self.digest(item)
        dependency_records = {
            f"{dep}/result.json": self.digest(f"{dep}/result.json") for dep in node.depends_on
        }
        receipt = StageReceipt.model_validate(
            {
                "stage": node.node_id,
                "node_cache_key": node.cache_key,
                "status": status,
                "reason": reason,
                "files": records,
                "dependency_records": dependency_records,
                "provider_operations": operations,
                "reported_cost_usd": reported_cost,
            }
        )
        self.write_json(
            f"{node.node_id}/result.json",
            receipt.model_dump(mode="json"),
            inputs=[*dependency_records, *files],
            params={"node_cache_key": node.cache_key},
            prompt="Commit the complete validated portrait-motion stage checkpoint.",
        )
        return receipt

    def reserve(self, node: Node, request: dict[str, Any], *, max_operations: int) -> str:
        """Persist intent before dispatch; ambiguous interrupted requests are never re-billed."""
        ref = f"{node.node_id}/submission.json"
        if self.path(ref).exists():
            raise ValueError("Unresolved provider submission; refusing automatic resubmission")
        submissions = list(self.root.glob("*/submission.json"))
        reserved = 0
        for path in submissions:
            previous = self.read(path.relative_to(self.root).as_posix())
            attempts = previous.get("reserved_attempts")
            if (
                type(attempts) is not int
                or not 1 <= attempts <= 6
                or previous.get("schema_version") != 1
                or previous.get("status") != "submitted"
            ):
                raise ValueError("Invalid persisted provider submission")
            reserved += attempts
        if reserved + node.max_attempts > max_operations:
            raise ValueError("Finite provider operation budget exhausted")
        atomic_write_json(
            self.path(ref),
            {
                "schema_version": 1,
                "status": "submitted",
                "node_cache_key": node.cache_key,
                "reserved_attempts": node.max_attempts,
                "request": request,
            },
        )
        return ref

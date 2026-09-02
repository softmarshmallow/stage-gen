"""Content-and-lineage validated reuse of one node's artifacts.

The engine owns cache *keys*; what a key is allowed to restore is the application's
business. A record is honoured only when the key matches, the recorded lineage still
matches what the dependencies actually produced this run, every restored byte hashes
to what was recorded, and the recipe's own admission check passes. Path existence is
never sufficient - a stale directory must not be able to publish itself as a hit.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat as stat_module
import uuid
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from gnode import (
    CacheDisposition,
    NodeArtifact,
    NodeExecutionResult,
    assert_safe_path_segment,
    atomic_write_bytes,
    atomic_write_json,
    resolve_relative_path_within_root,
    resolve_writable_path_within_root,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from gnode import Graph, Node, NodeExecutionContext

NODE_CACHE_SCHEMA_VERSION = 2
_NODE_CACHE_RECORD_FIELDS = frozenset(
    {"schema_version", "kind", "cache_key", "node_id", "lineage", "artifacts"}
)


@dataclass(slots=True)
class _RestoreState:
    target: Path
    data: bytes
    temporary: Path
    backup: Path
    existed: bool
    backed_up: bool = False
    install_attempted: bool = False


def _replace_path(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _replace_cache_path(source: Path, destination: Path) -> None:
    os.replace(source, destination)


class _CacheBundleRecoveryError(OSError):
    """A cache swap failed and its recovery bundle must be retained."""


class _ArtifactRestoreRecoveryError(OSError):
    """A run-artifact restore failed and its recovery files must be retained."""


class NodeArtifactCache:
    """One recipe's cache tier over a run directory and a cache directory."""

    def __init__(
        self,
        graph: Graph,
        *,
        run_dir: Path,
        cache_dir: Path,
        namespace: str,
        record_kind: str,
        admit: Callable[[Node, tuple[bytes, ...]], bool] | None = None,
    ) -> None:
        self._graph = graph
        self._run_dir = run_dir
        self._cache_dir = cache_dir
        self._namespace = namespace
        self._record_kind = record_kind
        self._admit = admit

    def read(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult | None:
        try:
            record_path, artifacts_dir = self._paths(node)
        except (OSError, ValueError):
            return None
        if record_path.is_symlink():
            return None
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if (
            not isinstance(record, dict)
            or set(record) != _NODE_CACHE_RECORD_FIELDS
            or type(record.get("schema_version")) is not int
            or record.get("schema_version") != NODE_CACHE_SCHEMA_VERSION
            or record.get("kind") != self._record_kind
            or record.get("node_id") != node.node_id
            or record.get("cache_key") != node.cache_key
            or record.get("lineage") != self.lineage(node, context)
        ):
            return None
        outputs = record.get("artifacts")
        if not isinstance(outputs, list):
            return None

        declared_refs = tuple(
            ref
            for port in node.ports
            for ref in (
                (port.artifact_ref, port.sidecar_ref)
                if port.sidecar_ref is not None
                else (port.artifact_ref,)
            )
        )
        output_refs = tuple(
            value.get("artifact_ref") if isinstance(value, dict) else None for value in outputs
        )
        if (
            any(not isinstance(ref, str) for ref in output_refs)
            or len(declared_refs) != len(set(declared_refs))
            or len(output_refs) != len(set(output_refs))
            or output_refs != declared_refs
        ):
            return None

        if artifacts_dir.is_symlink():
            return None
        try:
            cached_payloads = tuple(artifacts_dir.iterdir())
        except FileNotFoundError:
            if outputs:
                return None
            cached_payloads = ()
        except OSError:
            return None
        expected_payload_names = {f"{index}.bin" for index in range(len(outputs))}
        if {path.name for path in cached_payloads} != expected_payload_names or any(
            not path.is_file() or path.is_symlink() for path in cached_payloads
        ):
            return None

        restored: list[NodeArtifact] = []
        payloads: list[bytes] = []
        for index, value in enumerate(outputs):
            if not isinstance(value, dict) or not isinstance(value.get("artifact_ref"), str):
                return None
            try:
                data = (artifacts_dir / f"{index}.bin").read_bytes()
            except OSError:
                return None
            if sha256(data).hexdigest() != value.get("sha256") or len(data) != value.get("bytes"):
                return None
            payloads.append(data)
            try:
                restored.append(NodeArtifact.model_validate(value))
            except ValueError:
                return None
        if self._admit is not None and not self._admit(node, tuple(payloads)):
            return None

        try:
            self._assert_no_symlink_ancestors(self._run_dir.absolute(), "run directory")
        except ValueError:
            return None
        targets = []
        for artifact, data in zip(restored, payloads, strict=True):
            # A cache record is data, not authority: its refs must stay inside
            # the run directory even if the record was corrupted or crafted.
            try:
                target = resolve_writable_path_within_root(
                    self._run_dir, artifact.artifact_ref, "cached artifact path"
                )
            except ValueError:
                return None
            targets.append((target, data))
        try:
            self._restore_payloads(targets)
        except _ArtifactRestoreRecoveryError:
            raise
        except (OSError, ValueError):
            return None
        return NodeExecutionResult(
            cache=CacheDisposition.HIT,
            attempts=1,
            provider_operations=0,
            artifacts=tuple(restored),
            known_cost_usd=0.0,
        )

    def write(self, node: Node, context: NodeExecutionContext, result: NodeExecutionResult) -> None:
        payloads = self._validated_result_payloads(node, result)
        root = self._prepare_cache_parent(node)
        nonce = uuid.uuid4().hex
        staging = root.parent / f"{root.name}-staging-{nonce}"
        backup = root.parent / f"{root.name}-backup-{nonce}"
        staging.mkdir(mode=0o700)
        preserve_backup = False
        try:
            artifacts_dir = staging / "artifacts"
            artifacts_dir.mkdir(mode=0o700)
            for index, data in enumerate(payloads):
                atomic_write_bytes(artifacts_dir / f"{index}.bin", data)
            atomic_write_json(
                staging / "record.json",
                {
                    "schema_version": NODE_CACHE_SCHEMA_VERSION,
                    "kind": self._record_kind,
                    "cache_key": node.cache_key,
                    "node_id": node.node_id,
                    "lineage": self.lineage(node, context),
                    "artifacts": [item.model_dump(mode="json") for item in result.artifacts],
                },
            )
            self._install_cache_bundle(root, staging, backup)
        except _CacheBundleRecoveryError:
            preserve_backup = True
            raise
        finally:
            self._remove_private_bundle(staging)
            if not preserve_backup:
                self._remove_private_bundle(backup)

    def lineage(self, node: Node, context: NodeExecutionContext) -> list[dict[str, object]]:
        """Lineage covers exactly the dependencies the cache key covers.

        A barrier edge orders execution without contributing identity; binding
        its artifact digests here would re-bill every provider node whenever
        anything upstream of the barrier changed, which is precisely what the
        barrier declaration promises not to do.

        A dependency's declared provenance sidecars are also excluded. They are
        audit records rather than provider-consumed content and may carry a fresh
        timestamp when a deterministic dependency is rerun. The dependency cache
        key still binds that node's contract, while every primary/content artifact
        (including validation records and attempt ledgers) remains digest-bound.
        """

        barriers = set(node.barrier_only)
        lineage: list[dict[str, object]] = []
        for dependency in node.depends_on:
            if dependency in barriers:
                continue
            dependency_node = self._graph.node(dependency)
            provenance_sidecar_refs = {
                port.sidecar_ref for port in dependency_node.ports if port.sidecar_ref is not None
            }
            lineage.append(
                {
                    "node_id": dependency,
                    "cache_key": dependency_node.cache_key,
                    "artifact_sha256": [
                        artifact.sha256
                        for artifact in context.dependency_results[dependency].artifacts
                        if artifact.artifact_ref not in provenance_sidecar_refs
                    ],
                }
            )
        return lineage

    def _declared_refs(self, node: Node) -> tuple[str, ...]:
        return tuple(
            ref
            for port in node.ports
            for ref in (
                (port.artifact_ref, port.sidecar_ref)
                if port.sidecar_ref is not None
                else (port.artifact_ref,)
            )
        )

    def _cache_segments(self, node: Node) -> tuple[str, str, str]:
        return (
            assert_safe_path_segment(self._namespace, "node cache namespace"),
            assert_safe_path_segment(node.cache_key[:2], "node cache prefix"),
            assert_safe_path_segment(node.cache_key, "node cache key"),
        )

    def _cache_root(self, node: Node) -> Path:
        relative = "/".join(self._cache_segments(node))
        root = resolve_relative_path_within_root(
            self._cache_dir, relative, "node cache bundle path"
        )
        self._assert_cache_ancestry(root)
        return root

    def _assert_cache_ancestry(self, root: Path) -> None:
        cache_root = self._cache_dir.absolute()
        self._assert_no_symlink_ancestors(cache_root, "node cache root")
        candidates = [cache_root]
        current = cache_root
        for part in root.relative_to(cache_root).parts:
            current /= part
            candidates.append(current)
        for candidate in candidates:
            try:
                state = candidate.lstat()
            except FileNotFoundError:
                break
            if stat_module.S_ISLNK(state.st_mode):
                raise ValueError(f"node cache path has a symlink ancestor: {candidate}")
            if not stat_module.S_ISDIR(state.st_mode):
                raise ValueError(f"node cache path ancestor is not a directory: {candidate}")

    def _prepare_cache_parent(self, node: Node) -> Path:
        cache_root = self._cache_dir.absolute()
        self._assert_no_symlink_ancestors(cache_root, "node cache root")
        if os.path.lexists(cache_root):
            self._require_plain_directory(cache_root, "node cache root")
        else:
            cache_root.mkdir(parents=True, mode=0o700)
            self._require_plain_directory(cache_root, "node cache root")
        namespace, prefix, key = self._cache_segments(node)
        parent = cache_root
        for segment in (namespace, prefix):
            parent = parent / segment
            with contextlib.suppress(FileExistsError):
                parent.mkdir(mode=0o700)
            self._require_plain_directory(parent, "node cache ancestor")
        root = parent / key
        if os.path.lexists(root):
            self._require_plain_directory(root, "node cache bundle")
        self._assert_cache_ancestry(root)
        return root

    @staticmethod
    def _assert_no_symlink_ancestors(path: Path, label: str) -> None:
        for candidate in (*reversed(path.parents), path):
            try:
                state = candidate.lstat()
            except FileNotFoundError:
                continue
            if stat_module.S_ISLNK(state.st_mode):
                raise ValueError(f"{label} has a symlink ancestor: {candidate}")
            if candidate != path and not stat_module.S_ISDIR(state.st_mode):
                raise ValueError(f"{label} ancestor is not a directory: {candidate}")

    @staticmethod
    def _require_plain_directory(path: Path, label: str) -> None:
        state = path.lstat()
        if stat_module.S_ISLNK(state.st_mode) or not stat_module.S_ISDIR(state.st_mode):
            raise ValueError(f"{label} must be a non-symlink directory: {path}")

    def _validated_result_payloads(
        self, node: Node, result: NodeExecutionResult
    ) -> tuple[bytes, ...]:
        declared_refs = self._declared_refs(node)
        artifact_refs = tuple(artifact.artifact_ref for artifact in result.artifacts)
        if len(artifact_refs) != len(set(artifact_refs)) or artifact_refs != declared_refs:
            raise ValueError(
                f"node {node.node_id} cache outputs do not exactly match its declared ports"
            )
        self._assert_no_symlink_ancestors(self._run_dir.absolute(), "cache source run root")
        payloads: list[bytes] = []
        for artifact in result.artifacts:
            source = resolve_writable_path_within_root(
                self._run_dir, artifact.artifact_ref, "cache source artifact path"
            )
            if source.is_symlink():
                raise ValueError(
                    f"cache source artifact must not be a symlink: {artifact.artifact_ref}"
                )
            data = source.read_bytes()
            if sha256(data).hexdigest() != artifact.sha256 or len(data) != artifact.bytes:
                raise ValueError(
                    f"cache source artifact does not match its digest: {artifact.artifact_ref}"
                )
            payloads.append(data)
        return tuple(payloads)

    def _install_cache_bundle(self, root: Path, staging: Path, backup: Path) -> None:
        moved_existing = False
        if os.path.lexists(root):
            self._require_plain_directory(root, "node cache bundle")
            _replace_cache_path(root, backup)
            moved_existing = True
        try:
            self._assert_cache_ancestry(root.parent)
            _replace_cache_path(staging, root)
        except Exception:
            if moved_existing and os.path.lexists(backup):
                try:
                    _replace_cache_path(backup, root)
                except Exception as rollback_error:
                    raise _CacheBundleRecoveryError(
                        "node cache bundle installation failed and rollback was incomplete; "
                        "the recovery bundle was retained"
                    ) from rollback_error
            raise

    def _restore_payloads(self, targets: list[tuple[Path, bytes]]) -> None:
        token = uuid.uuid4().hex
        states: list[_RestoreState] = []
        for target, data in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            confined = resolve_writable_path_within_root(
                self._run_dir,
                target.relative_to(self._run_dir.resolve()).as_posix(),
                "cached artifact path",
            )
            existed = os.path.lexists(confined)
            if existed:
                target_stat = confined.lstat()
                if stat_module.S_ISLNK(target_stat.st_mode) or not stat_module.S_ISREG(
                    target_stat.st_mode
                ):
                    raise ValueError(f"cached artifact target must be a regular file: {confined}")
            states.append(
                _RestoreState(
                    target=confined,
                    data=data,
                    temporary=confined.parent / f".{confined.name}.{token}.cache-restore",
                    backup=confined.parent / f".{confined.name}.{token}.cache-backup",
                    existed=existed,
                )
            )

        try:
            for restore_state in states:
                atomic_write_bytes(restore_state.temporary, restore_state.data)
            for restore_state in states:
                if restore_state.existed:
                    _replace_path(restore_state.target, restore_state.backup)
                    restore_state.backed_up = True
            for restore_state in states:
                restore_state.install_attempted = True
                _replace_path(restore_state.temporary, restore_state.target)
        except Exception as error:
            rollback_errors: list[Exception] = []
            for restore_state in reversed(states):
                if restore_state.backed_up and os.path.lexists(restore_state.backup):
                    try:
                        _replace_path(restore_state.backup, restore_state.target)
                    except Exception as rollback_error:  # pragma: no cover - catastrophic I/O.
                        rollback_errors.append(rollback_error)
                elif (
                    not restore_state.existed
                    and restore_state.install_attempted
                    and os.path.lexists(restore_state.target)
                ):
                    try:
                        restore_state.target.unlink()
                    except OSError as rollback_error:  # pragma: no cover - catastrophic I/O.
                        rollback_errors.append(rollback_error)
            for restore_state in states:
                self._remove_private_file(restore_state.temporary)
            if rollback_errors:
                raise _ArtifactRestoreRecoveryError(
                    "cached artifact restoration failed and rollback was incomplete; "
                    "recovery backups were retained"
                ) from error
            raise OSError("cached artifact restoration failed and was rolled back") from error

        for restore_state in states:
            self._remove_private_file(restore_state.backup)

    @staticmethod
    def _remove_private_file(path: Path) -> None:
        if not os.path.lexists(path):
            return
        with contextlib.suppress(OSError):
            state = path.lstat()
            if not stat_module.S_ISDIR(state.st_mode):
                path.unlink()

    @staticmethod
    def _remove_private_bundle(path: Path) -> None:
        if not os.path.lexists(path):
            return
        with contextlib.suppress(OSError):
            state = path.lstat()
            if stat_module.S_ISLNK(state.st_mode) or not stat_module.S_ISDIR(state.st_mode):
                path.unlink()
            else:
                shutil.rmtree(path)

    def _paths(self, node: Node) -> tuple[Path, Path]:
        root = self._cache_root(node)
        return root / "record.json", root / "artifacts"


__all__ = ["NODE_CACHE_SCHEMA_VERSION", "NodeArtifactCache"]

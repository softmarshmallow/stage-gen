"""Fail-closed recovery at committed stage boundaries; no model-step replay."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from gnode import (
    ArtifactProvenance,
    CacheDisposition,
    Node,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
)
from stage_gen.components.character_3d.io import (
    canonical_digest,
    confined,
    digest,
    read_json,
    verified_input,
)

if TYPE_CHECKING:
    from stage_gen.recipes.character_3d.runner import CharacterRun
_EXCLUDED_DIRS = {"code", "ledger", "recovery", "invocations", "__pycache__"}
_EXCLUDED_ROOT_FILES = {
    "graph.json",
    "experiment.json",
    "runtime.json",
    "studio.json",
    "rig_studio.json",
    "summary.json",
    "outcome.json",
    "trace.jsonl",
}
_STUDIO_FIELDS = (
    "assets",
    "revisions",
    "observations",
    "counter",
    "frozen",
    "rig_revisions",
    "rig_frozen",
    "admitted_assembly",
)
_MAX_JSON = 32 * 1024 * 1024
_MAX_FILES = 10000


class RecoveryBlocked(NodeExecutionError):
    """Terminal refusal. Reconciliation is outside this run, never an in-run wait."""

    def __init__(self, reason: str, *, stage: str | None = None) -> None:
        self.reason, self.stage = (reason, stage)
        super().__init__("Recovery refused: " + reason + (" (" + stage + ")" if stage else ""))

    def record(self) -> dict[str, Any]:
        return {
            "status": "terminal_pending_reconciliation",
            "reason": self.reason,
            "stage": self.stage,
            "provider_replayed": False,
        }


def _json_copy[T](value: T) -> T:
    encoded = json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
    if len(encoded) > _MAX_JSON:
        raise RecoveryBlocked("checkpoint_state_too_large")
    return cast(T, json.loads(encoded))


def _publish(path: Path, value: object) -> None:
    """Publish once, atomically; a partial temp never counts as a commit."""
    confined(path.parent, path.name, must_exist=False)
    payload = json.dumps(value, indent=2, allow_nan=False).encode() + b"\n"
    if len(payload) > _MAX_JSON:
        raise RecoveryBlocked("checkpoint_record_too_large")
    descriptor, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        Path(temporary).unlink(missing_ok=True)


def default_recovery_state(run: CharacterRun) -> dict[str, Any]:
    """Explicit state allowlist: no backend, credential, environment or transcript object."""
    extension_hook = getattr(run, "recovery_state", None)
    return _json_copy(
        {
            "records": run.records,
            "parts": run.parts,
            "studio": {
                name: getattr(run.studio, name)
                for name in _STUDIO_FIELDS
                if hasattr(run.studio, name)
            },
            "worker_calls": run.worker.calls,
            "extension": extension_hook() if callable(extension_hook) else None,
        }
    )


def restore_default_recovery_state(run: CharacterRun, state: dict[str, Any]) -> None:
    state = _json_copy(state)
    count = state["worker_calls"]
    if type(count) is not int or not 0 <= count <= run.worker.max_calls:
        raise RecoveryBlocked("invalid_saved_worker_budget")
    extension = state.get("extension")
    hook = getattr(run, "restore_recovery_state", None)
    if extension is not None and (not callable(hook)):
        raise RecoveryBlocked("missing_extension_restore_hook")
    run.records.clear()
    run.records.update(state["records"])
    run.parts.clear()
    run.parts.update(state["parts"])
    run.studio.parts = run.parts
    for name, value in state["studio"].items():
        if name not in _STUDIO_FIELDS:
            raise RecoveryBlocked("unsupported_studio_field")
        setattr(run.studio, name, value)
    run.worker.calls = count
    if extension is not None:
        assert callable(hook)
        hook(extension)


class StageRecovery:
    """One process and one state-mutating stage at a time around the public registry.

    Use as the Scheduler's NodeHandler, not a second scheduler. prepare() must
    finish before any handler runs. Existing pre-checkpoint runs are refused.
    """

    def __init__(self, run: CharacterRun) -> None:
        self.run = run
        self.root = Path(run.run_root).absolute()
        self.directory = self.root / "recovery"
        self.completed: dict[str, dict[str, Any]] = {}
        self.manifest: dict[str, dict[str, Any]] = {}
        self.sequence: list[str] = []
        self.ledger: dict[str, Any] | None = None
        self.blocked: dict[str, Any] | None = None
        self._lock_fd: int | None = None
        self._serial = asyncio.Lock()
        self._prepared = False
        self._identity: dict[str, Any] | None = None
        self._halted = False

    def __enter__(self) -> StageRecovery:
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            raise RecoveryBlocked("symlinked_run_root")
        if self.directory.is_symlink():
            raise RecoveryBlocked("symlinked_recovery_directory")
        self.directory.mkdir(exist_ok=True)
        descriptor = os.open(
            self.directory / "run.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            raise RecoveryBlocked("run_already_owned") from None
        self._lock_fd = descriptor
        return self

    def __exit__(self, *_args: object) -> None:
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None

    def _inputs(self) -> list[dict[str, Any]]:
        experiment = self.run.experiment
        references = [("package", experiment[key]) for key in ("profile", "pricing")]
        references.extend(("input", part["source"]) for part in experiment.get("parts", []))
        if experiment.get("reference"):
            references.append(("input", experiment["reference"]))
        if experiment.get("assembly_input"):
            references.extend(
                ("input", experiment["assembly_input"][key]) for key in ("source", "review")
            )
        if experiment.get("review_input"):
            from stage_gen.recipes.character_3d.calibration_runner import (
                review_input_sources,
            )

            _, sources = review_input_sources(self.run.input_root, experiment["review_input"])
            references.extend(("input", source) for source in sources)
        for scope, source in references:
            verified_input(
                self.run.package_root if scope == "package" else self.run.input_root, source
            )
        return [{"scope": scope, **source} for scope, source in references]

    def _identity_record(self) -> dict[str, Any]:
        from stage_gen.components.character_3d.package_resources import verify_snapshot

        if self.run.package_root != self.root / "code":
            raise RecoveryBlocked("execution_must_use_frozen_run_code")
        verify_snapshot(self.root)
        runtime_path = confined(self.root, "runtime.json")
        runtime = read_json(runtime_path)
        entries = runtime["code"]
        paths = [item["path"] for item in entries]
        if not entries or len(paths) != len(set(paths)):
            raise RecoveryBlocked("invalid_runtime_manifest")
        for entry in entries:
            verified_input(self.run.package_root, {key: entry[key] for key in ("path", "sha256")})
        if read_json(confined(self.root, "experiment.json")) != self.run.experiment:
            raise RecoveryBlocked("experiment_changed")
        graph_path = confined(self.root, "graph.json", must_exist=False)
        if graph_path.exists() and read_json(graph_path) != self.run.graph.model_dump(mode="json"):
            raise RecoveryBlocked("graph_changed")
        return {
            "schema_version": 1,
            "graph_sha256": self.run.graph.graph_sha256,
            "runtime_dependencies": self.run.runtime_identity()
            if callable(getattr(self.run, "runtime_identity", None))
            else None,
            "experiment_sha256": canonical_digest(self.run.experiment),
            "runtime_sha256": digest(runtime_path),
            "inputs": self._inputs(),
        }

    def _files(self) -> dict[str, dict[str, Any]]:
        result = {}
        for directory, directories, names in os.walk(self.root, followlinks=False):
            base = Path(directory)
            relative = base.relative_to(self.root)
            for name in [*directories, *names]:
                if (base / name).is_symlink():
                    raise RecoveryBlocked("symlinked_run_artifact")
            directories[:] = [
                name
                for name in directories
                if name != "__pycache__"
                and (not (relative == Path(".") and name in _EXCLUDED_DIRS))
            ]
            for name in names:
                if relative == Path(".") and name in _EXCLUDED_ROOT_FILES:
                    continue
                path = base / name
                ref = path.relative_to(self.root).as_posix()
                if not stat.S_ISREG(path.stat().st_mode):
                    raise RecoveryBlocked("nonregular_run_artifact")
                result[ref] = {"sha256": digest(path), "bytes": path.stat().st_size}
                if len(result) > _MAX_FILES:
                    raise RecoveryBlocked("too_many_checkpoint_files")
        return result

    def _ledger(self) -> dict[str, Any] | None:
        path = confined(self.root, "ledger/ledger.json", must_exist=False)
        if not path.exists():
            return None
        ledger = read_json(path)
        attempts = ledger["attempts"]
        if ledger.get("dispatch_count") != len(attempts):
            raise RecoveryBlocked("ledger_count_mismatch")
        for item in attempts:
            episode = item.get("request", {}).get("episode_id")
            if episode not in {node.node_id for node in self.run.graph.nodes}:
                raise RecoveryBlocked("unknown_provider_episode")
            if item.get("status") == "reserved" or item.get("charge_status") != "reported":
                raise RecoveryBlocked("unresolved_provider_charge", stage=episode)
        return {
            "header_sha256": canonical_digest(
                {key: value for key, value in ledger.items() if key not in {"attempts", "events"}}
            ),
            "attempts": [
                {"attempt_id": item["attempt_id"], "sha256": canonical_digest(item)}
                for item in attempts
            ],
        }

    def _check_journals(self) -> None:
        root = self.root / "tool_journal"
        if not root.exists():
            return
        for path in root.rglob("*.started.json"):
            if path.parent.name not in {node.node_id for node in self.run.graph.nodes}:
                raise RecoveryBlocked("unknown_tool_episode")
            companion = path.with_name(path.name.replace(".started.json", ".finished.json"))
            if not companion.is_file():
                raise RecoveryBlocked("unfinished_tool_side_effect", stage=path.parent.name)

    def _validate_node(
        self, node: Node, result: NodeExecutionResult, state: dict[str, Any]
    ) -> None:
        if result.attempts > node.max_attempts or (node.is_local and result.provider_operations):
            raise RecoveryBlocked("invalid_scheduler_result", stage=node.node_id)
        artifacts = {item.artifact_ref: item for item in result.artifacts}
        if (
            len(artifacts) != len(result.artifacts)
            or set(artifacts) != node.declared_artifact_refs()
        ):
            raise RecoveryBlocked("incomplete_node_artifact_set", stage=node.node_id)
        for ref, artifact in artifacts.items():
            path = confined(self.root, ref)
            if digest(path) != artifact.sha256 or path.stat().st_size != artifact.bytes:
                raise RecoveryBlocked("node_artifact_changed", stage=node.node_id)
        for port in node.ports:
            if not port.sidecar_ref:
                raise RecoveryBlocked("node_sidecar_required", stage=node.node_id)
            value = read_json(confined(self.root, port.artifact_ref))
            meta = ArtifactProvenance.model_validate(
                read_json(confined(self.root, port.sidecar_ref))
            )
            artifact = artifacts[port.artifact_ref]
            if not meta.artifact or (meta.artifact.sha256, meta.artifact.bytes) != (
                artifact.sha256,
                artifact.bytes,
            ):
                raise RecoveryBlocked("sidecar_artifact_mismatch", stage=node.node_id)
            if state["records"].get(node.node_id) != value:
                raise RecoveryBlocked("record_state_mismatch", stage=node.node_id)
            if "cache_key" in meta.params:
                valid = meta.params.get("cache_key") == node.cache_key and meta.validation.get(
                    "accepted_value_sha256"
                ) == canonical_digest(value)
            else:
                metadata = meta.params.get("metadata", {})
                valid = (
                    metadata.get("stage") == node.node_id
                    and metadata.get("experiment_sha256") == canonical_digest(self.run.experiment)
                    and (meta.validation.get("submitted") is True)
                )
            if not valid:
                raise RecoveryBlocked("node_admission_lineage_mismatch", stage=node.node_id)
            for source in meta.inputs:
                if source.ref.startswith("run://"):
                    root, ref = (self.root, source.ref.removeprefix("run://"))
                elif source.ref.startswith("input://"):
                    root, ref = (self.run.input_root, source.ref.removeprefix("input://"))
                else:
                    raise RecoveryBlocked("unsupported_provenance_reference", stage=node.node_id)
                path = confined(root, ref)
                if digest(path) != source.sha256 or path.stat().st_size != source.bytes:
                    raise RecoveryBlocked("provenance_input_changed", stage=node.node_id)

    def _validate_assets(self, state: dict[str, Any]) -> None:
        root = getattr(self.run, "asset_input_root", self.run.input_root)
        for entry in [*state["parts"].values(), *state["studio"]["assets"].values()]:
            verified_input(root, entry["source"])

    @staticmethod
    def _result(record: dict[str, Any], *, hit: bool = False) -> NodeExecutionResult:
        return NodeExecutionResult(
            cache=CacheDisposition.HIT if hit else CacheDisposition(record["cache"]),
            attempts=1 if hit else record["attempts"],
            provider_operations=0 if hit else record["provider_operations"],
            known_cost_usd=0 if hit else record["known_cost_usd"],
            artifacts=tuple(NodeArtifact.model_validate(item) for item in record["artifacts"]),
        )

    def prepare(self, *, resume: bool = False) -> dict[str, Any]:
        try:
            return self._prepare(resume=resume)
        except RecoveryBlocked as error:
            self.blocked = error.record()
            raise
        except (ValueError, KeyError, TypeError, OSError):
            invalid = RecoveryBlocked("invalid_recovery_evidence")
            self.blocked = invalid.record()
            raise invalid from None

    def _prepare(self, *, resume: bool = False) -> dict[str, Any]:
        if self._lock_fd is None:
            raise RecoveryBlocked("exclusive_run_context_required")
        identity = self._identity_record()
        identity_path = self.directory / "identity.json"
        if not identity_path.exists():
            if resume or self._files() or (self.root / "ledger/ledger.json").exists():
                raise RecoveryBlocked("legacy_run_has_no_stage_checkpoints")
            _publish(identity_path, identity)
        elif not resume:
            raise RecoveryBlocked("existing_run_requires_explicit_resume")
        elif read_json(confined(self.directory, "identity.json")) != identity:
            raise RecoveryBlocked("frozen_identity_changed")
        self._identity = identity
        nodes = {node.node_id: node for node in self.run.graph.nodes}
        checkpoints = []
        for path in self.directory.glob("*.completed.json"):
            checkpoint = read_json(confined(self.directory, path.name))
            if checkpoint.get("schema_version") != 1 or checkpoint.get(
                "payload_sha256"
            ) != canonical_digest(
                {key: value for key, value in checkpoint.items() if key != "payload_sha256"}
            ):
                raise RecoveryBlocked("checkpoint_payload_changed")
            checkpoints.append((checkpoint["sequence"], path, checkpoint))
        previous = None
        last_state = None
        last_ledger = None
        for index, path, checkpoint in sorted(checkpoints):
            node_id = checkpoint["node_id"]
            if (
                index != len(self.sequence) + 1
                or node_id not in nodes
                or node_id in self.completed
                or (checkpoint["previous_sha256"] != previous)
                or (checkpoint["identity_sha256"] != canonical_digest(identity))
            ):
                raise RecoveryBlocked("invalid_checkpoint_chain", stage=node_id)
            node = nodes[node_id]
            if (
                checkpoint["cache_key"] != node.cache_key
                or not set(node.depends_on) <= self.completed.keys()
            ):
                raise RecoveryBlocked("checkpoint_dependencies_changed", stage=node_id)
            if any((checkpoint["files"].get(ref) != item for ref, item in self.manifest.items())):
                raise RecoveryBlocked("immutable_artifact_changed_between_stages", stage=node_id)
            self._validate_node(node, self._result(checkpoint["result"]), checkpoint["state"])
            self.completed[node_id] = checkpoint
            self.sequence.append(path.name)
            self.manifest = checkpoint["files"]
            last_state, last_ledger = (checkpoint["state"], checkpoint["ledger_attempts"])
            previous = digest(path)
        for path in self.directory.glob("*.started.json"):
            stage = read_json(confined(self.directory, path.name))["node_id"]
            if stage not in self.completed:
                raise RecoveryBlocked("stage_has_no_committed_checkpoint", stage=stage)
        self._check_journals()
        if self._ledger() != last_ledger:
            raise RecoveryBlocked("provider_activity_after_checkpoint")
        if self._files() != self.manifest:
            raise RecoveryBlocked("uncommitted_or_changed_run_files")
        if last_state is not None:
            self._validate_assets(last_state)
            restore_default_recovery_state(self.run, last_state)
        self.ledger = last_ledger
        self._prepared = True
        return {
            "status": "ready",
            "completed_nodes": list(self.completed),
            "provider_replayed": False,
            "worker_calls": self.run.worker.calls,
        }

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        try:
            return await self._execute_node(node, context)
        except BaseException as error:
            self.blocked = (
                error.record()
                if isinstance(error, RecoveryBlocked)
                else {
                    **RecoveryBlocked(
                        "stage_failed_before_checkpoint", stage=node.node_id
                    ).record(),
                    "error_type": type(error).__name__,
                }
            )
            raise

    async def _execute_node(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        async with self._serial:
            if not self._prepared or self._lock_fd is None or self._halted:
                raise RecoveryBlocked("recovery_not_prepared")
            if (
                self._identity_record() != self._identity
                or self._files() != self.manifest
                or self._ledger() != self.ledger
            ):
                raise RecoveryBlocked("checkpoint_content_changed", stage=node.node_id)
            if node.node_id in self.completed:
                checkpoint = self.completed[node.node_id]
                self._validate_node(node, self._result(checkpoint["result"]), checkpoint["state"])
                return self._result(checkpoint["result"], hit=True)
            if not set(node.depends_on) <= self.completed.keys():
                raise RecoveryBlocked("dependency_not_checkpointed", stage=node.node_id)
            self._halted = True
            _publish(
                self.directory / (node.node_id + ".started.json"),
                {
                    "node_id": node.node_id,
                    "cache_key": node.cache_key,
                    "started_at_unix": time.time(),
                    "identity_sha256": canonical_digest(self._identity),
                },
            )
            try:
                result = await self.run.registry(node, context)
                state = default_recovery_state(self.run)
                self._validate_assets(state)
                self._validate_node(node, result, state)
                self._check_journals()
                ledger = self._ledger()
                manifest = self._files()
            except BaseException:
                self._halted = True
                raise
            if any((manifest.get(ref) != item for ref, item in self.manifest.items())):
                raise RecoveryBlocked("stage_mutated_prior_artifact", stage=node.node_id)
            checkpoint = {
                "schema_version": 1,
                "node_id": node.node_id,
                "sequence": len(self.sequence) + 1,
                "cache_key": node.cache_key,
                "identity_sha256": canonical_digest(self._identity),
                "previous_sha256": digest(self.directory / self.sequence[-1])
                if self.sequence
                else None,
                "state": state,
                "files": manifest,
                "ledger_attempts": ledger,
                "result": {
                    "cache": result.cache.value,
                    "attempts": result.attempts,
                    "provider_operations": result.provider_operations,
                    "known_cost_usd": result.known_cost_usd,
                    "artifacts": [item.model_dump(mode="json") for item in result.artifacts],
                },
            }
            name = node.node_id + ".completed.json"
            checkpoint["payload_sha256"] = canonical_digest(checkpoint)
            _publish(self.directory / name, checkpoint)
            self.completed[node.node_id] = checkpoint
            self.sequence.append(name)
            self.manifest = manifest
            self.ledger = ledger
            self._halted = False
            return result

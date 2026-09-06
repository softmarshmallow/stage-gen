"""Thin composition boundary for oblique-survival execution.

Resolve the authored package, plan one scope, dispatch it, and read the manifest the
graph's own terminal node wrote. Nothing here generates.

The scope is a property of the plan rather than a mode flag on a run: node identity
never depends on it, so a narrow run and a wide one share every node they have in
common, and the cache is what makes the ladder cheap.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from gnode import (
    CacheDisposition,
    Node,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionResult,
    NodeType,
    assert_safe_path_segment,
)
from stage_gen.canonical import content_sha256
from stage_gen.config import CapabilityName, StageGenConfig
from stage_gen.recipes.dry_run import is_placeholder
from stage_gen.recipes.executor import RecipeExecutor, RecipePlan, RecipeRun
from stage_gen.recipes.node_cache import NodeArtifactCache
from stage_gen.recipes.oblique_survival import manifest as manifest_module
from stage_gen.recipes.oblique_survival.models import Package
from stage_gen.recipes.oblique_survival.prepared_survival import (
    ObliqueSurvivalNodeHandler,
    admit_cached,
)
from stage_gen.recipes.oblique_survival.survival_graph import (
    MANIFEST_REF,
    OBLIQUE_SURVIVAL_ATTEMPT_LEDGER_KIND,
    OBLIQUE_SURVIVAL_CACHE_NAMESPACE,
    OBLIQUE_SURVIVAL_CACHE_RECORD_KIND,
    REJECTS_ROOT,
    ObliqueSurvivalGraph,
    build_graph,
)
from stage_gen.recipes.oblique_survival.survival_request import resolve_survival_source
from stage_gen.recipes.oblique_survival.survival_types import (
    SCOPES,
    survival_type_index,
)

#: The operation each provider capability answers for, so a run asks for exactly the
#: credentials its own plan will spend and no more.
_CAPABILITY_BY_OPERATION: Mapping[str, CapabilityName] = {
    "image_generation": CapabilityName.NATIVE_IMAGE_GENERATION,
    "structured_generation": CapabilityName.STRUCTURED_GENERATION,
    "tool_loop": CapabilityName.TOOL_LOOP,
    "music_generation": CapabilityName.MUSIC_GENERATION,
    "sound_effect_generation": CapabilityName.SOUND_EFFECT_GENERATION,
}


def admit_scope(scope: str) -> str:
    """One rung of the ladder, refused by name rather than silently widened."""

    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}; known scopes are {list(SCOPES)}")
    return scope


@dataclass(frozen=True, slots=True)
class ObliqueSurvivalPlan(RecipePlan[Package, ObliqueSurvivalGraph]):
    #: The rung this plan was built for; it is on the graph too, and repeated here so
    #: a caller that holds only the plan does not have to reach through it.
    scope: str = "full"


@dataclass(frozen=True, slots=True)
class ObliqueSurvivalRun(RecipeRun[ObliqueSurvivalPlan]):
    manifest: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ImportReport:
    """What a one-time transfer of a prior run into the cache actually did."""

    prior_run: str
    scope: str
    nodes: int
    imported: int
    #: Nodes whose recorded key no longer matches the promoted graph's. They are never
    #: written under the new key: an import under a moved key would be a lie about
    #: identity, and these nodes simply run again.
    moved: tuple[str, ...] = ()
    #: Nodes the prior run never finished, so there is nothing to transfer.
    absent: tuple[str, ...] = ()
    synthesized_ledgers: int = 0

    def document(self) -> dict[str, object]:
        return {
            "prior_run": self.prior_run,
            "scope": self.scope,
            "nodes": self.nodes,
            "imported": self.imported,
            "moved": list(self.moved),
            "absent": list(self.absent),
            "synthesized_ledgers": self.synthesized_ledgers,
        }


@dataclass(slots=True)
class _PriorNode:
    """One node of a prior run, as its trace recorded it."""

    cache_key: str
    artifacts: list[NodeArtifact] = field(default_factory=list)


class ObliqueSurvivalExecutor(RecipeExecutor[Package, ObliqueSurvivalGraph]):
    """Resolve, plan, and dispatch one scope of one authored survival package."""

    IDENTITY_DOCUMENT = "oblique-survival-identity.json"
    #: An image node's six attempts at up to thirty minutes each outlast any stage.
    NODE_TIMEOUT_FLOOR_S = 3_600.0

    def __init__(self, config: StageGenConfig, *, scope: str = "full") -> None:
        super().__init__(config)
        self.scope = admit_scope(scope)

    # -- planning -------------------------------------------------------------

    def _resolve(self, input_path: Path) -> Package:
        return resolve_survival_source(input_path)

    def _build(self, resolved: Package) -> ObliqueSurvivalGraph:
        return build_graph(self._config, resolved, self.scope)

    def _type_index(self) -> Mapping[str, NodeType]:
        return survival_type_index()

    def resolve(self, input_path: Path) -> Package:
        return self._resolve(input_path)

    def plan(self, input_path: Path, scope: str | None = None) -> ObliqueSurvivalPlan:
        """Resolve one authored package into the exact plan for one scope, offline."""

        chosen = self.scope if scope is None else admit_scope(scope)
        resolved = self._resolve(input_path)
        plan = self.plan_graph(resolved, build_graph(self._config, resolved, chosen))
        return ObliqueSurvivalPlan(
            resolved=plan.resolved, graph=plan.graph, projection=plan.projection, scope=chosen
        )

    def required_capabilities(self, graph: ObliqueSurvivalGraph) -> tuple[CapabilityName, ...]:
        """Exactly the credentials this plan will spend, read off the plan itself.

        A scope that draws no music must not be refused for a missing music key, and a
        package whose every take is adopted spends nothing on that modality at all.
        """

        counts = graph.operation_counts()
        return tuple(
            capability
            for operation, capability in _CAPABILITY_BY_OPERATION.items()
            if counts.get(operation, 0) > 0
        )

    # -- runs -----------------------------------------------------------------

    async def dry_run(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        scope: str | None = None,
        failure_node_id: str | None = None,
        time_scale: float = 0.0001,
    ) -> ObliqueSurvivalRun:
        assert_safe_path_segment(invocation_id, "invocation_id")
        plan = self.plan(input_path, scope)
        await self.open_run(plan, run_dir=run_dir)
        summary = await self.dry_dispatch(
            plan,
            run_dir=run_dir,
            cache_dir=cache_dir,
            invocation_id=invocation_id,
            failure_node_id=failure_node_id,
            time_scale=time_scale,
        )
        return ObliqueSurvivalRun(
            plan=plan, summary=summary, run_dir=run_dir, manifest=self._close(run_dir)
        )

    async def run(
        self,
        input_path: Path,
        *,
        run_dir: Path,
        cache_dir: Path,
        invocation_id: str,
        scope: str | None = None,
    ) -> ObliqueSurvivalRun:
        assert_safe_path_segment(invocation_id, "invocation_id")
        plan = self.plan(input_path, scope)
        # Credentials are checked against this plan before a run directory exists, so a
        # missing key costs nothing and leaves nothing behind.
        self.require(*self.required_capabilities(plan.graph))
        await self.open_run(plan, run_dir=run_dir)
        async with self.services() as services:
            handler = ObliqueSurvivalNodeHandler(
                plan.graph,
                plan.resolved,
                run_dir=run_dir,
                cache_dir=cache_dir,
                images=services.image(),
                structured=services.structured(),
                tool_loop=services.tool_loop(),
                music=services.music(),
                sounds=services.sound_effect(),
            )
            summary = await self.dispatch(
                plan, handler, run_dir=run_dir, invocation_id=invocation_id
            )
        return ObliqueSurvivalRun(
            plan=plan, summary=summary, run_dir=run_dir, manifest=self._close(run_dir)
        )

    # -- closing --------------------------------------------------------------

    def _close(self, run_dir: Path) -> dict[str, object] | None:
        """The manifest as the run holds it: read, never rewritten.

        The spike wrote ``manifest.json`` twice -- once from the terminal node's own
        declared port and once from a finalize pass afterwards -- so a cached node and
        the file beside it could disagree about what the run published. The port is
        authoritative; ``finalize`` rebuilds only when a caller asks for it. A dry run's
        manifest is a placeholder, and a placeholder is not a manifest.
        """

        path = run_dir / MANIFEST_REF
        if not path.is_file() or is_placeholder(path):
            return None
        document = json.loads(path.read_bytes())
        return document if isinstance(document, dict) else None

    def finalize(self, run_dir: Path, *, input_path: Path) -> manifest_module.Manifest:
        """Rebuild the manifest from what the run has on disk, and publish it.

        Only for a run whose terminal node did not finish, or whose published assets
        were repaired by hand afterwards. It reads the authored package again because a
        manifest measures authored intent against produced bytes, and a run records the
        package's identity rather than a path back to it.
        """

        package = self._resolve(input_path)
        plan_document = json.loads((run_dir / "execution-plan.json").read_bytes())
        document = manifest_module.build_manifest(
            package,
            run_dir,
            run_id=run_dir.name,
            graph_sha256=str(plan_document["graph_sha256"]),
            scope=str(plan_document["scope"]),
        )
        (run_dir / MANIFEST_REF).write_bytes(manifest_module.manifest_bytes(document))
        return document

    # -- the one-time transfer ------------------------------------------------

    def import_run(
        self,
        prior_run_dir: Path,
        *,
        input_path: Path,
        cache_dir: Path,
        scope: str | None = None,
        staging_dir: Path | None = None,
    ) -> ImportReport:
        """Replay a prior run's artifacts into this recipe's cache, key by key.

        The prior run is read only. Every node's recorded cache key is recompared
        against the promoted graph's, every recorded digest is re-verified against the
        bytes on disk by the cache's own writer, and a node whose key has moved is
        reported rather than written under the new one. Ports the promoted graph
        declares and the prior run does not -- the attempt ledgers -- are synthesized
        from what that run kept, so an imported node is complete rather than nearly so.
        """

        plan = self.plan(input_path, scope)
        prior = _read_prior_run(prior_run_dir)
        staging = (staging_dir or cache_dir.parent / f"{cache_dir.name}-import-staging").resolve()
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        cache = NodeArtifactCache(
            plan.graph,
            run_dir=staging,
            cache_dir=cache_dir,
            namespace=OBLIQUE_SURVIVAL_CACHE_NAMESPACE,
            record_kind=OBLIQUE_SURVIVAL_CACHE_RECORD_KIND,
            admit=admit_cached,
        )
        moved = [
            node.node_id
            for node in plan.graph.nodes
            if node.node_id in prior and prior[node.node_id].cache_key != node.cache_key
        ]
        provider_moved = [node_id for node_id in moved if not plan.graph.node(node_id).is_local]
        if provider_moved:
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError(
                "refusing the transfer: these provider nodes' cache keys have moved since "
                "the prior run, so importing them would claim an identity that is not "
                "there: " + ", ".join(sorted(provider_moved))
            )
        absent: list[str] = []
        results: dict[str, NodeExecutionResult] = {}
        ledgers = 0
        try:
            for node in plan.graph.nodes:
                recorded = prior.get(node.node_id)
                if recorded is None:
                    absent.append(node.node_id)
                    continue
                if recorded.cache_key != node.cache_key:
                    continue
                artifacts = list(recorded.artifacts)
                _stage_refs(prior_run_dir, staging, artifacts)
                ledger = _ledger_ref(node)
                if ledger is not None:
                    artifacts.append(_write_ledger(prior_run_dir, staging, node, ledger))
                    ledgers += 1
                result = NodeExecutionResult(
                    cache=CacheDisposition.MISS,
                    attempts=1,
                    provider_operations=0,
                    artifacts=tuple(artifacts),
                    known_cost_usd=0.0,
                )
                context = NodeExecutionContext(
                    invocation_id=prior_run_dir.name,
                    graph_sha256=plan.graph.graph_sha256,
                    dependency_results=results,
                )
                cache.write(node, context, result)
                results[node.node_id] = result
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return ImportReport(
            prior_run=prior_run_dir.name,
            scope=plan.scope,
            nodes=len(plan.graph.nodes),
            imported=len(results),
            moved=tuple(moved),
            absent=tuple(absent),
            synthesized_ledgers=ledgers,
        )


def _read_prior_run(run_dir: Path) -> dict[str, _PriorNode]:
    """A prior run's finished nodes: the key it was taken under and what it published."""

    plan_document = json.loads((run_dir / "execution-plan.json").read_bytes())
    prior = {
        str(node["node_id"]): _PriorNode(cache_key=str(node["cache_key"]))
        for node in plan_document["nodes"]
    }
    finished: dict[str, _PriorNode] = {}
    with (run_dir / "execution-trace.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            if event.get("event") != "node_finished":
                continue
            node_id = str(event["node_id"])
            entry = prior.get(node_id)
            if entry is None:
                continue
            entry.artifacts = [
                NodeArtifact(
                    artifact_ref=str(item["artifact_ref"]),
                    sha256=str(item["sha256"]),
                    bytes=int(item["bytes"]),
                )
                for item in event.get("artifacts", ())
            ]
            finished[node_id] = entry
    return finished


def _stage_refs(source_root: Path, staging: Path, artifacts: Sequence[NodeArtifact]) -> None:
    """Put each recorded artifact where the cache writer will look, without copying.

    The prior run is not the run being written, and it must not be touched: the staged
    tree is hard links to its bytes, which the cache reads and digests exactly as if
    they were this run's. A link is not a symlink, so the writer's own refusal of
    symlinked sources still holds.
    """

    for artifact in artifacts:
        source = source_root / artifact.artifact_ref
        target = staging / artifact.artifact_ref
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                os.link(source, target)
            except OSError:
                shutil.copyfile(source, target)


def _ledger_ref(node: Node) -> str | None:
    for port in node.ports:
        if port.port_id == "attempts":
            return port.artifact_ref
    return None


def _write_ledger(source_root: Path, staging: Path, node: Node, ref: str) -> NodeArtifact:
    """The attempt ledger the promoted graph declares, for a run that declared none.

    The spike kept refused image attempts under ``production/rejected/<node>/`` and
    refused structured attempts in an ``<artifact>.attempts`` directory beside the
    artifact. Whatever of that survives is read back here and written as the ledger the
    node now declares; a node that refused nothing gets an empty one, which is the true
    statement rather than an absent file.
    """

    records: list[dict[str, object]] = []
    rejected = source_root / REJECTS_ROOT / node.node_id
    if rejected.is_dir():
        for reasons_path in sorted(rejected.glob("attempt-*.json")):
            try:
                entry = json.loads(reasons_path.read_bytes())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(entry, dict):
                records.append({str(key): value for key, value in entry.items()})
    for port in node.ports:
        attempts_dir = source_root / f"{port.artifact_ref}.attempts"
        if not attempts_dir.is_dir():
            continue
        for index, attempt_path in enumerate(sorted(attempts_dir.glob("attempt-*.json")), start=1):
            try:
                entry = json.loads(attempt_path.read_bytes())
            except (OSError, json.JSONDecodeError):
                continue
            records.append({"attempt": index, "rejected": entry})
    document = {
        "schema_version": 1,
        "kind": OBLIQUE_SURVIVAL_ATTEMPT_LEDGER_KIND,
        "node_id": node.node_id,
        "operation_id": node.node_id,
        "rejected_attempts": len(records),
        "attempts": records,
        "imported_from": source_root.name,
    }
    data = (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    target = staging / ref
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return NodeArtifact(artifact_ref=ref, sha256=content_sha256(data), bytes=len(data))


__all__ = [
    "ImportReport",
    "ObliqueSurvivalExecutor",
    "ObliqueSurvivalPlan",
    "ObliqueSurvivalRun",
    "admit_scope",
]

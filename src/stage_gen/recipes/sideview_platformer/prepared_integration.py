"""The provider-free terminal: restore the closure from the cache, then publish the manifest.

``manifest-assemble`` was declared as the graph's terminal node for as long as the graph
existed, and had no handler: the manifest was built outside the graph, the cache and the
trace, from run directories a caller listed by hand. This handler makes it a node.

Integration runs the manifest node's whole dependency closure with the world and content
handlers, each holding a backend that refuses. A node the cache holds is restored into the
run directory exactly as the paid checkpoints restore it, admission included; a local node
re-runs for free; a paid node the cache does not hold stops the run with the checkpoint
that would produce it. Nothing is spent by construction, not by promise.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from collections.abc import Sequence
from pathlib import Path

from gnode import (
    CacheDisposition,
    Node,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    atomic_write_json,
)
from stage_gen.orchestration.runtime import (
    create_provider_free_image_service,
    create_provider_free_music_service,
    create_provider_free_structured_service,
)
from stage_gen.recipes.sideview_platformer.execution_graph import ExecutionGraph
from stage_gen.recipes.sideview_platformer.package_types import MANIFEST_ASSEMBLE
from stage_gen.recipes.sideview_platformer.prepared_content import PreparedContentNodeHandler
from stage_gen.recipes.sideview_platformer.prepared_manifest import (
    PreparedManifestResult,
    assemble_prepared_runtime,
)
from stage_gen.recipes.sideview_platformer.prepared_world import PreparedWorldNodeHandler
from stage_gen.recipes.sideview_platformer.validation import ResolvedGamePackage

PROVIDER_FREE_REASON = (
    "integration is provider-free: this node's artifact is not in the cache, so the "
    "checkpoint that produces it (world, content or soundtrack) must run first"
)


class PreparedIntegrationNodeHandler:
    """Route every node to the checkpoint handler that owns it; assemble the terminal."""

    def __init__(
        self,
        graph: ExecutionGraph,
        package: ResolvedGamePackage,
        *,
        run_dir: Path,
        cache_dir: Path,
        output_dir: Path,
        terrain_template_path: Path,
        terrain_topology_reference_path: Path,
        artifact_roots: Sequence[Path] = (),
        replace_output: bool = False,
    ) -> None:
        self._package = package
        self._run_dir = run_dir
        self._output_dir = output_dir
        self._artifact_roots = tuple(artifact_roots)
        self._replace_output = replace_output
        self._world = PreparedWorldNodeHandler(
            graph,
            package,
            run_dir=run_dir,
            cache_dir=cache_dir,
            image_service=create_provider_free_image_service(PROVIDER_FREE_REASON),
            structured_service=create_provider_free_structured_service(PROVIDER_FREE_REASON),
            terrain_template_path=terrain_template_path,
            terrain_topology_reference_path=terrain_topology_reference_path,
        )
        self._content = PreparedContentNodeHandler(
            graph,
            package,
            run_dir=run_dir,
            cache_dir=cache_dir,
            image_service=create_provider_free_image_service(PROVIDER_FREE_REASON),
            structured_service=create_provider_free_structured_service(PROVIDER_FREE_REASON),
            music_service=create_provider_free_music_service(PROVIDER_FREE_REASON),
        )
        self._world_types = self._world.registered_type_ids
        #: The published run, once the terminal node has run. ``None`` until then.
        self.result: PreparedManifestResult | None = None

        #: Provider nodes the cache lacked and an artifact root supplied, in run order.
        self.adopted_node_ids: list[str] = []

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        if node.type_id == MANIFEST_ASSEMBLE.type_id:
            return await self._assemble(node)
        owner = self._world if node.type_id in self._world_types else self._content
        restored = owner.restore(node, context)
        if restored is not None:
            return restored
        if node.is_local:
            # Free and deterministic: re-derived over what the run holds, and cached.
            return await owner(node, context)
        adopted = await asyncio.to_thread(self._adopt_from_roots, node)
        if adopted is not None:
            self.adopted_node_ids.append(node.node_id)
            return adopted
        raise NodeExecutionError(PROVIDER_FREE_REASON, attempts=1, provider_operations=0)

    def _adopt_from_roots(self, node: Node) -> NodeExecutionResult | None:
        """Take a paid node's declared artifacts from the first root that holds all of them.

        Adoption is a run-level fact, not a cache write: the bytes reach the published
        closure, the trace says the node was adopted rather than restored, and the cache
        still lacks the node, so ``package plan --cache-dir`` keeps pricing it honestly.
        """

        refs = [
            ref
            for port in node.ports
            for ref in (
                (port.artifact_ref, port.sidecar_ref)
                if port.sidecar_ref is not None
                else (port.artifact_ref,)
            )
        ]
        for root in self._artifact_roots:
            sources: list[Path] = []
            for ref in refs:
                candidate = root.joinpath(*ref.split("/"))
                if candidate.is_symlink() or not candidate.is_file():
                    break
                resolved = candidate.resolve(strict=True)
                if not resolved.is_relative_to(root.resolve()):
                    break
                sources.append(resolved)
            if len(sources) != len(refs):
                continue
            artifacts: list[NodeArtifact] = []
            for ref, source in zip(refs, sources, strict=True):
                target = self._run_dir.joinpath(*ref.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                data = target.read_bytes()
                artifacts.append(
                    NodeArtifact(
                        artifact_ref=ref, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)
                    )
                )
            return NodeExecutionResult(
                cache=CacheDisposition.BYPASS,
                attempts=1,
                provider_operations=0,
                artifacts=tuple(artifacts),
            )
        return None

    async def _assemble(self, node: Node) -> NodeExecutionResult:
        # The run directory holds what the cache restored; caller roots come after it, so a
        # directory a caller names can supply what the cache lacks but never override it.
        result = await asyncio.to_thread(
            assemble_prepared_runtime,
            self._package,
            artifact_roots=(self._run_dir, *self._artifact_roots),
            output_dir=self._output_dir,
            replace_output=self._replace_output,
        )
        self.result = result
        ref = node.port("manifest").artifact_ref
        atomic_write_json(self._run_dir / ref, result.manifest)
        data = (self._run_dir / ref).read_bytes()
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=1,
            provider_operations=0,
            artifacts=(
                NodeArtifact(
                    artifact_ref=ref, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)
                ),
            ),
        )

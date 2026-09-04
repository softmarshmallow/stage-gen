"""The node handler every recipe dispatches through.

A recipe's handler answers the scheduler for every node in its graph: the cache first,
then the registered method for the node's type, and a failure mapped onto the ledger
the trace records. Six handlers wrote that loop six ways; the differences that survive
are hooks here, the rest is one implementation. Provider operations stay inside the
component that owns the retry: a method here builds a request, hands it to a service,
and publishes what came back.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path

from gnode import (
    CacheDisposition,
    CancellationError,
    Graph,
    Node,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    NodeHandler,
    NodeType,
    NodeTypeRegistry,
    resolve_relative_path_within_root,
)
from stage_gen.canonical import content_sha256
from stage_gen.recipes.node_cache import NodeArtifactCache

#: One node type's implementation: the node alone, because the run-level context the
#: engine passes is the same for every node of a run and the handler keeps it.
NodeMethod = Callable[[Node], Awaitable[NodeExecutionResult]]


def bind(method: NodeMethod) -> NodeHandler:
    async def handler(node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        return await method(node)

    return handler


class RecipeNodeHandler(ABC):
    """Cache first, then the type's own method; failures become one ledger entry.

    A subclass sets whatever its methods need - services, the resolved package, paths -
    and then calls ``super().__init__``, which builds the registry from ``_handlers``.
    """

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
        self._invocation_id: str | None = None
        self._cache = NodeArtifactCache(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=namespace,
            record_kind=record_kind,
            admit=admit,
        )
        registry = NodeTypeRegistry()
        for node_type, method in self._handlers():
            registry.register(node_type, bind(method))
        self._registry = registry

    @abstractmethod
    def _handlers(self) -> Iterable[tuple[NodeType, NodeMethod]]:
        """Every node type this handler owns, with the method that runs it."""

    # ---------------------------------------------------------------- dispatch

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        self._invocation_id = context.invocation_id
        cached = self._cache.read(node, context)
        if cached is not None:
            # The cached attempt ledger is provenance for the bytes being restored.
            # It comes back byte-for-byte; cache disposition belongs to the trace.
            return cached
        try:
            result = await self._registry(node, context)
        except CancellationError as error:
            self._cancelled(node, error)
            raise
        except NodeExecutionError as error:
            self._failed(node, error)
            raise
        except Exception as error:
            failure = self._failure(node, error)
            self._failed(node, failure)
            raise failure from error
        self._cache.write(node, context, result)
        return result

    def restore(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult | None:
        """The cache's answer alone: restored into the run, or ``None``. Never generates."""

        return self._cache.read(node, context)

    @property
    def registered_type_ids(self) -> frozenset[str]:
        """The node types this handler owns; a checkpoint router routes by it."""

        return frozenset(node_type.type_id for node_type in self._registry.types())

    @property
    def invocation_id(self) -> str:
        """The run this handler is answering for; known once the scheduler has called."""

        if self._invocation_id is None:
            raise RuntimeError("no node has been dispatched yet")
        return self._invocation_id

    # ------------------------------------------------------------------- hooks

    def _failure(self, node: Node, error: Exception) -> NodeExecutionError:
        """Map an exception that escaped a method onto the ledger the trace records.

        A retry owner that exhausted its attempts says how many on the error; for a
        provider node those are provider operations. A local node spends nothing.
        """

        attempts = min(max(int(getattr(error, "attempts", 1)), 1), node.max_attempts)
        return NodeExecutionError(
            f"{type(error).__name__}: {error}",
            attempts=attempts,
            provider_operations=0 if node.is_local else attempts,
        )

    def _failed(self, node: Node, error: NodeExecutionError) -> None:  # noqa: B027
        """A node failed with ``error``; a recipe that keeps its own ledger writes it here."""

    def _cancelled(self, node: Node, error: CancellationError) -> None:  # noqa: B027
        """A node was cancelled mid-flight; the count of started operations is on ``error``."""

    # ----------------------------------------------------------------- results

    def _result(
        self,
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

        refs: list[str] = []
        for port in node.ports:
            refs.append(port.artifact_ref)
            if port.sidecar_ref is not None:
                refs.append(port.sidecar_ref)
        artifacts: list[NodeArtifact] = []
        for ref in refs:
            path = self._run_dir / ref
            if not path.is_file():
                continue
            data = path.read_bytes()
            artifacts.append(
                NodeArtifact(artifact_ref=ref, sha256=content_sha256(data), bytes=len(data))
            )
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=provider_operations,
            artifacts=tuple(artifacts),
            known_cost_usd=known_cost_usd,
        )

    def _path(self, ref: str) -> Path:
        """A run-relative reference resolved inside the run directory, never outside it."""

        return resolve_relative_path_within_root(self._run_dir, ref, "run artifact path")

    def _read(self, ref: str) -> bytes:
        return self._path(ref).read_bytes()

    @staticmethod
    def _card_prompt(node: Node) -> str:
        """The plan is the single source of a node's static instruction text."""

        if node.card is None or node.card.prompt is None:
            raise ValueError(f"node {node.node_id} declares no card prompt")
        return node.card.prompt


__all__ = ["NodeMethod", "RecipeNodeHandler", "bind"]

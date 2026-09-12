#!/usr/bin/env python3
"""Check or rewrite the executable, provider-free model-policy snapshot.

The fixture census is demo-owned and packaged with ``stage-gen-legacy``.  It records
the checked-in image route catalog and policy table together with compact plans
for every canonical recipe fixture.  Checking and writing only parse local
files and build offline graphs; neither path loads credentials or constructs a
provider adapter.

    uv run python godot/legacy/tools/write_model_policy_snapshot.py
    uv run python godot/legacy/tools/write_model_policy_snapshot.py --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from gnode import Graph, atomic_write_text
from stage_gen.canonical import canonical_json_bytes
from stage_gen.config import StageGenConfig
from stage_gen.image_product import ImageProvider
from stage_gen.model_policy_maintenance import (
    ACTIVE_MODEL_POLICY_SNAPSHOT,
    GeneratedModelPolicyFileSnapshotV1,
    ModelPolicySnapshotV1,
    build_model_policy_snapshot,
    render_model_policy_snapshot,
)
from stage_gen.model_routes import IMAGE_ROUTE_CATALOG, image_workload_policies
from stage_gen.recipes.storefront.storefront_executor import StorefrontExecutor
from stage_gen.recipes.universe.universe_graph import (
    build_universe_gallery_graph,
    build_universe_semantic_graph,
    universe_graph_profile,
)
from stage_gen.recipes.universe.universe_request import (
    admitted_universe_from_document,
    read_universe_document,
    resolve_sample_ledger,
    resolve_universe_source,
)
from stage_gen_legacy.recipes.dialogue_scene.scene_executor import DialogueSceneExecutor
from stage_gen_legacy.recipes.oblique_survival.survival_executor import ObliqueSurvivalExecutor
from stage_gen_legacy.recipes.oblique_survival.survival_types import SCOPES as SURVIVAL_SCOPES
from stage_gen_legacy.recipes.pointclick_room.room_executor import PointClickRoomExecutor
from stage_gen_legacy.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen_legacy.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_PATH = (
    REPOSITORY_ROOT / "godot/legacy/python/stage_gen_legacy" / ACTIVE_MODEL_POLICY_SNAPSHOT
)

PLATFORMER_FIXTURE = "godot/legacy/inputs/bellweather"
RUNNER_FIXTURE = "godot/legacy/inputs/iron-petal-unit"
DIALOGUE_FIXTURE = "godot/legacy/inputs/the_grain"
POINTCLICK_FIXTURE = "godot/legacy/inputs/the_grain/rooms/window"
STOREFRONT_FIXTURE = "godot/legacy/inputs/ember-hollow"
SURVIVAL_FIXTURE = "godot/legacy/inputs/ember-hollow"
UNIVERSE_FIXTURE = "src/stage_gen/recipes/universe/examples/lantern_ferry"
UNIVERSE_ADMITTED_FIXTURE = "tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json"

PLATFORMER_DOCUMENT = "docs/spec/game/generation-pipeline.md"
RUNNER_DOCUMENT = "docs/spec/game/runner.md"
UNIVERSE_DOCUMENT = "docs/spec/universe/generation-v1.md"
SURVIVAL_DOCUMENT = "docs/spec/survival/generation-v1.md"
STOREFRONT_DOCUMENT = "docs/spec/storefront/generation-v1.md"

PLATFORMER_CACHE_GOLDEN = "tests/unit/recipes/sideview_platformer/bellweather.cache-keys.json"
RUNNER_CACHE_GOLDEN = "tests/unit/recipes/sideview_runner/iron-petal-unit.cache-keys.json"
SURVIVAL_CACHE_GOLDEN = "tests/contract/fixtures/oblique_survival/ember-hollow.cache-keys.json"


def _state_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes() if path.is_file() else b"").hexdigest()


def _read_json(path: Path) -> object:
    if not path.is_file():
        return {"missing": path.name}
    return json.loads(path.read_text(encoding="utf-8"))


def _document_contract(path: Path, *, label: str | None = None) -> object:
    marker = "pipeline-graph-contract" + ("" if label is None else f":{label}")
    pattern = re.compile(
        rf"<!-- {re.escape(marker)}:start -->\s*```json\s*(.*?)\s*```\s*"
        rf"<!-- {re.escape(marker)}:end -->",
        re.DOTALL,
    )
    if not path.is_file():
        return {"missing": path.name, "label": label}
    matches = pattern.findall(path.read_text(encoding="utf-8"))
    if len(matches) != 1:
        return {"malformed": path.name, "label": label}
    return json.loads(matches[0])


def _resources(graph: Graph) -> list[dict[str, object]]:
    return [resource.model_dump(mode="json") for resource in graph.resources]


def _graph_field(graph: Graph, name: str) -> object:
    value = graph.model_dump(mode="json").get(name)
    if value is None:
        raise ValueError(f"graph {graph.kind} does not declare {name}")
    return value


def _graph_contract(
    graph: Graph,
    *,
    kind: str,
    fixture_ref: str,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "kind": kind,
        "fixture_ref": fixture_ref,
        **(extra or {}),
        "graph_schema_version": graph.schema_version,
        "topology_sha256": graph.topology_sha256,
        "node_count": len(graph.nodes),
        "terminal_node_id": graph.terminal_node_id,
        "operation_counts": graph.operation_counts(),
        "resources": _resources(graph),
    }


def _generated_check(
    *,
    check_id: str,
    relative_path: str,
    expected: object,
    observed: object,
) -> GeneratedModelPolicyFileSnapshotV1:
    path = REPOSITORY_ROOT / relative_path
    return GeneratedModelPolicyFileSnapshotV1(
        check_id=check_id,
        path=relative_path,
        expected_state_sha256=_state_sha256(expected),
        observed_state_sha256=_state_sha256(observed),
        file_sha256=_file_sha256(path),
    )


def _planned_graphs() -> tuple[dict[str, Graph], dict[str, dict[str, str]]]:
    """Build canonical graphs without reading env or constructing run services."""

    config = StageGenConfig()
    platformer = PreparedPackageExecutor(config).plan(REPOSITORY_ROOT / PLATFORMER_FIXTURE).graph
    runner = SideviewRunnerExecutor(config).plan(REPOSITORY_ROOT / RUNNER_FIXTURE).graph
    dialogue = DialogueSceneExecutor(config).plan(REPOSITORY_ROOT / DIALOGUE_FIXTURE).graph
    pointclick = PointClickRoomExecutor(config).plan(REPOSITORY_ROOT / POINTCLICK_FIXTURE).graph
    storefront = StorefrontExecutor(config).plan(REPOSITORY_ROOT / STOREFRONT_FIXTURE).graph

    survival_executor = ObliqueSurvivalExecutor(config)
    survival_graphs = {
        scope: survival_executor.plan(REPOSITORY_ROOT / SURVIVAL_FIXTURE, scope).graph
        for scope in SURVIVAL_SCOPES
    }

    universe_root = REPOSITORY_ROOT / UNIVERSE_FIXTURE
    universe = resolve_universe_source(read_universe_document(universe_root), root=universe_root)
    admitted = admitted_universe_from_document(
        REPOSITORY_ROOT / UNIVERSE_ADMITTED_FIXTURE,
        poster_sha256=universe.poster_sha256,
    )
    samples = resolve_sample_ledger(
        universe_id=admitted.universe_id,
        entity_ids=admitted.entity_ids(),
    )
    universe_semantic = build_universe_semantic_graph(
        universe,
        profile=universe_graph_profile(config, images=False),
    )
    universe_gallery = build_universe_gallery_graph(
        universe,
        admitted,
        samples=samples,
        profile=universe_graph_profile(config, images=True),
        config=config,
    )
    graphs: dict[str, Graph] = {
        "dialogue_scene": dialogue,
        "oblique_survival": survival_graphs["full"],
        "pointclick_room": pointclick,
        "sideview_platformer": platformer,
        "sideview_runner": runner,
        "storefront": storefront,
        "universe_gallery": universe_gallery,
        "universe_semantic": universe_semantic,
    }
    survival_cache_keys = {
        scope: {node.node_id: node.cache_key for node in graph.nodes}
        for scope, graph in survival_graphs.items()
    }
    return graphs, survival_cache_keys


def _generated_file_checks(
    graphs: dict[str, Graph],
    survival_cache_keys: dict[str, dict[str, str]],
) -> tuple[GeneratedModelPolicyFileSnapshotV1, ...]:
    platformer = graphs["sideview_platformer"]
    runner = graphs["sideview_runner"]
    semantic = graphs["universe_semantic"]
    gallery = graphs["universe_gallery"]
    survival = graphs["oblique_survival"]
    storefront = graphs["storefront"]

    document_checks: tuple[tuple[str, str, str | None, dict[str, object]], ...] = (
        (
            "platformer_graph_contract",
            PLATFORMER_DOCUMENT,
            None,
            _graph_contract(
                platformer,
                kind="prepared-game-execution-graph-contract-v1",
                fixture_ref=PLATFORMER_FIXTURE,
            ),
        ),
        (
            "runner_graph_contract",
            RUNNER_DOCUMENT,
            None,
            _graph_contract(
                runner,
                kind="sideview-runner-execution-graph-contract-v1",
                fixture_ref=RUNNER_FIXTURE,
            ),
        ),
        (
            "universe_semantic_graph_contract",
            UNIVERSE_DOCUMENT,
            "semantic",
            _graph_contract(
                semantic,
                kind="universe-semantic-execution-graph-contract-v1",
                fixture_ref=UNIVERSE_FIXTURE,
                extra={"phase": _graph_field(semantic, "phase")},
            ),
        ),
        (
            "universe_gallery_graph_contract",
            UNIVERSE_DOCUMENT,
            "gallery",
            _graph_contract(
                gallery,
                kind="universe-gallery-execution-graph-contract-v1",
                fixture_ref=UNIVERSE_FIXTURE,
                extra={
                    "admitted_ref": UNIVERSE_ADMITTED_FIXTURE,
                    "phase": _graph_field(gallery, "phase"),
                    "entity_count": _graph_field(gallery, "entity_count"),
                },
            ),
        ),
        (
            "oblique_survival_graph_contract",
            SURVIVAL_DOCUMENT,
            None,
            _graph_contract(
                survival,
                kind="oblique-survival-execution-graph-contract-v1",
                fixture_ref=SURVIVAL_FIXTURE,
                extra={"scope": _graph_field(survival, "scope")},
            ),
        ),
        (
            "storefront_graph_contract",
            STOREFRONT_DOCUMENT,
            None,
            _graph_contract(
                storefront,
                kind="storefront-execution-graph-contract-v1",
                fixture_ref=STOREFRONT_FIXTURE,
                extra={"surface_count": _graph_field(storefront, "surface_count")},
            ),
        ),
    )
    checks = [
        _generated_check(
            check_id=check_id,
            relative_path=path,
            expected=expected,
            observed=_document_contract(REPOSITORY_ROOT / path, label=label),
        )
        for check_id, path, label, expected in document_checks
    ]
    for check_id, relative_path, expected in (
        (
            "platformer_cache_keys",
            PLATFORMER_CACHE_GOLDEN,
            {node.node_id: node.cache_key for node in platformer.nodes},
        ),
        (
            "runner_cache_keys",
            RUNNER_CACHE_GOLDEN,
            {node.node_id: node.cache_key for node in runner.nodes},
        ),
        ("oblique_survival_cache_keys", SURVIVAL_CACHE_GOLDEN, survival_cache_keys),
    ):
        checks.append(
            _generated_check(
                check_id=check_id,
                relative_path=relative_path,
                expected=expected,
                observed=_read_json(REPOSITORY_ROOT / relative_path),
            )
        )
    return tuple(checks)


def build_snapshot() -> ModelPolicySnapshotV1:
    graphs, survival_cache_keys = _planned_graphs()
    policy_selections = {
        "default": image_workload_policies(),
        **{provider.value: image_workload_policies(provider) for provider in ImageProvider},
    }
    recipes = tuple(
        (
            recipe_id,
            {
                "dialogue_scene": DIALOGUE_FIXTURE,
                "oblique_survival": SURVIVAL_FIXTURE,
                "pointclick_room": POINTCLICK_FIXTURE,
                "sideview_platformer": PLATFORMER_FIXTURE,
                "sideview_runner": RUNNER_FIXTURE,
                "storefront": STOREFRONT_FIXTURE,
                "universe_gallery": UNIVERSE_FIXTURE,
                "universe_semantic": UNIVERSE_FIXTURE,
            }[recipe_id],
            graph,
        )
        for recipe_id, graph in graphs.items()
    )
    return build_model_policy_snapshot(
        catalog=IMAGE_ROUTE_CATALOG,
        policy_selections=policy_selections,
        recipes=recipes,
        generated_files=_generated_file_checks(graphs, survival_cache_keys),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite the active snapshot instead of only checking it",
    )
    args = parser.parse_args(argv)
    snapshot = build_snapshot()
    rendered = render_model_policy_snapshot(snapshot)
    relative = SNAPSHOT_PATH.relative_to(REPOSITORY_ROOT)
    stale_dependencies = [entry.check_id for entry in snapshot.generated_files if entry.stale]
    if args.write:
        atomic_write_text(SNAPSHOT_PATH, rendered, mode=0o644)
        print(f"wrote {relative}")
        if stale_dependencies:
            print("generated dependencies remain stale: " + ", ".join(stale_dependencies))
            return 1
        return 0
    if not SNAPSHOT_PATH.is_file() or SNAPSHOT_PATH.read_text(encoding="utf-8") != rendered:
        print(f"{relative} is stale; read the diff, then run with --write")
        return 1
    if stale_dependencies:
        print("generated dependencies are stale: " + ", ".join(stale_dependencies))
        return 1
    print(f"{relative} is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

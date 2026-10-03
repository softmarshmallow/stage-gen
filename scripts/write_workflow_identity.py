#!/usr/bin/env python3
"""Check or write the workflow identity golden: every identity a code move must not change.

tests/contract/fixtures/workflow-identity.json holds values only - digests, strings,
versions and cache keys - never a module path, so moving code changes this script's
imports and never the fixture. Each section prices what a change to it would cost:

  movie_sprite_sources     the digested movie-sprite sources and the three identities
                           create_pipeline derives from them (paid generate/finish keys)
  character_frozen_set     every character_3d member and the package-map aliases (a change
                           needs a paid qualification cohort, not a carry-over)
  identities               pipeline ids and their observed cache namespaces, graph-document
                           kinds, cache constants, the run-view version, provenance names
                           and the product node-type inventory
  cache_keys               node_id -> cache_key for offline plans over committed files or
                           the constant bytes in workflow-identity-inputs.json

The input bytes are constants captured once. Nothing here regenerates them with Pillow or
FFmpeg, runs a provider or reads a credential; configuration is an explicit empty
environment.

    uv run python scripts/write_workflow_identity.py --check
    uv run python scripts/write_workflow_identity.py --only identities
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, get_args

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import stage_gen
import stage_gen.components.movie_sprite as movie_sprite_component
import stage_gen.identity as provenance_identities
import stage_gen.workflows.looping_parallax.pipeline as looping_parallax_pipeline
import stage_gen.workflows.movie_sprite.pipeline as movie_sprite_pipeline
import stage_gen.workflows.universe.universe_types as universe_types
from gnode import (
    BindingTable,
    Graph,
    GraphBuilder,
    Node,
    NodeExecutionResult,
    NodeType,
    SoftwareIdentity,
    ViewArchetype,
    atomic_write_text,
    seal_graph,
)
from stage_gen.components.portrait_motion.face_location import locator_node_type
from stage_gen.components.portrait_motion.nodes import portrait_motion_node_types
from stage_gen.config import load_config
from stage_gen.interfaces.cli import parse
from stage_gen.pipeline import (
    InputFiles,
    NodeBinding,
    PipelineContext,
    PipelineDefinition,
    PipelineGraph,
    define,
    object_digest,
    plan,
    record_port,
    run,
)
from stage_gen.pipeline.dry_run import DRY_RUN_CACHE_NAMESPACE, DRY_RUN_CACHE_RECORD_KIND
from stage_gen.pipeline.graph_document import GraphDocument
from stage_gen.pipeline.node_cache import NODE_CACHE_SCHEMA_VERSION
from stage_gen.workflows.looping_parallax import ParallaxLayer, ParallaxSpec
from stage_gen.workflows.looping_parallax import create_pipeline as create_parallax_pipeline
from stage_gen.workflows.movie_sprite import create_pipeline as create_movie_sprite_pipeline
from stage_gen.workflows.movie_sprite.authoring import digest as movie_sprite_digest
from stage_gen.workflows.movie_sprite.cli import build_definition
from stage_gen.workflows.universe.universe_executor import UniverseExecutor
from stage_gen.workflows.universe.universe_graph import (
    UNIVERSE_CACHE_NAMESPACE,
    UNIVERSE_CACHE_RECORD_KIND,
    UniverseGraph,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPOSITORY_ROOT / "tests/contract/fixtures"
GOLDEN_PATH = FIXTURES / "workflow-identity.json"
INPUTS_PATH = FIXTURES / "workflow-identity-inputs.json"

PACKAGE_ROOT = Path(stage_gen.__file__).parent
UNIVERSE_INPUT = Path(universe_types.__file__).parent / "inputs/lantern_ferry"
#: Every package that holds character_3d members; their paths and bytes are frozen.
CHARACTER_OWNERS = ("recipes", "orchestration", "components", "providers", "resources")
#: Modules whose NodeType constants are product node types.
NODE_TYPE_MODULES: tuple[ModuleType, ...] = (
    looping_parallax_pipeline,
    movie_sprite_pipeline,
    universe_types,
)

type Section = dict[str, Any]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def movie_sprite_sources(scratch: Path) -> Section:
    """The digested sources, and the identities computed exactly as create_pipeline does."""
    del scratch
    pipeline_path = Path(movie_sprite_pipeline.__file__)
    authoring_path = pipeline_path.parent / "authoring.py"
    component_files = sorted(Path(movie_sprite_component.__file__).parent.glob("*.py"))
    return {
        "authoring.py": _sha256(authoring_path),
        "pipeline.py": _sha256(pipeline_path),
        "components": {item.name: _sha256(item) for item in component_files},
        "authoring_identity": movie_sprite_digest(authoring_path.read_bytes()),
        "recipe_identity": movie_sprite_digest(pipeline_path.read_bytes()),
        "processing_identity": object_digest(
            {item.name: movie_sprite_digest(item.read_bytes()) for item in component_files}
        ),
    }


def character_frozen_set(scratch: Path) -> Section:
    """Package-relative path -> sha256 for every member, plus the package-map aliases."""
    del scratch
    files: dict[str, str] = {}
    for owner in CHARACTER_OWNERS:
        root = PACKAGE_ROOT / owner / "character_3d"
        if not root.is_dir():
            raise ValueError(f"character_3d member root is missing: stage_gen/{owner}")
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store":
                files[f"stage_gen/{path.relative_to(PACKAGE_ROOT).as_posix()}"] = _sha256(path)
    package_map = json.loads(
        (PACKAGE_ROOT / "resources/character_3d/package-map.json").read_text(encoding="utf-8")
    )
    return {"files": files, "package_map_aliases": package_map["aliases"]}


PROBE = NodeType(
    "identity/namespace.probe", "Namespace probe", ViewArchetype.TRANSFORM, "local", "1"
)


def _observed_sdk_cache(pipeline_id: str, scratch: Path) -> tuple[str, str]:
    """Run one constant local node under ``pipeline_id`` and read what the cache wrote.

    The namespace and record kind are observed on disk rather than recomputed, so a change
    to how the SDK derives them fails here even though no constant names them.
    """

    def build(inputs: InputFiles) -> Graph:
        del inputs
        builder = GraphBuilder(profile=BindingTable(()))
        builder.add(
            PROBE,
            "probe",
            domain="identity",
            description="Publish one constant record",
            ports=(record_port("record", "probe.json", "identity-probe-v1"),),
        )
        return seal_graph(
            Graph,
            schema_version=1,
            kind="identity-probe-graph-v1",
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id="probe",
        )

    async def publish(node: Node, context: PipelineContext) -> NodeExecutionResult:
        return await context.publish(node, {"record": b"{}"})

    definition = define(
        pipeline_id, title="Identity probe", build=build, bindings=[NodeBinding(PROBE, publish)]
    )
    root = scratch / "probe" / pipeline_id
    (root / "inputs").mkdir(parents=True)
    planned = plan(definition, input_root=root / "inputs")
    result = asyncio.run(run(planned, output_root=root / "run", cache_root=root / "cache"))
    if not result.summary.ok:
        raise RuntimeError(f"the namespace probe failed for {pipeline_id}")
    (namespace,) = (root / "cache").iterdir()
    (record_path,) = namespace.rglob("record.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    return namespace.name, str(record["kind"])


def _parallax_definition() -> PipelineDefinition:
    """The committed supplied_layers example's spec, restated so example moves stay out."""
    return create_parallax_pipeline(
        ParallaxSpec(
            width=640,
            height=360,
            layers=[
                ParallaxLayer(
                    layer_id="distant_hills", source="distant_hills.png", order=0, parallax=0.2
                ),
                ParallaxLayer(
                    layer_id="near_trees", source="near_trees.png", order=1, parallax=0.7
                ),
            ],
        )
    )


def _graph_document(document: type[GraphDocument]) -> Section:
    (recipe,) = get_args(document.model_fields["recipe"].annotation)
    return {
        "recipe": recipe,
        "current_kind": document.CURRENT_KIND,
        "current_schema_version": document.CURRENT_SCHEMA_VERSION,
        "legacy_graph_identities": sorted(
            [version, kind] for version, kind in document.LEGACY_GRAPH_IDENTITIES
        ),
        "run_summary_kind": document.RUN_SUMMARY_KIND,
        "projection_kind": document.PROJECTION_KIND,
        "view_kind": document.VIEW_KIND,
    }


def _node_types() -> Iterable[NodeType]:
    for module in NODE_TYPE_MODULES:
        yield from (value for value in vars(module).values() if isinstance(value, NodeType))
    yield from portrait_motion_node_types()
    yield locator_node_type()


def identities(scratch: Path) -> Section:
    movie_sprite = create_movie_sprite_pipeline(
        finish_ref="finish.json", authoring_ref="authoring.json"
    )
    pipelines: dict[str, dict[str, str]] = {}
    for definition in (_parallax_definition(), movie_sprite):
        namespace, record_kind = _observed_sdk_cache(definition.pipeline_id, scratch)
        pipelines[definition.pipeline_id] = {"namespace": namespace, "record_kind": record_kind}
    graph_documents = {section["recipe"]: section for section in (_graph_document(UniverseGraph),)}
    inventory = {
        (node_type.type_id, node_type.cache_identity, node_type.contract_version)
        for node_type in _node_types()
    }
    software = {
        value.name: value.version
        for value in vars(provenance_identities).values()
        if isinstance(value, SoftwareIdentity)
    }
    return {
        "pipelines": pipelines,
        "graph_documents": graph_documents,
        "sdk_graph": {
            "kind": PipelineGraph.model_fields["kind"].default,
            "schema_version": PipelineGraph.model_fields["schema_version"].default,
            "run_summary_kind": PipelineGraph.RUN_SUMMARY_KIND,
            "projection_kind": PipelineGraph.PROJECTION_KIND,
            "view_kind": PipelineGraph.VIEW_KIND,
        },
        "cache": {
            "universe_namespace": UNIVERSE_CACHE_NAMESPACE,
            "universe_record_kind": UNIVERSE_CACHE_RECORD_KIND,
            "dry_run_namespace": DRY_RUN_CACHE_NAMESPACE,
            "dry_run_record_kind": DRY_RUN_CACHE_RECORD_KIND,
            "node_cache_schema_version": NODE_CACHE_SCHEMA_VERSION,
        },
        "view_schema_version": Graph.VIEW_SCHEMA_VERSION,
        "software_identities": dict(sorted(software.items())),
        "node_types": [list(entry) for entry in sorted(inventory)],
    }


def materialize_inputs(name: str, scratch: Path) -> Path:
    """Write one set of the constant input bytes into ``scratch`` and return its root."""
    encoded = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))[name]
    root = scratch / "inputs" / name
    for relative, data in encoded.items():
        parts = PurePosixPath(relative).parts
        if PurePosixPath(relative).is_absolute() or ".." in parts:
            raise ValueError(f"identity input escapes its root: {relative}")
        target = root.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(data, validate=True))
    return root


def plan_looping_parallax(scratch: Path) -> Graph:
    return plan(
        _parallax_definition(), input_root=materialize_inputs("looping-parallax", scratch)
    ).graph


def plan_movie_sprite_generate(scratch: Path) -> Graph:
    """The paid generate path, from argv through `stage-gen plan movie-sprite`, built by the
    one function that builds a movie-sprite definition from argv."""
    input_root = materialize_inputs("movie-sprite-generate", scratch)
    args = parse(
        [
            "plan",
            "movie-sprite",
            "--input",
            str(input_root),
            "--authoring",
            "authoring.json",
            "--finish",
            "finish.json",
            "--output",
            str(scratch / "movie-sprite-plan"),
        ]
    )
    return plan(build_definition(args), input_root=args.input_root, targets=[args.target]).graph


def plan_universe_semantic(scratch: Path) -> Graph:
    """The committed lantern_ferry package; the gallery phase needs a semantic run."""
    del scratch
    return UniverseExecutor(load_config(env={})).plan_semantic(UNIVERSE_INPUT).graph


#: Each pinned plan; the gallery phase is absent because it plans only from a semantic run.
CACHE_KEY_PLANS: dict[str, Callable[[Path], Graph]] = {
    "looping-parallax": plan_looping_parallax,
    "movie-sprite-generate": plan_movie_sprite_generate,
    "universe-semantic": plan_universe_semantic,
}


def cache_key_map(graph: Graph) -> dict[str, str]:
    return {node.node_id: node.cache_key for node in sorted(graph.nodes, key=lambda n: n.node_id)}


def cache_keys(scratch: Path) -> Section:
    return {name: cache_key_map(build(scratch / name)) for name, build in CACHE_KEY_PLANS.items()}


SECTIONS: dict[str, Callable[[Path], Section]] = {
    "movie_sprite_sources": movie_sprite_sources,
    "character_frozen_set": character_frozen_set,
    "identities": identities,
    "cache_keys": cache_keys,
}


def compute(names: Iterable[str]) -> dict[str, Section]:
    with tempfile.TemporaryDirectory(prefix="workflow-identity-") as scratch:
        return {name: SECTIONS[name](Path(scratch) / name) for name in names}


def render(sections: Mapping[str, Section]) -> str:
    return json.dumps(sections, indent=1, sort_keys=True) + "\n"


def differences(expected: object, actual: object, prefix: str = "") -> list[str]:
    """Dotted paths that differ between two JSON values; the whole failure message."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        lines: list[str] = []
        for key in sorted(set(expected) | set(actual), key=str):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in actual:
                lines.append(f"  removed {path}")
            elif key not in expected:
                lines.append(f"  added   {path}")
            else:
                lines.extend(differences(expected[key], actual[key], path))
        return lines
    if expected == actual:
        return []
    if isinstance(expected, list) and isinstance(actual, list):
        before = [json.dumps(item) for item in expected]
        after = [json.dumps(item) for item in actual]
        changed = [f"  removed {prefix} item {item}" for item in before if item not in after]
        changed += [f"  added   {prefix} item {item}" for item in after if item not in before]
        return changed or [f"  changed {prefix}: order or repetition"]
    return [f"  changed {prefix}: {json.dumps(expected)} -> {json.dumps(actual)}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="compare without writing")
    parser.add_argument("--only", choices=tuple(SECTIONS), help="check or rewrite one section")
    args = parser.parse_args(argv)
    names = (args.only,) if args.only else tuple(SECTIONS)
    actual = compute(names)
    pinned: dict[str, Section] = (
        json.loads(GOLDEN_PATH.read_text(encoding="utf-8")) if GOLDEN_PATH.is_file() else {}
    )
    if args.check:
        lines = [
            line
            for name in names
            for line in (
                differences(pinned[name], actual[name], name)
                if name in pinned
                else [f"  missing section {name}"]
            )
        ]
        for line in lines:
            print(line)
        if lines:
            print("workflow identity moved; read the diff before rewriting any section")
            return 1
        print("workflow identity is current")
        return 0
    atomic_write_text(GOLDEN_PATH, render({**pinned, **actual}), mode=0o644)
    print(f"wrote {', '.join(names)} to {GOLDEN_PATH.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

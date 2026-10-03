#!/usr/bin/env python3
"""Check or write the workflow identity golden: every identity a code move must not change.

tests/contract/fixtures/workflow-identity.json holds values only - digests, strings,
versions and cache keys - never a module path, so moving code changes this script's
imports and never the fixture. Each section prices what a change to it would cost:

  character_frozen_set     every character_3d member and the package-map aliases (a change
                           needs a paid qualification cohort, not a carry-over)
  identities               cache constants, the run-view version, provenance names and
                           the product node-type inventory
  cache_keys               node_id -> cache_key for offline plans and free runs over
                           committed files or the constant bytes in
                           workflow-identity-inputs.json, and the key of each paid call a
                           free run made through a stand-in that answers with constant bytes

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
import re
import runpy
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import stage_gen
import stage_gen.identity as provenance_identities
from gnode import (
    CallRecord,
    Graph,
    HostServices,
    JobLog,
    LongJob,
    NodeType,
    Route,
    RunView,
    SoftwareIdentity,
    WorkflowRun,
    atomic_write_text,
    plan_async,
    project_run,
)
from gnode import run as gnode_run
from stage_gen.pipeline import (
    PipelineGraph,
)
from stage_gen.pipeline.dry_run import DRY_RUN_CACHE_NAMESPACE, DRY_RUN_CACHE_RECORD_KIND
from stage_gen.pipeline.node_cache import NODE_CACHE_SCHEMA_VERSION
from stage_gen.workflows._gnode import GnodeWorkflow
from stage_gen.workflows._registry import discover

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPOSITORY_ROOT / "tests/contract/fixtures"
GOLDEN_PATH = FIXTURES / "workflow-identity.json"
INPUTS_PATH = FIXTURES / "workflow-identity-inputs.json"

PACKAGE_ROOT = Path(stage_gen.__file__).parent
UNIVERSE_INPUTS = PACKAGE_ROOT / "workflows/universe/inputs/lantern_ferry/inputs.yaml"
UNIVERSE_ANSWERS = FIXTURES / "universe/lantern_ferry.answers.json"
#: Every package that holds character_3d members; their paths and bytes are frozen.
CHARACTER_OWNERS = ("recipes", "orchestration", "components", "providers", "resources")
#: Modules whose NodeType constants are product node types.

type Section = dict[str, Any]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _node_types() -> Iterable[NodeType]:
    # A workflow file's steps, each titled and typed by the gnode type it uses.
    for workflow in discover():
        if workflow.root.joinpath("workflow.yaml").is_file():
            yield from GnodeWorkflow.read(workflow.package).types.values()


def identities(scratch: Path) -> Section:
    del scratch
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
        "sdk_graph": {
            "kind": PipelineGraph.model_fields["kind"].default,
            "schema_version": PipelineGraph.model_fields["schema_version"].default,
            "run_summary_kind": PipelineGraph.RUN_SUMMARY_KIND,
            "projection_kind": PipelineGraph.PROJECTION_KIND,
            "view_kind": PipelineGraph.VIEW_KIND,
        },
        "cache": {
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


#: The looping-parallax sample's placement over the constant layer bytes.
PARALLAX_INPUTS = {
    "canvas": {"width": 640, "height": 360},
    "layers": [
        {"layer_id": "distant_hills", "file": "distant_hills.png", "order": 0, "parallax": 0.2},
        {"layer_id": "near_trees", "file": "near_trees.png", "order": 1, "parallax": 0.7},
    ],
}


def run_looping_parallax(scratch: Path) -> RunView:
    """The sample run offline, free: every identity, downstream of results included."""
    root = materialize_inputs("looping-parallax", scratch)
    inputs = root / "inputs.yaml"
    inputs.write_text(json.dumps(PARALLAX_INPUTS), encoding="utf-8")
    project = scratch / "project"
    project.mkdir()
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    completed = gnode_run("looping-parallax", input_files=[inputs], cwd=project)
    if not completed.ok:
        raise RuntimeError(f"the looping-parallax sample failed: {completed.failed}")
    return project_run(completed.run_dir)


class _ConstantClip:
    """``video.generate`` answered with the constant clip, as a long job: never a provider."""

    def __init__(self, store: Any, clip: bytes) -> None:
        self.store, self.clip = store, clip

    def job(self) -> LongJob:
        async def start(route: Route, request: Any, take: int, log: JobLog) -> CallRecord:
            del route, request, take, log
            return CallRecord(
                {"video": self.store.put_bytes(self.clip, kind="video/mp4", name="video")},
                None,
                0.0,
            )

        async def collect(
            route: Route, request: Any, take: int, handle: Any, log: JobLog
        ) -> CallRecord:
            raise AssertionError("nothing was left to collect")

        return LongJob(start, collect)


def run_movie_sprite_take(scratch: Path) -> dict[str, str]:
    """The take path run offline, free: the paid take answered with a constant clip, so
    every step identity and the take's call key are pinned, finishing included."""
    root = materialize_inputs("movie-sprite-take", scratch)
    inputs = root / "take.yaml"
    inputs.write_text(
        json.dumps(
            {
                "character": "character.png",
                "seconds": 3,
                "resolution": "360p",
                "finish": "finish.json",
            }
        ),
        encoding="utf-8",
    )
    project = scratch / "project"
    project.mkdir()
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    planned = asyncio.run(plan_async("movie-sprite", input_files=[inputs], cwd=project))
    if not planned.ok:
        raise RuntimeError(f"the movie-sprite take does not plan: {planned.problems}")
    clip = _ConstantClip(planned.planner.store, (root / "take.mp4").read_bytes())
    services = HostServices(
        store=planned.planner.store, capabilities={"video.generate": clip.job()}, live=True
    )
    run_dir = project / "runs/take"
    outcome = asyncio.run(WorkflowRun(planned, run_dir=run_dir, services=services).run())
    if not outcome.ok:
        raise RuntimeError(f"the movie-sprite take failed: {outcome.failed}")
    keys = cache_key_map(project_run(run_dir))
    for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") == "call":
            keys[f"{event['id']} {event['capability']}"] = event["call"]
    return dict(sorted(keys.items()))


def _schema_title(location: str) -> str:
    return str(json.loads(Path(location).read_text(encoding="utf-8"))["title"])


def _universe_answers(store: Any) -> dict[str, Any]:
    """Every paid call of the lantern_ferry world, answered from committed constants."""

    answers = json.loads(UNIVERSE_ANSWERS.read_text(encoding="utf-8"))
    picture = base64.b64decode(answers["image_png_base64"])

    async def structured(route: Route, request: Any, take: int) -> CallRecord:
        del route, take
        title = _schema_title(request["schema"].location)
        answer = answers[title]
        if title in {"EntityDirection", "ImageReview"}:
            bound = re.search(r"(?:Bound|Required) entity_id: (\w+)", str(request["prompt"]))
            assert bound is not None, title
            answer = answer[bound[1]]
        return CallRecord({}, {"json": answer}, 0.0)

    async def image(route: Route, request: Any, take: int) -> CallRecord:
        del route, request, take
        return CallRecord(
            {"image": store.put_bytes(picture, kind="image/png", name="image")}, None, 0.0
        )

    return {"structured.generate": structured, "image.generate": image}


def run_universe(scratch: Path) -> dict[str, str]:
    """The committed lantern_ferry world, run free: every call answered from constants, so
    every step identity and every paid call's key is pinned, the gallery included."""
    project = scratch / "project"
    project.mkdir(parents=True)
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    planned = asyncio.run(plan_async("universe", input_files=[UNIVERSE_INPUTS], cwd=project))
    if not planned.ok:
        raise RuntimeError(f"the universe sample does not plan: {planned.problems}")
    store = planned.planner.store
    services = HostServices(store=store, capabilities=_universe_answers(store), live=True)
    run_dir = project / "runs/universe"
    outcome = asyncio.run(WorkflowRun(planned, run_dir=run_dir, services=services).run())
    if not outcome.ok:
        raise RuntimeError(f"the universe sample failed: {outcome.failed}")
    return _run_keys(run_dir)


#: Draws the portrait sample and answers its paid calls from the sample's own colours.
PORTRAIT_INPUTS_SCRIPT = PACKAGE_ROOT / "workflows/portrait_motion/inputs/make_inputs.py"


def run_portrait_motion(scratch: Path) -> dict[str, str]:
    """The face path run offline, free: every paid call answered by the sample's stand-in,
    so every step identity and every call's key is pinned, the reconstruction included."""
    root = materialize_inputs("portrait-motion", scratch)
    inputs = root / "face.yaml"
    inputs.write_text(
        json.dumps({"portrait": "sprite.png", "spec": "spec.json", "face_crop": True}),
        encoding="utf-8",
    )
    project = scratch / "project"
    project.mkdir()
    (project / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    planned = asyncio.run(plan_async("portrait-motion", input_files=[inputs], cwd=project))
    if not planned.ok:
        raise RuntimeError(f"the portrait sample does not plan: {planned.problems}")
    store = planned.planner.store
    stand_in = runpy.run_path(str(PORTRAIT_INPUTS_SCRIPT))["stand_in"]
    services = HostServices(store=store, capabilities=stand_in(store), live=True)
    run_dir = project / "runs/face"
    outcome = asyncio.run(WorkflowRun(planned, run_dir=run_dir, services=services).run())
    if not outcome.ok:
        raise RuntimeError(f"the portrait sample failed: {outcome.failed}")
    return _run_keys(run_dir)


def _run_keys(run_dir: Path) -> dict[str, str]:
    """Every finished step's identity, and every paid call's key, of one run."""
    keys = {
        node.node_id: node.cache_key
        for node in project_run(run_dir).nodes
        if node.state == "succeeded" and node.cache_key
    }
    for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") == "call":
            keys[f"{event['id']} {event['capability']}"] = event["call"]
    return dict(sorted(keys.items()))


#: Each pinned plan or free run.
CACHE_KEY_PLANS: dict[str, Callable[[Path], Graph | RunView | dict[str, str]]] = {
    "looping-parallax": run_looping_parallax,
    "movie-sprite-take": run_movie_sprite_take,
    "portrait-motion": run_portrait_motion,
    "universe": run_universe,
}


def cache_key_map(graph: Graph | RunView | dict[str, str]) -> dict[str, str]:
    if isinstance(graph, dict):
        return graph
    keys = {node.node_id: node.cache_key for node in graph.nodes}
    return dict(sorted(keys.items()))


def cache_keys(scratch: Path) -> Section:
    return {name: cache_key_map(build(scratch / name)) for name, build in CACHE_KEY_PLANS.items()}


SECTIONS: dict[str, Callable[[Path], Section]] = {
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

"""A workflow run, projected for the dashboard: ``plan.json`` and ``events.jsonl`` as one view.

The dashboard draws every run from one document (``gnode-run-view-v1``). For a workflow run
it is a pure projection of the run folder: the plan the run started from, the log of what
happened (instances a later phase or take added included), and the files the log names.
Nothing else enters it, so a copied run folder projects the same on any machine; reading
never writes, and a log cut short by a crash is read up to its last whole line.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gnode.graph import CacheDisposition, Graph, Resource, RetryOwner
from gnode.node_types import ViewArchetype
from gnode.view import (
    NodeState,
    RunState,
    RunView,
    RunViewArtifact,
    RunViewNode,
    artifact_media_type,
)
from gnode.workflow.folders import step_file, view_file
from gnode.workflow.values import FactsReader, FileValue, digest_of

PLAN_FILE = "plan.json"
EVENTS_FILE = "events.jsonl"

_DISPLAYS = (("image/", "image"), ("audio/", "audio"), ("video/", "video"), ("text/", "text"))
_ARCHETYPES = {
    "image": ViewArchetype.IMAGE,
    "structured": ViewArchetype.STRUCTURED,
    "vision": ViewArchetype.JUDGE,
    "video": ViewArchetype.VIDEO,
    "music": ViewArchetype.MUSIC,
    "sound": ViewArchetype.SOUND,
}
_FINISHED = frozenset({"node_finished", "node_failed", "node_skipped"})


class RunFolderError(ValueError):
    """A folder that is not a workflow run: no ``plan.json`` written by ``gnode run``."""


def is_workflow_run(run_dir: Path) -> bool:
    try:
        document = json.loads((run_dir / PLAN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(document, dict) and document.get("gnode") == "graph/v2"


def read_plan(run_dir: Path) -> dict[str, Any]:
    if not is_workflow_run(run_dir):
        raise RunFolderError(f"{run_dir} is not a gnode workflow run")
    document: dict[str, Any] = json.loads((run_dir / PLAN_FILE).read_text(encoding="utf-8"))
    return document


def read_events(run_dir: Path) -> list[dict[str, Any]]:
    """Every whole event in the log, in order; a torn last line is left unread."""

    path = run_dir / EVENTS_FILE
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            break
        if isinstance(event, dict):
            events.append(event)
    return events


def _run_state(events: list[dict[str, Any]]) -> RunState:
    state: RunState = "planned"
    for event in events:
        name = event.get("event")
        if name == "run_started":
            state = "unfinished"
        elif name == "run_finished":
            state = "succeeded" if event.get("ok") else "failed"
        elif name == "run_canceled":
            state = "canceled"
    return state


def _resource(route: str | None) -> str:
    if route is None:
        return "local"
    text = "".join(c if c.isalnum() else "." for c in route.lower())
    return ".".join(part for part in text.split(".") if part) or "route"


def _media_type(kind: str, artifact_ref: str) -> str:
    if "/" in kind:
        return kind
    return artifact_media_type(artifact_ref)


def _display(media_type: str) -> str:
    for prefix, display in _DISPLAYS:
        if media_type.startswith(prefix):
            return display
    return "data"


def _files(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    if "file" in value:
        return [value["file"]]
    if "collection" in value:
        return [file for _, item in value["collection"] for file in _files(item)]
    if "list" in value:
        return [file for item in value["list"] for file in _files(item)]
    return []


def _artifacts(run_dir: Path, path: str, outputs: Mapping[str, Any]) -> list[RunViewArtifact]:
    artifacts: list[RunViewArtifact] = []
    for port, value in outputs.items():
        files = _files(value)
        for index, file in enumerate(files):
            ref = step_file(
                path, port, file["kind"], key=file.get("key"), index=index, count=len(files)
            )
            media_type = _media_type(file["kind"], ref)
            artifacts.append(
                RunViewArtifact(
                    artifact_ref=ref,
                    sha256=file["digest"],
                    bytes=file["size"],
                    media_type=media_type,
                    present=(run_dir / ref).is_file(),
                    display=_display(media_type),
                )
            )
    return artifacts


def _archetype(entry: Mapping[str, Any]) -> ViewArchetype:
    if entry.get("judges"):
        return ViewArchetype.JUDGE
    for capability in entry.get("routes", {}):
        found = _ARCHETYPES.get(str(capability).split(".", 1)[0])
        if found is not None:
            return found
    return ViewArchetype.TRANSFORM


def project_run(run_dir: Path) -> RunView:
    """The run's view: every instance the plan or the log names, in that order."""

    plan = read_plan(run_dir)
    events = read_events(run_dir)
    run_state = _run_state(events)
    ended = run_state in {"succeeded", "failed", "canceled"}
    steps: Mapping[str, Mapping[str, Any]] = plan.get("steps", {})
    workflow_id = str(plan.get("workflow", {}).get("id", "workflow"))

    entries: dict[str, dict[str, Any]] = {}
    for instance in plan.get("instances", []):
        if instance.get("state") != "absent":
            entries[instance["id"]] = dict(instance)
    last: dict[str, dict[str, Any]] = {}
    calls: dict[str, list[dict[str, Any]]] = {}
    invocation_id: str | None = None
    for event in events:
        name = event.get("event")
        if name == "run_started":
            invocation_id = event.get("invocation_id")
        identifier = event.get("id")
        if not isinstance(identifier, str):
            continue
        if name == "node_started":
            entry = entries.setdefault(identifier, {"id": identifier})
            for field in ("path", "step", "uses", "take", "identity", "reads", "routes"):
                if field in event:
                    entry[field] = event[field]
            last[identifier] = event
        elif name in _FINISHED:
            last[identifier] = event
        elif name == "call":
            calls.setdefault(identifier, []).append(event)

    nodes: list[RunViewNode] = []
    resources: dict[str, Resource] = {}
    for identifier, entry in entries.items():
        routes: dict[str, str] = dict(entry.get("routes", {}))
        route = next(iter(routes.values()), None)
        model, _, provider = (route or "").rpartition("@")
        resource_id = _resource(route)
        resources.setdefault(
            resource_id, Resource(resource_id=resource_id, rate_limit_owner="none")
        )
        final: Mapping[str, Any] = last.get(identifier) or {}
        name = final.get("event")
        state: NodeState
        error: str | None = None
        if name == "node_finished":
            state = "succeeded"
        elif name in {"node_failed", "node_skipped"}:
            state = "failed" if name == "node_failed" else "skipped"
            error = final.get("error") or final.get("reason")
        elif name == "node_started":
            state = "failed" if ended else "running"
            error = "the run ended before this step finished" if ended else None
        elif entry.get("state") == "done":
            state = "succeeded"
        else:
            state = "skipped" if ended else "pending"
            error = entry.get("reason")
        terminal = name in _FINISHED
        made = [call for call in calls.get(identifier, []) if not call.get("cached")]
        costs = [call.get("cost_usd") for call in made]
        known_cost = (
            round(sum(float(cost) for cost in costs if cost is not None), 6)
            if route is not None and all(cost is not None for cost in costs)
            else None
        )
        step = steps.get(str(entry.get("step", "")), {})
        path = str(entry.get("path", identifier))
        price = entry.get("price", {})
        identity = entry.get("identity")
        cache = final.get("cache") if name == "node_finished" else None
        nodes.append(
            RunViewNode(
                node_id=identifier,
                type_id=str(entry.get("uses", "")),
                title=step.get("title") or path.rsplit(".", 1)[-1],
                archetype=_archetype(entry),
                domain=workflow_id,
                description=step.get("description") or f"{entry.get('uses', 'step')} at {path}",
                depends_on=tuple(dep for dep in entry.get("reads", []) if dep in entries),
                operation="local" if route is None else next(iter(routes)),
                resource_id=resource_id,
                provider=provider or None,
                model=model or None,
                retry_owner=RetryOwner.NONE if route is None else RetryOwner.COMPONENT,
                max_attempts=1 if route is None else 6,
                cache_key=identity
                if isinstance(identity, str) and len(identity) == 64
                else hashlib.sha256(identifier.encode()).hexdigest(),
                estimated_duration_seconds=0.0,
                estimated_cost_low_usd=float(price.get("low_usd", 0.0)),
                estimated_cost_high_usd=float(price.get("high_usd", 0.0)),
                state=state,
                ended_offset_ms=final.get("offset_ms") if terminal else None,
                duration_ms=final.get("duration_ms") if terminal else None,
                cache=CacheDisposition(cache) if cache in {"hit", "miss"} else None,
                provider_operations=len(made) if route is not None else None,
                known_cost_usd=known_cost,
                error=str(error)[:2_000] if error else None,
                artifacts=tuple(_artifacts(run_dir, path, final.get("outputs", {})))
                if name == "node_finished"
                else (),
            )
        )

    finished = [event for event in events if event.get("event") == "run_finished"]
    log = run_dir / EVENTS_FILE
    return RunView(
        schema_version=Graph.VIEW_SCHEMA_VERSION,
        kind=Graph.VIEW_KIND,
        graph_sha256=str(plan.get("plan") or digest_of(plan)),
        topology_sha256=digest_of(
            sorted([node.node_id, sorted(node.depends_on)] for node in nodes)
        ),
        invocation_id=invocation_id,
        run_state=run_state,
        trace_modified_at=datetime.fromtimestamp(log.stat().st_mtime, UTC).isoformat()
        if log.is_file()
        else None,
        duration_ms=finished[-1].get("offset_ms") if finished else None,
        known_cost_usd=finished[-1].get("charged_usd") if finished else None,
        state_counts=dict(sorted(Counter(node.state for node in nodes).items())),
        resources=tuple(sorted(resources.values(), key=lambda r: r.resource_id)),
        nodes=tuple(nodes),
    )


VIEW_CONTEXT_KIND = "gnode-view-context-v1"
#: A JSON file a view shows is inlined up to this size; past it the view reads its URL.
INLINE_JSON_BYTES = 256 * 1024


def _context_value(
    run_dir: Path, value: Mapping[str, Any], facts_reader: FactsReader | None
) -> Any:
    if "file" in value:
        file = value["file"]
        ref = view_file(file["digest"], file["kind"])
        path = run_dir / ref
        found: dict[str, Any] = {
            "kind": file["kind"],
            "digest": file["digest"],
            "size": file["size"],
            "key": file.get("key"),
            "ref": ref,
            "facts": {},
        }
        if facts_reader is not None and path.is_file():
            measured = FileValue(
                digest=file["digest"],
                kind=file["kind"],
                name=file.get("name", ref),
                size=file["size"],
                location=str(path),
            )
            found["facts"] = dict(facts_reader(measured))
        if file["kind"] == "json" and file["size"] <= INLINE_JSON_BYTES and path.is_file():
            found["value"] = json.loads(path.read_text(encoding="utf-8"))
        return found
    if "collection" in value:
        return {
            key: _context_value(run_dir, item, facts_reader) for key, item in value["collection"]
        }
    if "list" in value:
        return [_context_value(run_dir, item, facts_reader) for item in value["list"]]
    if value.get("none"):
        return None
    return value.get("value")


def _holds_files(value: Mapping[str, Any]) -> bool:
    if "file" in value:
        return True
    items = [item for _, item in value.get("collection", [])] + list(value.get("list", []))
    return bool(items) and all(_holds_files(item) for item in items)


_SEGMENT = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_-]*)(?:\[(?P<key>'(?:[^'\\]|\\.)*')\])?")


def _path_parts(path: str) -> list[tuple[str, str | None]]:
    """``entity['bellwright'].draw`` as ``[("entity", "bellwright"), ("draw", None)]``."""

    parts: list[tuple[str, str | None]] = []
    position = 0
    while position < len(path):
        match = _SEGMENT.match(path, position)
        if match is None:
            return [(path, None)]
        key = match["key"]
        unquoted = None if key is None else re.sub(r"\\(.)", r"\1", key[1:-1])
        parts.append((match["name"], unquoted))
        position = match.end()
        if position < len(path):
            if path[position] != ".":
                return [(path, None)]
            position += 1
    return parts


def _place_step(tree: dict[str, Any], path: str, entry: dict[str, Any]) -> None:
    """File one step's entry under its groups: a repeat holds ``instances`` by key."""

    node = tree
    parts = _path_parts(path)
    for name, key in parts[:-1]:
        if key is None:
            node = node.setdefault(name, {"steps": {}})["steps"]
            continue
        instances = node.setdefault(name, {"instances": []})["instances"]
        instance = next((i for i in instances if i["key"] == key), None)
        if instance is None:
            instance = {"key": key, "status": "succeeded", "steps": {}}
            instances.append(instance)
        if entry["status"] != "succeeded":
            instance["status"] = entry["status"]
        node = instance["steps"]
    name, key = parts[-1]
    if key is None:
        node[name] = entry
        return
    instances = node.setdefault(name, {"instances": []})["instances"]
    instances[:] = [i for i in instances if i["key"] != key]
    instances.append({"key": key, **entry})


def _workflow_context(
    run_dir: Path,
    plan: Mapping[str, Any],
    events: list[dict[str, Any]],
    run: Mapping[str, Any],
    facts_reader: FactsReader | None,
) -> dict[str, Any]:
    """The whole run, as a workflow's own view reads it: every step by name, and outputs."""

    declared: Mapping[str, Mapping[str, Any]] = plan.get("steps", {})
    started: dict[str, Mapping[str, Any]] = {}
    tree: dict[str, Any] = {}
    statuses = {"node_finished": "succeeded", "node_failed": "failed", "node_skipped": "skipped"}
    for event in events:
        name = event.get("event")
        identifier = event.get("id")
        if name == "node_started" and isinstance(identifier, str):
            started[identifier] = event
        if name not in statuses or not isinstance(identifier, str):
            continue
        start = started.get(identifier, {})
        path = str(event.get("path", identifier))
        step = declared.get(str(start.get("step", "")), {})
        takes = start.get("take") or [1]
        _place_step(
            tree,
            path,
            {
                "path": path,
                "title": step.get("title") or path.rsplit(".", 1)[-1],
                "status": statuses[name],
                "take": takes[-1],
                "facts": event.get("facts", {}),
                "outputs": {
                    output: _context_value(run_dir, value, facts_reader)
                    for output, value in event.get("outputs", {}).items()
                },
            },
        )
    finished = [event for event in events if event.get("event") == "run_finished"]
    outputs = finished[-1].get("outputs", {}) if finished else {}
    return {
        "kind": VIEW_CONTEXT_KIND,
        "scope": "workflow",
        "node_id": None,
        "template": plan["view"],
        "steps": tree,
        "outputs": {
            name: _context_value(run_dir, value, facts_reader) for name, value in outputs.items()
        },
        "run": run,
    }


def view_contexts(
    run_dir: Path, *, facts_reader: FactsReader | None = None
) -> list[dict[str, Any]]:
    """Each finished step with a view, as its view reads it (``gnode-view-context-v1``),
    then the whole run, when the workflow has a view of its own (``scope: workflow``).

    ``step`` is the step: its path, title, status, take, cost and every resolved ``with``
    value; ``inputs`` are the files among them and ``outputs`` the files it made, each
    ``{kind, digest, size, key, ref, facts}`` (``ref`` is where the run folder keeps it for
    the view; a host adds its ``url``), a small JSON file with its parsed ``value``;
    ``facts`` are the step's facts and ``run`` the run it belongs to.
    """

    plan = read_plan(run_dir)
    events = read_events(run_dir)
    steps: Mapping[str, Mapping[str, Any]] = plan.get("steps", {})
    started: dict[str, dict[str, Any]] = {}
    shown: dict[str, dict[str, Any]] = {}
    spent: dict[str, float] = {}
    for event in events:
        identifier = event.get("id")
        if not isinstance(identifier, str):
            continue
        if event.get("event") == "node_started":
            started[identifier] = event
            shown.pop(identifier, None)
        elif event.get("event") == "node_finished" and isinstance(event.get("view"), str):
            shown[identifier] = event
        elif event.get("event") == "call" and isinstance(event.get("cost_usd"), int | float):
            spent[identifier] = spent.get(identifier, 0.0) + float(event["cost_usd"])
    finished = [event for event in events if event.get("event") == "run_finished"]
    run = {
        "id": run_dir.name,
        "workflow": plan.get("workflow", {}).get("id"),
        "status": _run_state(events),
        "cost_usd": finished[-1].get("charged_usd") if finished else None,
    }
    contexts = []
    for identifier, done in shown.items():
        start = started.get(identifier, {})
        declared = steps.get(str(start.get("step", "")), {})
        path = str(done.get("path", identifier))
        given = start.get("with", {})
        contexts.append(
            {
                "kind": VIEW_CONTEXT_KIND,
                "scope": "node",
                "node_id": identifier,
                "template": done["view"],
                "step": {
                    "path": path,
                    "step": start.get("step"),
                    "title": declared.get("title") or path.rsplit(".", 1)[-1],
                    "status": "succeeded",
                    "take": start.get("take", [1])[-1] if start.get("take") else 1,
                    "cost_usd": round(spent.get(identifier, 0.0), 6),
                    "with": {
                        name: _context_value(run_dir, value, facts_reader)
                        for name, value in given.items()
                    },
                },
                "inputs": {
                    name: _context_value(run_dir, value, facts_reader)
                    for name, value in given.items()
                    if _holds_files(value)
                },
                "outputs": {
                    name: _context_value(run_dir, value, facts_reader)
                    for name, value in done.get("outputs", {}).items()
                },
                "facts": done.get("facts", {}),
                "run": run,
            }
        )
    if isinstance(plan.get("view"), str):
        contexts.append(_workflow_context(run_dir, plan, events, run, facts_reader))
    return contexts


def verify_run(run_dir: Path) -> list[str]:
    """Every file the log names, checked in the run folder against its recorded digest."""

    problems: list[str] = []
    for node in project_run(run_dir).nodes:
        for artifact in node.artifacts:
            path = run_dir / artifact.artifact_ref
            if not path.is_file():
                problems.append(f"{node.node_id}: {artifact.artifact_ref} is missing")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
                problems.append(
                    f"{node.node_id}: {artifact.artifact_ref} differs from its recorded digest"
                )
    return problems


__all__ = [
    "INLINE_JSON_BYTES",
    "VIEW_CONTEXT_KIND",
    "RunFolderError",
    "is_workflow_run",
    "project_run",
    "read_events",
    "read_plan",
    "verify_run",
    "view_contexts",
]

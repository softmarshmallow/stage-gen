"""The JSON Schemas of gnode's documents: what any other implementation must read and write.

Every document crosses a language boundary, so each has a published schema, versioned by
name. The authored documents (workflow, project) come from their models; the rest are
written here. ``scripts/write_gnode_schemas.py`` keeps ``src/gnode/schemas/`` current.
"""

from __future__ import annotations

from typing import Any

from gnode.workflow.document import ProjectDocument, WorkflowDocument

DRAFT = "https://json-schema.org/draft/2020-12/schema"
SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
MONEY = {"type": "number", "minimum": 0}
TAKES = {"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 1}


def _with_head(name: str, title: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"$schema": DRAFT, "$id": f"urn:gnode:schema:{name}", "title": title, **schema}


def workflow_schema() -> dict[str, Any]:
    return _with_head(
        "gnode-workflow-v1",
        "gnode workflow file (gnode: workflow/v1)",
        WorkflowDocument.model_json_schema(by_alias=True, mode="validation"),
    )


def project_schema() -> dict[str, Any]:
    return _with_head(
        "gnode-project-v1",
        "gnode project file, gnode.yaml (gnode: project/v1)",
        ProjectDocument.model_json_schema(by_alias=True, mode="validation"),
    )


def takes_schema() -> dict[str, Any]:
    return _with_head(
        "gnode-takes-v1",
        "gnode takes file: the take each step path uses, written by reroll and pick",
        {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["take"],
                "additionalProperties": False,
                "properties": {
                    "take": {"type": "integer", "minimum": 1},
                    "result": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                },
            },
        },
    )


def routes_schema() -> dict[str, Any]:
    price = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "low_usd": MONEY,
            "high_usd": MONEY,
            "usd": MONEY,
            "unit": {"enum": ["call", "1k_chars", "second"]},
            "max_units": {"type": "number", "exclusiveMinimum": 0},
        },
    }
    return _with_head(
        "gnode-routes-v1",
        "gnode route catalog: which model serves a capability, its price and features",
        {
            "type": "object",
            "required": ["gnode", "routes"],
            "properties": {
                "gnode": {"const": "routes/v1"},
                "routes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["capability", "route", "price"],
                        "additionalProperties": False,
                        "properties": {
                            "capability": {"type": "string"},
                            "route": {"type": "string", "pattern": "^.+@[a-z0-9._-]+$"},
                            "price": price,
                            "features": {"type": "array", "items": {"type": "string"}},
                            "concurrency": {"type": "integer", "minimum": 1},
                            "requests_per_minute": {"type": "integer", "minimum": 1},
                            "contract": {"type": "object"},
                        },
                    },
                },
            },
        },
    )


_STATE = {"enum": ["planned", "maybe", "absent", "blocked", "failed", "done"]}


def graph_schema() -> dict[str, Any]:
    instance = {
        "type": "object",
        "required": ["id", "path", "step", "take", "uses", "state", "identity", "phase"],
        "properties": {
            "id": {"type": "string"},
            "path": {"type": "string"},
            "step": {"type": "string"},
            "take": TAKES,
            "uses": {"type": "string"},
            "state": _STATE,
            "identity": {"anyOf": [SHA256, {"type": "null"}]},
            "phase": {"type": "integer", "minimum": 1},
            "key": {"type": ["string", "null"]},
            "judges": {"type": ["string", "null"]},
            "judged_by": {"type": "array", "items": {"type": "string"}},
            "waiting_on": {"type": "array", "items": {"type": "string"}},
            "needs": {"type": "array", "items": {"type": "string"}},
            "reads": {
                "description": "the instances it reads or waits on: its upstream in the graph",
                "type": "array",
                "items": {"type": "string"},
            },
            "routes": {"type": "object", "additionalProperties": {"type": "string"}},
            "price": {
                "type": "object",
                "properties": {"low_usd": MONEY, "high_usd": MONEY},
            },
            "view": {"type": ["boolean", "string"]},
            "reason": {"type": "string"},
        },
    }
    return _with_head(
        "gnode-graph-v2",
        "gnode expanded graph: every step instance with its wiring, identity, state and price",
        {
            "type": "object",
            "required": ["gnode", "instances"],
            "properties": {
                "gnode": {"const": "graph/v2"},
                "workflow": {},
                "steps": {
                    "description": "each declared step, by its path, as a reader sees it",
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "title": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                            "uses": {"type": ["string", "null"]},
                            "view": {"type": ["boolean", "string"]},
                        },
                    },
                },
                "plan": SHA256,
                "view_origins": {"type": "array", "items": {"type": "string"}},
                "inputs": {},
                "instances": {"type": "array", "items": instance},
                "pending": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["path", "max", "phase"],
                        "properties": {
                            "path": {"type": "string"},
                            "max": {"type": "integer", "minimum": 1},
                            "phase": {"type": "integer", "minimum": 1},
                            "high_usd": MONEY,
                        },
                    },
                },
                "estimate": {"type": "object"},
                "problems": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["where", "message"],
                        "properties": {
                            "where": {"type": "string"},
                            "message": {"type": "string"},
                        },
                    },
                },
            },
        },
    )


def events_schema() -> dict[str, Any]:
    """One line of a run's ``events.jsonl``: a common envelope, then the event's own fields."""

    names = [
        "run_started",
        "run_finished",
        "run_canceled",
        "phase_planned",
        "node_started",
        "node_finished",
        "node_failed",
        "node_skipped",
        "node_retry",
        "call",
        "budget_reserved",
        "budget_settled",
        "budget_refused",
        "problem",
    ]
    return _with_head(
        "gnode-run-events-v1",
        "gnode run record: one event per line of events.jsonl, oldest first",
        {
            "type": "object",
            "required": [
                "schema_version",
                "kind",
                "event",
                "invocation_id",
                "graph_sha256",
                "offset_ms",
            ],
            "properties": {
                "schema_version": {"const": 1},
                "kind": {"const": "gnode-run-events-v1"},
                "event": {"enum": names},
                "invocation_id": {"type": "string"},
                "graph_sha256": SHA256,
                "offset_ms": {"type": "integer", "minimum": 0},
                "id": {"type": "string"},
                "path": {"type": "string"},
                "take": TAKES,
                "identity": {"anyOf": [SHA256, {"type": "null"}]},
                "cache": {"enum": ["hit", "miss"]},
                "outputs": {"type": "object"},
                "facts": {"type": "object"},
                "error": {"type": ["string", "null"]},
                "charged_usd": MONEY,
                "amount_usd": MONEY,
            },
        },
    )


def protocol_schema() -> dict[str, Any]:
    """What the engine sends a node body, what the body may call back for, what it returns."""

    file = {
        "type": "object",
        "required": ["path", "kind", "digest"],
        "properties": {
            "path": {"type": "string"},
            "kind": {"type": "string"},
            "digest": SHA256,
            "key": {"type": ["string", "null"]},
            "facts": {"type": "object"},
        },
    }
    staged: dict[str, Any] = {
        "anyOf": [
            file,
            {"type": "array", "items": file},
            {"type": "object", "additionalProperties": file},
            {"type": "null"},
        ]
    }
    return _with_head(
        "gnode-node-protocol-v1",
        "gnode node protocol: request, callbacks and response of one node body",
        {
            "$defs": {
                "request": {
                    "type": "object",
                    "required": ["instance", "type", "params", "inputs"],
                    "properties": {
                        "instance": {"type": "string"},
                        "type": {"type": "string"},
                        "take": {"type": "integer", "minimum": 1},
                        "params": {"type": "object"},
                        "inputs": {"type": "object", "additionalProperties": staged},
                        "work_dir": {"type": "string"},
                    },
                },
                "callback": {
                    "type": "object",
                    "required": ["call"],
                    "properties": {
                        "call": {"enum": ["capability", "fact", "annotate", "progress", "tool"]},
                        "capability": {"type": "string"},
                        "request": {"type": "object"},
                        "name": {"type": "string"},
                        "value": {},
                    },
                },
                "response": {
                    "type": "object",
                    "required": ["outputs"],
                    "properties": {
                        "outputs": {"type": "object"},
                        "failure": {"type": "string"},
                    },
                },
            },
            "oneOf": [
                {"$ref": "#/$defs/request"},
                {"$ref": "#/$defs/callback"},
                {"$ref": "#/$defs/response"},
            ],
        },
    )


def annotations_schema() -> dict[str, Any]:
    point = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
    return _with_head(
        "gnode-annotations-v1",
        "gnode annotations: a list of marks on an image; what they mean is the prompt's",
        {
            "type": "object",
            "required": ["kind", "annotations"],
            "properties": {
                "kind": {"const": "gnode-annotations-v1"},
                "annotations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "shape": {"enum": ["point", "points", "box"]},
                            "at": point,
                            "points": {"type": "array", "items": point, "minItems": 2},
                            "closed": {"type": "boolean"},
                            "box": {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 4,
                                "maxItems": 4,
                            },
                            "label": {"type": "string"},
                            "color": {"type": "string"},
                            "tag": {"type": "string"},
                        },
                    },
                },
            },
        },
    )


def view_context_schema() -> dict[str, Any]:
    """What a view template receives: the step it shows and its run, read-only.

    A host adds each file's ``url`` before handing the context over; ``ref`` is where the
    run folder keeps the file for the view, so a copied run still shows it.
    """

    file = {
        "type": "object",
        "required": ["kind", "digest", "ref"],
        "properties": {
            "kind": {"type": "string"},
            "digest": SHA256,
            "size": {"type": "integer", "minimum": 0},
            "key": {"type": ["string", "null"]},
            "ref": {"type": "string", "pattern": "^views/files/[0-9a-f]{64}(\\.[a-z0-9]+)?$"},
            "url": {"type": "string"},
            "facts": {"type": "object"},
            "value": {},
        },
    }
    return _with_head(
        "gnode-view-context-v1",
        "gnode view context: what a step's view reads, as `context()` returns it",
        {
            "type": "object",
            "required": ["kind", "scope", "node_id", "template", "step", "inputs", "outputs"],
            "properties": {
                "kind": {"const": "gnode-view-context-v1"},
                "scope": {"const": "node"},
                "node_id": {"type": "string"},
                "template": {"type": "string", "pattern": "^views/[0-9a-f]{64}\\.html$"},
                "step": {
                    "type": "object",
                    "required": ["path", "title", "status"],
                    "properties": {
                        "path": {"type": "string"},
                        "step": {"type": ["string", "null"]},
                        "title": {"type": "string"},
                        "status": {"type": "string"},
                        "take": {"type": "integer", "minimum": 1},
                        "cost_usd": MONEY,
                        "with": {"type": "object"},
                    },
                },
                "inputs": {"type": "object"},
                "outputs": {"type": "object"},
                "facts": {"type": "object"},
                "run": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "workflow": {"type": ["string", "null"]},
                        "status": {"type": "string"},
                        "cost_usd": {"anyOf": [MONEY, {"type": "null"}]},
                    },
                },
            },
            "$defs": {"file": file},
        },
    )


def all_schemas() -> dict[str, dict[str, Any]]:
    """Every published schema, by file name."""

    return {
        "gnode-workflow-v1.schema.json": workflow_schema(),
        "gnode-project-v1.schema.json": project_schema(),
        "gnode-takes-v1.schema.json": takes_schema(),
        "gnode-routes-v1.schema.json": routes_schema(),
        "gnode-graph-v2.schema.json": graph_schema(),
        "gnode-run-events-v1.schema.json": events_schema(),
        "gnode-node-protocol-v1.schema.json": protocol_schema(),
        "gnode-annotations-v1.schema.json": annotations_schema(),
        "gnode-view-context-v1.schema.json": view_context_schema(),
    }


__all__ = ["all_schemas"]

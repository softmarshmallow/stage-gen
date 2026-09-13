"""Current compiled Scenario program admission, without execution or host effects."""

from __future__ import annotations

from typing import Any

from .catalog import Catalog
from .validation import ScenarioError, json_value, logical_id, validate_value

NODE_FIELDS = {
    "line": {
        "text",
        "text_key",
        "speaker",
        "expression",
        "presentation",
        "cues",
        "next",
        "gates",
        "advance_mode",
    },
    "choice": {
        "options",
        "text",
        "text_key",
        "speaker",
        "expression",
        "presentation",
        "cues",
        "gates",
    },
    "branch": {"edges", "default"},
    "set": {"values", "next"},
    "jump": {"target"},
    "effect": {"effect", "instance_id", "target", "scope", "duration", "clock", "next"},
    "stop": {"instance_id", "next"},
    "wait": {"duration", "clock", "operation", "event", "next"},
    "end": {"outcome"},
}
EFFECT_FIELDS = {"effect", "instance_id", "target", "scope", "duration", "clock"}
CLOCKS = {"sequence", "presentation", "reading"}


def admit_program(document: Any, catalog: Catalog) -> dict[str, Any]:
    """Validate the closed wire shape and all reachable names before activation.

    All declared nodes must be reachable and an ending must be reachable. Cycles
    formed solely from instructions that cannot suspend are refused. This is a
    conservative structural guarantee, not a proof of host effect completion.
    """

    data = json_value(document, "program")
    if not isinstance(data, dict):
        raise ScenarioError("program: expected an object")
    expected = {
        "kind",
        "schema_version",
        "scenario_id",
        "entry",
        "nodes",
        "speakers",
        "facts",
        "required_capabilities",
        "source_map",
        "metadata",
    }
    if set(data) - expected:
        raise ScenarioError(f"program: unknown fields {sorted(set(data) - expected)}")
    if (
        data.get("kind") != "scenario-program-v3"
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != 3
    ):
        raise ScenarioError("program: expected scenario-program-v3 schema_version 3")
    logical_id(data.get("scenario_id"), "program.scenario_id")
    entry = logical_id(data.get("entry"), "program.entry")
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes or len(nodes) > 10000:
        raise ScenarioError("program.nodes: expected between 1 and 10000 nodes")
    speakers = _speakers(data.get("speakers", []))
    facts = _facts(data.get("facts", {}))
    capabilities = data.get("required_capabilities", {})
    if not isinstance(capabilities, dict):
        raise ScenarioError("program.required_capabilities: expected an object")
    for name, version in capabilities.items():
        logical_id(name, "required capability")
        if type(version) is not int or version < 1:
            raise ScenarioError(f"capability {name}: version must be a positive integer")
        if name not in catalog.capabilities or catalog.capabilities[name]["version"] != version:
            raise ScenarioError(f"capability {name}: required version {version} is not installed")
    required: dict[str, int] = dict(capabilities)
    targets: dict[str, list[str]] = {}
    invisible: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ScenarioError("program.nodes: expected node objects")
        node_id = logical_id(node.get("id"), "node.id")
        if node_id in targets:
            raise ScenarioError(f"node {node_id}: duplicate stable ID")
        kind = node.get("kind")
        if not isinstance(kind, str) or kind not in NODE_FIELDS:
            raise ScenarioError(f"node {node_id}: unknown instruction {kind!r}")
        unknown = set(node) - NODE_FIELDS[kind] - {"id", "kind"}
        if unknown:
            raise ScenarioError(f"node {node_id}: unknown fields {sorted(unknown)}")
        where = f"node {node_id}"
        outgoing: list[str] = []
        if kind in {"line", "set", "effect", "stop", "wait"}:
            outgoing.append(logical_id(node.get("next"), f"{where}.next"))
        if kind in {"line", "choice"}:
            if kind == "line" or "text" in node or "text_key" in node:
                _text(node, where)
            _gates(node, where)
            if "speaker" in node and (
                not isinstance(node["speaker"], str) or node["speaker"] not in speakers
            ):
                raise ScenarioError(f"{where}: undeclared speaker {node['speaker']!r}")
            if "expression" in node:
                logical_id(node["expression"], f"{where}.expression")
                if "speaker" not in node:
                    raise ScenarioError(f"{where}: an expression requires a speaker")
            presentation = node.get("presentation", {})
            if not isinstance(presentation, dict):
                raise ScenarioError(f"{where}.presentation: expected an object")
            for key in ("channel", "profile"):
                if key in presentation:
                    logical_id(presentation[key], f"{where}.presentation.{key}")
            cues = node.get("cues", [])
            if not isinstance(cues, list):
                raise ScenarioError(f"{where}.cues: expected an array")
            seen: set[str] = set()
            for cue in cues:
                if not isinstance(cue, dict) or set(cue) - EFFECT_FIELDS - {
                    "id",
                    "at",
                    "on",
                    "after",
                }:
                    raise ScenarioError(f"{where}: invalid cue fields")
                cue_id = logical_id(cue.get("id"), f"{where}.cue.id")
                if cue_id in seen:
                    raise ScenarioError(f"{where}: duplicate cue ID {cue_id}")
                seen.add(cue_id)
                if ("at" in cue) == ("on" in cue):
                    raise ScenarioError(f"{where}.{cue_id}: exactly one of at or on is required")
                if "at" in cue:
                    _seconds(cue["at"], f"{where}.{cue_id}.at")
                    if "after" in cue:
                        raise ScenarioError(f"{where}.{cue_id}: after requires an event cue")
                else:
                    logical_id(cue["on"], f"{where}.{cue_id}.on")
                    _seconds(cue.get("after", 0), f"{where}.{cue_id}.after")
                _effect(cue, catalog, required, f"{where}.{cue_id}")
        if kind == "choice":
            options = node.get("options")
            if not isinstance(options, list) or not 1 <= len(options) <= 64:
                raise ScenarioError(f"{where}.options: expected between 1 and 64 choices")
            seen = set()
            for option in options:
                if not isinstance(option, dict) or set(option) - {
                    "id",
                    "text",
                    "text_key",
                    "target",
                    "condition",
                    "set",
                }:
                    raise ScenarioError(f"{where}: invalid choice fields")
                option_id = logical_id(option.get("id"), f"{where}.choice.id")
                if option_id in seen:
                    raise ScenarioError(f"{where}: duplicate choice ID {option_id}")
                seen.add(option_id)
                _text(option, f"{where}.{option_id}")
                outgoing.append(logical_id(option.get("target"), f"{where}.{option_id}.target"))
                _assignments(option.get("condition", {}), facts, f"{where}.{option_id}.condition")
                _assignments(
                    option.get("set", {}), facts, f"{where}.{option_id}.set", writable=True
                )
        elif kind == "branch":
            edges = node.get("edges")
            if not isinstance(edges, list) or not edges:
                raise ScenarioError(f"{where}.edges: expected nonempty array")
            for edge in edges:
                if not isinstance(edge, dict) or set(edge) != {"condition", "target"}:
                    raise ScenarioError(f"{where}: branch edges require condition and target")
                _assignments(edge["condition"], facts, f"{where}.condition")
                outgoing.append(logical_id(edge["target"], f"{where}.target"))
            outgoing.append(logical_id(node.get("default"), f"{where}.default"))
        elif kind == "set":
            _assignments(node.get("values"), facts, f"{where}.values", writable=True)
        elif kind == "jump":
            outgoing.append(logical_id(node.get("target"), f"{where}.target"))
        elif kind == "effect":
            _effect(node, catalog, required, where)
        elif kind == "stop":
            logical_id(node.get("instance_id"), f"{where}.instance_id")
        elif kind == "wait":
            if sum(key in node for key in ("duration", "operation", "event")) != 1:
                raise ScenarioError(f"{where}: wait requires one duration, operation or event")
            if "duration" in node:
                _seconds(node["duration"], f"{where}.duration")
                _clock(node.get("clock", "sequence"), where)
            elif "clock" in node:
                raise ScenarioError(f"{where}: clock is only valid on a duration wait")
            else:
                key = "operation" if "operation" in node else "event"
                logical_id(node[key], f"{where}.{key}")
        elif kind == "end":
            logical_id(node.get("outcome"), f"{where}.outcome")
        targets[node_id] = outgoing
        if kind not in {"line", "choice", "wait", "end"} or (
            kind == "wait" and node.get("duration") == 0
        ):
            invisible.add(node_id)
    if entry not in targets:
        raise ScenarioError(f"program.entry: unknown node {entry!r}")
    for node_id, outgoing in targets.items():
        unknown = set(outgoing) - targets.keys()
        if unknown:
            raise ScenarioError(f"node {node_id}: unknown targets {sorted(unknown)}")
    reachable = _reachable(entry, targets)
    if reachable != targets.keys():
        raise ScenarioError(f"program: unreachable nodes {sorted(targets.keys() - reachable)}")
    if not any(node["kind"] == "end" for node in nodes if node["id"] in reachable):
        raise ScenarioError("program: no ending is reachable")
    _refuse_invisible_cycles(targets, invisible)
    data["required_capabilities"] = dict(sorted(required.items()))
    return data


def _speakers(value: Any) -> set[str]:
    if not isinstance(value, list):
        raise ScenarioError("program.speakers: expected an array")
    result: set[str] = set()
    for speaker in value:
        if not isinstance(speaker, dict) or set(speaker) - {"id", "display_name"}:
            raise ScenarioError("program.speakers: expected id and optional display_name")
        name = logical_id(speaker.get("id"), "speaker.id")
        if name in result:
            raise ScenarioError(f"speaker {name}: duplicate declaration")
        if "display_name" in speaker and (
            not isinstance(speaker["display_name"], str) or not speaker["display_name"].strip()
        ):
            raise ScenarioError(f"speaker {name}: display_name must be nonempty text")
        result.add(name)
    return result


def _facts(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioError("program.facts: expected an object")
    for name, fact in value.items():
        logical_id(name, "fact name")
        if not isinstance(fact, dict) or set(fact) - {"type", "default", "values", "external"}:
            raise ScenarioError(f"fact {name}: invalid declaration")
        if not isinstance(fact.get("type"), str) or fact["type"] not in {"boolean", "string"}:
            raise ScenarioError(f"fact {name}: expected boolean or string type")
        schema: dict[str, Any] = {"type": fact["type"]}
        if "values" in fact:
            if (
                fact["type"] != "string"
                or not isinstance(fact["values"], list)
                or not fact["values"]
            ):
                raise ScenarioError(f"fact {name}: values requires a nonempty string list")
            if any(not isinstance(item, str) for item in fact["values"]) or len(
                set(fact["values"])
            ) != len(fact["values"]):
                raise ScenarioError(f"fact {name}: string values must be unique")
            schema["enum"] = fact["values"]
        elif fact["type"] == "string":
            raise ScenarioError(f"fact {name}: string facts require declared values")
        validate_value(fact.get("default"), schema, f"fact {name}.default")
        if "external" in fact and type(fact["external"]) is not bool:
            raise ScenarioError(f"fact {name}.external: expected boolean")
    return value


def _assignments(value: Any, facts: dict[str, Any], where: str, *, writable: bool = False) -> None:
    if not isinstance(value, dict):
        raise ScenarioError(f"{where}: expected fact assignments")
    for name, item in value.items():
        if name not in facts:
            raise ScenarioError(f"{where}: undeclared fact {name!r}")
        if writable and facts[name].get("external", False):
            raise ScenarioError(f"{where}: external fact {name!r} is game-owned and read-only")
        schema: dict[str, Any] = {"type": facts[name]["type"]}
        if "values" in facts[name]:
            schema["enum"] = facts[name]["values"]
        validate_value(item, schema, f"{where}.{name}")


def _gates(node: dict[str, Any], where: str) -> None:
    gates = node.get("gates", [])
    if not isinstance(gates, list):
        raise ScenarioError(f"{where}.gates: expected an array")
    events: set[str] = set()
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) - {"event", "finish_on_advance"}:
            raise ScenarioError(f"{where}.gates: expected event and finish_on_advance")
        event = logical_id(gate.get("event"), f"{where}.gate.event")
        if event in events:
            raise ScenarioError(f"{where}.gates: duplicate gate event {event}")
        events.add(event)
        if type(gate.get("finish_on_advance", False)) is not bool:
            raise ScenarioError(f"{where}.gates: finish_on_advance must be boolean")
    if node.get("advance_mode") == "on_gates" and not gates:
        raise ScenarioError(f"{where}: on_gates requires at least one explicit gate")
    if not isinstance(node.get("advance_mode", "manual"), str) or node.get(
        "advance_mode", "manual"
    ) not in {"manual", "on_gates"}:
        raise ScenarioError(f"{where}.advance_mode: unsupported progression mode")


def _text(value: dict[str, Any], where: str) -> None:
    if ("text" in value) == ("text_key" in value):
        raise ScenarioError(f"{where}: exactly one of text or text_key is required")
    key = "text" if "text" in value else "text_key"
    if not isinstance(value[key], str) or not value[key].strip():
        raise ScenarioError(f"{where}.{key}: expected nonempty text")


def _seconds(value: Any, where: str) -> None:
    validate_value(value, {"type": "number", "min": 0}, where)


def _clock(value: Any, where: str) -> None:
    if not isinstance(value, str) or value not in CLOCKS:
        raise ScenarioError(f"{where}: unknown clock {value!r}")


def _effect(value: dict[str, Any], catalog: Catalog, required: dict[str, int], where: str) -> None:
    logical_id(value.get("instance_id"), f"{where}.instance_id")
    normalized = catalog.effect(value.get("effect"), f"{where}.effect")
    required[normalized["type"]] = normalized["version"]
    if "target" in value:
        logical_id(value["target"], f"{where}.target")
    if not isinstance(value.get("scope", "node"), str) or value.get("scope", "node") not in {
        "node",
        "sequence",
    }:
        raise ScenarioError(f"{where}: unknown operation scope")
    _clock(value.get("clock", "sequence"), where)
    if "duration" in value:
        _seconds(value["duration"], f"{where}.duration")


def _reachable(entry: str, graph: dict[str, list[str]]) -> set[str]:
    found: set[str] = set()
    pending = [entry]
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(graph[current])
    return found


def _refuse_invisible_cycles(graph: dict[str, list[str]], invisible: set[str]) -> None:
    # Kahn elimination is iterative, so a long authored scene cannot overflow the
    # Python call stack. Any remaining invisible subgraph contains a silent cycle.
    indegree = {name: 0 for name in invisible}
    for name in invisible:
        for target in graph[name]:
            if target in invisible:
                indegree[target] += 1
    pending = [name for name, degree in indegree.items() if degree == 0]
    while pending:
        current = pending.pop()
        del indegree[current]
        for target in graph[current]:
            if target in indegree:
                indegree[target] -= 1
                if indegree[target] == 0:
                    pending.append(target)
    if indegree:
        raise ScenarioError(f"program: invisible instruction cycle near {sorted(indegree)}")

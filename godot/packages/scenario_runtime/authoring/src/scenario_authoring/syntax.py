"""Concise v3 source with stable IDs; parsing never evaluates authored code."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .validation import ScenarioError, logical_id

DECODER = json.JSONDecoder()


@dataclass
class ParsedSource:
    scenario_id: str = ""
    entry: str | None = None
    speakers: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    requirements: dict[str, int] = field(default_factory=dict)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    locations: dict[str, dict[str, Any]] = field(default_factory=dict)


def parse_source(text: str, *, source_name: str = "<memory>") -> ParsedSource:
    """Read source into explicit nodes, expanding bounded reusable sequences.

    `@id` identifies the next instruction. A sequence definition is an indented
    source template; `use name with={...}` instantiates it with exact `$parameter`
    values. It does not add a runtime call stack or arbitrary expression language.
    """

    if "\t" in text:
        raise ScenarioError(f"{source_name}: tabs are not allowed; indent with spaces")
    lines = [(number, line.rstrip()) for number, line in enumerate(text.splitlines(), 1)]
    macros: dict[str, list[tuple[int, str]]] = {}
    main: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        number, line = lines[index]
        stripped = line.strip()
        if line.startswith("sequence ") and stripped.endswith(":"):
            name = logical_id(stripped[9:-1].strip(), f"{source_name}:{number}: sequence")
            if name in macros:
                raise ScenarioError(f"{source_name}:{number}: duplicate sequence {name}")
            body: list[tuple[int, str]] = []
            index += 1
            while index < len(lines):
                nested_number, nested = lines[index]
                if nested.strip() and not nested.startswith(" "):
                    break
                if nested.strip() and not nested.startswith("    "):
                    raise ScenarioError(
                        f"{source_name}:{nested_number}: indent sequence by four spaces"
                    )
                body.append((nested_number, nested[4:] if nested.startswith("    ") else nested))
                index += 1
            if not any(item.strip() and not item.strip().startswith("#") for _, item in body):
                raise ScenarioError(f"{source_name}:{number}: empty reusable sequence")
            macros[name] = body
            continue
        main.append((number, line))
        index += 1
    parsed = ParsedSource()
    raw_nodes, raw_locations = _parse_lines(main, parsed, source_name, declarations=True)
    macro_nodes: dict[str, tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]] = {}
    for name, body in macros.items():
        macro_nodes[name] = _parse_lines(body, ParsedSource(), source_name, declarations=False)
    if not parsed.scenario_id:
        raise ScenarioError(f"{source_name}: missing `scenario <id>` declaration")
    parsed.nodes, parsed.locations = _expand(raw_nodes, raw_locations, macro_nodes, (), "", {})
    if not parsed.nodes:
        raise ScenarioError(f"{source_name}: scenario contains no instructions")
    for index, node in enumerate(parsed.nodes):
        if node["kind"] in {"line", "set", "effect", "stop", "wait"} and "next" not in node:
            if index + 1 == len(parsed.nodes):
                where = parsed.locations[node["id"]]
                raise ScenarioError(
                    f"{source_name}:{where['line']}: final instruction needs an ending"
                )
            node["next"] = parsed.nodes[index + 1]["id"]
    return parsed


def _logical_lines(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Join balanced JSON/call continuations while preserving the source line."""

    result: list[tuple[int, str]] = []
    pending: list[str] = []
    start = 0
    stack: list[str] = []
    quoted = False
    escaped = False
    pairs = {"}": "{", "]": "[", ")": "("}
    for number, line in lines:
        if not pending:
            start = number
        pending.append(line)
        if not line.lstrip().startswith("#"):
            for character in line:
                if quoted:
                    if escaped:
                        escaped = False
                    elif character == "\\":
                        escaped = True
                    elif character == '"':
                        quoted = False
                elif character == '"':
                    quoted = True
                elif character in "[{(":
                    stack.append(character)
                elif character in "]})":
                    if not stack or stack[-1] != pairs[character]:
                        raise ScenarioError(f"line {number}: unmatched closing delimiter")
                    stack.pop()
        if not stack:
            result.append((start, "\n".join(pending)))
            pending = []
            quoted = False
            escaped = False
    if pending:
        raise ScenarioError(f"line {start}: unclosed JSON or effect definition")
    return result


def _parse_lines(
    lines: list[tuple[int, str]], parsed: ParsedSource, source_name: str, *, declarations: bool
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    locations: dict[str, dict[str, Any]] = {}
    pending: tuple[str, int] | None = None
    current: dict[str, Any] | None = None
    for number, raw in _logical_lines(lines):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        try:
            if raw.startswith(" "):
                if current is None:
                    raise ScenarioError("indented content requires a line, menu or branch")
                if current["kind"] in {"line", "choice"} and text.startswith("present "):
                    presentation, remaining = _value(text[8:])
                    if remaining or not isinstance(presentation, dict):
                        raise ScenarioError("present requires one JSON object")
                    current.setdefault("presentation", {}).update(presentation)
                elif current["kind"] in {"line", "choice"} and text.startswith("gate "):
                    event, _, tail = text[5:].partition(" ")
                    current.setdefault("gates", []).append({"event": event, **_options(tail)})
                elif current["kind"] == "line" and text.startswith("advance_mode "):
                    current["advance_mode"] = text[13:].strip()
                elif current["kind"] in {"line", "choice"} and text.startswith("cue "):
                    current.setdefault("cues", []).append(_cue(text[4:]))
                elif current["kind"] == "choice":
                    current["options"].append(_choice(text))
                elif current["kind"] == "branch":
                    if text.startswith("else -> "):
                        if "default" in current:
                            raise ScenarioError("branch has multiple default targets")
                        current["default"] = text[8:].strip()
                    elif text.startswith("if "):
                        condition, rest = _value(text[3:])
                        if not rest.startswith("-> "):
                            raise ScenarioError("branch edge requires `if {facts} -> target`")
                        current["edges"].append(
                            {"condition": condition, "target": rest[3:].strip()}
                        )
                    else:
                        raise ScenarioError("branch child requires `if` or `else`")
                else:
                    raise ScenarioError("this instruction does not accept indented children")
                continue
            if text.startswith("@"):
                if pending is not None:
                    raise ScenarioError("the previous stable ID has no instruction")
                name, _, tail = text[1:].partition(" ")
                pending = (logical_id(name.rstrip(":"), "node ID"), number)
                current = None
                if not tail:
                    continue
                text = tail.strip()
            if declarations and pending is None and _declaration(text, parsed):
                continue
            if pending is None:
                raise ScenarioError("each instruction needs a stable `@id`")
            node_id, node_line = pending
            if node_id in locations:
                raise ScenarioError(f"duplicate stable ID {node_id}")
            current = {"id": node_id, **_instruction(text)}
            locations[node_id] = {"source": source_name, "line": node_line, "column": 1}
            nodes.append(current)
            pending = None
        except (ScenarioError, ValueError, TypeError) as error:
            raise ScenarioError(f"{source_name}:{number}: {error}") from None
    if pending:
        raise ScenarioError(f"{source_name}:{pending[1]}: stable ID has no instruction")
    return nodes, locations


def _declaration(text: str, parsed: ParsedSource) -> bool:
    word, _, rest = text.partition(" ")
    if word == "scenario":
        if parsed.scenario_id:
            raise ScenarioError("scenario may be declared only once")
        parsed.scenario_id = logical_id(rest.strip(), "scenario ID")
    elif word == "entry":
        if parsed.entry is not None:
            raise ScenarioError("entry may be declared only once")
        parsed.entry = logical_id(rest.strip(), "entry ID")
    elif word == "speaker":
        name, _, tail = rest.partition(" ")
        speaker: dict[str, Any] = {"id": logical_id(name, "speaker ID")}
        if tail:
            display, remaining = _value(tail)
            if remaining or not isinstance(display, str):
                raise ScenarioError("speaker display name must be a quoted string")
            speaker["display_name"] = display
        parsed.speakers.append(speaker)
    elif word == "fact":
        name, separator, tail = rest.partition("=")
        if not separator:
            raise ScenarioError("fact requires `name = value`")
        external = name.strip().endswith(" external")
        name = name.strip().removesuffix(" external").strip()
        logical_id(name, "fact ID")
        if name in parsed.facts:
            raise ScenarioError(f"duplicate fact {name}")
        default, tail = _value(tail.strip())
        definition: dict[str, Any] = {
            "type": "boolean" if isinstance(default, bool) else "string",
            "default": default,
        }
        if external:
            definition["external"] = True
        if tail:
            if not tail.startswith("in "):
                raise ScenarioError("fact values use `in [allowed_values]`")
            values, remaining = _value(tail[3:])
            if remaining:
                raise ScenarioError("unexpected text after fact declaration")
            definition["values"] = values
        parsed.facts[name] = definition
    elif word == "require":
        name, _, version = rest.partition(" ")
        logical_id(name, "capability ID")
        if name in parsed.requirements:
            raise ScenarioError(f"duplicate capability requirement {name}")
        parsed.requirements[name] = int(version)
    else:
        return False
    return True


def _instruction(text: str) -> dict[str, Any]:
    word, _, rest = text.partition(" ")
    if word == "start":
        return {"kind": "effect", **_effect(rest)}
    if word == "stop":
        name, _, tail = rest.partition(" ")
        return {"kind": "stop", "instance_id": name, **_options(tail)}
    if word == "wait":
        return {"kind": "wait", **_options(rest)}
    if word == "set":
        values = _options(rest)
        next_node = values.pop("next", None)
        return {"kind": "set", "values": values, **({"next": next_node} if next_node else {})}
    if word == "jump":
        return {"kind": "jump", "target": rest.strip()}
    if word == "end":
        return {"kind": "end", "outcome": rest.strip()}
    if word.rstrip(":") == "menu":
        options = _options(rest.removesuffix(":"))
        presentation = options.pop("presentation", {})
        if not isinstance(presentation, dict):
            raise ScenarioError("presentation must be an object")
        for name in ("channel", "profile", "portrait", "anchor"):
            if name in options:
                presentation[name] = options.pop(name)
        return {
            "kind": "choice",
            "options": [],
            **options,
            "presentation": {"channel": "dialogue", "profile": "bottom", **presentation},
        }
    if word == "branch:":
        if rest:
            raise ScenarioError("branch children belong on indented lines")
        return {"kind": "branch", "edges": []}
    if word == "use":
        name, _, tail = rest.partition(" ")
        options = _options(tail)
        if set(options) - {"with"} or not isinstance(options.get("with", {}), dict):
            raise ScenarioError("use accepts only `with={parameter_values}`")
        return {"kind": "_use", "sequence": name, "parameters": options.get("with", {})}
    return {"kind": "line", **_dialogue(text)}


def _dialogue(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if text.startswith(('"', "key ")):
        pass
    else:
        speaker, _, text = text.partition(" ")
        if speaker == "say":
            speaker, _, text = text.partition(" ")
        if speaker != "narrate":
            result["speaker"] = speaker
            if not text.startswith(('"', "key ")):
                expression, _, text = text.partition(" ")
                result["expression"] = expression
    payload, tail = _text(text)
    result.update(payload)
    options = _options(tail)
    presentation = options.pop("presentation", {})
    if not isinstance(presentation, dict):
        raise ScenarioError("presentation must be an object")
    for name in ("channel", "profile", "portrait", "anchor"):
        if name in options:
            presentation[name] = options.pop(name)
    result["presentation"] = {"channel": "dialogue", "profile": "bottom", **presentation}
    result.update(options)
    return result


def _text(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("key "):
        name, _, rest = text[4:].partition(" ")
        return {"text_key": name}, rest.strip()
    if not text.startswith('"'):
        raise ScenarioError("utterance text must be quoted or written as `key text_id`")
    value, rest = _value(text)
    if not isinstance(value, str):
        raise ScenarioError("expected quoted text")
    return {"text": value}, rest


def _choice(text: str) -> dict[str, Any]:
    name, _, rest = text.partition(" ")
    payload, rest = _text(rest)
    if not rest.startswith("-> "):
        raise ScenarioError("choice requires `option_id text -> target`")
    target, _, tail = rest[3:].partition(" ")
    options = _options(tail)
    if "if" in options:
        options["condition"] = options.pop("if")
    return {"id": name, **payload, "target": target, **options}


def _cue(text: str) -> dict[str, Any]:
    name, _, rest = text.partition(" ")
    result: dict[str, Any] = {"id": name}
    if rest.startswith("at "):
        at, rest = _value(rest[3:])
        result["at"] = at
    elif rest.startswith("on "):
        event, _, rest = rest[3:].partition(" ")
        result["on"] = event
        if rest.startswith("after "):
            after, rest = _value(rest[6:])
            result["after"] = after
    else:
        raise ScenarioError("cue requires `at seconds` or `on text_revealed`")
    if not rest.startswith("start "):
        raise ScenarioError("cue requires a start instruction")
    return {**result, **_effect(rest[6:], scope="node")}


def _effect(text: str, *, scope: str = "sequence") -> dict[str, Any]:
    match = re.match(r"([$A-Za-z0-9_.:-]+)(.*)", text)
    if not match:
        raise ScenarioError("start requires an effect name")
    name, rest = match.groups()
    if rest.startswith("("):
        parameters, rest = _value(rest[1:])
        if not rest.startswith(")") or not isinstance(parameters, dict):
            raise ScenarioError('inline effects use `type({"parameter": value})`')
        reference: dict[str, Any] = {"type": name, "parameters": parameters}
        rest = rest[1:].strip()
    else:
        reference = {"preset": name, "parameters": {}}
        rest = rest.strip()
    if not rest.startswith("as "):
        raise ScenarioError("start requires `as instance_id`")
    instance, _, tail = rest[3:].partition(" ")
    options = _options(tail)
    parameters = options.pop("parameters", {})
    if not isinstance(parameters, dict):
        raise ScenarioError("effect parameters must be an object")
    reference["parameters"].update(parameters)
    return {
        "effect": reference,
        "instance_id": instance,
        "scope": scope,
        "clock": "presentation",
        **options,
    }


def _value(text: str) -> tuple[Any, str]:
    text = text.strip()
    try:
        value, end = DECODER.raw_decode(text)
    except json.JSONDecodeError:
        raise ScenarioError("expected a JSON string, boolean, number, array or object") from None
    return value, text[end:].strip()


def _options(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    text = text.strip()
    while text:
        match = re.match(r"([a-z][a-z0-9_]*)\s*=\s*", text)
        if not match:
            raise ScenarioError(f"expected named parameter near {text!r}")
        name = match.group(1)
        if name in result:
            raise ScenarioError(f"duplicate parameter {name}")
        tail = text[match.end() :]
        if not tail:
            raise ScenarioError(f"parameter {name} has no value")
        if tail[0] in '"[{0123456789-' or tail.startswith(("true", "false", "null")):
            value, text = _value(tail)
        else:
            value, _, text = tail.partition(" ")
            text = text.strip()
        result[name] = value
    return result


def _expand(
    nodes: list[dict[str, Any]],
    locations: dict[str, dict[str, Any]],
    macros: dict[str, tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]],
    stack: tuple[str, ...],
    prefix: str,
    parameters: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    result: list[dict[str, Any]] = []
    result_locations: dict[str, dict[str, Any]] = {}
    ids = {node["id"]: prefix + node["id"] for node in nodes}
    instances = {
        entry["instance_id"]
        for node in nodes
        for entry in ([node] if node["kind"] == "effect" else node.get("cues", []))
        if "instance_id" in entry and not entry["instance_id"].startswith("$")
    }
    for original in nodes:
        node = (
            _substitute(copy.deepcopy(original), parameters) if stack else copy.deepcopy(original)
        )
        node["id"] = ids[original["id"]]
        location = copy.deepcopy(locations[original["id"]])
        if stack:
            location["sequence"] = stack[-1]
        if node["kind"] == "_use":
            name = node["sequence"]
            if name not in macros:
                raise ScenarioError(f"node {node['id']}: unknown reusable sequence {name!r}")
            if name in stack or len(stack) >= 32:
                raise ScenarioError(f"node {node['id']}: recursive or overly deep sequence call")
            expanded, expanded_locations = _expand(
                *macros[name],
                macros,
                (*stack, name),
                node["id"] + "__",
                node["parameters"],
            )
            if not expanded:
                raise ScenarioError(f"node {node['id']}: empty reusable sequence")
            result.append({"id": node["id"], "kind": "jump", "target": expanded[0]["id"]})
            result_locations[node["id"]] = location
            result.extend(expanded)
            result_locations.update(expanded_locations)
        else:
            for key in ("next", "target", "default"):
                if key in node:
                    node[key] = ids.get(node[key], node[key])
            for child in [*node.get("options", []), *node.get("edges", [])]:
                if "target" in child:
                    child["target"] = ids.get(child["target"], child["target"])
            for child in [node, *node.get("cues", [])]:
                for key in ("instance_id", "operation"):
                    if child.get(key) in instances:
                        child[key] = prefix + child[key]
            result.append(node)
            result_locations[node["id"]] = location
        if len(result) > 10000:
            raise ScenarioError("sequence expansion exceeds the 10000-node limit")
    return result, result_locations


def _substitute(value: Any, parameters: dict[str, Any]) -> Any:
    if isinstance(value, str) and re.fullmatch(r"\$[A-Za-z][A-Za-z0-9_]*", value):
        name = value[1:]
        if name not in parameters:
            raise ScenarioError(f"reusable sequence parameter {name!r} is missing")
        return copy.deepcopy(parameters[name])
    if isinstance(value, list):
        return [_substitute(item, parameters) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, parameters) for key, item in value.items()}
    return value

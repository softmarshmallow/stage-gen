"""Transport repairs every recipe's structured calls need, and none of them owns.

Three small things sit between a strict structured route and a caller that wants
a validated contract back. The strict transport cannot carry ``$defs``, so local
references are inlined before a schema is sent. OpenRouter sometimes returns a
``completionState`` envelope around the object it was asked for, and unwrapping
that is a transport concern rather than a question about any one recipe's
vocabulary. And a usage record may or may not carry a cost the provider will
stand behind.

They live here because two recipes wrote them character for character alike and
recipes may not import each other: a direct child of ``recipes/`` is the shared
home the import-boundary contract allows. Nothing here knows a genre, a medium
or a document kind, which is the test for whether something belongs.

The honest longer-term home for the envelope decoder is the provider adapter
that meets the envelope; moving it there is a wider change than the one that
brought this module into being.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from collections.abc import Mapping


def inline_local_schema_refs(schema: Mapping[str, object]) -> dict[str, object]:
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        return dict(schema)

    def expand(value: object) -> object:
        if isinstance(value, list):
            return [expand(item) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            target = definitions.get(reference.removeprefix("#/$defs/"))
            if not isinstance(target, dict):
                raise ValueError(f"unknown local schema reference: {reference}")
            siblings = {key: item for key, item in value.items() if key != "$ref"}
            return expand({**copy.deepcopy(target), **siblings})
        return {str(key): expand(item) for key, item in value.items() if key != "$defs"}

    expanded = expand(dict(schema))
    if not isinstance(expanded, dict):
        raise TypeError("expanded schema root must remain an object")
    return expanded


def decode_completion_wrapper(value: object, stats: Counter[str]) -> object:
    """Unwrap the provider's occasional ``completionState`` envelope."""

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped.startswith("{"):
            return value
        try:
            parsed = json.loads(stripped)
        except ValueError:
            return value
        if not isinstance(parsed, dict) or "completionState" not in parsed:
            return value
        stats["wrapper_strings"] += 1
        return decode_completion_wrapper(parsed, stats)
    if isinstance(value, list):
        return [decode_completion_wrapper(item, stats) for item in value]
    if not isinstance(value, dict):
        return value
    if "completionState" not in value:
        return {str(key): decode_completion_wrapper(item, stats) for key, item in value.items()}
    if value.get("completionState") != "complete":
        stats["incomplete_wrappers"] += 1
        return value
    stats["wrapper_nodes"] += 1
    entries = value.get("entries")
    if isinstance(entries, list):
        decoded: dict[str, object] = {}
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str):
                stats["malformed_wrappers"] += 1
                return value
            decoded[entry[0]] = decode_completion_wrapper(entry[1], stats)
        return decoded
    items = value.get("items")
    if isinstance(items, list):
        return [decode_completion_wrapper(item, stats) for item in items]
    if "value" in value:
        return decode_completion_wrapper(value["value"], stats)
    stats["malformed_wrappers"] += 1
    return value


def known_cost(usage: object) -> float | None:
    if not isinstance(usage, Mapping):
        return None
    cost = usage.get("cost")
    return float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None


__all__ = ["decode_completion_wrapper", "inline_local_schema_refs", "known_cost"]

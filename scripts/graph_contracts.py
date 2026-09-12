"""Private repository tooling for labelled JSON graph evidence in Markdown.

Shared by the product and Godot evidence writers; contains no recipe or game
imports. This is repository tooling, not an asset SDK or standalone Godot API.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CONTRACT_START = "<!-- pipeline-graph-contract:start -->"
CONTRACT_END = "<!-- pipeline-graph-contract:end -->"


def contract_markers(label: str | None) -> tuple[str, str, re.Pattern[str]]:
    """Delimiters for one block. A label lets one document carry several."""

    start = CONTRACT_START if label is None else f"<!-- pipeline-graph-contract:{label}:start -->"
    end = CONTRACT_END if label is None else f"<!-- pipeline-graph-contract:{label}:end -->"
    pattern = re.compile(
        rf"{re.escape(start)}\s*```json\s*(.*?)\s*```\s*{re.escape(end)}",
        re.DOTALL,
    )
    return start, end, pattern


def document_contract(document: Path, *, label: str | None = None) -> dict[str, Any]:
    """Read the snapshot currently written into the document."""

    start, end, pattern = contract_markers(label)
    source = document.read_text(encoding="utf-8")
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError(f"the document must carry exactly one {label or 'graph'}-contract block")
    matches = pattern.findall(source)
    if len(matches) != 1:
        raise ValueError("the graph-contract block is malformed")
    value = json.loads(matches[0])
    if not isinstance(value, dict):
        raise ValueError("the graph-contract block must be a JSON object")
    return value


def render(contract: dict[str, Any], *, label: str | None = None) -> str:
    start, end, _ = contract_markers(label)
    return f"{start}\n```json\n{json.dumps(contract, indent=2)}\n```\n{end}"


def write_contract(contract: dict[str, Any], document: Path, *, label: str | None = None) -> bool:
    """Replace the block in place. Returns True when the document changed."""

    start, end, pattern = contract_markers(label)
    source = document.read_text(encoding="utf-8")
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError(f"the document must carry exactly one {label or 'graph'}-contract block")
    updated = pattern.sub(lambda _: render(contract, label=label), source, count=1)
    if updated == source:
        return False
    document.write_text(updated, encoding="utf-8")
    return True

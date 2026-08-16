"""Provider-neutral consumer manifest projections."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def to_canonical_manifest_entry(artifact: dict[str, Any]) -> dict[str, Any]:
    transparency = artifact.get("transparency")
    if not isinstance(transparency, dict):
        result: dict[str, Any] = {"path": artifact["path"]}
        if artifact.get("provenancePath") is not None:
            result["provenancePath"] = artifact["provenancePath"]
        return result
    return {
        "path": transparency["canonicalPath"],
        "provenancePath": transparency["canonicalProvenancePath"],
        "transparency": deepcopy(transparency),
    }

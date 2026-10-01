"""What the four Bellweather importers share: run lineage, package references and verdicts.

Every file an importer opens goes through the request's ``RecordingReader``, so the example
names the digest of each run file, package file and game script it was made from.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from stage_gen.examples import (
    FiguresLedger,
    ImportRequest,
    Lineage,
    RecordingReader,
    WorkflowExample,
    relative_to_base,
    sha256_bytes,
)

#: (run folder, summary entry, plan entry) of the run where a node actually ran.
type Ran = tuple[Path, dict[str, Any], dict[str, Any]]
#: An example and the ledger of every picture derived for it.
type Imported = tuple[WorkflowExample, FiguresLedger]


class ImporterOptions(BaseModel):
    """The run table of one example in ``examples.toml``: which runs, oldest first, and the
    package they were made from, as paths relative to the repository."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runs: list[str] = Field(min_length=1)
    package: str = Field(min_length=1)


def imported(request: ImportRequest, document: dict[str, Any], run_dir: Path) -> Imported:
    """The example, and its ledger named after the package run folder its pictures came from
    (the example's ``delivered_run`` may be a folder inside it)."""
    example = WorkflowExample.model_validate(document)
    return example, request.media.figures(relative_to_base(request.base, run_dir))


def lineage(request: ImportRequest) -> Lineage:
    return Lineage(request.reader, [run.resolve() for run in request.runs])


def where(lineage: Lineage, ids: Iterable[str]) -> dict[str, Ran]:
    """Each node from the run that produced the bytes the last run delivered."""
    return {node_id: lineage.where_it_ran(node_id) for node_id in ids}


def feeds(ran: Mapping[str, Ran]) -> dict[str, list[str]]:
    """Each node's upstream nodes among those shown, as the plan wired them."""
    return {
        node_id: [d for d in planned["depends_on"] if d in ran]
        for node_id, (_, _, planned) in ran.items()
    }


def digest(reader: RecordingReader, path: Path) -> str:
    return sha256_bytes(reader.bytes(path))


def sent_digests(sidecar: Mapping[str, Any]) -> dict[str, str]:
    """The inputs a provider request recorded, by digest."""
    return {str(item["sha256"]): str(item["ref"]) for item in sidecar["inputs"]}


def package_reference(package: Path, sent: Mapping[str, str]) -> Path:
    """The package reference a request sent, from its ``package://.../references/...`` ref."""
    ref = next(ref for ref in sent.values() if ref.startswith("package://"))
    return package / "references" / ref.split("/references/", 1)[1].split("#", 1)[0]


def verdict_of(review: Mapping[str, Any]) -> dict[str, Any]:
    """A recorded review, restated as an example node's verdict."""
    return {
        "accepted": review["verdict"] == "accept",
        "criteria": [
            {"name": name, "passed": passed, "evidence": ""}
            for name, passed in review["checks"].items()
        ],
        "issues": review.get("issues", []),
    }


def estimated_cost(ran: Mapping[str, Ran], ids: Sequence[str]) -> float:
    """The plan's high estimate for each node, times the attempts it took."""
    return sum(
        (ran[n][2].get("estimated_cost_high_usd") or 0) * (ran[n][1].get("attempts") or 1)
        for n in ids
    )


def missing_nodes(ids: Iterable[str], nodes: Mapping[str, object]) -> None:
    if missing := sorted(set(ids) - set(nodes)):
        raise ValueError(f"nodes this example does not show: {missing}")

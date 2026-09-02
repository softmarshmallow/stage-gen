"""Read one authored case offline, prove it, refuse it, then hand it on.

The order is the scenario resolver's order and for the same reason: parse, prove,
and only then let anything downstream build on it. A case that cannot be finished
costs nothing to refuse and is expensive to discover in play.

This module resolves the case's own structure and nothing below it. Binding the
beats to the leaves they name - resolving each scenario and each room, and
checking the beat's declared reads and writes against what the leaf actually does
- lives in `stage_gen.orchestration.case_binding`, because a component may not
import a recipe and a room is a recipe.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from stage_gen.components._authored_package import read_package_member
from stage_gen.components._game_input import parse_toml_contract, sha256_bytes
from stage_gen.components.case.models import (
    CASE_CATALOG_NAME,
    CaseAdmissionReport,
    CaseCatalog,
    CaseDocument,
)
from stage_gen.components.case.proof import admit_case

CASE_RESOLUTION_VERSION = "case-resolution-v1"


@dataclass(frozen=True, slots=True)
class ResolvedCase:
    """One authored case, proven finishable and ready to bind or play."""

    case: CaseDocument
    admission: CaseAdmissionReport
    case_bytes: bytes
    case_sha256: str

    def identity(self) -> dict[str, object]:
        """The portable record of exactly which case a run was planned from."""

        return {
            "schema_version": 1,
            "kind": "case-identity-v1",
            "game_id": self.case.game_id,
            "case_id": self.case.case_id,
            "revision": self.case.revision,
            "resolution_version": CASE_RESOLUTION_VERSION,
            "case_sha256": self.case_sha256,
            "beat_count": self.admission.beat_count,
        }


def canonical_case_json(case: CaseDocument) -> bytes:
    """The repository's ordinary canonical form: sorted, compact, nulls omitted."""

    return json.dumps(
        case.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def read_case_catalog(root: Path) -> CaseCatalog:
    """Read and validate `cases/index.toml`, following no symlink at any depth."""

    data = read_package_member(root, CASE_CATALOG_NAME, label="case catalog")
    return parse_toml_contract(data, model=CaseCatalog, label="case-catalog-v1")


def read_case_document(root: Path, case_id: str) -> CaseDocument:
    """Read and validate one `cases/<id>.toml`, following no symlink at any depth."""

    source = f"cases/{case_id}.toml"
    data = read_package_member(root, source, label="case document")
    case = parse_toml_contract(data, model=CaseDocument, label="case-v1")
    # The catalog names the file and the file names itself; a disagreement means
    # one of the two is about a case nobody asked for.
    if case.case_id != case_id:
        raise ValueError(
            f"{source} declares case_id `{case.case_id}`, which its own path does not name"
        )
    return case


def resolve_case(root: Path, case_id: str) -> ResolvedCase:
    """Admit one authored case's structure, touching no provider and no leaf."""

    case = read_case_document(root, case_id)
    admission = admit_case(case)
    case_bytes = canonical_case_json(case)
    return ResolvedCase(
        case=case,
        admission=admission,
        case_bytes=case_bytes,
        case_sha256=sha256_bytes(case_bytes),
    )


def resolve_case_catalog(root: Path) -> tuple[ResolvedCase, ...]:
    """Admit every case a game declares, in catalog order rather than the disk's."""

    catalog = read_case_catalog(root)
    return tuple(resolve_case(root, case_id) for case_id in catalog.case_ids)


__all__ = [
    "CASE_RESOLUTION_VERSION",
    "ResolvedCase",
    "canonical_case_json",
    "read_case_catalog",
    "read_case_document",
    "resolve_case",
    "resolve_case_catalog",
]

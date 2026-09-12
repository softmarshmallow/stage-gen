"""The `case-v1` authored container: the beat graph above the narrative leaves.

Recipe-neutral, like the scenario beneath it. A case names leaves by exact
package-relative path and knows only their kind, their outcomes, and the facts
they trade - never their prose, their art, or the recipe that generates either.
See `docs/spec/game/case.md`.
"""

from .models import (
    CASE_CATALOG_KIND,
    CASE_CATALOG_NAME,
    CASE_CATALOG_SCHEMA_VERSION,
    CASE_KIND,
    CASE_SCHEMA_VERSION,
    ROOM_DOCUMENT_SUFFIX,
    ROOM_WIN_OUTCOME,
    RUN_TAG_PATTERN,
    Beat,
    BeatEdge,
    CaseAdmissionReport,
    CaseCatalog,
    CaseDocument,
    CaseRuntime,
    CaseSource,
    FactAvailability,
    FactDeclaration,
    RuntimeBeat,
    TerminalWitness,
)
from .proof import CaseAdmissionError, admit_case
from .resolve import (
    CASE_RESOLUTION_VERSION,
    ResolvedCase,
    canonical_case_json,
    read_case_catalog,
    read_case_document,
    resolve_case,
    resolve_case_catalog,
)

__all__ = [
    "CASE_CATALOG_KIND",
    "CASE_CATALOG_NAME",
    "CASE_CATALOG_SCHEMA_VERSION",
    "CASE_KIND",
    "CASE_RESOLUTION_VERSION",
    "CASE_SCHEMA_VERSION",
    "ROOM_DOCUMENT_SUFFIX",
    "ROOM_WIN_OUTCOME",
    "RUN_TAG_PATTERN",
    "Beat",
    "BeatEdge",
    "CaseAdmissionError",
    "CaseAdmissionReport",
    "CaseCatalog",
    "CaseDocument",
    "CaseRuntime",
    "CaseSource",
    "FactAvailability",
    "FactDeclaration",
    "ResolvedCase",
    "RuntimeBeat",
    "TerminalWitness",
    "admit_case",
    "canonical_case_json",
    "read_case_catalog",
    "read_case_document",
    "resolve_case",
    "resolve_case_catalog",
]

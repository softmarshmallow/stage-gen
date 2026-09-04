"""The identity table is derived from the code, and the docs cite from it (C-R5)."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

from stage_gen.identities import (
    RETIRED_FAMILIES,
    RETIRED_STRINGS,
    contract_identities,
    current_versions,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
DOCUMENT = REPOSITORY_ROOT / "docs/contract-identities.md"

#: History lives here and is not held to the current version: the research and the
#: plans record what was, and the todo list is a ledger of what was decided when.
HISTORY_ROOTS = ("docs/research", "docs/plans", "docs/decisions")
HISTORY_FILES = ("TODO.md",)


def _load_writer() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/write_contract_identities.py"
    spec = importlib.util.spec_from_file_location("stage_gen_contract_identities_writer", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _current_documents() -> list[Path]:
    documents = sorted(REPOSITORY_ROOT.glob("*.md")) + sorted(
        (REPOSITORY_ROOT / "docs").rglob("*.md")
    )
    current: list[Path] = []
    for path in documents:
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        if any(relative.startswith(root) for root in HISTORY_ROOTS):
            continue
        if path.name in HISTORY_FILES or path == DOCUMENT:
            continue  # the table itself names what it retires
        current.append(path)
    return current


def _live_lines(text: str) -> list[tuple[int, str]]:
    """Lines held to the current version.

    Not a `retired` note, not a `Was` history table, and not a quoted refusal - a document
    that shows what a consumer says when a block is published at a version it does not
    read (`published as … ; this build reads …`) is describing the refusal, not citing.
    """

    live: list[tuple[int, str]] = []
    in_history_table = False
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            in_history_table = False
            continue
        if re.match(r"^\|\s*Was\b", line):
            in_history_table = True
        if (
            in_history_table
            or re.search(r"\bretire[ds]?\b", line, flags=re.IGNORECASE)
            or "is published as" in line
            or "this build reads" in line
        ):
            continue
        live.append((number, line))
    return live


def test_the_identity_document_is_derived_from_the_code() -> None:
    writer = _load_writer()
    assert DOCUMENT.read_text(encoding="utf-8") == writer.render(), (
        "docs/contract-identities.md is stale; run "
        "`uv run python scripts/write_contract_identities.py --write`"
    )


def test_every_identity_resolves_to_one_authority() -> None:
    identities = contract_identities()
    assert len({entry.identity for entry in identities}) == len(identities)
    for entry in identities:
        assert entry.sibling(entry.version) == entry.identity
    doubled = {family: v for family, v in current_versions().items() if len(v) > 1}
    # Recorded in the module docstring; a third would be a new decision, not a drift.
    assert set(doubled) <= {"dialogue-scene", "scenario-program"}, doubled
    live_families = set(current_versions())
    assert live_families.isdisjoint(family for family, _ in RETIRED_FAMILIES)


def test_current_documents_cite_only_current_identities() -> None:
    versions = current_versions()
    families = sorted(versions, key=len, reverse=True)
    family_pattern = re.compile(
        r"(?<![A-Za-z0-9_/.-])(?P<family>"
        + "|".join(re.escape(family) for family in families)
        + r")[-_]v(?P<version>\d+)(?![A-Za-z0-9])"
    )
    retired_pattern = re.compile(
        r"(?<![A-Za-z0-9_/.-])(?P<family>"
        + "|".join(re.escape(family) for family, _ in RETIRED_FAMILIES)
        + r")-v\d+(?![A-Za-z0-9])"
    )
    violations: list[str] = []
    for path in _current_documents():
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        for number, line in _live_lines(path.read_text(encoding="utf-8")):
            for match in family_pattern.finditer(line):
                found = int(match["version"])
                current = versions[match["family"]]
                if found not in current:
                    expected = " or ".join(f"v{v}" for v in sorted(current))
                    violations.append(
                        f"{relative}:{number} cites {match.group(0)}; current is {expected}"
                    )
            for match in retired_pattern.finditer(line):
                violations.append(f"{relative}:{number} cites retired family {match.group(0)}")
            for text, _ in RETIRED_STRINGS:
                if text in line:
                    violations.append(f"{relative}:{number} cites retired string {text}")
    assert not violations, "documents citing non-current identities:\n" + "\n".join(violations)

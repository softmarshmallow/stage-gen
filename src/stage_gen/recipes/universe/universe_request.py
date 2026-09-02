"""Resolve one authored universe source package, and the admitted universe it leads to.

A universe package is a directory: ``universe.toml`` beside the synopsis, the
expansion direction, and the ``references/`` poster the world is read from.
Everything the plan needs is materialized here, touching no provider. Member
bytes are read under package confinement and the poster is matched against the
digest the author recorded, so nothing is ever generated against a source that
silently changed.

The gallery phase starts from an admitted universe rather than from the source
alone, because how many entities exist — and therefore how many branches the
graph has — is only known once the semantic phase has been admitted.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from stage_gen.canonical import content_sha256
from stage_gen.components._authored_package import read_digest_bound_member, read_package_member
from stage_gen.recipes.universe.medium import MediumContract, medium_contract
from stage_gen.recipes.universe.models import (
    GalleryPlan,
    SampleLedger,
    UniverseProposal,
    UniverseSource,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

UNIVERSE_DOCUMENT_NAME = "universe.toml"

#: Run-relative refs the semantic phase writes and the gallery phase reads back.
SEMANTIC_UNIVERSE_REF = "semantic/universe.json"
SEMANTIC_ADMISSION_REF = "semantic/admission.json"
POSTER_PROXY_REF = "production/source-lock/poster-proxy.jpg"


@dataclass(frozen=True, slots=True)
class ResolvedUniverseSource:
    """One authored universe package, read and digest-bound, provider untouched."""

    source: UniverseSource
    source_sha256: str
    medium: MediumContract
    poster_bytes: bytes
    poster_sha256: str
    synopsis_text: str
    synopsis_sha256: str
    direction_text: str
    direction_sha256: str

    @property
    def universe_id(self) -> str:
        return self.source.universe_id

    @property
    def title(self) -> str:
        return self.source.display_name

    def synopsis_paragraphs(self) -> list[tuple[str, str]]:
        return synopsis_paragraphs(self.synopsis_text)

    def direction_requirements(self) -> list[tuple[str, str]]:
        return direction_requirements(self.direction_text)

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "universe-identity-v1",
            "universe_id": self.universe_id,
            "source_sha256": self.source_sha256,
            "medium_id": self.medium.medium_id,
            "poster_sha256": self.poster_sha256,
            "synopsis_sha256": self.synopsis_sha256,
            "direction_sha256": self.direction_sha256,
            "publication_authorized": False,
        }


def read_universe_document(root: Path) -> object:
    """Parse ``universe.toml`` out of one authored universe package directory."""

    try:
        return tomllib.loads((root / UNIVERSE_DOCUMENT_NAME).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"unreadable universe source document: {error}") from None


def resolve_universe_source(document: object, *, root: Path) -> ResolvedUniverseSource:
    """Validate and materialize everything the plan needs, touching no provider."""

    source = UniverseSource.model_validate(document)
    medium = medium_contract(source.medium)
    poster = read_digest_bound_member(
        root,
        source.poster.source,
        expected_sha256=source.poster.source_sha256,
        label="universe poster",
    )
    synopsis = read_package_member(root, source.synopsis.source, label="universe synopsis")
    direction = read_package_member(
        root, source.expansion_direction.source, label="universe expansion direction"
    )
    synopsis_text = synopsis.decode("utf-8")
    direction_text = direction.decode("utf-8")
    resolved = ResolvedUniverseSource(
        source=source,
        source_sha256=content_sha256(
            (root / UNIVERSE_DOCUMENT_NAME).read_bytes(),
        ),
        medium=medium,
        poster_bytes=poster,
        poster_sha256=source.poster.source_sha256,
        synopsis_text=synopsis_text,
        synopsis_sha256=content_sha256(synopsis),
        direction_text=direction_text,
        direction_sha256=content_sha256(direction),
    )
    # Both parsers are strict and both feed prompt ids the evaluators check
    # against. Running them here turns an unparseable package into a resolution
    # error rather than a confusing evaluator failure six provider calls later.
    resolved.synopsis_paragraphs()
    resolved.direction_requirements()
    return resolved


def synopsis_paragraphs(text: str) -> list[tuple[str, str]]:
    """Blank-line-separated blocks, headings skipped, numbered in reading order."""

    paragraphs: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or lines[0].startswith("#"):
            continue
        paragraphs.append((f"synopsis_p{len(paragraphs) + 1:02d}", " ".join(lines)))
    if not paragraphs:
        raise ValueError("synopsis has no paragraphs")
    return paragraphs


def direction_requirements(text: str) -> list[tuple[str, str]]:
    """``- <requirement_id>: <text>`` bullets, two-space continuations folded in."""

    items: list[tuple[str, str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        match = re.match(r"^- ([a-z][a-z0-9_]{1,95}): (.+)$", line)
        if match:
            if current:
                items.append((current[0], " ".join(current[1:])))
            current = [match.group(1), match.group(2).strip()]
        elif current and line.startswith("  ") and line.strip():
            current.append(line.strip())
        elif current:
            items.append((current[0], " ".join(current[1:])))
            current = None
    if current:
        items.append((current[0], " ".join(current[1:])))
    ids = [item[0] for item in items]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("expansion direction must list unique requirement ids")
    return items


@dataclass(frozen=True, slots=True)
class AdmittedUniverse:
    """The semantic phase's handoff: what exists, and what each image must teach."""

    universe_bytes: bytes
    universe_sha256: str
    universe_id: str
    title: str
    medium_id: str
    #: The source poster's own digest, not the review proxy's. The proxy is a
    #: re-encode, so binding it would make image identity depend on the imaging
    #: library's encoder rather than on the world the images are drawn from.
    poster_sha256: str
    proposal: UniverseProposal
    plan: GalleryPlan

    def entity_ids(self) -> tuple[str, ...]:
        return tuple(entity.entity_id for entity in self.proposal.entities)


def admitted_universe_from_bytes(data: bytes, *, poster_sha256: str) -> AdmittedUniverse:
    """Parse one admitted-universe document, whoever wrote it."""

    try:
        value = json.loads(data)
    except json.JSONDecodeError as error:
        raise ValueError(f"unreadable admitted universe: {error}") from None
    if not isinstance(value, dict):
        raise ValueError("admitted universe must be a JSON object")
    if value.get("schema_version") != 1 or value.get("kind") != "universe-admitted-v1":
        raise ValueError("unsupported admitted universe document")
    if value.get("publication_authorized") is not False:
        raise ValueError("admitted universe must state publication_authorized = false")
    proposal = UniverseProposal.model_validate(value["proposal"])
    plan = GalleryPlan.model_validate(value["plan"])
    planned = {item.entity_id for item in plan.plans}
    proposed = {entity.entity_id for entity in proposal.entities}
    if planned != proposed:
        raise ValueError("admitted universe plans a different entity set than it proposes")
    return AdmittedUniverse(
        universe_bytes=data,
        universe_sha256=content_sha256(data),
        universe_id=str(value["universe_id"]),
        title=str(value["title"]),
        medium_id=str(value["medium_id"]),
        poster_sha256=poster_sha256,
        proposal=proposal,
        plan=plan,
    )


def admitted_universe_from_document(path: Path, *, poster_sha256: str) -> AdmittedUniverse:
    """Read one standalone admitted-universe document, as a fixture supplies it."""

    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError(f"unreadable admitted universe document: {error}") from None
    return admitted_universe_from_bytes(data, poster_sha256=poster_sha256)


def load_admitted_universe(semantic_run_dir: Path, *, poster_sha256: str) -> AdmittedUniverse:
    """Read an admitted universe out of a finished semantic run directory."""

    universe_path = semantic_run_dir / SEMANTIC_UNIVERSE_REF
    admission_path = semantic_run_dir / SEMANTIC_ADMISSION_REF
    if not universe_path.is_file() or not admission_path.is_file():
        raise ValueError("semantic run is not admitted: universe.json or admission.json missing")
    data = universe_path.read_bytes()
    try:
        admission = json.loads(admission_path.read_bytes())
    except json.JSONDecodeError as error:
        raise ValueError(f"unreadable semantic admission: {error}") from None
    if not isinstance(admission, dict):
        raise ValueError("semantic admission must be a JSON object")
    universe_binding = admission.get("universe")
    bound = universe_binding.get("sha256") if isinstance(universe_binding, dict) else None
    if admission.get("semantic_status") != "pass" or bound != content_sha256(data):
        raise ValueError("admission record does not bind the current universe bytes")
    return admitted_universe_from_bytes(data, poster_sha256=poster_sha256)


def read_poster_proxy(semantic_run_dir: Path) -> bytes:
    """The downscaled poster the semantic run observed, carried into the gallery run."""

    path = semantic_run_dir / POSTER_PROXY_REF
    if not path.is_file():
        raise ValueError(f"semantic run has no poster proxy at {POSTER_PROXY_REF}")
    return path.read_bytes()


def resolve_sample_ledger(
    *,
    universe_id: str,
    entity_ids: Sequence[str],
    prior: Path | None = None,
    rerolls: Sequence[str] = (),
) -> SampleLedger:
    """Which draw each entity gets this run: carried forward, then incremented.

    A ledger is total over the planned entities, so every image node's identity
    names its draw explicitly instead of defaulting to one; a later reroll then
    moves exactly the branch it names.
    """

    known = list(dict.fromkeys(entity_ids))
    samples = dict.fromkeys(known, 0)
    if prior is not None:
        carried = _read_sample_ledger(prior)
        if carried.universe_id != universe_id:
            raise ValueError(
                f"sample ledger is for {carried.universe_id!r}, not {universe_id!r}",
            )
        unknown = sorted(set(carried.samples) - set(known))
        if unknown:
            raise ValueError(f"sample ledger names entities this universe does not plan: {unknown}")
        samples.update(carried.samples)
    unknown_rerolls = sorted({entity_id for entity_id in rerolls if entity_id not in samples})
    if unknown_rerolls:
        raise ValueError(f"cannot reroll entities this universe does not plan: {unknown_rerolls}")
    for entity_id in rerolls:
        samples[entity_id] += 1
    return SampleLedger(
        schema_version=1,
        kind="universe-sample-ledger-v1",
        universe_id=universe_id,
        samples=samples,
    )


def _read_sample_ledger(path: Path) -> SampleLedger:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"unreadable sample ledger: {error}") from None
    return SampleLedger.model_validate(value)


__all__ = [
    "POSTER_PROXY_REF",
    "SEMANTIC_ADMISSION_REF",
    "SEMANTIC_UNIVERSE_REF",
    "UNIVERSE_DOCUMENT_NAME",
    "AdmittedUniverse",
    "ResolvedUniverseSource",
    "admitted_universe_from_bytes",
    "admitted_universe_from_document",
    "direction_requirements",
    "load_admitted_universe",
    "read_poster_proxy",
    "read_universe_document",
    "resolve_sample_ledger",
    "resolve_universe_source",
    "synopsis_paragraphs",
]

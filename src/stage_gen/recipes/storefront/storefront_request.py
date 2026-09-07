"""Resolve one authored storefront package, touching no provider.

A storefront package is a directory: ``storefront.toml`` beside the positioning
note and the ``references/`` art the look is read from. It normally sits inside a
game package, next to ``game.toml``, but it is resolved on its own terms and
reads none of the game's runtime contracts — so a storefront can be drawn before
the game it fronts is playable.

Reference bytes are matched against the digest the author recorded, so nothing is
ever drawn against art that silently changed underneath the package.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from stage_gen.canonical import content_sha256
from stage_gen.components._authored_package import read_digest_bound_member, read_package_member
from stage_gen.recipes.storefront.models import DrawLedger, StorefrontSource
from stage_gen.recipes.storefront.surfaces import Surface, SurfaceSource, surface

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

STOREFRONT_DOCUMENT_NAME = "storefront.toml"

#: Run-relative refs the recipe writes. The per-surface ones are functions rather
#: than f-strings spelled out twice: the graph declares a port at one address and
#: the handler reads its upstream at the same one, and two literals that have to
#: agree are two literals that eventually do not.
DIRECTION_REF = "production/direction.json"
LISTING_REF = "package/listing.json"
INVENTORY_REF = "package/inventory.json"
DRAW_LEDGER_REF = "draw-ledger.json"


def drawn_ref(surface_id: str) -> str:
    """What the provider returned, before the cut to the ship canvas."""

    return f"production/drawn/{surface_id}.png"


def shipped_ref(surface_id: str) -> str:
    """What the package contains: the exact ship canvas."""

    return f"package/surfaces/{surface_id}.png"


def validation_ref(surface_id: str) -> str:
    return f"package/surfaces/{surface_id}.validation.json"


def record_ref(surface_id: str) -> str:
    return f"package/surfaces/{surface_id}.json"


def proxy_ref(surface_id: str) -> str:
    return f"production/review/{surface_id}.png"


def review_ref(surface_id: str) -> str:
    return f"production/review/{surface_id}.json"


class CaptureNotAvailableError(ValueError):
    """A package asked for a still of real play, which cannot be produced yet.

    Raised while resolving, before any spend, and named rather than silently
    substituted: a package that asks for a captured frame and receives a drawn
    one has been answered with something else without being told.
    """


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    """One authored reference picture, read and digest-bound."""

    reference_id: str
    source: str
    sha256: str
    data: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class ResolvedStorefront:
    """One authored storefront package, materialized for planning."""

    source: StorefrontSource
    source_sha256: str
    positioning_text: str
    positioning_sha256: str
    references: tuple[ResolvedReference, ...]
    draws: DrawLedger

    @property
    def storefront_id(self) -> str:
        return self.source.storefront_id

    @property
    def title(self) -> str:
        return self.source.display_name

    def reference_digests(self) -> tuple[str, ...]:
        return tuple(reference.sha256 for reference in self.references)

    def declared(self, surface_id: str) -> Surface:
        return surface(self.source.surface(surface_id).kind.value)

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "storefront-identity-v1",
            "storefront_id": self.storefront_id,
            "source_sha256": self.source_sha256,
            "positioning_sha256": self.positioning_sha256,
            "reference_sha256": list(self.reference_digests()),
            "surface_ids": [item.surface_id for item in self.source.surfaces],
            "publication_authorized": False,
        }


def read_storefront_document(root: Path) -> object:
    """Parse ``storefront.toml`` out of one authored package directory."""

    try:
        return tomllib.loads((root / STOREFRONT_DOCUMENT_NAME).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"unreadable storefront source document: {error}") from None


def _media_type(source: str) -> str:
    suffix = Path(source).suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    raise ValueError(f"reference {source!r} must be a .png, .jpg or .webp picture")


def resolve_storefront(
    document: object,
    *,
    root: Path,
    draws: DrawLedger | None = None,
) -> ResolvedStorefront:
    """Validate and materialize everything the plan needs, touching no provider."""

    source = StorefrontSource.model_validate(document)
    refused = [item.surface_id for item in source.surfaces if item.source is SurfaceSource.CAPTURE]
    if refused:
        raise CaptureNotAvailableError(
            "these surfaces ask for a still captured from real play, which this "
            f"repository cannot produce yet: {refused}. Deterministic play-and-capture "
            "is not built; a captured frame will enter as an authored input and run the "
            "same normalize, validate, review and record chain. Until then, set "
            'source = "generated" to draw the still, or drop the surface.'
        )
    positioning = read_package_member(root, source.positioning.source, label="positioning note")
    references = tuple(
        ResolvedReference(
            reference_id=reference.reference_id,
            source=reference.source,
            sha256=reference.source_sha256,
            data=read_digest_bound_member(
                root,
                reference.source,
                expected_sha256=reference.source_sha256,
                label=f"storefront reference {reference.reference_id}",
            ),
            media_type=_media_type(reference.source),
        )
        for reference in source.references
    )
    ledger = draws or empty_ledger(source.storefront_id)
    if ledger.storefront_id != source.storefront_id:
        raise ValueError(
            f"draw ledger is for {ledger.storefront_id!r}, not this storefront package"
        )
    unknown = sorted(set(ledger.draws) - {item.surface_id for item in source.surfaces})
    if unknown:
        raise ValueError(f"draw ledger names surfaces this package does not declare: {unknown}")
    return ResolvedStorefront(
        source=source,
        source_sha256=content_sha256((root / STOREFRONT_DOCUMENT_NAME).read_bytes()),
        positioning_text=positioning.decode("utf-8"),
        positioning_sha256=content_sha256(positioning),
        references=references,
        draws=ledger,
    )


def empty_ledger(storefront_id: str) -> DrawLedger:
    return DrawLedger(
        schema_version=1, kind="storefront-draw-ledger-v1", storefront_id=storefront_id, draws={}
    )


def read_draw_ledger(path: Path) -> DrawLedger:
    return DrawLedger.model_validate_json(path.read_bytes())


def apply_rerolls(ledger: DrawLedger, surface_ids: Iterable[str]) -> DrawLedger:
    """Advance one draw index per named surface; everything else stays a cache hit."""

    draws = dict(ledger.draws)
    for surface_id in surface_ids:
        draws[surface_id] = draws.get(surface_id, 0) + 1
    return ledger.model_copy(update={"draws": draws})


def ledger_bytes(ledger: DrawLedger) -> bytes:
    return (
        json.dumps(ledger.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def surface_order(resolved: ResolvedStorefront) -> Sequence[str]:
    """Authored order, which is the order the plan and the package both read in."""

    return [item.surface_id for item in resolved.source.surfaces]


__all__ = [
    "DIRECTION_REF",
    "DRAW_LEDGER_REF",
    "INVENTORY_REF",
    "LISTING_REF",
    "STOREFRONT_DOCUMENT_NAME",
    "CaptureNotAvailableError",
    "ResolvedReference",
    "ResolvedStorefront",
    "apply_rerolls",
    "empty_ledger",
    "ledger_bytes",
    "read_draw_ledger",
    "drawn_ref",
    "proxy_ref",
    "read_storefront_document",
    "record_ref",
    "resolve_storefront",
    "review_ref",
    "shipped_ref",
    "surface_order",
    "validation_ref",
]

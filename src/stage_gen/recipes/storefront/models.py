"""Storefront contracts: what a package declares, and what generation returns.

Field names use lower_snake_case; there are no compatibility aliases. Every model
forbids unknown keys, so a misspelled surface key is a resolution error rather
than a silently ignored intent four provider calls later.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from stage_gen.recipes.storefront.surfaces import SurfaceKind, SurfaceSource, surface

StableId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,95}$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, Field(min_length=1)]
Grade = Literal["pass", "fail"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- the authored package ----------------------------------------------------


class SourceDocument(ContractModel):
    source: Text


class ReferenceImage(ContractModel):
    """One authored picture attached to every surface call.

    ``role`` is stated rather than assumed: these are the game's own art, read
    for its grammar — palette, light, line, subject — and not a layout to copy.
    """

    reference_id: StableId
    source: Text
    source_sha256: Sha256
    role: Literal["visual_evidence_and_art_grammar_only"] = "visual_evidence_and_art_grammar_only"


class AuthoredSurface(ContractModel):
    """One surface the package asks for, and the one prompt that is its own."""

    surface_id: StableId
    kind: SurfaceKind
    source: SurfaceSource = SurfaceSource.GENERATED
    brief: Text


class SourceRights(ContractModel):
    #: The engine's own rights vocabulary, minus the approved value: an authored
    #: package states what it knows about its inputs and never asserts that the
    #: output may be redistributed.
    status: Literal["unreviewed", "restricted"]
    basis: list[Text] = Field(default_factory=list)
    #: Generation is exploration. Publication is a separate human decision, so
    #: the authored package can never assert it.
    publication_authorized: Literal[False]


class StorefrontSource(ContractModel):
    """One authored storefront package: ``storefront.toml`` and what it names."""

    schema_version: Literal[1]
    kind: Literal["storefront-source-v1"]
    storefront_id: StableId
    display_name: Text
    revision: int = Field(ge=1)
    # No medium field. Universe needs one because it compiles concepts before it
    # has seen anything; a storefront package always ships the game's own art, so
    # the look is read off the references and sealed in the compiled direction
    # rather than named by a taxonomy keyword the author has to learn.
    positioning: SourceDocument
    references: list[ReferenceImage] = Field(min_length=1, max_length=8)
    surfaces: list[AuthoredSurface] = Field(min_length=1, max_length=16)
    rights: SourceRights

    @model_validator(mode="after")
    def ids_are_unique(self) -> StorefrontSource:
        for label, values in (
            ("reference_id", [item.reference_id for item in self.references]),
            ("surface_id", [item.surface_id for item in self.surfaces]),
        ):
            duplicates = sorted({value for value in values if values.count(value) > 1})
            if duplicates:
                raise ValueError(f"duplicate {label}: {duplicates}")
        return self

    def surface(self, surface_id: str) -> AuthoredSurface:
        for item in self.surfaces:
            if item.surface_id == surface_id:
                return item
        raise KeyError(f"no authored surface {surface_id!r}")


# --- what generation returns -------------------------------------------------


class StorefrontDirection(ContractModel):
    """The look every surface inherits, compiled once from the references.

    One shared contract rather than a clause repeated in every brief: the whole
    reason the storefront reads as one product is that the icon, the stills and
    the banner were drawn under the same sentence about light and palette.
    """

    schema_version: Literal[1]
    kind: Literal["storefront-direction-v1"]
    storefront_id: StableId
    #: What the storefront is selling, in one line, in the game's own terms.
    proposition: Text
    #: Read off the references, not invented: the palette, the light, the line.
    palette: Text
    light: Text
    rendering: Text
    #: The subject that recurs across surfaces so they read as one set.
    recurring_subject: Text
    #: What every surface must avoid, stated once.
    avoid: list[Text] = Field(min_length=1, max_length=12)


class StoreListing(ContractModel):
    """The words beside the pictures. Lengths are the storefronts' own limits."""

    schema_version: Literal[1]
    kind: Literal["storefront-listing-v1"]
    storefront_id: StableId
    app_name: Annotated[str, Field(min_length=1, max_length=30)]
    subtitle: Annotated[str, Field(min_length=1, max_length=30)]
    short_description: Annotated[str, Field(min_length=1, max_length=80)]
    long_description: Annotated[str, Field(min_length=1, max_length=4000)]
    keywords: list[Annotated[str, Field(min_length=1, max_length=24)]] = Field(
        min_length=3, max_length=12
    )
    promotional_text: Annotated[str, Field(min_length=1, max_length=170)]


class SurfaceReview(ContractModel):
    """An independent verdict on one drawn surface, judged from its proxy.

    A rejection is a result, not a failure: the run still reaches its terminal
    and the package records a status for every surface, because redrawing one is
    a deliberate, priced decision rather than an automatic retry.
    """

    schema_version: Literal[1]
    kind: Literal["storefront-surface-review-v1"]
    surface_id: StableId
    #: Does it do the job this surface kind exists to do?
    fitness: Grade
    #: Does it look like the same product as the references?
    direction_fidelity: Grade
    #: Legibility at the size this surface is actually seen at.
    legibility: Grade
    #: Lettering is refused on every surface: the storefront draws its own.
    free_of_lettering: Grade
    verdict: Grade
    notes: list[Text] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def verdict_follows_the_grades(self) -> SurfaceReview:
        grades = (self.fitness, self.direction_fidelity, self.legibility, self.free_of_lettering)
        expected = "pass" if all(grade == "pass" for grade in grades) else "fail"
        if self.verdict != expected:
            raise ValueError(f"verdict must be {expected!r} given the four grades")
        return self


# --- reroll ledger -----------------------------------------------------------


class DrawLedger(ContractModel):
    """Which draw of each surface this run asks for.

    Cache keys are deterministic, so a rejected picture cannot be redrawn by
    running again: the same key restores the same image. The draw index is the
    one input that exists to be changed by hand, and it enters only the image
    node's identity, so rerolling one surface leaves the direction, the listing
    and every other surface as cache hits.
    """

    schema_version: Literal[1]
    kind: Literal["storefront-draw-ledger-v1"]
    storefront_id: StableId
    draws: dict[StableId, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def draws_are_indices(self) -> DrawLedger:
        negative = sorted(key for key, value in self.draws.items() if value < 0)
        if negative:
            raise ValueError(f"draw index must not be negative: {negative}")
        return self

    def draw(self, surface_id: str) -> int:
        return self.draws.get(surface_id, 0)


def ship_canvas(kind: SurfaceKind) -> tuple[int, int]:
    """The exact canvas one surface kind ships, read off the closed table."""

    declared = surface(kind.value)
    return declared.ship_width, declared.ship_height


__all__ = [
    "AuthoredSurface",
    "ContractModel",
    "DrawLedger",
    "ReferenceImage",
    "Sha256",
    "SourceDocument",
    "SourceRights",
    "StableId",
    "StoreListing",
    "StorefrontDirection",
    "StorefrontSource",
    "SurfaceReview",
    "Text",
    "ship_canvas",
]

"""The closed table of storefront surfaces: what ships, and what is drawn to get it.

A store surface is defined by an exact pixel canvas that a storefront will refuse
if it is off by one. A provider is not that kind of instrument: the image route
advertises aspect ratios and accepts the route's verified flexible-size request,
and what comes back still has to be inspected rather than assumed
(docs/models/gpt-image-2.5.md). So every surface
carries two canvases, and they are different columns on purpose:

``draw`` is what the provider is asked for — sized to what the route draws well,
at the ship canvas's own ratio so the crop that follows is a trim and not a
recomposition. ``ship`` is what the package contains, reached by a deterministic
local normalization the recipe owns. When the two are equal the normalization is
a re-encode and says so.

Nothing here is a real storefront's vocabulary. The pixel canvases are public
platform requirements; the names, the prose and the framing are this repository's.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class SurfaceKind(StrEnum):
    """Every surface this recipe knows how to draw. An id outside it is refused."""

    APP_ICON = "app_icon"
    STORE_STILL_PORTRAIT = "store_still_portrait"
    STORE_STILL_LANDSCAPE = "store_still_landscape"
    FEATURE_GRAPHIC = "feature_graphic"


class SurfaceSource(StrEnum):
    """Where a surface's picture comes from.

    ``CAPTURE`` is declared here and refused while planning: a still of real play
    needs a deterministic play-and-capture harness this repository does not have
    yet. It is in the vocabulary so a package can say what it wants and be told
    why it cannot have it, rather than discovering a silent substitution in the
    output. When the harness lands, a captured still enters as an authored input
    and runs the same normalize, validate, review and record chain below it.
    """

    GENERATED = "generated"
    CAPTURE = "capture"


@dataclass(frozen=True, slots=True)
class Surface:
    """One surface's geometry, its output contract, and what it is for."""

    kind: SurfaceKind
    title: str
    #: The canvas the package ships. Exact; a storefront rejects anything else.
    ship_width: int
    ship_height: int
    #: The canvas the provider is asked to draw, at the ship ratio.
    draw_width: int
    draw_height: int
    #: Every storefront surface is opaque. The icon is stricter: a storefront
    #: refuses an icon that carries an alpha channel at all, even a fully
    #: opaque one, so this is "has no alpha band", not "is not see-through".
    forbids_alpha_channel: bool
    #: A ceiling, not a target. A file past it is a defect, not a big picture.
    max_bytes: int
    #: Told to the direction compiler and to the reviewer, in these words.
    purpose: str

    @property
    def ship_size(self) -> str:
        return f"{self.ship_width}x{self.ship_height}"

    @property
    def draw_size(self) -> str:
        return f"{self.draw_width}x{self.draw_height}"

    @property
    def resizes(self) -> bool:
        """Whether normalization does real work, or is the re-encode branch."""

        return (self.draw_width, self.draw_height) != (self.ship_width, self.ship_height)

    def __post_init__(self) -> None:
        """Refuse a draw canvas the bound route will not accept, at import.

        Both rules were learned the expensive way. The route requires every edge
        to be a multiple of 16 and says so only when the request is already in
        flight, so a table entry that breaks it costs six attempts per surface
        before anything explains why — the check belongs here, where the number
        is written, not at the provider. And the draw canvas has to sit at the
        ship canvas's own ratio, or the cut that follows stops being a trim and
        starts recomposing the picture by cropping its sides off.
        """

        for edge, label in (
            (self.draw_width, "draw_width"),
            (self.draw_height, "draw_height"),
        ):
            if edge % DRAW_EDGE_MULTIPLE:
                raise ValueError(
                    f"{self.kind.value}: {label} {edge} is not a multiple of "
                    f"{DRAW_EDGE_MULTIPLE}; the image route refuses it"
                )
        drift = abs(self.draw_width / self.draw_height - self.ship_width / self.ship_height) / (
            self.ship_width / self.ship_height
        )
        if drift > MAX_RATIO_DRIFT:
            raise ValueError(
                f"{self.kind.value}: the draw canvas {self.draw_size} is {drift:.3%} "
                f"off the ship ratio {self.ship_size}; the cut would recompose the "
                "picture rather than trim it"
            )


#: 2560 is the long edge the image route draws at without argument, proven by the
#: universe recipe's gallery. A ship canvas past that is drawn near it and scaled
#: up by the normalization; a much smaller one is drawn large and scaled down,
#: which is the cheap way to buy detail the storefront will actually show.
DRAW_LONG_EDGE: Final = 2560

#: Every edge the image route is asked for must be a multiple of this. Universe's
#: canvases all happen to satisfy it, which is how the rule stayed invisible until
#: a table copied their magnitude without their arithmetic.
DRAW_EDGE_MULTIPLE: Final = 16

#: How far a draw canvas may sit from its ship ratio. Past this the centre-crop
#: is cutting content off the sides rather than trimming rounding.
MAX_RATIO_DRIFT: Final = 0.001

SURFACES: Final[dict[SurfaceKind, Surface]] = {
    SurfaceKind.APP_ICON: Surface(
        kind=SurfaceKind.APP_ICON,
        title="App icon",
        ship_width=1024,
        ship_height=1024,
        # Drawn at its own size. An icon is read at sixty pixels on a home screen,
        # so detail bought above 1024 is detail nobody will ever see, and the icon
        # is the one surface where a square native canvas is exactly the request.
        draw_width=1024,
        draw_height=1024,
        forbids_alpha_channel=True,
        max_bytes=8 * 1024 * 1024,
        purpose=(
            "One mark that stays legible at sixty pixels: a single subject, one "
            "silhouette, no lettering, no interface, no border and no rounded "
            "corner drawn into the art — the platform applies its own mask."
        ),
    ),
    SurfaceKind.STORE_STILL_PORTRAIT: Surface(
        kind=SurfaceKind.STORE_STILL_PORTRAIT,
        title="Store preview still, portrait",
        ship_width=1290,
        ship_height=2796,
        # 1152x2496 rather than the 2560-tall canvas the other surfaces use: it is
        # the tallest pair of sixteen-multiples that lands within 0.04% of this
        # ship ratio, and the ratio matters more than the last 10% of height.
        draw_width=1152,
        draw_height=2496,
        forbids_alpha_channel=False,
        max_bytes=16 * 1024 * 1024,
        purpose=(
            "One upright frame that shows what playing this is like: the world "
            "and the moment, read top to bottom, with room at the top for the "
            "caption the listing adds over it."
        ),
    ),
    SurfaceKind.STORE_STILL_LANDSCAPE: Surface(
        kind=SurfaceKind.STORE_STILL_LANDSCAPE,
        title="Store preview still, landscape",
        ship_width=2796,
        ship_height=1290,
        draw_width=2496,
        draw_height=1152,
        forbids_alpha_channel=False,
        max_bytes=16 * 1024 * 1024,
        purpose=(
            "The same moment read left to right: a wide frame where the world "
            "extends past both edges and the subject sits off centre."
        ),
    ),
    SurfaceKind.FEATURE_GRAPHIC: Surface(
        kind=SurfaceKind.FEATURE_GRAPHIC,
        title="Feature graphic",
        ship_width=1024,
        ship_height=500,
        # Drawn twice over and scaled down: this banner is cropped hard by the
        # surfaces that show it, and the detail survives the downscale.
        draw_width=2064,
        draw_height=1008,
        forbids_alpha_channel=False,
        max_bytes=8 * 1024 * 1024,
        purpose=(
            "A wide banner whose middle survives being cropped to a square: the "
            "subject centred, the sides quiet, and no lettering anywhere."
        ),
    ),
}


def surface(kind: str) -> Surface:
    """The declared surface for one kind; an unknown kind is refused by name."""

    try:
        return SURFACES[SurfaceKind(kind)]
    except ValueError:
        known = ", ".join(sorted(member.value for member in SurfaceKind))
        raise ValueError(
            f"unknown storefront surface kind {kind!r}; known kinds: {known}"
        ) from None


def surfaces_digest_material() -> tuple[str, ...]:
    """Every geometry fact an image node's identity depends on, in a stable order.

    A surface whose ship canvas or draw canvas moved is a different picture, and
    the picture drawn to the superseded canvas is not a valid answer to the new
    question — so this material rides the image tier's digest.
    """

    return tuple(
        f"{item.kind.value}:{item.draw_size}->{item.ship_size}:"
        f"alpha_channel_forbidden={int(item.forbids_alpha_channel)}"
        for item in (SURFACES[kind] for kind in SurfaceKind)
    )


__all__ = [
    "DRAW_LONG_EDGE",
    "SURFACES",
    "Surface",
    "SurfaceKind",
    "SurfaceSource",
    "surface",
    "surfaces_digest_material",
]

"""The shell's screen geometry: what a layout id resolves to, and what it reserves.

A layout id is the whole authored geometry, exactly as it is for a UI atlas role: a
package names a layout and never writes a rectangle. What is different here is *why*
the rectangles exist. A UI role's cells say where the art goes; a shell layout's rects
say where the art must **stay out of the way** — the band the wordmark is set in, the
column the control stack occupies, the strip a card or a tip is read from. They are
reserved regions, and the gate measures them on the plate the model returned.

Every shell plate is one 2560 by 1440 canvas: the native 16:9 size the bound image
route already draws for the universe recipe's wide mode (``WIDE_SIZE``), so this
family invents no raster shape.

Rects are canvas pixels. A consumer scales the whole canvas to its window and scales
every rect by the same factor, so nothing here is a screen size.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The one canvas this family draws on: native 16:9 on the bound image route.
SHELL_CANVAS: tuple[int, int] = (2560, 1440)

#: A backdrop is a picture with no holes; a mark or an emblem is a shape on air.
OPAQUE_ALPHA_POLICY = "fully_opaque_v1"
CUTOUT_ALPHA_POLICY = "transparent_exterior_v1"

TITLE_SCREEN_LAYOUT = "title_screen_16x9_v1"
LOADING_SCREEN_LAYOUT = "loading_screen_16x9_v1"
OPENING_LAYOUT = "opening_16x9_v1"
OPENING_CLIP_LAYOUT = "opening_clip_16x9_v1"

#: How a still shot is moved over its seconds. The host owns the easing; the document
#: owns only which move, because only the feel depends on the rest.
SHOT_MOVES: tuple[str, ...] = ("hold", "push_in", "pull_out", "pan_left", "pan_right")
#: How one shot leaves for the next. ``wipe`` defers to the screen-FX plate.
SHOT_TRANSITIONS: tuple[str, ...] = ("cut", "dissolve", "wipe")

#: A depth role for a parallax layer, far to near. The first is the opaque picture; the
#: rest are cut-outs drawn over it and drifted at their own rate by the host.
BACKDROP_DEPTHS: tuple[str, ...] = ("far", "mid", "near")


@dataclass(frozen=True, slots=True)
class Rect:
    """A canvas-pixel rectangle, published as-is for a consumer to scale."""

    x: int
    y: int
    width: int
    height: int

    def record(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True, slots=True)
class ShellLayout:
    """One screen's declared geometry: the canvas, and the regions kept quiet.

    ``reserved`` maps a region name to the rect the gate measures for flatness and
    contrast. A region is quiet or the plate is refused, because a title whose wordmark
    lands on a busy centre is unreadable however good the painting is — and that is a
    failure no reviewer should have to catch and no author can prevent by prompting.

    ``drift`` is how far, in canvas pixels, the host may move a parallax layer from
    centre in each direction. The gate measures each reserved region over the union of
    that drift, so a region that is quiet in the still frame but slides under a tree
    branch is refused while it is still cheap to redraw.
    """

    layout: str
    reserved: tuple[tuple[str, Rect], ...]
    drift: int = 0
    canvas: tuple[int, int] = SHELL_CANVAS

    def __post_init__(self) -> None:
        if not self.reserved:
            raise ValueError(f"{self.layout} reserves no region")
        names = [name for name, _ in self.reserved]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.layout} names a reserved region twice")
        width, height = self.canvas
        if self.drift < 0 or 2 * self.drift >= min(width, height):
            raise ValueError(f"{self.layout} drift does not fit its canvas")
        for name, rect in self.reserved:
            if rect.width <= 0 or rect.height <= 0:
                raise ValueError(f"{self.layout} region {name} is empty")
            if rect.x < 0 or rect.y < 0:
                raise ValueError(f"{self.layout} region {name} starts outside the canvas")
            if rect.x + rect.width > width or rect.y + rect.height > height:
                raise ValueError(f"{self.layout} region {name} leaves the canvas")

    def region(self, name: str) -> Rect:
        for candidate, rect in self.reserved:
            if candidate == name:
                return rect
        raise KeyError(f"{self.layout} reserves no region {name!r}")

    def region_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.reserved)

    def drift_union(self, name: str) -> Rect:
        """The region grown by the drift the host may apply, which is what the gate reads.

        A still layout drifts by zero and this is the region itself.
        """

        rect = self.region(name)
        width, height = self.canvas
        left = max(0, rect.x - self.drift)
        top = max(0, rect.y - self.drift)
        right = min(width, rect.x + rect.width + self.drift)
        bottom = min(height, rect.y + rect.height + self.drift)
        return Rect(left, top, right - left, bottom - top)

    def geometry_record(self) -> dict[str, object]:
        """The declared geometry as a portable record; part of the generation cache key.

        The record is hashed rather than any rendered guide, so a change to how a guide
        is drawn cannot re-bill a plate while a change to the geometry must.
        """

        return {
            "layout": self.layout,
            "canvas": {"width": self.canvas[0], "height": self.canvas[1]},
            "drift": self.drift,
            "reserved": [{"region": name, "rect": rect.record()} for name, rect in self.reserved],
        }


#: The title screen. The mark band is the upper third's centre, where a wordmark and an
#: emblem sit together; the control stack is the column of buttons below it. Both are
#: measured over a 96-pixel drift, because the host parallaxes the layers behind them.
TITLE_SCREEN = ShellLayout(
    layout=TITLE_SCREEN_LAYOUT,
    reserved=(
        ("mark_band", Rect(x=512, y=180, width=1536, height=460)),
        ("control_stack", Rect(x=960, y=760, width=640, height=480)),
    ),
    drift=96,
)

#: The loading screen. One strip at the foot holds the progress readout and the tip, and
#: nothing parallaxes, so the drift is zero.
LOADING_SCREEN = ShellLayout(
    layout=LOADING_SCREEN_LAYOUT,
    reserved=(("status_strip", Rect(x=256, y=1120, width=2048, height=240)),),
)

#: An opening shot. The card band is the lower third a line of authored text is set in.
#: A shot that carries no card is not measured against it: the region is reserved for
#: the shots that use it, and gating a full-bleed establishing shot on a band nothing is
#: drawn in would refuse good pictures for nothing.
OPENING_SHOT = ShellLayout(
    layout=OPENING_LAYOUT,
    reserved=(("card_band", Rect(x=320, y=1020, width=1920, height=300)),),
)

#: An opening shot that is a clip. The same screen and the same reserved card band as a
#: still shot, on the canvas a video route actually draws: 1920 by 1080 rather than the
#: 2560 by 1440 the image route uses. The proportions are identical because both are
#: 16:9, which is why a card band published against either lands in the same place - a
#: host scales the whole canvas to its window and every rect by the same factor. That
#: invariant is what the clip gate's aspect check is protecting.
#:
#: The resolution is a property of the layout rather than of the document because a
#: package names a layout and never writes a rectangle. A second rung on the route's
#: ladder would be a second layout id, not a field.
OPENING_CLIP = ShellLayout(
    layout=OPENING_CLIP_LAYOUT,
    reserved=(("card_band", Rect(x=160, y=510, width=960, height=150)),),
    canvas=(1280, 720),
)

SHELL_LAYOUTS: dict[str, ShellLayout] = {
    layout.layout: layout for layout in (TITLE_SCREEN, LOADING_SCREEN, OPENING_SHOT, OPENING_CLIP)
}


__all__ = [
    "BACKDROP_DEPTHS",
    "CUTOUT_ALPHA_POLICY",
    "LOADING_SCREEN",
    "LOADING_SCREEN_LAYOUT",
    "OPAQUE_ALPHA_POLICY",
    "OPENING_CLIP",
    "OPENING_CLIP_LAYOUT",
    "OPENING_LAYOUT",
    "OPENING_SHOT",
    "Rect",
    "SHELL_CANVAS",
    "SHELL_LAYOUTS",
    "ShellLayout",
    "SHOT_MOVES",
    "SHOT_TRANSITIONS",
    "TITLE_SCREEN",
    "TITLE_SCREEN_LAYOUT",
]

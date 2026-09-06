"""Generated paintover templates.

The terrain atlas proved that a model will respect a lattice it can see: hand it
a plate ruled with cyan guides and magenta cells, tell it to paint inside them,
and the cells come back separable by measurement instead of by trust. The 12x4
terrain template is locked to the 47-mask tile topology, so this spike draws its
own N x M plate under the same colour contract and asks the same question of a
flame cycle.

Whether that generalises from tile masks to animation frames is one of the four
things this spike is meant to find out.
"""

from __future__ import annotations

from io import BytesIO
from typing import Final

from PIL import Image, ImageDraw

#: Must satisfy stage_gen.media.guide_lattice.CYAN_GUIDES: red < 80, green > 170,
#: blue > 170. Anything else and the lattice detector will not see the lines.
GUIDE_RGB: Final = (0, 214, 224)
#: The colour magenta_chroma_alpha keys to transparency.
MAGENTA_RGB: Final = (255, 0, 255)
GUIDE_WIDTH_PX: Final = 3
LATTICE_CELL_PX: Final = 256
#: The lattice's backing. Magenta was inherited from the terrain atlas, which
#: was designed before native alpha existed: the model painted opaque and the
#: backing was keyed out afterwards, and a keyed edge is an anti-aliased blend
#: that keeps a pink rim. With true alpha asked of the model there is nothing
#: to key: the template is cyan guides on a transparent canvas, the model
#: paints between them and leaves the rest clear, and the cells are cut with
#: the alpha they came with. One switch, so the old backing is one edit away.
LATTICE_TRANSPARENT: Final = True
#: A prop sheet's cell. Half a sprite's canvas on a side, a quarter of its
#: pixels: the price of drawing every look of a prop in one op at one scale.
SHEET_CELL_PX: Final = 512


def lattice_template(
    columns: int,
    rows: int,
    cell_px: int = LATTICE_CELL_PX,
    *,
    transparent: bool = LATTICE_TRANSPARENT,
) -> bytes:
    """A ruled grid: ``columns + 1`` by ``rows + 1`` cyan lines on transparent, or on magenta.

    The guide lines are drawn *inside* the canvas at the cell boundaries,
    including the outer edges, so the detector sees a complete lattice and the
    canvas edge is never mistaken for a line.
    """

    width = columns * cell_px
    height = rows * cell_px
    guide: tuple[int, ...]
    if transparent:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        guide = (*GUIDE_RGB, 255)
    else:
        image = Image.new("RGB", (width, height), MAGENTA_RGB)
        guide = GUIDE_RGB
    draw = ImageDraw.Draw(image)
    half = GUIDE_WIDTH_PX // 2
    for column in range(columns + 1):
        x = min(max(column * cell_px, half), width - half - 1)
        draw.line([(x, 0), (x, height - 1)], fill=guide, width=GUIDE_WIDTH_PX)
    for row in range(rows + 1):
        y = min(max(row * cell_px, half), height - half - 1)
        draw.line([(0, y), (width - 1, y)], fill=guide, width=GUIDE_WIDTH_PX)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def template_id(
    columns: int,
    rows: int,
    cell_px: int = LATTICE_CELL_PX,
    *,
    transparent: bool = LATTICE_TRANSPARENT,
) -> str:
    backing = "_alpha" if transparent else ""
    return f"oblique_survival_lattice_{columns}x{rows}_{cell_px}{backing}_v1"


def template_ref(
    columns: int,
    rows: int,
    cell_px: int = LATTICE_CELL_PX,
    *,
    transparent: bool = LATTICE_TRANSPARENT,
) -> str:
    """Where a lattice lives in a run. The 256-px magenta path predates the cell size."""

    backing = "-alpha" if transparent else ""
    if cell_px == LATTICE_CELL_PX:
        return f"production/templates/lattice-{columns}x{rows}{backing}.png"
    return f"production/templates/lattice-{columns}x{rows}-{cell_px}{backing}.png"


def backing_words(*, transparent: bool = LATTICE_TRANSPARENT) -> tuple[str, str]:
    """What a paintover prompt says about the space it does not paint: (leave, around)."""

    if transparent:
        return (
            "Leave everything you do not paint fully transparent: output true alpha, with no "
            "background colour anywhere.",
            "clear transparent space around it",
        )
    return ("Leave pure magenta everywhere you do not paint.", "clear magenta around it")

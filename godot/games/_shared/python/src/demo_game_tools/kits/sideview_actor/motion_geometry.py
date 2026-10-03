"""Canonical motion-strip geometry for side-view actors.

The one shape a motion strip is asked for, validated against, and repacked
into is camera-scoped: any side-view genre draws its actors as horizontal
strips on the same canvases. Which *states* an actor performs, and which of
them select a non-default geometry, is genre vocabulary and stays with the
genre's motion contract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

MotionSourceFacing = Literal["right", "back", "front"]

MOTION_ATLAS_COLUMNS = 4
MOTION_ATLAS_ROWS = 1
MOTION_ATLAS_REQUIRED_CELLS = 4
MOTION_ATLAS_WIDTH = 1536
MOTION_ATLAS_HEIGHT = 1024
CANONICAL_SIDE_SOURCE_FACING: Literal["right"] = "right"


@dataclass(frozen=True)
class MotionAtlasGeometry:
    """The one shape a motion strip is asked for, validated against, and repacked into.

    Registration is deliberately not here. How a strip is packed into cells is a property of what
    the model drew, so it is authored per motion as `MotionPresentation.anchor`; only the shape the
    provider is asked for is recipe-owned.

    Grid and canvas travel together because they are not independently valid: a cell is
    ``width / columns`` by ``height / rows``, and a cell whose aspect is far from the figure's
    wastes most of the pixels it is given. Measured on the climb states, four cells on the
    1536x1024 canvas gave a 283x737 figure while two cells on 2464x3328 gave 925x2957 - the same
    1:2.7 cell aspect, but no cell spent on a pose that duplicates its neighbour.
    """

    columns: int
    rows: int
    required_cells: int
    width: int
    height: int

    @property
    def provider_size(self) -> str:
        """The ``WIDTHxHEIGHT`` string the image request carries."""

        return f"{self.width}x{self.height}"

    @property
    def frame_word(self) -> str:
        """The cell count as a word, for the prompt sentence that asks for the strip."""

        try:
            return _FRAME_COUNT_WORDS[self.required_cells]
        except KeyError as error:
            raise ValueError(
                f"no prompt word for a {self.required_cells}-cell motion atlas"
            ) from error


#: Spelled out because the provider follows a written count more reliably than a digit, and only
#: the counts a motion atlas may actually carry are spelled.
_FRAME_COUNT_WORDS = {2: "two", 3: "three", 4: "four"}


DEFAULT_MOTION_ATLAS_GEOMETRY = MotionAtlasGeometry(
    columns=MOTION_ATLAS_COLUMNS,
    rows=MOTION_ATLAS_ROWS,
    required_cells=MOTION_ATLAS_REQUIRED_CELLS,
    width=MOTION_ATLAS_WIDTH,
    height=MOTION_ATLAS_HEIGHT,
)


def dialogue_atlas_grid(expression_count: int) -> tuple[int, int]:
    """Return the one provider and runtime topology for an expression atlas."""

    if expression_count <= 0:
        raise ValueError("dialogue expression count must be positive")
    if expression_count <= 4:
        return 2, 2
    return 3, math.ceil(expression_count / 3)


def runtime_mirrors_source(facing: MotionSourceFacing) -> bool:
    """Whether runtime creates the opposite gameplay facing by horizontal reflection."""

    return facing == CANONICAL_SIDE_SOURCE_FACING


__all__ = [
    "CANONICAL_SIDE_SOURCE_FACING",
    "DEFAULT_MOTION_ATLAS_GEOMETRY",
    "MOTION_ATLAS_COLUMNS",
    "MOTION_ATLAS_HEIGHT",
    "MOTION_ATLAS_REQUIRED_CELLS",
    "MOTION_ATLAS_ROWS",
    "MOTION_ATLAS_WIDTH",
    "MotionAtlasGeometry",
    "MotionSourceFacing",
    "dialogue_atlas_grid",
    "runtime_mirrors_source",
]

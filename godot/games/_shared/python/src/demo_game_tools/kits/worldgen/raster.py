"""Plates: RGBA masks rasterised from grids, discs and polylines, streamed.

A plate is data, never colour: a consumer samples it with no colour space,
and its alpha is a channel like any other. The caller decides what each
channel means; this module only fills, stamps and encodes.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from io import BytesIO
from typing import Final

from PIL import Image

#: Metres per plate cell at the finest a plate is drawn.
PLATE_CELL_METERS: Final = 0.25
#: The plate never exceeds this many cells a side: a 512 m world draws 0.5 m
#: cells. A consumer's finest structural signal is well above a cell either
#: way, and the memory of a pure-Python 2048² plate is not worth what it draws.
PLATE_CELLS_MAX: Final = 1024
PLATE_CELLS_MIN: Final = 16


def plate_cells(size_meters: float) -> int:
    return min(PLATE_CELLS_MAX, max(PLATE_CELLS_MIN, round(size_meters / PLATE_CELL_METERS)))


class Plate:
    """A square RGBA8 plate over a world ``size_meters`` across, row 0 at minimum z."""

    def __init__(self, cells: int, size_meters: float) -> None:
        self.cells = cells
        self.size = size_meters
        self.raw = bytearray(cells * cells * 4)

    @property
    def cell_meters(self) -> float:
        return self.size / self.cells

    def fill_channel(self, channel: int, rows: Iterable[Iterable[int]]) -> None:
        """Write one channel from streamed rows of 0..255 ints."""

        raw = self.raw
        cells = self.cells
        for j, row in enumerate(rows):
            base = j * cells * 4 + channel
            for i, value in enumerate(row):
                raw[base + i * 4] = value

    def fill_constant(self, channel: int, value: int) -> None:
        raw = self.raw
        for offset in range(channel, len(raw), 4):
            raw[offset] = value

    def stamp_disc(
        self,
        channel: int,
        x: float,
        z: float,
        radius_meters: float,
        *,
        gain: float,
        cap: float,
        power: int = 2,
    ) -> None:
        """Add ``gain * (1 - d/r)**power`` to a channel inside a disc, capped."""

        if radius_meters <= 0.0:
            return
        cells = self.cells
        half = self.size / 2.0
        cx = (x + half) / self.size * cells
        cz = (z + half) / self.size * cells
        cell_radius = radius_meters / self.size * cells
        lo_x, hi_x = int(cx - cell_radius) - 1, int(cx + cell_radius) + 2
        lo_z, hi_z = int(cz - cell_radius) - 1, int(cz + cell_radius) + 2
        raw = self.raw
        cap_byte = round(cap * 255.0)
        for row in range(max(0, lo_z), min(cells, hi_z)):
            for column in range(max(0, lo_x), min(cells, hi_x)):
                distance = math.hypot(column + 0.5 - cx, row + 0.5 - cz)
                if distance >= cell_radius:
                    continue
                falloff = (1.0 - distance / cell_radius) ** power
                offset = (row * cells + column) * 4 + channel
                raw[offset] = min(cap_byte, raw[offset] + round(falloff * gain * 255.0))

    def stamp_polyline(
        self, channel: int, points: Sequence[tuple[float, float]], width_meters: float, value: int
    ) -> None:
        """Set a channel inside a band of ``width_meters`` around a polyline."""

        if len(points) < 2 or width_meters <= 0.0:
            return
        cells = self.cells
        half = self.size / 2.0
        reach = width_meters / 2.0
        cell = self.cell_meters
        raw = self.raw
        for index in range(len(points) - 1):
            ax, az = points[index]
            bx, bz = points[index + 1]
            lo_x = int((min(ax, bx) - reach + half) / cell) - 1
            hi_x = int((max(ax, bx) + reach + half) / cell) + 2
            lo_z = int((min(az, bz) - reach + half) / cell) - 1
            hi_z = int((max(az, bz) + reach + half) / cell) + 2
            for row in range(max(0, lo_z), min(cells, hi_z)):
                z = (row + 0.5) * cell - half
                for column in range(max(0, lo_x), min(cells, hi_x)):
                    x = (column + 0.5) * cell - half
                    if segment_distance(x, z, ax, az, bx, bz) <= reach:
                        raw[(row * cells + column) * 4 + channel] = value

    def png(self) -> bytes:
        image = Image.frombytes("RGBA", (self.cells, self.cells), bytes(self.raw))
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


def segment_distance(px: float, pz: float, ax: float, az: float, bx: float, bz: float) -> float:
    dx = bx - ax
    dz = bz - az
    length_sq = dx * dx + dz * dz
    t = (
        0.0
        if length_sq <= 1e-9
        else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / length_sq))
    )
    return math.hypot(px - (ax + dx * t), pz - (az + dz * t))


def polyline_distance(x: float, z: float, points: Sequence[tuple[float, float]]) -> float:
    if not points:
        return math.inf
    if len(points) == 1:
        return math.hypot(x - points[0][0], z - points[0][1])
    return min(
        segment_distance(x, z, points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    )

"""Generic geometric capability contracts for offline route admission."""

from __future__ import annotations

import math
from typing import Self

from pydantic import ConfigDict, Field, model_validator

from gnode.contracts.artifacts import PersistedContractModel


class ExactSize2DV1(PersistedContractModel):
    """One exact positive two-dimensional output extent."""

    model_config = ConfigDict(frozen=True)

    width: int = Field(ge=1)
    height: int = Field(ge=1)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def longest_edge(self) -> int:
        return max(self.width, self.height)

    @property
    def aspect_ratio(self) -> float:
        return self.longest_edge / min(self.width, self.height)


class ExactSizeConstraints2DV1(PersistedContractModel):
    """Route limits for exact 2D extents, independent of modality or provider."""

    model_config = ConfigDict(frozen=True)

    width_multiple: int = Field(default=1, ge=1)
    height_multiple: int = Field(default=1, ge=1)
    min_area: int | None = Field(default=None, ge=1)
    max_area: int | None = Field(default=None, ge=1)
    max_edge: int | None = Field(default=None, ge=1)
    max_aspect_ratio: float | None = Field(default=None, ge=1.0)
    allowed_sizes: tuple[ExactSize2DV1, ...] | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if (
            self.min_area is not None
            and self.max_area is not None
            and self.min_area > self.max_area
        ):
            raise ValueError("exact size min_area must not exceed max_area")
        if self.max_aspect_ratio is not None and not math.isfinite(self.max_aspect_ratio):
            raise ValueError("exact size max_aspect_ratio must be finite")
        if self.allowed_sizes is not None:
            if not self.allowed_sizes:
                raise ValueError("exact size allowed_sizes must not be empty")
            pairs = tuple((size.width, size.height) for size in self.allowed_sizes)
            if pairs != tuple(sorted(set(pairs))):
                raise ValueError("exact size allowed_sizes must be unique and sorted")
        return self

    def failures(self, size: ExactSize2DV1) -> tuple[str, ...]:
        """Return every deterministic reason ``size`` violates this contract."""

        failures: list[str] = []
        if self.allowed_sizes is not None and size not in self.allowed_sizes:
            failures.append(f"size {size.width}x{size.height} is not an allowed exact size")
        if size.width % self.width_multiple:
            failures.append(f"width {size.width} is not a multiple of {self.width_multiple}")
        if size.height % self.height_multiple:
            failures.append(f"height {size.height} is not a multiple of {self.height_multiple}")
        if self.min_area is not None and size.area < self.min_area:
            failures.append(f"area {size.area} is below minimum {self.min_area}")
        if self.max_area is not None and size.area > self.max_area:
            failures.append(f"area {size.area} exceeds maximum {self.max_area}")
        if self.max_edge is not None and size.longest_edge > self.max_edge:
            failures.append(f"longest edge {size.longest_edge} exceeds maximum {self.max_edge}")
        if self.max_aspect_ratio is not None and size.aspect_ratio > self.max_aspect_ratio:
            failures.append(
                f"aspect ratio {size.aspect_ratio:g}:1 exceeds maximum {self.max_aspect_ratio:g}:1"
            )
        return tuple(failures)


__all__ = ["ExactSize2DV1", "ExactSizeConstraints2DV1"]

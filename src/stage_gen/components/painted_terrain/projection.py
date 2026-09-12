"""Projection constraints for independently generated structural ground paintings."""

from typing import Literal

from gnode import PersistedContractModel

GroundProjectionMode = Literal["orthographic_v1"]
DEFAULT_GROUND_PROJECTION: GroundProjectionMode = "orthographic_v1"


class GroundProjection(PersistedContractModel):
    """Parallel front elevation supported by the occupancy-preserving canonicalizer."""

    mode: GroundProjectionMode


__all__ = ["DEFAULT_GROUND_PROJECTION", "GroundProjection", "GroundProjectionMode"]

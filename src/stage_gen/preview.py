"""Application-owned artifact preview contracts.

GNode carries preview hints as JSON. A renderer selects a supported kind and
validates it before display. Historical motion hints remain a separate, bounded
contract so new preview capabilities do not reinterpret old artifact geometry.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from gnode import PersistedContractModel


class LegacyMotionPreview(PersistedContractModel):
    """The historical uniform 1..16 by 1 motion strip used by legacy views."""

    frame_count: int = Field(ge=1, le=16)
    mode: Literal["hold", "loop", "once", "gameplay_driven"] | None = None
    frames_per_second: float | None = Field(default=None, gt=0.0)
    canonical_frame_indices: tuple[int, ...] = ()


__all__ = ["LegacyMotionPreview"]

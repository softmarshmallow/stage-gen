"""Explicit caller policy for semantic review, separate from its quality bar."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

type ReviewMode = Literal["required", "none"]
REVIEW_MODES = ("required", "none")


def review_mode(experiment: Mapping[str, Any]) -> ReviewMode:
    """Omission retains required review, including existing frozen experiments."""
    mode = experiment.get("review_mode", "required")
    if not isinstance(mode, str) or mode not in REVIEW_MODES:
        raise ValueError("review_mode must be required or none")
    return cast(ReviewMode, mode)

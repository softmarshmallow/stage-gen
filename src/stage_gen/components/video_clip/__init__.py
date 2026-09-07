"""Objective admission for a generated clip, independent of what it is for."""

from .admission import (
    CLIP_ASPECT_RATIO,
    CLIP_ASPECT_TOLERANCE,
    CLIP_DURATION_TOLERANCE_SECONDS,
    CLIP_LUMA_LIVE_FRAME_BAND,
    CLIP_LUMA_MEAN_BAND,
    CLIP_MOTION_FLOOR_MEAN,
    ClipAdmissionError,
    admit_clip_bytes,
    admit_clip_file,
    clip_admission_facts,
)

__all__ = [
    "CLIP_ASPECT_RATIO",
    "CLIP_ASPECT_TOLERANCE",
    "CLIP_DURATION_TOLERANCE_SECONDS",
    "CLIP_LUMA_LIVE_FRAME_BAND",
    "CLIP_LUMA_MEAN_BAND",
    "CLIP_MOTION_FLOOR_MEAN",
    "ClipAdmissionError",
    "admit_clip_bytes",
    "admit_clip_file",
    "clip_admission_facts",
]

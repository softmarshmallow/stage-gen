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
from .review import (
    CLIP_REVIEW_CELL_WIDTH,
    CLIP_REVIEW_COLUMNS,
    CLIP_REVIEW_FRAME_MAX,
    CLIP_REVIEW_FRAME_MIN,
    CLIP_REVIEW_SECONDS_PER_FRAME,
    clip_review_frame_count,
    clip_sample_times,
)

__all__ = [
    "CLIP_ASPECT_RATIO",
    "CLIP_ASPECT_TOLERANCE",
    "CLIP_DURATION_TOLERANCE_SECONDS",
    "CLIP_LUMA_LIVE_FRAME_BAND",
    "CLIP_LUMA_MEAN_BAND",
    "CLIP_MOTION_FLOOR_MEAN",
    "CLIP_REVIEW_CELL_WIDTH",
    "CLIP_REVIEW_COLUMNS",
    "CLIP_REVIEW_FRAME_MAX",
    "CLIP_REVIEW_FRAME_MIN",
    "CLIP_REVIEW_SECONDS_PER_FRAME",
    "ClipAdmissionError",
    "admit_clip_bytes",
    "admit_clip_file",
    "clip_admission_facts",
    "clip_review_frame_count",
    "clip_sample_times",
]

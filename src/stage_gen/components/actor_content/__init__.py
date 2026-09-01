"""Genre-neutral drawn-actor contract blocks shared by genre content catalogs.

A drawn actor's reference binding, motion playback, and their closure rules are
the same facts in any genre; which states an actor performs and what it carries
stay with the genre's own catalog models.
"""

from .models import (
    DEFAULT_MOTION_ANCHOR,
    CanonicalFrameIndex,
    ContentReference,
    MotionAnchor,
    MotionPlaybackMode,
    MotionPresentation,
    ReferencesContent,
    validate_motion_states,
    validate_reference_closure,
)

__all__ = [
    "DEFAULT_MOTION_ANCHOR",
    "CanonicalFrameIndex",
    "ContentReference",
    "MotionAnchor",
    "MotionPlaybackMode",
    "MotionPresentation",
    "ReferencesContent",
    "validate_motion_states",
    "validate_reference_closure",
]

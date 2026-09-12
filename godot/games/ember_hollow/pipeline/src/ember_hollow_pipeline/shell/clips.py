"""The shell's own gate on a generated clip, over the modality's objective one.

``components.video_clip`` answers what is true of any clip: one picture stream, the
codec asked for, the length asked for, 16:9, and — the one that matters — that it
moves. This module answers the two questions only the shell can ask.

**Does it fill the screen the layout declares.** A clip stands where a still would, so
its canvas is the clip layout's, and the aspect check is what lets a card band published
against the still canvas land in the same place over it.

**Does it end where it said it would.** ``ending = "match_title"`` is the only ending
that is a claim about the picture rather than about presentation: it says the cinematic
finishes on the screen the player is about to be looking at. That is measurable, so it
is measured — the last frame against the title's own far backdrop, both reduced to a
coarse signature so a camera move, a grade, or the Theora re-encode all still read as
the same picture.

Measured on the shell spike, over the published `.ogv` rather than the response:

    the same picture through a Theora round trip     0.30
    the same picture pushed in 10%                   9.15
    the same picture at 0.92 brightness              9.70
    ------------------------------------------- the ceiling, 12.0
    the closest pair of genuinely different plates  31.47
    this package's last shot against its title      59.62

Two clean populations with a 3.5x gap, and the ceiling sits in it.
"""

from __future__ import annotations

from stage_gen.components.screen_art.layouts import ShellLayout
from stage_gen.media import frame_signature, signature_distance

SHELL_CLIP_VALIDATION_VERSION = "shell-clip-validation-v1"

#: The largest signature distance at which two frames are still the same picture.
#: Set from the measurements above: 1.24x the worst true match, 2.6x under the closest
#: false one.
CLIP_MATCH_TITLE_MAX_DISTANCE = 12.0


class ShellClipError(ValueError):
    """A generated clip that cannot stand in the shot the document gave it."""


def match_title_verdict(last_frame: bytes, title_backdrop: bytes) -> dict[str, object]:
    """Refuse a ``match_title`` ending whose last frame is a different picture."""

    distance = signature_distance(frame_signature(last_frame), frame_signature(title_backdrop))
    if distance > CLIP_MATCH_TITLE_MAX_DISTANCE:
        raise ShellClipError(
            f"the opening ends on match_title but its last frame is {distance:.2f} from the "
            f"title backdrop, past the {CLIP_MATCH_TITLE_MAX_DISTANCE} a re-encode, a camera "
            "move and a grade together stay inside; it is a different picture"
        )
    return {
        "ending": "match_title",
        "match_distance": round(distance, 3),
        "match_distance_max": CLIP_MATCH_TITLE_MAX_DISTANCE,
    }


def shell_clip_record(
    facts: dict[str, object],
    *,
    layout: ShellLayout,
    seconds: float,
    published_facts: dict[str, object] | None = None,
) -> dict[str, object]:
    """The clip's validation record: what was measured, on which pass, against what.

    Both passes are recorded. The response is gated before it is persisted and the
    published `.ogv` is gated again after the transcode, which is what makes the
    transcode publication rather than repair: it cannot hide anything from the gate that
    runs after it.
    """

    record: dict[str, object] = {
        "validation_version": SHELL_CLIP_VALIDATION_VERSION,
        "layout": layout.layout,
        "canvas": {"width": layout.canvas[0], "height": layout.canvas[1]},
        "shot_seconds": seconds,
        "source": facts,
    }
    if published_facts is not None:
        record["published"] = published_facts
        record["pixel_rewrite"] = "theora_publication_v1"
    return record


__all__ = [
    "CLIP_MATCH_TITLE_MAX_DISTANCE",
    "SHELL_CLIP_VALIDATION_VERSION",
    "ShellClipError",
    "match_title_verdict",
    "shell_clip_record",
]

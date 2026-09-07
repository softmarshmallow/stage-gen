"""How a clip is shown to whoever judges it: how many frames, and when.

Sampling is a property of clips, not of what a clip is for. It lives beside the
admission gate so that every reader of a clip - the pipeline's own reviewer, and the
standalone inspect command somebody runs before adopting a take - is shown the same
frames of the same file. A sheet you judged by hand and a sheet the graph judged later
disagreeing about which seconds they showed would make the two verdicts incomparable.
"""

from __future__ import annotations

#: How densely a reviewer is shown a clip, and the grid it is laid out on.
#:
#: Roughly one sample a second, because a clip is not one held shot. The first cut of
#: this took four frames whatever the length - calibrated on a single locked-off
#: establishing shot, where four beats is plenty - and then a ten-second clip carrying
#: six hard cuts was sampled at 2, 4, 6 and 8 seconds. Its first three shots all happen
#: inside the first three and a half seconds, so the reviewer never saw them and
#: correctly reported that the brief's opening beats were absent. It was judging the
#: sampling, not the clip.
#:
#: Frames are cheap; the sheet is what has to stay readable, so each cell is scaled down
#: rather than the count held low.
CLIP_REVIEW_SECONDS_PER_FRAME = 1.0
CLIP_REVIEW_FRAME_MIN = 4
CLIP_REVIEW_FRAME_MAX = 12
CLIP_REVIEW_COLUMNS = 4
CLIP_REVIEW_CELL_WIDTH = 640


def clip_review_frame_count(seconds: float) -> int:
    """How many frames a clip of this length is judged on."""

    if seconds <= 0:
        raise ValueError("a clip has a positive length")
    wanted = round(seconds / CLIP_REVIEW_SECONDS_PER_FRAME)
    return max(CLIP_REVIEW_FRAME_MIN, min(CLIP_REVIEW_FRAME_MAX, wanted))


def clip_sample_times(seconds: float, *, count: int | None = None) -> tuple[float, ...]:
    """When to sample a clip of this length, evenly and never on the last frame.

    Deterministic, so the same clip always produces the same contact sheet and a review
    is a judgement about the picture rather than about which frames it happened to get.
    """

    if seconds <= 0:
        raise ValueError("a clip has a positive length")
    if count is None:
        count = clip_review_frame_count(seconds)
    if count < 1:
        raise ValueError("a contact sheet shows at least one frame")
    step = seconds / (count + 1)
    return tuple(round(step * (index + 1), 3) for index in range(count))

"""How densely a clip is sampled for whoever judges it.

Sampling belongs to clips rather than to the shell, because two readers of one file -
the pipeline's reviewer and the standalone inspect command run before a take is adopted
- have to be shown the same frames or their verdicts are about different pictures.
"""

from __future__ import annotations

import pytest

from stage_gen.components.video_clip import (
    CLIP_REVIEW_FRAME_MAX,
    CLIP_REVIEW_FRAME_MIN,
    clip_review_frame_count,
    clip_sample_times,
)


def test_review_frames_are_sampled_evenly_and_never_on_the_last_frame() -> None:
    assert clip_sample_times(10.0, count=3) == (2.5, 5.0, 7.5)
    assert max(clip_sample_times(4.0)) < 4.0
    with pytest.raises(ValueError, match="positive length"):
        clip_sample_times(0.0)


def test_a_cut_sequence_is_sampled_densely_enough_to_show_its_beats() -> None:
    """About one frame a second, because a clip is not one held shot.

    Learned by reading a verdict: four frames of a ten-second clip land at 2, 4, 6 and 8
    seconds, and a brief whose first three shots all happen inside the first three and a
    half never had them looked at. The reviewer reported them absent, correctly, and was
    judging the sampling rather than the clip.
    """

    assert clip_review_frame_count(10.0) == 10
    early = clip_sample_times(10.0)[0]
    assert early < 1.0, "a one-second opening shot has to be sampled inside its own second"

    # Bounded at both ends: a short clip still gets enough frames to read, and a long
    # one does not turn the sheet into a wall.
    assert clip_review_frame_count(1.0) == CLIP_REVIEW_FRAME_MIN
    assert clip_review_frame_count(60.0) == CLIP_REVIEW_FRAME_MAX

from __future__ import annotations

import pytest
from pydantic import ValidationError

from stage_gen.preview import LegacyMotionPreview


@pytest.mark.parametrize("frame_count", [0, 17, 64])
def test_legacy_motion_limit_is_preserved(frame_count: int) -> None:
    with pytest.raises(ValidationError):
        LegacyMotionPreview(frame_count=frame_count)


def test_legacy_motion_round_trip_preserves_historical_fields() -> None:
    motion = LegacyMotionPreview(frame_count=4, mode="loop", frames_per_second=8)
    assert LegacyMotionPreview.model_validate_json(motion.model_dump_json()) == motion

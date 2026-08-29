from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from stage_gen.media.comparison_plate import BandedComparisonPlate
from stage_gen.recipes.scrolling_preview.motion_rebase import (
    MotionRebaseError,
    MotionRebaseReading,
    StateRebaseReading,
    admit_first_pass_record,
    build_motion_rebase_plate,
    build_motion_rebase_verification_plate,
    evaluate_motion_rebase,
    evaluate_motion_rebase_correction,
    motion_rebase_prompt,
    motion_rebase_verification_prompt,
    parse_motion_rebase,
)

STATES = ("idle", "run", "hurt", "death")


def _frame(height: int) -> bytes:
    image = Image.new("RGBA", (52, height + 12), (0, 0, 0, 0))
    for y in range(6, 6 + height):
        for x in range(6, 46):
            image.putpixel((x, y), (30, 90, 200, 255))
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _frames(heights: dict[str, int]) -> dict[str, tuple[bytes, ...]]:
    return {state: tuple(_frame(height) for _ in range(4)) for state, height in heights.items()}


def _plate() -> BandedComparisonPlate:
    return build_motion_rebase_plate(_frames({"idle": 100, "run": 80, "hurt": 90, "death": 60}))


def _reading(**multipliers: float) -> MotionRebaseReading:
    return MotionRebaseReading(
        baseline_state="idle",
        states=[
            StateRebaseReading(state=state, multiplier=value, evidence="head mass compared")
            for state, value in multipliers.items()
        ],
    )


def test_baseline_leads_the_plate_and_is_marked() -> None:
    plate = build_motion_rebase_plate(_frames({"run": 80, "idle": 100, "death": 60}))

    assert plate.group_keys[0] == "idle"
    # The baseline leads every band, because a band judged without it is a ratio against nothing.
    for band in plate.bands:
        assert band.baseline_key == "idle"
        assert band.group_keys[0] == "idle"


def test_plate_requires_the_actor_to_publish_its_baseline() -> None:
    with pytest.raises(MotionRebaseError, match=r"no 'idle' atlas"):
        build_motion_rebase_plate(_frames({"run": 80, "death": 60}))


def test_admits_a_covering_reading_and_publishes_the_record() -> None:
    plate = _plate()
    record = evaluate_motion_rebase(
        _reading(idle=1.0, run=1.25, hurt=1.081, death=1.222),
        published_states=STATES,
        plate=plate,
    )

    assert record["baseline_state"] == "idle"
    assert record["states"] == {"death": 1.22, "hurt": 1.08, "idle": 1.0, "run": 1.25}
    assert record["plate_sha256"] == plate.sha256


def test_rejects_a_baseline_that_is_not_its_own_reference() -> None:
    with pytest.raises(MotionRebaseError, match=r"baseline multiplier must be 1\.00"):
        evaluate_motion_rebase(
            _reading(idle=1.15, run=1.25, hurt=1.08, death=1.22),
            published_states=STATES,
            plate=_plate(),
        )


def test_rejects_a_reading_that_misses_a_published_atlas() -> None:
    with pytest.raises(MotionRebaseError, match="does not cover published atlases: death"):
        evaluate_motion_rebase(
            _reading(idle=1.0, run=1.25, hurt=1.08),
            published_states=STATES,
            plate=_plate(),
        )


def test_rejects_a_reading_for_a_state_the_actor_does_not_publish() -> None:
    with pytest.raises(MotionRebaseError, match="does not publish: climb"):
        evaluate_motion_rebase(
            _reading(idle=1.0, run=1.25, hurt=1.08, death=1.22, climb=1.05),
            published_states=STATES,
            plate=_plate(),
        )


@pytest.mark.parametrize("multiplier", [0.19, 5.01, 12.0])
def test_rejects_a_multiplier_outside_the_band_rather_than_clamping(multiplier: float) -> None:
    with pytest.raises(MotionRebaseError, match="outside the admitted band"):
        evaluate_motion_rebase(
            _reading(idle=1.0, run=multiplier, hurt=1.08, death=1.22),
            published_states=STATES,
            plate=_plate(),
        )


def test_rejects_a_plate_whose_lineage_does_not_match_the_published_atlases() -> None:
    stale = build_motion_rebase_plate(_frames({"idle": 100, "run": 80, "hurt": 90}))
    with pytest.raises(MotionRebaseError, match="plate lineage does not cover"):
        evaluate_motion_rebase(
            _reading(idle=1.0, run=1.25, hurt=1.08, death=1.22),
            published_states=STATES,
            plate=stale,
        )


def test_rejects_a_judge_answering_against_another_baseline() -> None:
    reading = MotionRebaseReading(
        baseline_state="run",
        states=[StateRebaseReading(state="idle", multiplier=1.0, evidence="x")],
    )
    with pytest.raises(MotionRebaseError, match="judge answered against baseline"):
        evaluate_motion_rebase(reading, published_states=STATES, plate=_plate())


def test_prompt_names_every_state_and_forbids_normalising_pose() -> None:
    prompt = motion_rebase_prompt("a game character", STATES)

    for state in STATES:
        assert state in prompt
    assert "ONE uniform scale" in prompt
    # The prompt must not offer 1.0 as the safe answer, and must name pose-invariant features.
    assert "Do not default to 1.0" in prompt
    assert "head width" in prompt
    assert "baseline copy inside its own band" in prompt


def test_reading_round_trips_through_the_structured_parser() -> None:
    parsed = parse_motion_rebase(
        {
            "baseline_state": "idle",
            "states": [{"state": "idle", "multiplier": 1.0, "evidence": "reference"}],
        }
    )
    assert parsed.states[0].state == "idle"


def test_admits_the_climb_disparity_measured_on_the_canonical_actor() -> None:
    # The shipped climb strips are drawn roughly 3.7x the master states, so they need a
    # multiplier near 0.27. A band that refused this would refuse the reference game.
    record = evaluate_motion_rebase(
        _reading(idle=1.0, run=1.0, hurt=1.0, death=0.27),
        published_states=STATES,
        plate=_plate(),
    )

    states = record["states"]
    assert isinstance(states, dict)
    assert states["death"] == 0.27


_HEIGHTS = {"idle": 100, "run": 80, "hurt": 90, "death": 60}


def _judged_first_pass(**multipliers: float) -> dict[str, object]:
    plate = _plate()
    return evaluate_motion_rebase(_reading(**multipliers), published_states=STATES, plate=plate)


def test_verification_plate_applies_the_first_pass() -> None:
    frames = _frames({"idle": 100, "walk": 95, "climb": 350})
    first_pass = {"idle": 1.0, "walk": 1.05, "climb": 100 / 350}

    raw = build_motion_rebase_plate(frames)
    verification = build_motion_rebase_verification_plate(frames, first_pass)

    # Raw, the climb canvas forces its own band and squashes the baseline it shares it with.
    # With the pass applied everything reads at the baseline's size on one band, which is the
    # easy form of the judging task - and the climb band's squashed baseline is gone entirely.
    assert len(raw.bands) == 2
    assert len(verification.bands) == 1
    drawn = {frame.group_key: frame.drawn_height for frame in verification.frames}
    assert drawn["climb"] == pytest.approx(drawn["idle"], abs=2)
    assert drawn["walk"] == pytest.approx(drawn["idle"], abs=6)


def test_verification_plate_requires_a_multiplier_for_every_state() -> None:
    with pytest.raises(MotionRebaseError, match="no multiplier for: run"):
        build_motion_rebase_verification_plate(_frames({"idle": 100, "run": 80}), {"idle": 1.0})


def test_first_pass_record_round_trips_through_admission() -> None:
    plate = _plate()
    record = evaluate_motion_rebase(
        _reading(idle=1.0, run=1.25, hurt=1.08, death=0.27),
        published_states=STATES,
        plate=plate,
    )

    admitted = admit_first_pass_record(record, published_states=STATES, plate=plate)
    assert admitted == {"idle": 1.0, "run": 1.25, "hurt": 1.08, "death": 0.27}


def test_admission_refuses_a_first_pass_that_outlived_its_artwork() -> None:
    record = _judged_first_pass(idle=1.0, run=1.25, hurt=1.08, death=0.27)
    changed = build_motion_rebase_plate(_frames({"idle": 100, "run": 80, "hurt": 90, "death": 75}))

    with pytest.raises(MotionRebaseError, match="stale"):
        admit_first_pass_record(record, published_states=STATES, plate=changed)


def test_correction_composes_with_the_first_pass_into_the_published_record() -> None:
    plate = _plate()
    first_pass = {"idle": 1.0, "run": 1.25, "hurt": 1.08, "death": 0.27}
    verification = build_motion_rebase_verification_plate(_frames(_HEIGHTS), first_pass)

    record = evaluate_motion_rebase_correction(
        _reading(idle=1.0, run=0.92, hurt=1.0, death=1.1),
        first_pass=first_pass,
        published_states=STATES,
        plate=plate,
        verification_plate=verification,
    )

    assert record["states"] == {"death": 0.3, "hurt": 1.08, "idle": 1.0, "run": 1.15}
    assert record["first_pass"] == {"death": 0.27, "hurt": 1.08, "idle": 1.0, "run": 1.25}
    assert record["correction"] == {"death": 1.1, "hurt": 1.0, "idle": 1.0, "run": 0.92}
    assert record["plate_sha256"] == plate.sha256
    assert record["verification_plate_sha256"] == verification.sha256


def test_a_correction_outside_the_verification_band_is_refused() -> None:
    first_pass = {"idle": 1.0, "run": 1.25, "hurt": 1.08, "death": 0.27}
    verification = build_motion_rebase_verification_plate(_frames(_HEIGHTS), first_pass)

    with pytest.raises(MotionRebaseError, match="outside the verification"):
        evaluate_motion_rebase_correction(
            _reading(idle=1.0, run=2.5, hurt=1.0, death=1.0),
            first_pass=first_pass,
            published_states=STATES,
            plate=_plate(),
            verification_plate=verification,
        )


def test_a_composed_multiplier_outside_the_contract_band_is_refused() -> None:
    first_pass = {"idle": 1.0, "run": 4.0, "hurt": 1.08, "death": 0.27}
    verification = build_motion_rebase_verification_plate(_frames(_HEIGHTS), first_pass)

    with pytest.raises(MotionRebaseError, match="composes to"):
        evaluate_motion_rebase_correction(
            _reading(idle=1.0, run=1.5, hurt=1.0, death=1.0),
            first_pass=first_pass,
            published_states=STATES,
            plate=_plate(),
            verification_plate=verification,
        )


def test_verification_prompt_asks_for_the_residual_not_a_remeasurement() -> None:
    prompt = motion_rebase_verification_prompt("a game character", STATES)

    for state in STATES:
        assert state in prompt
    assert "ALREADY been rescaled" in prompt
    assert "residual" in prompt
    assert "head width" in prompt
    assert "Do not echo 1.0" in prompt

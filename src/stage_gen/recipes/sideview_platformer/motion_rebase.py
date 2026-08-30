"""Bring one actor's motion atlases into agreement with each other.

An actor's states are generated in separate provider calls, and separate calls do not share a
scale. The published atlases therefore disagree about how large the character is drawn, and the
disagreement is invisible in the alpha: a crouch is shorter because of the pose, a mis-scaled
sheet is shorter because of the artwork, and a bounding box cannot tell those apart.

This module answers exactly one question - is this the same character, drawn at the same scale,
as the baseline? - and answers it as a ratio. It deliberately does not answer how big the
character is; that is a magnitude, it is authored, and it belongs to the asset unit.

The contract is `docs/spec/motion-rebase.md`. Plate composition is provider-neutral and lives in
`stage_gen.media.comparison_plate`; what a group means is decided here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from pydantic import BaseModel, ConfigDict, Field

from stage_gen.media.comparison_plate import (
    BandedComparisonPlate,
    PlateGroup,
    compose_banded_comparison_plate,
)

MOTION_REBASE_SCHEMA_NAME: Final = "scrolling_preview_motion_rebase_v1"
MOTION_REBASE_CORRECTION_SCHEMA_NAME: Final = "scrolling_preview_motion_rebase_correction_v1"
MOTION_REBASE_ERROR_CODE: Final = "scrolling-motion-rebase-v1"

#: The baseline is an upright rest pose. Ratios alone cannot recover stature, so any consumer that
#: needs a standing height - camera framing, hitbox derivation, a name label offset - reads it from
#: this state's frame. A baseline drawn crouched or airborne silently corrupts all of them.
BASELINE_STATE: Final = "idle"

#: A reading outside the band is rejected rather than clamped: a silently rebased actor is harder
#: to notice than a stage that fails.
#:
#: The band is deliberately wider than the contract's original [0.4, 2.5]. Measured on the
#: canonical actor, the climb strips are generated on a 1115x2850 canvas against the master
#: states' 457x799 and are drawn roughly 3.7x larger, so they need a multiplier near 0.27. A band
#: that rejects the reference game is not a safety rail, it is a bug: separately generated
#: atlases genuinely do disagree by more than a factor of two, which is precisely why this
#: contract exists. The band still catches a nonsense reading.
MINIMUM_MULTIPLIER: Final = 0.2
MAXIMUM_MULTIPLIER: Final = 5.0

#: A verification correction is a residual, not a re-measurement. After the first pass every
#: state is composed near the baseline's size, so a correction beyond this band does not mean
#: the artwork disagrees more than expected - it means the first pass failed, and compounding a
#: failed reading with a large "correction" would launder it. The stage fails closed instead.
MINIMUM_CORRECTION: Final = 0.5
MAXIMUM_CORRECTION: Final = 2.0


class MotionRebaseError(ValueError):
    """An actor's motion atlases could not be rebased onto their baseline."""

    def __init__(self, message: str) -> None:
        super().__init__(f"{MOTION_REBASE_ERROR_CODE}: {message}")
        self.code = MOTION_REBASE_ERROR_CODE


class StateRebaseReading(BaseModel):
    """One state's scale relative to the baseline, as the judge returns it."""

    model_config = ConfigDict(extra="forbid", strict=True)

    state: str = Field(min_length=1, max_length=64)
    multiplier: float = Field(
        description=(
            "How much this state's artwork must be scaled to match the baseline's drawn size. "
            "Greater than 1.0 when the state was drawn smaller than the baseline."
        ),
    )
    evidence: str = Field(min_length=1, max_length=300)


class MotionRebaseReading(BaseModel):
    """Every state's reading for one actor, judged against one plate."""

    model_config = ConfigDict(extra="forbid", strict=True)

    baseline_state: str = Field(min_length=1, max_length=64)
    states: list[StateRebaseReading] = Field(min_length=1)


def motion_rebase_json_schema() -> dict[str, object]:
    return cast(dict[str, object], MotionRebaseReading.model_json_schema())


def parse_motion_rebase(decoded: object) -> MotionRebaseReading:
    return MotionRebaseReading.model_validate(decoded)


def motion_rebase_prompt(subject: str, states: Sequence[str]) -> str:
    """Ask for one ratio per state, against a baseline the model can see in the same image.

    The plate is described rather than assumed: the model is told the scale is uniform and that
    a group drawn small really is small, because the instinct to normalise poses is exactly the
    error being measured.
    """

    listed = ", ".join(states)
    return (
        f"This image is a comparison plate for {subject}. It carries every animation frame of "
        "every motion state, grouped by state, with the state's name above each group.\n"
        "The plate is divided into horizontal BANDS separated by a grey rule. Within one band "
        "every frame is drawn at ONE uniform scale, so a group that looks smaller than its "
        "neighbours in the same band really was drawn smaller. Bands do NOT share a scale with "
        "each other, which is why the group marked (baseline) is repeated at the start of every "
        "band. Always compare a state against the baseline copy inside its own band, never "
        "against a group in a different band.\n"
        "A dashed horizontal rule across every group marks that band's baseline standing height, "
        "and each group sits on its own ground line.\n"
        f"For each of these states, report how much its artwork must be scaled so the character "
        f"reads at the same size as in its band's baseline: {listed}.\n"
        "Report the baseline itself as exactly 1.0.\n"
        "Judge the size the CHARACTER is drawn at, not how tall the pose happens to be. Compare "
        "parts whose size does not change with pose: head width at its widest, the diameter of "
        "the eye, the thickness of an upper arm or a boot, and the weight of the ink outline. A "
        "prone or collapsed frame is a pose, not a smaller drawing.\n"
        "Do not default to 1.0. Give the ratio your feature comparison actually supports, to two "
        "decimals, even when it is close to 1 - 0.92 and 1.08 are useful answers. Reserve exactly "
        "1.0 for a state whose measured features genuinely match the baseline.\n"
        "In your evidence, name the feature you compared and the ratio you read from it.\n"
        "Return a multiplier greater than 1.0 when a state was drawn too small, and less than "
        "1.0 when it was drawn too large."
    )


def _multipliers_by_state(reading: MotionRebaseReading) -> dict[str, float]:
    multipliers: dict[str, float] = {}
    for entry in reading.states:
        if entry.state in multipliers:
            raise MotionRebaseError(f"state {entry.state!r} was judged more than once")
        multipliers[entry.state] = entry.multiplier
    return multipliers


def _require_coverage(
    multipliers: Mapping[str, float],
    published_states: Sequence[str],
    baseline_state: str,
) -> set[str]:
    published = set(published_states)
    if baseline_state not in published:
        raise MotionRebaseError(f"published atlases do not include the baseline {baseline_state!r}")
    missing = sorted(published - set(multipliers))
    if missing:
        raise MotionRebaseError(f"reading does not cover published atlases: {', '.join(missing)}")
    unknown = sorted(set(multipliers) - published)
    if unknown:
        raise MotionRebaseError(
            f"reading covers states this actor does not publish: {', '.join(unknown)}"
        )
    return published


def _require_baseline_identity(multipliers: Mapping[str, float], baseline_state: str) -> None:
    value = multipliers[baseline_state]
    if abs(value - 1.0) > 0.005:
        raise MotionRebaseError(
            f"baseline multiplier must be 1.00, got {value:.3f}; a baseline that "
            "is not its own reference makes every other ratio meaningless"
        )


def build_motion_rebase_plate(
    frames_by_state: Mapping[str, Sequence[bytes]],
    *,
    baseline_state: str = BASELINE_STATE,
) -> BandedComparisonPlate:
    """Compose the judging plate: every frame of every atlas, at one uniform source scale.

    Showing every frame is required rather than decorative. It is what makes the
    one-scale-per-atlas claim checkable instead of assumed, and it is how a genuine per-frame
    anomaly would be seen at all.
    """

    if baseline_state not in frames_by_state:
        raise MotionRebaseError(
            f"actor has no {baseline_state!r} atlas, so it declares no baseline to judge against"
        )
    groups = [
        PlateGroup(
            key=state,
            frames=tuple(frames_by_state[state]),
            baseline=state == baseline_state,
        )
        # Sorted so the baseline leads the plate and the layout is stable run to run.
        for state in sorted(frames_by_state, key=lambda name: (name != baseline_state, name))
    ]
    return compose_banded_comparison_plate(groups)


def evaluate_motion_rebase(
    reading: MotionRebaseReading,
    *,
    published_states: Sequence[str],
    plate: BandedComparisonPlate,
    baseline_state: str = BASELINE_STATE,
) -> dict[str, object]:
    """Admit one reading and turn it into the published rebase record, or reject it.

    Admission fails closed on every gate the contract names: baseline identity, coverage of every
    published atlas, the multiplier band, and plate lineage.
    """

    if reading.baseline_state != baseline_state:
        raise MotionRebaseError(
            f"judge answered against baseline {reading.baseline_state!r}, "
            f"but the actor declares {baseline_state!r}"
        )
    multipliers = _multipliers_by_state(reading)
    published = _require_coverage(multipliers, published_states, baseline_state)
    _require_baseline_identity(multipliers, baseline_state)
    for state, multiplier in sorted(multipliers.items()):
        if not MINIMUM_MULTIPLIER <= multiplier <= MAXIMUM_MULTIPLIER:
            raise MotionRebaseError(
                f"state {state!r} read {multiplier:.3f}, outside the admitted band "
                f"[{MINIMUM_MULTIPLIER}, {MAXIMUM_MULTIPLIER}]"
            )

    plate_states = set(plate.group_keys)
    if plate_states != published:
        raise MotionRebaseError(
            "plate lineage does not cover exactly the published atlases; "
            f"plate carries {sorted(plate_states)}, actor publishes {sorted(published)}"
        )

    rounded = {state: round(multiplier, 2) for state, multiplier in multipliers.items()}
    rounded[baseline_state] = 1.0
    return {
        "baseline_state": baseline_state,
        "states": {state: rounded[state] for state in sorted(rounded)},
        "plate_sha256": plate.sha256,
        "evidence": {entry.state: entry.evidence for entry in reading.states},
    }


def build_motion_rebase_verification_plate(
    frames_by_state: Mapping[str, Sequence[bytes]],
    first_pass: Mapping[str, float],
    *,
    baseline_state: str = BASELINE_STATE,
) -> BandedComparisonPlate:
    """Compose the closed-loop plate: every frame drawn with its first-pass multiplier applied.

    An absolute reading across atlases that disagree by a factor of three is the hard form of
    the task. Applying the first pass and judging the *result* turns it into the easy form -
    every state now sits near the baseline, so the judge reads a small residual instead of a
    large ratio - and the second reading corrects the first instead of repeating its conditions.
    """

    if baseline_state not in frames_by_state:
        raise MotionRebaseError(
            f"actor has no {baseline_state!r} atlas, so it declares no baseline to judge against"
        )
    missing = sorted(set(frames_by_state) - set(first_pass))
    if missing:
        raise MotionRebaseError(f"first pass carries no multiplier for: {', '.join(missing)}")
    groups = [
        PlateGroup(
            key=state,
            frames=tuple(frames_by_state[state]),
            baseline=state == baseline_state,
            prescale=float(first_pass[state]),
        )
        for state in sorted(frames_by_state, key=lambda name: (name != baseline_state, name))
    ]
    return compose_banded_comparison_plate(groups)


def admit_first_pass_record(
    record: object,
    *,
    published_states: Sequence[str],
    plate: BandedComparisonPlate,
    baseline_state: str = BASELINE_STATE,
) -> dict[str, float]:
    """Re-admit a first-pass record read back from disk, or refuse it as stale.

    The record is re-derived rather than trusted: its multipliers must still cover exactly the
    published atlases, sit inside the band, and its plate digest must match a plate rebuilt from
    today's bytes. An atlas regenerated after the first pass changes that digest, and a reading
    taken against artwork that no longer exists is refused rather than corrected.
    """

    if not isinstance(record, dict):
        raise MotionRebaseError("first-pass rebase record is not an object")
    if record.get("baseline_state") != baseline_state:
        raise MotionRebaseError(
            f"first-pass record answers against baseline {record.get('baseline_state')!r}, "
            f"but the actor declares {baseline_state!r}"
        )
    raw_states = record.get("states")
    if not isinstance(raw_states, dict):
        raise MotionRebaseError("first-pass record carries no per-state multipliers")
    multipliers: dict[str, float] = {}
    for state, value in raw_states.items():
        if not isinstance(state, str):
            raise MotionRebaseError("first-pass record keys a multiplier by a non-string state")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MotionRebaseError(f"first-pass multiplier for {state!r} is not a number")
        multipliers[state] = float(value)
    _require_coverage(multipliers, published_states, baseline_state)
    _require_baseline_identity(multipliers, baseline_state)
    for state, multiplier in sorted(multipliers.items()):
        if not MINIMUM_MULTIPLIER <= multiplier <= MAXIMUM_MULTIPLIER:
            raise MotionRebaseError(
                f"first-pass multiplier for {state!r} is {multiplier:.3f}, outside the admitted "
                f"band [{MINIMUM_MULTIPLIER}, {MAXIMUM_MULTIPLIER}]"
            )
    if record.get("plate_sha256") != plate.sha256:
        raise MotionRebaseError(
            "first-pass record was judged against a different plate than these atlases compose; "
            "an atlas changed after the first pass, so the reading is stale and must be retaken"
        )
    return multipliers


def motion_rebase_verification_prompt(subject: str, states: Sequence[str]) -> str:
    """Ask for the residual left by the first pass, on a plate composed with it applied."""

    listed = ", ".join(states)
    return (
        f"This image is a verification plate for {subject}. It carries every animation frame of "
        "every motion state, grouped by state, with the state's name above each group.\n"
        "Every state has ALREADY been rescaled by a first-pass multiplier: if that pass were "
        "perfect, the character would read at exactly the same size in every group. Your job is "
        "to report the residual error that remains, per state.\n"
        "The plate may be divided into horizontal BANDS separated by a grey rule. Within one "
        "band every group shares one scale, and the group marked (baseline) is repeated at the "
        "start of every band. Always compare a state against the baseline copy inside its own "
        "band, never against a group in a different band.\n"
        "A dashed horizontal rule across every group marks that band's baseline standing height, "
        "and each group sits on its own ground line.\n"
        f"For each of these states, report the correction that would make the character read at "
        f"exactly the same size as its band's baseline: {listed}.\n"
        "Report the baseline itself as exactly 1.0.\n"
        "Judge the size the CHARACTER is drawn at, not how tall the pose happens to be. Compare "
        "parts whose size does not change with pose: head width at its widest, the diameter of "
        "the eye, the thickness of an upper arm or a boot, and the weight of the ink outline. An "
        "overhead reach or a collapsed frame is a pose, not a scale error.\n"
        "Corrections are expected to be small: most fall between 0.80 and 1.25. Do not echo 1.0 "
        "out of caution - report the ratio your feature comparison actually supports, to two "
        "decimals, and reserve exactly 1.0 for a state whose measured features genuinely match "
        "the baseline.\n"
        "In your evidence, name the feature you compared and the ratio you read from it.\n"
        "Return a correction greater than 1.0 when the state still reads too small, and less "
        "than 1.0 when it still reads too large."
    )


def evaluate_motion_rebase_correction(
    reading: MotionRebaseReading,
    *,
    first_pass: Mapping[str, float],
    published_states: Sequence[str],
    plate: BandedComparisonPlate,
    verification_plate: BandedComparisonPlate,
    baseline_state: str = BASELINE_STATE,
) -> dict[str, object]:
    """Admit the residual reading, compose it with the first pass, and publish the final record.

    Admission fails closed on every gate the first pass carries, plus one of its own: a
    correction outside its narrow band means the first pass failed rather than drifted, and a
    failed pass is refused instead of laundered through a large correction.
    """

    if reading.baseline_state != baseline_state:
        raise MotionRebaseError(
            f"judge answered against baseline {reading.baseline_state!r}, "
            f"but the actor declares {baseline_state!r}"
        )
    corrections = _multipliers_by_state(reading)
    published = _require_coverage(corrections, published_states, baseline_state)
    if set(first_pass) != published:
        raise MotionRebaseError(
            f"first pass covers {sorted(first_pass)}, but the actor publishes {sorted(published)}"
        )
    _require_baseline_identity(corrections, baseline_state)
    for state, correction in sorted(corrections.items()):
        if not MINIMUM_CORRECTION <= correction <= MAXIMUM_CORRECTION:
            raise MotionRebaseError(
                f"state {state!r} needed correction {correction:.3f}, outside the verification "
                f"band [{MINIMUM_CORRECTION}, {MAXIMUM_CORRECTION}]; a residual this large means "
                "the first pass failed and must be retaken"
            )
    for candidate, label in ((plate, "plate"), (verification_plate, "verification plate")):
        keys = set(candidate.group_keys)
        if keys != published:
            raise MotionRebaseError(
                f"{label} lineage does not cover exactly the published atlases; "
                f"it carries {sorted(keys)}, actor publishes {sorted(published)}"
            )
    rounded_corrections = {state: round(value, 2) for state, value in corrections.items()}
    rounded_corrections[baseline_state] = 1.0
    final: dict[str, float] = {}
    for state in sorted(published):
        composed = round(first_pass[state] * rounded_corrections[state], 2)
        if not MINIMUM_MULTIPLIER <= composed <= MAXIMUM_MULTIPLIER:
            raise MotionRebaseError(
                f"state {state!r} composes to {composed:.3f}, outside the admitted band "
                f"[{MINIMUM_MULTIPLIER}, {MAXIMUM_MULTIPLIER}]"
            )
        final[state] = composed
    final[baseline_state] = 1.0
    return {
        "baseline_state": baseline_state,
        "states": final,
        "first_pass": {state: round(first_pass[state], 2) for state in sorted(published)},
        "correction": {state: rounded_corrections[state] for state in sorted(published)},
        "plate_sha256": plate.sha256,
        "verification_plate_sha256": verification_plate.sha256,
        "evidence": {entry.state: entry.evidence for entry in reading.states},
    }

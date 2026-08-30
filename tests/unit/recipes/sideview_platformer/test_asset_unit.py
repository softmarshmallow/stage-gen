from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from stage_gen.components.game_contract.package import PreparedScale
from stage_gen.recipes.sideview_platformer.asset_unit import (
    AssetUnitError,
    ResolvedMagnitude,
    admit_entity_consistency,
    admit_rank_ladder,
    calibrate_subject,
    measure_subject_extent,
    recovery_plate_steps,
    resolve_declared_magnitude,
    resolve_player_magnitude,
    resolve_rank_magnitude,
    sprite_scale,
)

TILE_PX = 64


def _scale(**overrides: object) -> PreparedScale:
    payload: dict[str, object] = {
        "unit": "player_height",
        "player_height_tiles": 2.40,
        "minimum": 0.25,
        "steps": [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0],
        "ranks": {"common": 0.5, "uncommon": 0.65, "elite": 0.85, "boss": 1.5},
    }
    payload.update(overrides)
    return PreparedScale.model_validate(payload)


def _subject(height: int, *, pad: int = 5, alpha: int = 255) -> bytes:
    image = Image.new("RGBA", (40, height + pad * 2), (0, 0, 0, 0))
    for y in range(pad, pad + height):
        for x in range(4, 30):
            image.putpixel((x, y), (10, 120, 90, alpha))
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_the_player_defines_the_unit_and_may_not_declare_one() -> None:
    assert resolve_player_magnitude(None) == ResolvedMagnitude(1.0, "definition")
    with pytest.raises(AssetUnitError, match="must not declare height_units"):
        resolve_player_magnitude(1.0)


def test_measurement_runs_on_the_trimmed_subject_not_the_canvas() -> None:
    # Same subject, twice the padding: a canvas measurement would differ, a subject one must not.
    assert measure_subject_extent(_subject(90, pad=5), subject="prop") == 90
    assert measure_subject_extent(_subject(90, pad=60), subject="prop") == 90


def test_measurement_uses_the_runtime_painted_threshold() -> None:
    assert measure_subject_extent(_subject(20, alpha=65), subject="prop") == 20
    with pytest.raises(AssetUnitError, match="no painted pixels"):
        measure_subject_extent(_subject(20, alpha=64), subject="prop")


def test_pixels_per_unit_divides_the_extent_by_the_declaration() -> None:
    calibration = calibrate_subject(
        magnitude=ResolvedMagnitude(2.4, "authored"),
        subject_extent_px=480,
        measured_sha256="f" * 64,
        scale=_scale(),
        tile_px=TILE_PX,
        subject="petalstone_well",
    )

    assert calibration.source_px_per_unit == pytest.approx(200.0)
    assert calibration.as_record()["height_units_source"] == "authored"


def test_two_subjects_at_one_magnitude_project_to_one_drawn_height() -> None:
    scale = _scale()
    # Different artwork resolutions, same declared magnitude: the projection must agree.
    coarse = calibrate_subject(
        magnitude=ResolvedMagnitude(2.4, "authored"),
        subject_extent_px=240,
        measured_sha256="a" * 64,
        scale=scale,
        tile_px=TILE_PX,
        subject="coarse",
    )
    fine = calibrate_subject(
        magnitude=ResolvedMagnitude(2.4, "authored"),
        subject_extent_px=960,
        measured_sha256="b" * 64,
        scale=scale,
        tile_px=TILE_PX,
        subject="fine",
    )

    def drawn(record: dict[str, object], extent: int) -> float:
        return extent * sprite_scale(record, player_height_tiles=2.40, tile_px=TILE_PX)

    assert drawn(coarse.as_record(), 240) == pytest.approx(drawn(fine.as_record(), 960))
    # And that height is the magnitude projected exactly once: 2.4 units x 2.4 tiles x 64 px.
    assert drawn(coarse.as_record(), 240) == pytest.approx(2.4 * 2.40 * TILE_PX)


def test_a_declaration_below_the_floor_is_refused_rather_than_clamped() -> None:
    with pytest.raises(AssetUnitError, match="below the package floor"):
        resolve_declared_magnitude(_scale(), 0.1, subject="sunleaf_coin")


def test_an_undeclared_subject_inherits_the_smallest_legible_step() -> None:
    resolved = resolve_declared_magnitude(_scale(), None, subject="unnamed_prop")

    assert resolved == ResolvedMagnitude(0.25, "inherited")


def test_mob_magnitude_resolves_from_rank_so_silhouette_carries_threat() -> None:
    scale = _scale()

    assert resolve_rank_magnitude(scale, "boss") == ResolvedMagnitude(1.5, "rank")
    assert resolve_rank_magnitude(scale, "common") == ResolvedMagnitude(0.5, "rank")
    with pytest.raises(AssetUnitError, match=r"no \[scale.ranks\] entry"):
        resolve_rank_magnitude(scale, "mythic")


def test_rank_ladder_must_be_monotonic_and_bounded_by_the_player() -> None:
    admit_rank_ladder(_scale(), {"toad": "uncommon", "dragon": "boss"})

    with pytest.raises(AssetUnitError, match="not above"):
        admit_rank_ladder(
            _scale(ranks={"common": 0.8, "uncommon": 0.6, "elite": 0.85, "boss": 1.5}), {}
        )
    with pytest.raises(AssetUnitError, match="only a boss"):
        admit_rank_ladder(
            _scale(ranks={"common": 0.5, "uncommon": 0.65, "elite": 1.2, "boss": 1.5}), {}
        )


def test_a_mob_whose_rank_has_no_magnitude_is_refused() -> None:
    with pytest.raises(AssetUnitError, match="no declared magnitude"):
        admit_rank_ladder(_scale(ranks={"common": 0.5}), {"toad": "elite"})


def test_a_subject_disagreeing_with_its_own_concept_is_refused() -> None:
    admit_entity_consistency(subject="well", subject_px_per_unit=200, concept_px_per_unit=300)

    with pytest.raises(AssetUnitError, match="a factor of"):
        admit_entity_consistency(subject="well", subject_px_per_unit=200, concept_px_per_unit=1400)


def test_recovery_offers_the_declared_step_ladder_as_choices() -> None:
    assert recovery_plate_steps(_scale()) == (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
    with pytest.raises(AssetUnitError, match=r"no \[scale\] steps"):
        recovery_plate_steps(_scale(steps=[]))


def test_scale_vocabulary_refuses_a_step_below_its_own_floor() -> None:
    with pytest.raises(ValueError, match="below the declared minimum"):
        _scale(minimum=0.5, steps=[0.25, 1.0])


def test_scale_vocabulary_requires_an_ascending_ladder() -> None:
    with pytest.raises(ValueError, match="must ascend"):
        _scale(steps=[1.0, 0.5])

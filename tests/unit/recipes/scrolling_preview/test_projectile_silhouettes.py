from __future__ import annotations

from typing import get_args

import pytest

from stage_gen.components.game_content.models import ProjectileSilhouette
from stage_gen.recipes.scrolling_preview.projectile_silhouettes import (
    PROJECTILE_SILHOUETTES,
    projectile_silhouette_art,
)


def test_every_silhouette_the_contract_accepts_has_an_art_directive() -> None:
    """The check the module exists for.

    A silhouette a package can author and this module has never heard of would otherwise reach the
    prompt builder, the validator, and the review with no directive at all - the silent failure
    mode this recipe has already recorded three times for facing, framing, and reach.
    """

    declared = {entry.silhouette for entry in PROJECTILE_SILHOUETTES}
    assert declared == set(get_args(ProjectileSilhouette))


def test_each_directive_leads_with_the_axis_and_names_the_drawn_direction() -> None:
    # Leading, not trailing. This recipe has watched the same directive fail as a final sub-clause
    # and succeed as an opening labelled one.
    for entry in PROJECTILE_SILHOUETTES:
        assert entry.axis_directive.startswith("AXIS, before anything else:")
        assert entry.shape_clause
        assert entry.review_clause


def test_only_the_axial_silhouette_claims_a_leading_end() -> None:
    # The whole point of the vocabulary: a runtime may mirror or rotate an axial subject along the
    # axis it was drawn on, and must not imply a direction for one that has none.
    axial = projectile_silhouette_art("axial_v1")
    assert "RIGHT" in axial.axis_directive

    for silhouette in ("radial_v1", "irregular_v1"):
        directive = projectile_silhouette_art(silhouette).axis_directive
        assert "NO leading end" in directive or "no clean long axis" in directive


def test_an_undeclared_silhouette_raises_rather_than_defaulting() -> None:
    with pytest.raises(KeyError, match="no art contract is declared"):
        projectile_silhouette_art("spiral_v1")

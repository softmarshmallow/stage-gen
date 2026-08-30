from __future__ import annotations

from typing import get_args

import pytest

from stage_gen.components.platformer_content.models import (
    WEAPON_CLASSES_BY_PLAYER_EQUIPMENT,
    PlayerEquipment,
)
from stage_gen.components.platformer_gameplay.models import WeaponClass
from stage_gen.recipes.sideview_platformer.weapon_silhouettes import (
    PLAYER_EQUIPMENT_ART,
    player_equipment_art,
)


def test_every_equipment_the_contract_accepts_has_an_art_directive() -> None:
    """The check the module exists for.

    An equipment a package can author and this module has never heard of would otherwise reach the
    prompt builder and the review with no directive at all - the silent failure mode this recipe
    has already recorded for facing, framing, reach, and projectile axis.
    """

    declared = {entry.equipment for entry in PLAYER_EQUIPMENT_ART}
    assert declared == set(get_args(PlayerEquipment))


def test_every_equipment_declares_which_kits_it_can_fight_with() -> None:
    # The single declaration site. A member added to the vocabulary and not to the map would be
    # silently unpairable with every weapon class, which reads as "no package may author it".
    assert set(WEAPON_CLASSES_BY_PLAYER_EQUIPMENT) == set(get_args(PlayerEquipment))


def test_every_weapon_class_is_reachable_from_some_equipment() -> None:
    # The other direction, and the one that fails silently: a weapon class added to gameplay with
    # no equipment naming it would reject every package that selected it, at package validation,
    # with an error about the player's artwork.
    reachable = set().union(*WEAPON_CLASSES_BY_PLAYER_EQUIPMENT.values())
    assert reachable == set(get_args(WeaponClass))


def test_each_directive_leads_with_equipment_and_names_a_review_clause() -> None:
    # Leading, not trailing. This recipe has watched the same directive fail as a final sub-clause
    # and succeed as an opening labelled one.
    for entry in PLAYER_EQUIPMENT_ART:
        assert entry.carry_directive.startswith("EQUIPMENT, before anything else:")
        assert entry.review_clause


def test_the_weaponless_kits_prohibit_rather_than_omit() -> None:
    # Measured, not stylistic: during the rope spike the propless phrasing lost the sword more
    # often than it kept it, and only an explicit "never drawn" prohibition cleared the prop.
    # An equipment that means "no blade" must therefore say so out loud.
    for equipment in ("unarmed_v1", "thrown_kit_v1", "focus_implement_v1"):
        directive = player_equipment_art(equipment).carry_directive
        assert "NO" in directive
        assert "drawn anywhere in the image" in directive


def test_the_carrying_kits_demand_presence_in_every_frame() -> None:
    # The other measured failure: the wayfarer's sword vanished in 2 of 10 ladder strips and 4 of
    # 6 rope strips under a plain "preserve equipment" clause.
    for equipment in ("hand_weapon_v1", "focus_implement_v1"):
        assert "EVERY frame" in player_equipment_art(equipment).carry_directive


def test_an_undeclared_equipment_raises_rather_than_defaulting() -> None:
    with pytest.raises(KeyError, match="no art contract is declared"):
        player_equipment_art("greatbow_v1")

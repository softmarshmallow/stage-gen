"""The platformer genre member: resolution and the cross-contract rules.

Resolution turns the member's authored sources into typed contracts through
the package capture, locking every map, content and UI reference by digest,
then proves the member offline: one game_id everywhere, maps that gameplay
covers and can reach, portals that spawns and transitions resolve, the motion
states and artwork the gameplay obliges, and every cross-reference a runtime
would otherwise discover missing. :class:`ResolvedGamePackage` is the
platformer recipe's view of a resolved package with the member's contracts as
named fields.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.game_contract import PlatformerGenreMember, PreparedGameContract
from stage_gen.components.game_soundtrack import GameSoundtrack, load_game_soundtrack_bytes
from stage_gen.components.game_ui import GameUi, load_game_ui_bytes
from stage_gen.components.platformer_content import (
    PLAYER_CLIMB_STATE_BY_CLIMBABLE_ROLE,
    WEAPON_CLASSES_BY_PLAYER_EQUIPMENT,
    ItemContentCatalog,
    MobContentCatalog,
    NpcContentCatalog,
    PlayerContentCatalog,
    ProjectileContentCatalog,
    PropContentCatalog,
    load_item_content_bytes,
    load_mob_content_bytes,
    load_npc_content_bytes,
    load_player_content_bytes,
    load_projectile_content_bytes,
    load_prop_content_bytes,
)
from stage_gen.components.platformer_gameplay import (
    GameplayContract,
    GrantItemEffect,
    SetQuestStateEffect,
    load_gameplay_contract_bytes,
)
from stage_gen.components.platformer_map import PreparedGameMap, load_prepared_game_map_bytes
from stage_gen.components.scenario import (
    ResolvedScenario,
    ScenarioCatalog,
    load_scenario_catalog_bytes,
    resolve_scenario_bytes,
)
from stage_gen.orchestration.package_capture import (
    GamePackageValidationError,
    PackageCapture,
    ResolvedPreparedPackage,
    assert_subset,
    load_locked,
)


@dataclass(frozen=True, slots=True)
class ResolvedPlatformerMember:
    """The platformer member's resolved contracts."""

    member: PlatformerGenreMember
    gameplay: GameplayContract
    ui: GameUi
    soundtrack: GameSoundtrack
    maps: tuple[PreparedGameMap, ...]
    player: PlayerContentCatalog
    mobs: MobContentCatalog
    npcs: NpcContentCatalog
    props: PropContentCatalog
    items: ItemContentCatalog
    projectiles: ProjectileContentCatalog | None
    scenario_catalog: ScenarioCatalog
    scenarios: tuple[ResolvedScenario, ...]

    def identity(self) -> dict[str, object]:
        return {
            "map_ids": [entry.map_id for entry in self.maps],
            "player_ids": [entry.player_id for entry in self.player.players],
            "mob_ids": [entry.mob_id for entry in self.mobs.mobs],
            "npc_ids": [entry.npc_id for entry in self.npcs.npcs],
            "prop_ids": [entry.prop_id for entry in self.props.props],
            "item_ids": [entry.item_id for entry in self.items.items],
            "projectile_ids": (
                []
                if self.projectiles is None
                else [entry.projectile_id for entry in self.projectiles.projectiles]
            ),
            "scenario_ids": [entry.declarations.scenario_id for entry in self.scenarios],
            "track_ids": list(self.soundtrack.track_ids),
        }


@dataclass(frozen=True, slots=True)
class ResolvedGamePackage(ResolvedPreparedPackage):
    """A resolved package narrowed to its platformer member, with its contracts as fields.

    This is the platformer recipe's established view: every module that plans,
    generates or publishes the platformer reads `package.gameplay`, `package.maps`
    and the rest as named fields. Build one with :meth:`of`; a package without a
    platformer member has no such view.
    """

    platformer: PlatformerGenreMember
    gameplay: GameplayContract
    ui: GameUi
    soundtrack: GameSoundtrack
    maps: tuple[PreparedGameMap, ...]
    player: PlayerContentCatalog
    mobs: MobContentCatalog
    npcs: NpcContentCatalog
    props: PropContentCatalog
    items: ItemContentCatalog
    #: None for a package whose weapons throw nothing, which is most of them.
    projectiles: ProjectileContentCatalog | None
    scenario_catalog: ScenarioCatalog
    scenarios: tuple[ResolvedScenario, ...]

    @classmethod
    def of(cls, package: ResolvedPreparedPackage) -> ResolvedGamePackage:
        member = package.member("platformer", ResolvedPlatformerMember)
        if member is None:
            raise GamePackageValidationError(
                "missing_genre_member", "prepared package declares no platformer genre member"
            )
        shared = {
            entry.name: getattr(package, entry.name) for entry in fields(ResolvedPreparedPackage)
        }
        return cls(
            **shared,
            platformer=member.member,
            gameplay=member.gameplay,
            ui=member.ui,
            soundtrack=member.soundtrack,
            maps=member.maps,
            player=member.player,
            mobs=member.mobs,
            npcs=member.npcs,
            props=member.props,
            items=member.items,
            projectiles=member.projectiles,
            scenario_catalog=member.scenario_catalog,
            scenarios=member.scenarios,
        )


def resolve_platformer_member(
    capture: PackageCapture,
    *,
    game: PreparedGameContract,
    member: PlatformerGenreMember,
) -> ResolvedPlatformerMember:
    """Resolve and prove the platformer member out of the captured package."""

    resolved = _load_platformer_member(capture, member=member)
    for game_map in resolved.maps:
        for map_reference in game_map.references:
            capture.image(
                map_reference.source,
                map_reference.source_sha256,
                f"map {game_map.map_id} reference {map_reference.reference_id}",
            )
    for label, catalog in (
        ("player", resolved.player),
        ("mob", resolved.mobs),
        ("NPC", resolved.npcs),
        ("prop", resolved.props),
        ("item", resolved.items),
        *(() if resolved.projectiles is None else (("projectile", resolved.projectiles),)),
    ):
        for content_reference in catalog.references:
            capture.image(
                content_reference.source,
                content_reference.source_sha256,
                f"{label} reference {content_reference.reference_id}",
            )
    for ui_reference in resolved.ui.references:
        capture.image(
            ui_reference.source,
            ui_reference.source_sha256,
            f"UI reference {ui_reference.reference_id}",
        )
    _validate_cross_contracts(
        game=game,
        platformer=resolved.member,
        gameplay=resolved.gameplay,
        soundtrack=resolved.soundtrack,
        maps=resolved.maps,
        player=resolved.player,
        mobs=resolved.mobs,
        npcs=resolved.npcs,
        props=resolved.props,
        items=resolved.items,
        projectiles=resolved.projectiles,
        ui=resolved.ui,
        scenario_catalog=resolved.scenario_catalog,
        scenarios=resolved.scenarios,
    )
    return resolved


def _load_platformer_member(
    capture: PackageCapture,
    *,
    member: PlatformerGenreMember,
) -> ResolvedPlatformerMember:
    gameplay = load_locked(
        capture.member(member.gameplay.source),
        load_gameplay_contract_bytes,
        "invalid_gameplay_contract",
    )
    ui = load_locked(
        capture.member(member.ui.source),
        load_game_ui_bytes,
        "invalid_game_ui_contract",
    )
    if ui.inventory_panel is None:
        # The panel is optional in the contract because other genres never draw one; this
        # runtime does, so the requirement is stated here rather than imposed on everyone.
        raise GamePackageValidationError(
            "invalid_game_ui_contract", "the platformer UI contract requires an inventory panel"
        )
    if ui.cursor_set is not None:
        # The mirror rule: the cursor set is optional for a runtime that owns a mouse
        # pointer, and this one leaves the pointer to the browser, so a declared set would
        # be billed and never shown.
        raise GamePackageValidationError(
            "invalid_game_ui_contract",
            "the platformer UI contract must not declare a cursor_set the browser never draws",
        )
    soundtrack = load_locked(
        capture.member(member.soundtrack.source),
        lambda data: load_game_soundtrack_bytes(data, source_suffix=".toml"),
        "invalid_soundtrack_contract",
    )
    maps = tuple(
        load_locked(
            capture.member(binding.source),
            load_prepared_game_map_bytes,
            "invalid_map_contract",
        )
        for binding in member.maps
    )
    player = load_locked(
        capture.member(member.content.player.source),
        load_player_content_bytes,
        "invalid_player_content",
    )
    mobs = load_locked(
        capture.member(member.content.mobs.source),
        load_mob_content_bytes,
        "invalid_mob_content",
    )
    npcs = load_locked(
        capture.member(member.content.npcs.source),
        load_npc_content_bytes,
        "invalid_npc_content",
    )
    props = load_locked(
        capture.member(member.content.props.source),
        load_prop_content_bytes,
        "invalid_prop_content",
    )
    items = load_locked(
        capture.member(member.content.items.source),
        load_item_content_bytes,
        "invalid_item_content",
    )
    projectiles = (
        None
        if member.content.projectiles is None
        else load_locked(
            capture.member(member.content.projectiles.source),
            load_projectile_content_bytes,
            "invalid_projectile_content",
        )
    )
    scenario_catalog = load_locked(
        capture.member(member.scenarios.index_source),
        load_scenario_catalog_bytes,
        "invalid_scenario_catalog",
    )
    scenarios = tuple(
        _resolve_scenario_member(capture, scenario_id)
        for scenario_id in scenario_catalog.scenario_ids
    )
    return ResolvedPlatformerMember(
        member=member,
        gameplay=gameplay,
        ui=ui,
        soundtrack=soundtrack,
        maps=maps,
        player=player,
        mobs=mobs,
        npcs=npcs,
        props=props,
        items=items,
        projectiles=projectiles,
        scenario_catalog=scenario_catalog,
        scenarios=scenarios,
    )


def _resolve_scenario_member(capture: PackageCapture, scenario_id: str) -> ResolvedScenario:
    """Admit one scenario out of the captured package, failing with its own code."""

    try:
        return resolve_scenario_bytes(
            capture.member(f"scenarios/{scenario_id}.toml"),
            capture.member(f"scenarios/{scenario_id}.scenario"),
            scenario_id=scenario_id,
        )
    except (AuthoredContractLoadError, ValueError) as error:
        raise GamePackageValidationError("invalid_scenario_contract", str(error)) from error


def _validate_cross_contracts(
    *,
    game: PreparedGameContract,
    platformer: PlatformerGenreMember,
    gameplay: GameplayContract,
    ui: GameUi,
    soundtrack: GameSoundtrack,
    maps: tuple[PreparedGameMap, ...],
    player: PlayerContentCatalog,
    mobs: MobContentCatalog,
    npcs: NpcContentCatalog,
    props: PropContentCatalog,
    items: ItemContentCatalog,
    projectiles: ProjectileContentCatalog | None,
    scenario_catalog: ScenarioCatalog,
    scenarios: tuple[ResolvedScenario, ...],
) -> None:
    owned = [
        gameplay.game_id,
        ui.game_id,
        soundtrack.game_id,
        *(entry.game_id for entry in maps),
        player.game_id,
        mobs.game_id,
        npcs.game_id,
        props.game_id,
        items.game_id,
        *(() if projectiles is None else (projectiles.game_id,)),
        scenario_catalog.game_id,
        *(entry.declarations.game_id for entry in scenarios),
    ]
    if any(game_id != game.game_id for game_id in owned):
        raise GamePackageValidationError(
            "cross_game_identity", "every package contract must share game.toml game_id"
        )

    map_ids = {entry.map_id for entry in maps}
    if [entry.map_id for entry in maps] != [entry.map_id for entry in platformer.maps]:
        raise GamePackageValidationError(
            "map_identity_mismatch", "resolved map order and IDs must match game.toml"
        )
    if {entry.map_id for entry in gameplay.map_uses} != map_ids:
        raise GamePackageValidationError(
            "gameplay_map_mismatch", "gameplay map_uses must cover every package map exactly"
        )
    gameplay_map_refs = {
        gameplay.entry_map_id,
        *(entry.map_id for entry in gameplay.spawns),
        *(entry.from_map_id for entry in gameplay.transitions),
        *(entry.to_map_id for entry in gameplay.transitions),
        *(entry.map_id for entry in gameplay.mob_population.maps),
        *(entry.map_id for entry in gameplay.boss_encounters),
        *(entry.map_id for entry in gameplay.npc_placements),
        *(entry.map_id for entry in gameplay.prop_placements),
        *(entry.map_id for entry in gameplay.interactions),
    }
    assert_subset(gameplay_map_refs, map_ids, "gameplay map_id")
    maps_by_id = {entry.map_id: entry for entry in maps}
    for spawn in gameplay.spawns:
        game_map = maps_by_id[spawn.map_id]
        endpoints = {
            endpoint.anchor: endpoint
            for endpoint in (() if game_map.portal is None else game_map.portal.endpoints)
        }
        endpoint = endpoints.get(spawn.anchor)
        if endpoint is None:
            raise GamePackageValidationError(
                "spawn_portal_mismatch",
                f"spawn {spawn.spawn_id} anchor does not resolve a portal endpoint on "
                f"{spawn.map_id}",
            )
        if abs(endpoint.normalized_x - spawn.normalized_x) > 1e-9:
            raise GamePackageValidationError(
                "spawn_portal_position_mismatch",
                f"spawn {spawn.spawn_id} normalized_x must equal its map-owned portal endpoint",
            )
    for transition in gameplay.transitions:
        game_map = maps_by_id[transition.from_map_id]
        endpoint_anchors = {
            endpoint.anchor
            for endpoint in (() if game_map.portal is None else game_map.portal.endpoints)
        }
        if transition.from_anchor not in endpoint_anchors:
            raise GamePackageValidationError(
                "transition_portal_mismatch",
                f"transition {transition.transition_id} source does not resolve a map portal "
                "endpoint",
            )
    if any(game_map.climbable is not None for game_map in maps) and (
        "climb" not in gameplay.navigation.allowed_movements
    ):
        raise GamePackageValidationError(
            "climbable_movement_mismatch",
            "a map declares climbables but gameplay does not allow climb",
        )
    hostile_map_ids = {
        entry.map_id for entry in gameplay.map_uses if entry.hostile_population_enabled
    }
    population_map_ids = {entry.map_id for entry in gameplay.mob_population.maps}
    if hostile_map_ids != population_map_ids:
        raise GamePackageValidationError(
            "population_map_mismatch",
            "hostile map uses and mob-population maps must match exactly",
        )
    reachable_maps = {gameplay.entry_map_id}
    changed = True
    while changed:
        changed = False
        for transition in gameplay.transitions:
            if (
                transition.from_map_id in reachable_maps
                and transition.to_map_id not in reachable_maps
            ):
                reachable_maps.add(transition.to_map_id)
                changed = True
    if reachable_maps != map_ids:
        raise GamePackageValidationError(
            "unreachable_gameplay_map",
            "every package map must be reachable from entry_map_id through transitions",
        )

    player_ids = {entry.player_id for entry in player.players}
    mob_ids = {entry.mob_id for entry in mobs.mobs}
    npc_ids = {entry.npc_id for entry in npcs.npcs}
    prop_ids = {entry.prop_id for entry in props.props}
    item_ids = {entry.item_id for entry in items.items}
    track_ids = set(soundtrack.track_ids)
    scenario_ids = {entry.declarations.scenario_id for entry in scenarios}

    cast = platformer.cast
    if player_ids != {cast.player_id} or gameplay.player.player_id != cast.player_id:
        raise GamePackageValidationError(
            "player_identity_mismatch", "game, gameplay, and player content must name one player"
        )
    if mob_ids != set(cast.mob_ids):
        raise GamePackageValidationError(
            "mob_identity_mismatch", "game cast mob_ids must equal the mob catalog"
        )
    if npc_ids != set(cast.npc_ids):
        raise GamePackageValidationError(
            "npc_identity_mismatch", "game cast npc_ids must equal the NPC catalog"
        )
    if scenario_ids != set(scenario_catalog.scenario_ids):
        raise GamePackageValidationError(
            "scenario_identity_mismatch", "scenario catalog and resolved scenarios disagree"
        )
    for source, scenario in zip(scenario_catalog.scenarios, scenarios, strict=True):
        if source.scenario_id != scenario.declarations.scenario_id:
            raise GamePackageValidationError(
                "scenario_identity_mismatch", "scenario source ID does not match its contract"
            )

    required_player_states = {"idle", "walk"}
    movement_states = {"jump": "jump", "crouch": "crouch"}
    for movement, state in movement_states.items():
        if movement in gameplay.navigation.allowed_movements:
            required_player_states.add(state)
    if "climb" in gameplay.navigation.allowed_movements:
        # Climb is one movement with one pose per climbable role, so the states a package owes
        # are decided by what its maps actually place rather than by the movement alone. Without
        # this a package could place ropes and ship only the ladder strip, and the runtime would
        # draw a rope climb as a ladder climb with nothing rejecting it.
        required_player_states.update(_placed_climbable_roles(maps))
    if gameplay.combat.enabled:
        required_player_states.update(
            {
                gameplay.combat.basic_action,
                gameplay.combat.secondary_action,
                "hurt",
                "death",
            }
        )
        # Artwork obligation, in the same shape as the states above: the drawn character and the
        # kit they fight with are one fact authored in two files, and until this check existed a
        # package could ship a sword-carrying figure that throws darts with nothing objecting.
        #
        # Both sides are closed names, so this reads no prose and makes no judgement about whether
        # the weapon suits the character - that stays the author's business. It only refuses two
        # declarations that cannot both be true. What the picture actually shows is judged by the
        # actor review, which can see it, exactly as mob facing is.
        for entry in player.players:
            allowed = WEAPON_CLASSES_BY_PLAYER_EQUIPMENT[entry.equipment]
            if gameplay.combat.weapon_class not in allowed:
                raise GamePackageValidationError(
                    "player_equipment_mismatch",
                    f"player {entry.player_id} is drawn as {entry.equipment}, which cannot fight "
                    f"as {gameplay.combat.weapon_class}",
                )
    assert_subset(
        required_player_states,
        {motion.state for motion in player.players[0].motions},
        "required player motion state",
    )
    required_mob_states = {"idle", "move", "attack", "hurt", "death"}
    for mob in mobs.mobs:
        assert_subset(
            required_mob_states,
            {motion.state for motion in mob.motions},
            f"required motion state for mob {mob.mob_id}",
        )

    assert_subset(gameplay.player.starting_item_ids, item_ids, "starting item_id")
    assert_subset({gameplay.inventory.currency_item_id}, item_ids, "currency item_id")
    # Guarded rather than folded into the calls above: the field is optional, and `assert_subset`
    # takes an iterable of names, so an unset projectile would be reported as the id `None`.
    #
    # A package that names a round it did not draw has published a world that does not hold
    # together, so the reference is resolved here. The converse is deliberately not an error: a
    # catalog holding something no weapon currently fires is unspent art, not a broken package,
    # and a game with a second weapon class would make that reading wrong.
    projectile_ids = (
        set() if projectiles is None else {entry.projectile_id for entry in projectiles.projectiles}
    )
    if gameplay.combat.projectile_id is not None:
        if projectiles is None:
            raise GamePackageValidationError(
                "unresolved_cross_reference",
                "gameplay names a projectile but the package declares no projectile catalog",
            )
        assert_subset({gameplay.combat.projectile_id}, projectile_ids, "projectile_id")
    assert_subset(
        {
            entry.mob_id
            for map_entry in gameplay.mob_population.maps
            for zone in map_entry.zones
            for entry in zone.spawn_table
        },
        mob_ids,
        "population mob_id",
    )
    assert_subset({entry.mob_id for entry in gameplay.boss_encounters}, mob_ids, "boss mob_id")
    assert_subset(
        {entry.track_id for entry in gameplay.boss_encounters}, track_ids, "boss track_id"
    )
    assert_subset(
        {track_id for entry in gameplay.map_uses for track_id in entry.track_ids},
        track_ids,
        "map-use track_id",
    )
    assert_subset({entry.mob_id for entry in gameplay.loot_rules}, mob_ids, "loot mob_id")
    assert_subset({entry.item_id for entry in gameplay.loot_rules}, item_ids, "loot item_id")
    assert_subset({entry.npc_id for entry in gameplay.npc_placements}, npc_ids, "placed npc_id")
    assert_subset({entry.prop_id for entry in gameplay.prop_placements}, prop_ids, "placed prop_id")
    assert_subset(
        {entry.actor_id for entry in gameplay.interactions}, npc_ids, "interaction actor_id"
    )
    assert_subset(
        {entry.scenario_id for entry in gameplay.interactions},
        scenario_ids,
        "interaction scenario_id",
    )
    assert_subset(
        {entry.completion_item_id for entry in gameplay.quests}, item_ids, "quest item_id"
    )

    quest_ids = {entry.quest_id for entry in gameplay.quests}
    effect_ids = {entry.effect_id for entry in gameplay.effects}
    for effect in gameplay.effects:
        if isinstance(effect, SetQuestStateEffect):
            assert_subset({effect.quest_id}, quest_ids, "effect quest_id")
        elif isinstance(effect, GrantItemEffect):
            assert_subset({effect.item_id}, item_ids, "effect item_id")

    npc_by_id = {entry.npc_id: entry for entry in npcs.npcs}
    player_entry = player.players[0]
    actor_ids = player_ids | npc_ids
    # The scenario proved itself finishable on its own. What it cannot know is
    # whether this game can draw the people it names, so that is checked here.
    by_scenario = {entry.declarations.scenario_id: entry for entry in scenarios}
    for scenario in scenarios:
        for member_entry in scenario.declarations.cast:
            assert_subset({member_entry.actor_id}, actor_ids, "scenario actor_id")
            if member_entry.actor_id == player_entry.player_id:
                expressions = set(player_entry.dialogue_art.expressions)
            else:
                expressions = set(npc_by_id[member_entry.actor_id].dialogue_expressions)
            assert_subset(set(member_entry.expressions), expressions, "scenario expression")

    # And an interaction binds consequences to endings, so both halves must
    # resolve: an outcome the scenario never reaches would be dead authoring,
    # and an effect gameplay does not declare would fire nothing.
    for interaction in gameplay.interactions:
        bound = by_scenario[interaction.scenario_id]
        outcomes = {ending.outcome_id for ending in bound.declarations.endings}
        assert_subset(
            {outcome.outcome_id for outcome in interaction.outcomes},
            outcomes,
            "interaction outcome_id",
        )
        for outcome in interaction.outcomes:
            assert_subset(set(outcome.effect_ids), effect_ids, "interaction effect_id")


def _placed_climbable_roles(maps: Sequence[PreparedGameMap]) -> set[str]:
    """Return the player climb states the maps' placed climbables require.

    Keyed on placements rather than on the declared variant lists: a map may declare a rope
    appearance it never places, and an unplaced appearance owes the player no artwork.
    """

    required: set[str] = set()
    for game_map in maps:
        climbable = game_map.climbable
        if climbable is None:
            continue
        # Which climb states the player needs follows from the roster a map can DRAW, not from
        # where instances stand. Placement is generated terrain and does not exist yet at
        # package resolution; a declared rope variant already means the player must be able to
        # climb a rope, whatever the generator later does with it.
        for role, variants in (("ladder", climbable.ladders), ("rope", climbable.ropes)):
            if variants:
                required.add(PLAYER_CLIMB_STATE_BY_CLIMBABLE_ROLE[role])
    return required


__all__ = [
    "ResolvedGamePackage",
    "ResolvedPlatformerMember",
    "resolve_platformer_member",
]

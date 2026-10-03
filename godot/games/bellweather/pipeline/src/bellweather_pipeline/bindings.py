"""The gameplay bindings a package must resolve, and the content it promises to cover.

Both are computed from the package alone: every scenario speaker's expression must be one the
speaker's art declares, and the coverage matrix states what the content build owes the game,
family by family, so a family nothing counts is a family nothing checks.
"""

from __future__ import annotations

from bellweather_pipeline.motion_contract import motion_source_facing
from bellweather_pipeline.validation import ResolvedGamePackage
from demo_game_tools.kits.ui_art.nodes import document_roles


def gameplay_bindings(package: ResolvedGamePackage) -> dict[str, object]:
    """Gameplay, scenario, placement, drop and stable-ID bindings, every reference resolved."""

    gameplay = package.gameplay
    speaker_expressions = []
    player = package.player.players[0]
    npc_by_id = {entry.npc_id: entry for entry in package.npcs.npcs}
    for scenario in package.scenarios:
        scenario_id = scenario.declarations.scenario_id
        for member in scenario.declarations.cast:
            expressions = (
                player.dialogue_art.expressions
                if member.actor_id == player.player_id
                else npc_by_id[member.actor_id].dialogue_expressions
            )
            for expression in member.expressions:
                if expression not in expressions:
                    raise ValueError(
                        f"scenario expression does not resolve: {scenario_id}/"
                        f"{member.actor_id}/{expression}"
                    )
                speaker_expressions.append(
                    {
                        "scenario_id": scenario_id,
                        "speaker_id": member.actor_id,
                        "expression": expression,
                    }
                )
    return {
        "schema_version": 1,
        "kind": "prepared-gameplay-bindings-v1",
        "game_id": package.game.game_id,
        "package_sha256": package.package_sha256,
        "player_id": gameplay.player.player_id,
        "starting_item_ids": gameplay.player.starting_item_ids,
        "currency_item_id": gameplay.inventory.currency_item_id,
        "mob_spawn_ids": sorted(
            {
                entry.mob_id
                for map_entry in gameplay.mob_population.maps
                for zone in map_entry.zones
                for entry in zone.spawn_table
            }
        ),
        "boss_mob_ids": [entry.mob_id for entry in gameplay.boss_encounters],
        "loot": [entry.model_dump(mode="json") for entry in gameplay.loot_rules],
        "npc_placements": [entry.model_dump(mode="json") for entry in gameplay.npc_placements],
        "prop_placements": [entry.model_dump(mode="json") for entry in gameplay.prop_placements],
        "interactions": [entry.model_dump(mode="json") for entry in gameplay.interactions],
        "scenario_speaker_expressions": speaker_expressions,
        "effect_ids": [entry.effect_id for entry in gameplay.effects],
        "track_ids": sorted(
            {track_id for map_use in gameplay.map_uses for track_id in map_use.track_ids}
        ),
        "map_topology": [
            {
                "map_id": game_map.map_id,
                # The authored request, not generated geometry: content direction needs the
                # shape of the world, and taking it from the map keeps this independent of
                # terrain generation.
                "occupancy_rows": game_map.terrain.rows,
                "occupancy_columns": game_map.terrain.columns,
                "climbable_ids": (
                    []
                    if game_map.climbable is None
                    else [entry.variant_id for entry in game_map.climbable.variants]
                ),
                "climbable_variants": (
                    []
                    if game_map.climbable is None
                    else [entry.variant_id for entry in game_map.climbable.variants]
                ),
                "portal_anchors": (
                    []
                    if game_map.portal is None
                    else [entry.anchor for entry in game_map.portal.endpoints]
                ),
            }
            for game_map in package.maps
        ],
        "all_references_resolved": True,
    }


def coverage_matrix(package: ResolvedGamePackage) -> dict[str, object]:
    """Every content family the build draws, with the operations it owes."""

    projectile_ids = (
        []
        if package.projectiles is None
        else [entry.projectile_id for entry in package.projectiles.projectiles]
    )
    return {
        "schema_version": 1,
        "kind": "prepared-content-coverage-matrix-v1",
        "game_id": package.game.game_id,
        "package_sha256": package.package_sha256,
        "players": [
            {
                "player_id": entry.player_id,
                "motions": [motion.model_dump(mode="json") for motion in entry.motions],
                "source_facings": {
                    motion.state: motion_source_facing("player", motion.state)
                    for motion in entry.motions
                },
                "dialogue_expressions": entry.dialogue_art.expressions,
            }
            for entry in package.player.players
        ],
        "mobs": [
            {
                "mob_id": entry.mob_id,
                "motions": [motion.model_dump(mode="json") for motion in entry.motions],
                "source_facings": {
                    motion.state: motion_source_facing("mob", motion.state)
                    for motion in entry.motions
                },
            }
            for entry in package.mobs.mobs
        ],
        "npcs": [
            {
                "npc_id": entry.npc_id,
                "motions": [motion.model_dump(mode="json") for motion in entry.motions],
                "source_facings": {
                    motion.state: motion_source_facing(
                        "npc", motion.state, npc_world_orientation=package.npcs.world_orientation
                    )
                    for motion in entry.motions
                },
                "dialogue_expressions": entry.dialogue_expressions,
            }
            for entry in package.npcs.npcs
        ],
        "prop_ids": [entry.prop_id for entry in package.props.props],
        "item_ids": [entry.item_id for entry in package.items.items],
        "projectile_ids": projectile_ids,
        "track_ids": list(package.soundtrack.track_ids),
        "scenario_ids": [entry.declarations.scenario_id for entry in package.scenarios],
        # Content families only: map layers and their loops are the map build's fan-out.
        "required_image_operations": (
            sum(2 + len(entry.motions) for entry in package.player.players)
            + sum(1 + len(entry.motions) for entry in package.mobs.mobs)
            + 3 * len(package.npcs.npcs)
            + len(package.props.props)
            + len(package.items.items)
            + len(projectile_ids)
            + 1
            + len(document_roles(package.ui))
        ),
        # One board-and-review pass per catalog family (props, items, inventory panel), one per
        # nine-slice atlas role, one per actor, and one for a declared projectile catalog.
        "required_structured_reviews": (
            len(package.player.players)
            + len(package.mobs.mobs)
            + len(package.npcs.npcs)
            + 3
            + len(document_roles(package.ui))
            + (1 if package.projectiles is not None else 0)
        ),
        "required_music_operations": len(package.soundtrack.tracks),
    }


__all__ = ["coverage_matrix", "gameplay_bindings"]

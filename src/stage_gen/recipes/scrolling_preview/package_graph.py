"""Build the exact scrolling-preview asset DAG from one resolved game package."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from stage_gen.components.game_content import (
    DEFAULT_MOTION_ANCHOR,
    ContentReference,
    MotionPresentation,
)
from stage_gen.components.game_map import PreparedGameMap, PreparedMapReference
from stage_gen.config import StageGenConfig
from stage_gen.media import (
    BRIDGE_REGISTRATION_VERSION,
    GENERATED_BRIDGE_VERSION,
    MIRROR_REPEAT_VERSION,
)
from stage_gen.orchestration.execution_graph import (
    ExecutionGraph,
    ExecutionNode,
    ExecutionResource,
    OperationKind,
    RetryOwner,
    build_node_cache_key,
    finalize_execution_graph,
)
from stage_gen.orchestration.game_package import ResolvedGamePackage
from stage_gen.recipes.scrolling_preview.layer_contract import (
    LAYER_PLACEMENT_CANONICALIZER,
    LOOP_BRIDGE_BRIEF_VERSION,
    LOOP_BRIDGE_CONTEXT_SPAN_PX,
    LOOP_BRIDGE_SPAN_PX,
    NON_GENERATIVE_LAYER_FIELDS,
    PLACEMENT_ONLY_GROUND_FIELDS,
    RUNTIME_ONLY_LAYER_FIELDS,
)
from stage_gen.recipes.scrolling_preview.motion_contract import (
    DEFAULT_MOTION_ATLAS_GEOMETRY,
    MotionActorKind,
    motion_atlas_geometry,
    motion_source_facing,
    recipe_owned_motion_direction,
)
from stage_gen.recipes.scrolling_preview.terrain_atlas import (
    MATERIAL_ASSEMBLER_ID,
    MATERIAL_SOURCE_CONTRACT_ID,
)
from stage_gen.resources import (
    inventory_template_path,
    terrain_atlas_lookup_path,
    terrain_atlas_template_path,
    terrain_atlas_topology_reference_path,
)

PACKAGE_GRAPH_CONTRACT_VERSION = "scrolling-preview-prepared-package-v10"
CONTENT_CONCEPT_CONTRACT_VERSION = "prepared-content-concept-v1"
CONTENT_MOTION_CONTRACT_VERSION = "prepared-content-motion-atlas-v3"
CONTENT_DIALOGUE_CONTRACT_VERSION = "prepared-content-dialogue-atlas-v1"
CONTENT_ALPHA_REPACK_CONTRACT_VERSION = "alpha-component-repack-v1"
CONTENT_CATALOG_CONTRACT_VERSION = "prepared-content-isolated-catalog-v1"
CONTENT_PROP_CONTACT_VALIDATION_VERSION = "prepared-content-prop-contact-v1"
CONTENT_REVIEW_CONTRACT_VERSION = "prepared-content-review-v4"
CONTENT_ACTOR_PLAYBACK_REVIEW_CONTRACT_VERSION = "prepared-content-actor-playback-review-v1"
CONTENT_PLAYER_REVIEW_CONTRACT_VERSION = "prepared-content-player-review-v6"
CONTENT_BINDING_CONTRACT_VERSION = "prepared-content-binding-report-v1"
CONTENT_SOUNDTRACK_CONTRACT_VERSION = "prepared-content-soundtrack-v1"
UI_INVENTORY_PANEL_CONTRACT_VERSION = "prepared-ui-inventory-panel-v2"
UI_INVENTORY_PANEL_REVIEW_VERSION = "prepared-ui-inventory-panel-review-v1"
MAP_CLIMBABLE_CONTRACT_VERSION = "prepared-map-climbable-atlas-v1"
MAP_PORTAL_CONTRACT_VERSION = "prepared-map-portal-pair-1x2-v1"


@dataclass(frozen=True, slots=True)
class PackageGraphProfile:
    image_provider: str
    image_model: str
    image_ipm: int
    structured_provider: str
    structured_model: str
    music_provider: str
    music_model: str


def package_graph_profile(config: StageGenConfig) -> PackageGraphProfile:
    """Select provider routes without reading or retaining provider credentials."""

    return PackageGraphProfile(
        image_provider="openai",
        image_model=config.openai_image_model,
        image_ipm=config.openai_image_ipm,
        structured_provider="openrouter",
        structured_model=config.text_model,
        music_provider="openrouter",
        music_model=config.music_model,
    )


def build_package_execution_graph(
    package: ResolvedGamePackage,
    *,
    profile: PackageGraphProfile,
) -> ExecutionGraph:
    """Expand every authored map and content entry into stable executable nodes."""

    builder = _GraphBuilder(package, profile)
    package_node = builder.add(
        "package-resolve",
        domain="package",
        description="validate and capture the complete prepared package",
        operation=OperationKind.LOCAL,
        input_digests=(package.package_sha256,),
        outputs=("package.identity.json",),
        duration_seconds=0.1,
    )
    package_root = package_node.node_id

    terminal_nodes: list[str] = []
    terminal_nodes.extend(_add_map_nodes(builder, package_root))
    terminal_nodes.extend(_add_player_nodes(builder, package_root))
    terminal_nodes.extend(_add_mob_nodes(builder, package_root))
    terminal_nodes.extend(_add_npc_nodes(builder, package_root))
    terminal_nodes.append(_add_prop_nodes(builder, package_root))
    terminal_nodes.append(_add_item_nodes(builder, package_root))
    terminal_nodes.append(_add_ui_nodes(builder, package_root))
    terminal_nodes.extend(_add_soundtrack_nodes(builder, package_root))

    binding = builder.add(
        "gameplay-bindings-validate",
        domain="gameplay",
        description="validate gameplay, sequence, placement, drop, and stable-ID bindings",
        operation=OperationKind.LOCAL,
        depends_on=(package_root,),
        cache_depends_on=(),
        input_digests=(
            _object_sha256({"contract": CONTENT_BINDING_CONTRACT_VERSION}),
            *_file_digests(
                package,
                (
                    "gameplay.toml",
                    *(entry.source for entry in package.game.maps),
                    "sequences/index.toml",
                    *(entry.source for entry in package.sequence_catalog.sequences),
                ),
            ),
        ),
        outputs=("gameplay.bindings.json", "content/coverage-matrix.json"),
        duration_seconds=0.5,
    )
    terminal_nodes.append(binding.node_id)

    manifest = builder.add(
        "manifest-assemble",
        domain="manifest",
        description="assemble the terminal game manifest from validated artifact bindings",
        operation=OperationKind.LOCAL,
        depends_on=tuple(terminal_nodes),
        input_digests=(package.canonical_game_sha256,),
        outputs=("manifest.json",),
        duration_seconds=1.0,
    )
    return finalize_execution_graph(
        game_id=package.game.game_id,
        package_sha256=package.package_sha256,
        resources=builder.resources,
        nodes=builder.nodes,
        terminal_node_id=manifest.node_id,
    )


def _add_map_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    terminals: list[str] = []
    for game_map in builder.package.maps:
        references = {entry.reference_id: entry for entry in game_map.references}
        # Loop construction is consumed after generation, so it is excluded here for the same
        # reason placement is: switching a map between mirror and bridge must re-run the loop node
        # only, never re-bill every layer image.
        map_direction = _object_sha256(
            {
                "game": _visual_direction(builder.package),
                "view": game_map.view.model_dump(mode="json"),
                "continuity": game_map.continuity.model_dump(
                    mode="json", exclude={"loop_construction"}
                ),
            }
        )
        layer_validations: list[str] = []
        for layer in game_map.layers:
            # Vertical placement is consumed downstream of the image, so it must not enter the
            # generation digest: changing an anchor re-runs one local node instead of re-billing
            # a provider image that would come back byte-identical.
            input_digests = (
                map_direction,
                _object_sha256(
                    layer.model_dump(mode="json", exclude=set(NON_GENERATIVE_LAYER_FIELDS))
                ),
                *_reference_digests(references, layer.reference_ids),
            )
            generated = builder.add_external(
                f"map-{game_map.map_id}-layer-{layer.layer_id}-generate",
                domain=f"map-{game_map.map_id}",
                description=f"generate map layer {game_map.map_id}/{layer.layer_id}",
                operation=OperationKind.IMAGE_GENERATION,
                depends_on=(package_root,),
                cache_depends_on=(),
                input_digests=input_digests,
                outputs=(f"maps/{game_map.map_id}/layers/{layer.layer_id}.raw.png",),
            )
            # Loop construction sits between generation and validation because the bridge variant
            # needs a provider call, while the mirror variant is purely local. Admission runs
            # first inside the node, so a layer the model already returned as a clean repeat unit
            # costs nothing on either route.
            bridged = game_map.continuity.loop_construction == "generated_bridge"
            loop_digests = (
                _object_sha256(
                    {
                        "construction": game_map.continuity.loop_construction,
                        "mirror": MIRROR_REPEAT_VERSION,
                        "bridge": GENERATED_BRIDGE_VERSION,
                        "registration": BRIDGE_REGISTRATION_VERSION,
                        "brief": LOOP_BRIDGE_BRIEF_VERSION,
                        "context_span": LOOP_BRIDGE_CONTEXT_SPAN_PX,
                        "bridge_span": LOOP_BRIDGE_SPAN_PX,
                        "alpha_mode": layer.alpha_mode,
                    }
                ),
            )
            loop_outputs = (
                f"maps/{game_map.map_id}/layers/{layer.layer_id}.loop.png",
                f"maps/{game_map.map_id}/layers/{layer.layer_id}.loop.json",
            )
            if bridged:
                looped = builder.add_external(
                    f"map-{game_map.map_id}-layer-{layer.layer_id}-loop",
                    domain=f"map-{game_map.map_id}",
                    description=f"admit or bridge the x-axis loop for {layer.layer_id}",
                    operation=OperationKind.IMAGE_GENERATION,
                    depends_on=(generated.node_id,),
                    cache_depends_on=(),
                    input_digests=loop_digests,
                    outputs=loop_outputs,
                )
            else:
                looped = builder.add(
                    f"map-{game_map.map_id}-layer-{layer.layer_id}-loop",
                    domain=f"map-{game_map.map_id}",
                    description=f"admit or mirror the x-axis loop for {layer.layer_id}",
                    operation=OperationKind.LOCAL,
                    depends_on=(generated.node_id,),
                    input_digests=loop_digests,
                    outputs=loop_outputs,
                    duration_seconds=1.0,
                )
            validated = builder.add(
                f"map-{game_map.map_id}-layer-{layer.layer_id}-validate",
                domain=f"map-{game_map.map_id}",
                description=f"validate alpha and x-axis repeat admission for {layer.layer_id}",
                operation=OperationKind.LOCAL,
                depends_on=(looped.node_id,),
                input_digests=(
                    _object_sha256(
                        layer.model_dump(mode="json", exclude=set(RUNTIME_ONLY_LAYER_FIELDS))
                    ),
                    _object_sha256(
                        {
                            "canonicalizer": "prepared-map-loop-construction-v1",
                            "placement": LAYER_PLACEMENT_CANONICALIZER,
                        }
                    ),
                ),
                outputs=(
                    f"maps/{game_map.map_id}/layers/{layer.layer_id}.png",
                    f"maps/{game_map.map_id}/layers/{layer.layer_id}.validation.json",
                    f"maps/{game_map.map_id}/layers/{layer.layer_id}.repeat.png",
                ),
                duration_seconds=1.0,
            )
            layer_validations.append(validated.node_id)

        # The atlas paintover is appearance only: authored geometry and vertical fit select cells
        # and placement downstream without changing what the image model is asked to paint.
        ground_direction = game_map.ground.model_dump(
            mode="json", exclude=set(PLACEMENT_ONLY_GROUND_FIELDS)
        )
        ground = builder.add_external(
            f"map-{game_map.map_id}-ground-generate",
            domain=f"map-{game_map.map_id}",
            description=f"paint the declared 47-mask ground atlas for {game_map.map_id}",
            operation=OperationKind.IMAGE_GENERATION,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=(
                map_direction,
                _object_sha256(ground_direction),
                *_reference_digests(references, game_map.ground.reference_ids),
                hashlib.sha256(terrain_atlas_template_path().read_bytes()).hexdigest(),
                hashlib.sha256(terrain_atlas_topology_reference_path().read_bytes()).hexdigest(),
                _object_sha256({"generation_contract": MATERIAL_SOURCE_CONTRACT_ID}),
            ),
            outputs=(f"maps/{game_map.map_id}/ground.raw.png",),
        )
        ground_validation = builder.add(
            f"map-{game_map.map_id}-ground-validate",
            domain=f"map-{game_map.map_id}",
            description=f"validate the {game_map.ground.mode} ground contract",
            operation=OperationKind.LOCAL,
            depends_on=(ground.node_id,),
            input_digests=(
                _object_sha256(ground_direction),
                _object_sha256({"canonicalizer": MATERIAL_ASSEMBLER_ID}),
                hashlib.sha256(terrain_atlas_lookup_path().read_bytes()).hexdigest(),
                hashlib.sha256(terrain_atlas_template_path().read_bytes()).hexdigest(),
            ),
            outputs=(
                f"maps/{game_map.map_id}/ground.png",
                f"maps/{game_map.map_id}/ground.validation.json",
                f"maps/{game_map.map_id}/ground.evidence.png",
            ),
            duration_seconds=1.5,
        )
        presentation_validations: list[str] = []
        if game_map.climbable is not None:
            climbable = builder.add_external(
                f"map-{game_map.map_id}-climbable-generate",
                domain=f"map-{game_map.map_id}",
                description=f"generate map-local climbable atlas for {game_map.map_id}",
                operation=OperationKind.IMAGE_GENERATION,
                depends_on=(package_root,),
                cache_depends_on=(),
                input_digests=(
                    map_direction,
                    _object_sha256({"contract": MAP_CLIMBABLE_CONTRACT_VERSION}),
                    _object_sha256(game_map.climbable.model_dump(mode="json")),
                    *_reference_digests(references, game_map.climbable.reference_ids),
                ),
                outputs=(f"maps/{game_map.map_id}/climbable.raw.png",),
            )
            climbable_validation = builder.add(
                f"map-{game_map.map_id}-climbable-validate",
                domain=f"map-{game_map.map_id}",
                description=f"isolate and validate the climbable atlas for {game_map.map_id}",
                operation=OperationKind.LOCAL,
                depends_on=(climbable.node_id,),
                input_digests=(
                    _object_sha256({"contract": MAP_CLIMBABLE_CONTRACT_VERSION}),
                    _object_sha256(game_map.climbable.model_dump(mode="json")),
                ),
                outputs=(
                    f"maps/{game_map.map_id}/climbable.png",
                    f"maps/{game_map.map_id}/climbable.validation.json",
                ),
                duration_seconds=0.75,
            )
            presentation_validations.append(climbable_validation.node_id)
        if game_map.portal is not None:
            portal = builder.add_external(
                f"map-{game_map.map_id}-portal-generate",
                domain=f"map-{game_map.map_id}",
                description=f"generate map-local portal pair for {game_map.map_id}",
                operation=OperationKind.IMAGE_GENERATION,
                depends_on=(package_root,),
                cache_depends_on=(),
                input_digests=(
                    map_direction,
                    _object_sha256({"contract": MAP_PORTAL_CONTRACT_VERSION}),
                    _object_sha256(game_map.portal.model_dump(mode="json")),
                    *_reference_digests(references, game_map.portal.reference_ids),
                ),
                outputs=(f"maps/{game_map.map_id}/portal.raw.png",),
            )
            portal_validation = builder.add(
                f"map-{game_map.map_id}-portal-validate",
                domain=f"map-{game_map.map_id}",
                description=f"isolate and validate the portal pair for {game_map.map_id}",
                operation=OperationKind.LOCAL,
                depends_on=(portal.node_id,),
                input_digests=(
                    _object_sha256({"contract": MAP_PORTAL_CONTRACT_VERSION}),
                    _object_sha256(game_map.portal.model_dump(mode="json")),
                ),
                outputs=(
                    f"maps/{game_map.map_id}/portal.png",
                    f"maps/{game_map.map_id}/portal.validation.json",
                ),
                duration_seconds=0.75,
            )
            presentation_validations.append(portal_validation.node_id)
        composite = builder.add(
            f"map-{game_map.map_id}-composite",
            domain=f"map-{game_map.map_id}",
            description=f"compose all declared layers and ground for {game_map.map_id}",
            operation=OperationKind.LOCAL,
            depends_on=(*layer_validations, ground_validation.node_id),
            input_digests=(
                _object_sha256(_map_without_runtime_presentation(game_map)),
                _object_sha256({"compositor": "prepared-map-placed-compositor-v6"}),
            ),
            outputs=(f"maps/{game_map.map_id}/composite.png",),
            duration_seconds=2.0,
        )
        review = builder.add_external(
            f"map-{game_map.map_id}-review",
            domain=f"map-{game_map.map_id}",
            description=f"review complete map composition {game_map.map_id}",
            operation=OperationKind.STRUCTURED_GENERATION,
            depends_on=(composite.node_id, *presentation_validations),
            input_digests=(
                map_direction,
                _object_sha256({"review_contract": "prepared-map-review-v4"}),
            ),
            outputs=(f"maps/{game_map.map_id}/review.json",),
        )
        terminals.append(review.node_id)
    return terminals


def _add_player_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    terminals: list[str] = []
    references = {entry.reference_id: entry for entry in builder.package.player.references}
    for player in builder.package.player.players:
        identity = (
            _visual_direction_digest(builder.package),
            _object_sha256({"contract": CONTENT_CONCEPT_CONTRACT_VERSION}),
            _object_sha256(player.model_dump(mode="json", exclude={"motions"})),
            *_reference_digests(references, player.reference_ids),
        )
        concept = builder.add_external(
            f"player-{player.player_id}-concept-generate",
            domain=f"player-{player.player_id}",
            description=f"generate identity concept for player {player.player_id}",
            operation=OperationKind.IMAGE_GENERATION,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=identity,
            outputs=(f"content/players/{player.player_id}/concept.png",),
        )
        validations: list[str] = []
        for motion in player.motions:
            state = motion.state
            source_facing = motion_source_facing("player", state)
            generated = builder.add_external(
                f"player-{player.player_id}-state-{state}-generate",
                domain=f"player-{player.player_id}",
                description=f"generate {state} state from one {source_facing}-facing source strip",
                operation=OperationKind.IMAGE_GENERATION,
                depends_on=(concept.node_id,),
                input_digests=(
                    _object_sha256({"contract": CONTENT_MOTION_CONTRACT_VERSION}),
                    _object_sha256(_motion_identity("player", state, source_facing)),
                ),
                outputs=(f"content/players/{player.player_id}/states/{state}.source.png",),
            )
            validations.append(
                builder.add(
                    f"player-{player.player_id}-state-{state}-validate",
                    domain=f"player-{player.player_id}",
                    description=(
                        f"validate player {state} geometry, alpha, source facing, and registration"
                    ),
                    operation=OperationKind.LOCAL,
                    depends_on=(generated.node_id,),
                    input_digests=(
                        _object_sha256({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                        _object_sha256(_motion_repack_identity(motion)),
                    ),
                    outputs=(
                        f"content/players/{player.player_id}/states/{state}.png",
                        f"content/players/{player.player_id}/states/{state}.validation.json",
                    ),
                    duration_seconds=0.75,
                ).node_id
            )
        dialogue = builder.add_external(
            f"player-{player.player_id}-dialogue-generate",
            domain=f"player-{player.player_id}",
            description=f"generate declared dialogue expressions for player {player.player_id}",
            operation=OperationKind.IMAGE_GENERATION,
            depends_on=(concept.node_id,),
            input_digests=(
                _object_sha256({"contract": CONTENT_DIALOGUE_CONTRACT_VERSION}),
                _object_sha256(player.dialogue_art.model_dump(mode="json")),
            ),
            outputs=(f"content/players/{player.player_id}/dialogue.source.png",),
        )
        dialogue_validation = builder.add(
            f"player-{player.player_id}-dialogue-validate",
            domain=f"player-{player.player_id}",
            description="validate player dialogue expression coverage",
            operation=OperationKind.LOCAL,
            depends_on=(dialogue.node_id,),
            input_digests=(
                _object_sha256({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                _object_sha256(player.dialogue_art.model_dump(mode="json")),
            ),
            outputs=(
                f"content/players/{player.player_id}/dialogue.png",
                f"content/players/{player.player_id}/dialogue.validation.json",
            ),
            duration_seconds=0.75,
        )
        contact = builder.add(
            f"player-{player.player_id}-contact-sheet",
            domain=f"player-{player.player_id}",
            description=f"assemble complete player review board for {player.player_id}",
            operation=OperationKind.LOCAL,
            depends_on=(*validations, dialogue_validation.node_id),
            input_digests=(_object_sha256(player.model_dump(mode="json", exclude={"motions"})),),
            outputs=(f"content/players/{player.player_id}/contact-sheet.png",),
            duration_seconds=1.0,
        )
        review = builder.add_external(
            f"player-{player.player_id}-review",
            domain=f"player-{player.player_id}",
            description=(
                "review identity, motion, facing, scale, and expression continuity for "
                f"{player.player_id}"
            ),
            operation=OperationKind.STRUCTURED_GENERATION,
            depends_on=(contact.node_id,),
            input_digests=(
                *identity,
                _object_sha256({"contract": CONTENT_REVIEW_CONTRACT_VERSION}),
                _object_sha256({"contract": CONTENT_ACTOR_PLAYBACK_REVIEW_CONTRACT_VERSION}),
                _object_sha256({"contract": CONTENT_PLAYER_REVIEW_CONTRACT_VERSION}),
            ),
            outputs=(f"content/players/{player.player_id}/review.json",),
        )
        terminals.append(review.node_id)
    return terminals


def _add_mob_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    terminals: list[str] = []
    references = {entry.reference_id: entry for entry in builder.package.mobs.references}
    for mob in builder.package.mobs.mobs:
        identity = (
            _visual_direction_digest(builder.package),
            _object_sha256({"contract": CONTENT_CONCEPT_CONTRACT_VERSION}),
            _object_sha256(mob.model_dump(mode="json", exclude={"motions"})),
            *_reference_digests(references, mob.reference_ids),
        )
        concept = builder.add_external(
            f"mob-{mob.mob_id}-concept-generate",
            domain=f"mob-{mob.mob_id}",
            description=f"generate identity concept for mob {mob.mob_id}",
            operation=OperationKind.IMAGE_GENERATION,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=identity,
            outputs=(f"content/mobs/{mob.mob_id}/concept.png",),
        )
        validations: list[str] = []
        for motion in mob.motions:
            state = motion.state
            source_facing = motion_source_facing("mob", state)
            generated = builder.add_external(
                f"mob-{mob.mob_id}-state-{state}-generate",
                domain=f"mob-{mob.mob_id}",
                description=(
                    f"generate {state} state for mob {mob.mob_id} from one "
                    f"{source_facing}-facing source strip"
                ),
                operation=OperationKind.IMAGE_GENERATION,
                depends_on=(concept.node_id,),
                input_digests=(
                    _object_sha256({"contract": CONTENT_MOTION_CONTRACT_VERSION}),
                    _object_sha256(_motion_identity("mob", state, source_facing)),
                ),
                outputs=(f"content/mobs/{mob.mob_id}/states/{state}.source.png",),
            )
            validations.append(
                builder.add(
                    f"mob-{mob.mob_id}-state-{state}-validate",
                    domain=f"mob-{mob.mob_id}",
                    description=f"validate mob {mob.mob_id} {state} state",
                    operation=OperationKind.LOCAL,
                    depends_on=(generated.node_id,),
                    input_digests=(
                        _object_sha256({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                        _object_sha256(_motion_repack_identity(motion)),
                    ),
                    outputs=(
                        f"content/mobs/{mob.mob_id}/states/{state}.png",
                        f"content/mobs/{mob.mob_id}/states/{state}.validation.json",
                    ),
                    duration_seconds=0.75,
                ).node_id
            )
        contact = builder.add(
            f"mob-{mob.mob_id}-contact-sheet",
            domain=f"mob-{mob.mob_id}",
            description=f"assemble complete mob review board for {mob.mob_id}",
            operation=OperationKind.LOCAL,
            depends_on=tuple(validations),
            input_digests=(_object_sha256(mob.model_dump(mode="json", exclude={"motions"})),),
            outputs=(f"content/mobs/{mob.mob_id}/contact-sheet.png",),
            duration_seconds=1.0,
        )
        review = builder.add_external(
            f"mob-{mob.mob_id}-review",
            domain=f"mob-{mob.mob_id}",
            description=f"review identity and state continuity for mob {mob.mob_id}",
            operation=OperationKind.STRUCTURED_GENERATION,
            depends_on=(contact.node_id,),
            input_digests=(
                *identity,
                _object_sha256({"contract": CONTENT_REVIEW_CONTRACT_VERSION}),
                _object_sha256({"contract": CONTENT_ACTOR_PLAYBACK_REVIEW_CONTRACT_VERSION}),
            ),
            outputs=(f"content/mobs/{mob.mob_id}/review.json",),
        )
        terminals.append(review.node_id)
    return terminals


def _add_npc_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    terminals: list[str] = []
    references = {entry.reference_id: entry for entry in builder.package.npcs.references}
    for npc in builder.package.npcs.npcs:
        source_facing = motion_source_facing(
            "npc",
            "idle",
            npc_world_orientation=builder.package.npcs.world_orientation,
        )
        identity = (
            _visual_direction_digest(builder.package),
            _object_sha256({"contract": CONTENT_CONCEPT_CONTRACT_VERSION}),
            _object_sha256(npc.model_dump(mode="json", exclude={"motions"})),
            *_reference_digests(references, npc.reference_ids),
        )
        concept = builder.add_external(
            f"npc-{npc.npc_id}-concept-generate",
            domain=f"npc-{npc.npc_id}",
            description=f"generate identity concept for NPC {npc.npc_id}",
            operation=OperationKind.IMAGE_GENERATION,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=identity,
            outputs=(f"content/npcs/{npc.npc_id}/concept.png",),
        )
        world = builder.add_external(
            f"npc-{npc.npc_id}-world-generate",
            domain=f"npc-{npc.npc_id}",
            description=(
                f"generate NPC {npc.npc_id} world sprite from one "
                f"{source_facing}-facing source strip"
            ),
            operation=OperationKind.IMAGE_GENERATION,
            depends_on=(concept.node_id,),
            input_digests=(
                _object_sha256({"contract": CONTENT_MOTION_CONTRACT_VERSION}),
                _object_sha256(
                    {
                        "states": [motion.state for motion in npc.motions],
                        "source_facing": source_facing,
                    }
                ),
            ),
            outputs=(f"content/npcs/{npc.npc_id}/world.source.png",),
        )
        world_validation = builder.add(
            f"npc-{npc.npc_id}-world-validate",
            domain=f"npc-{npc.npc_id}",
            description=f"validate NPC {npc.npc_id} world sprite",
            operation=OperationKind.LOCAL,
            depends_on=(world.node_id,),
            input_digests=(
                _object_sha256({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                _object_sha256([_motion_repack_identity(motion) for motion in npc.motions]),
            ),
            outputs=(
                f"content/npcs/{npc.npc_id}/world.png",
                f"content/npcs/{npc.npc_id}/world.validation.json",
            ),
            duration_seconds=0.75,
        )
        dialogue = builder.add_external(
            f"npc-{npc.npc_id}-dialogue-generate",
            domain=f"npc-{npc.npc_id}",
            description=f"generate NPC {npc.npc_id} dialogue expressions",
            operation=OperationKind.IMAGE_GENERATION,
            depends_on=(concept.node_id,),
            input_digests=(
                _object_sha256({"contract": CONTENT_DIALOGUE_CONTRACT_VERSION}),
                _object_sha256(npc.dialogue_expressions),
            ),
            outputs=(f"content/npcs/{npc.npc_id}/dialogue.source.png",),
        )
        dialogue_validation = builder.add(
            f"npc-{npc.npc_id}-dialogue-validate",
            domain=f"npc-{npc.npc_id}",
            description=f"validate NPC {npc.npc_id} dialogue expression coverage",
            operation=OperationKind.LOCAL,
            depends_on=(dialogue.node_id,),
            input_digests=(
                _object_sha256({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                _object_sha256(npc.dialogue_expressions),
            ),
            outputs=(
                f"content/npcs/{npc.npc_id}/dialogue.png",
                f"content/npcs/{npc.npc_id}/dialogue.validation.json",
            ),
            duration_seconds=0.75,
        )
        contact = builder.add(
            f"npc-{npc.npc_id}-contact-sheet",
            domain=f"npc-{npc.npc_id}",
            description=f"assemble NPC {npc.npc_id} review board",
            operation=OperationKind.LOCAL,
            depends_on=(world_validation.node_id, dialogue_validation.node_id),
            input_digests=(_object_sha256(npc.model_dump(mode="json", exclude={"motions"})),),
            outputs=(f"content/npcs/{npc.npc_id}/contact-sheet.png",),
            duration_seconds=1.0,
        )
        review = builder.add_external(
            f"npc-{npc.npc_id}-review",
            domain=f"npc-{npc.npc_id}",
            description=f"review world and dialogue identity for NPC {npc.npc_id}",
            operation=OperationKind.STRUCTURED_GENERATION,
            depends_on=(contact.node_id,),
            input_digests=(
                *identity,
                _object_sha256({"contract": CONTENT_REVIEW_CONTRACT_VERSION}),
                _object_sha256({"contract": CONTENT_ACTOR_PLAYBACK_REVIEW_CONTRACT_VERSION}),
            ),
            outputs=(f"content/npcs/{npc.npc_id}/review.json",),
        )
        terminals.append(review.node_id)
    return terminals


def _add_prop_nodes(builder: _GraphBuilder, package_root: str) -> str:
    references = {entry.reference_id: entry for entry in builder.package.props.references}
    validations: list[str] = []
    for prop in builder.package.props.props:
        generated = builder.add_external(
            f"prop-{prop.prop_id}-generate",
            domain="props",
            description=f"generate isolated prop {prop.prop_id}",
            operation=OperationKind.IMAGE_GENERATION,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=(
                _visual_direction_digest(builder.package),
                _object_sha256({"contract": CONTENT_CATALOG_CONTRACT_VERSION}),
                _object_sha256(prop.model_dump(mode="json")),
                *_reference_digests(references, prop.reference_ids),
            ),
            outputs=(f"content/props/{prop.prop_id}.png",),
        )
        validations.append(
            builder.add(
                f"prop-{prop.prop_id}-validate",
                domain="props",
                description=f"validate isolated alpha and framing for prop {prop.prop_id}",
                operation=OperationKind.LOCAL,
                depends_on=(generated.node_id,),
                input_digests=(
                    _object_sha256(prop.model_dump(mode="json")),
                    _object_sha256({"contract": CONTENT_PROP_CONTACT_VALIDATION_VERSION}),
                ),
                outputs=(f"content/props/{prop.prop_id}.validation.json",),
                duration_seconds=0.5,
            ).node_id
        )
    contact = builder.add(
        "props-contact-sheet",
        domain="props",
        description="assemble the complete prop catalog review board",
        operation=OperationKind.LOCAL,
        depends_on=tuple(validations),
        input_digests=(
            _object_sha256(builder.package.props.model_dump(mode="json")),
            _object_sha256({"contract": CONTENT_REVIEW_CONTRACT_VERSION}),
        ),
        outputs=("content/props/contact-sheet.png",),
        duration_seconds=1.0,
    )
    return builder.add_external(
        "props-review",
        domain="props",
        description="review complete prop identity and isolation coverage",
        operation=OperationKind.STRUCTURED_GENERATION,
        depends_on=(contact.node_id,),
        input_digests=(_object_sha256(builder.package.props.model_dump(mode="json")),),
        outputs=("content/props/review.json",),
    ).node_id


def _add_item_nodes(builder: _GraphBuilder, package_root: str) -> str:
    references = {entry.reference_id: entry for entry in builder.package.items.references}
    validations: list[str] = []
    for item in builder.package.items.items:
        generated = builder.add_external(
            f"item-{item.item_id}-generate",
            domain="items",
            description=f"generate isolated item {item.item_id}",
            operation=OperationKind.IMAGE_GENERATION,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=(
                _visual_direction_digest(builder.package),
                _object_sha256({"contract": CONTENT_CATALOG_CONTRACT_VERSION}),
                _object_sha256(item.model_dump(mode="json")),
                *_reference_digests(references, item.reference_ids),
            ),
            outputs=(f"content/items/{item.item_id}.png",),
        )
        validations.append(
            builder.add(
                f"item-{item.item_id}-validate",
                domain="items",
                description=f"validate isolated alpha and framing for item {item.item_id}",
                operation=OperationKind.LOCAL,
                depends_on=(generated.node_id,),
                input_digests=(_object_sha256(item.model_dump(mode="json")),),
                outputs=(f"content/items/{item.item_id}.validation.json",),
                duration_seconds=0.5,
            ).node_id
        )
    contact = builder.add(
        "items-contact-sheet",
        domain="items",
        description="assemble the complete item catalog review board",
        operation=OperationKind.LOCAL,
        depends_on=tuple(validations),
        input_digests=(
            _object_sha256(builder.package.items.model_dump(mode="json")),
            _object_sha256({"contract": CONTENT_REVIEW_CONTRACT_VERSION}),
        ),
        outputs=("content/items/contact-sheet.png",),
        duration_seconds=1.0,
    )
    return builder.add_external(
        "items-review",
        domain="items",
        description="review complete item identity and isolation coverage",
        operation=OperationKind.STRUCTURED_GENERATION,
        depends_on=(contact.node_id,),
        input_digests=(_object_sha256(builder.package.items.model_dump(mode="json")),),
        outputs=("content/items/review.json",),
    ).node_id


def _add_soundtrack_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    terminals: list[str] = []
    for track in builder.package.soundtrack.tracks:
        generated = builder.add_external(
            f"track-{track.track_id}-generate",
            domain="soundtrack",
            description=f"generate soundtrack track {track.track_id}",
            operation=OperationKind.MUSIC_GENERATION,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=(
                _object_sha256({"contract": CONTENT_SOUNDTRACK_CONTRACT_VERSION}),
                _object_sha256(track.model_dump(mode="json")),
            ),
            outputs=(f"soundtrack/{track.track_id}.mp3",),
        )
        validation = builder.add(
            f"track-{track.track_id}-validate",
            domain="soundtrack",
            description=(
                "validate audio container, duration, channels, and loop intent for "
                f"{track.track_id}"
            ),
            operation=OperationKind.LOCAL,
            depends_on=(generated.node_id,),
            input_digests=(_object_sha256(track.generation.model_dump(mode="json")),),
            outputs=(f"soundtrack/{track.track_id}.validation.json",),
            duration_seconds=1.0,
        )
        terminals.append(validation.node_id)
    return terminals


def _add_ui_nodes(builder: _GraphBuilder, package_root: str) -> str:
    panel = builder.package.ui.inventory_panel
    references = {entry.reference_id: entry for entry in builder.package.ui.references}
    generated = builder.add_external(
        "ui-inventory-panel-generate",
        domain="ui",
        description="generate the authored inventory panel presentation",
        operation=OperationKind.IMAGE_GENERATION,
        depends_on=(package_root,),
        cache_depends_on=(),
        input_digests=(
            _visual_direction_digest(builder.package),
            _object_sha256({"contract": UI_INVENTORY_PANEL_CONTRACT_VERSION}),
            _object_sha256(panel.model_dump(mode="json")),
            *(references[reference_id].source_sha256 for reference_id in panel.reference_ids),
            hashlib.sha256(inventory_template_path().read_bytes()).hexdigest(),
        ),
        outputs=("ui/inventory_panel.raw.png",),
    )
    validated = builder.add(
        "ui-inventory-panel-validate",
        domain="ui",
        description="validate opaque panel and slot interiors on a transparent exterior",
        operation=OperationKind.LOCAL,
        depends_on=(generated.node_id,),
        input_digests=(
            _object_sha256({"contract": UI_INVENTORY_PANEL_CONTRACT_VERSION}),
            _object_sha256(panel.model_dump(mode="json")),
        ),
        outputs=(
            "ui/inventory_panel.png",
            "ui/inventory_panel.validation.json",
            "ui/inventory_panel.evidence.png",
        ),
        duration_seconds=0.75,
    )
    return builder.add_external(
        "ui-inventory-panel-review",
        domain="ui",
        description="review inventory readability, style, and filled slot surfaces",
        operation=OperationKind.STRUCTURED_GENERATION,
        depends_on=(validated.node_id,),
        input_digests=(
            _object_sha256({"contract": UI_INVENTORY_PANEL_REVIEW_VERSION}),
            _object_sha256(panel.model_dump(mode="json")),
        ),
        outputs=("ui/inventory_panel.review.json",),
    ).node_id


class _GraphBuilder:
    def __init__(self, package: ResolvedGamePackage, profile: PackageGraphProfile) -> None:
        self.package = package
        self.profile = profile
        self.nodes: list[ExecutionNode] = []
        self._by_id: dict[str, ExecutionNode] = {}
        self.resources = (
            ExecutionResource(
                resource_id="local",
                max_in_flight=32,
                rate_limit_owner="none",
            ),
            ExecutionResource(
                resource_id="openai-image",
                max_in_flight=None,
                requests_per_minute=profile.image_ipm,
                rate_limit_owner="provider_adapter",
            ),
            ExecutionResource(
                resource_id="openrouter-structured",
                max_in_flight=None,
                rate_limit_owner="none",
            ),
            ExecutionResource(
                resource_id="openrouter-music",
                max_in_flight=None,
                rate_limit_owner="none",
            ),
        )

    def add_external(
        self,
        node_id: str,
        *,
        domain: str,
        description: str,
        operation: OperationKind,
        depends_on: Sequence[str],
        cache_depends_on: Sequence[str] | None = None,
        input_digests: Sequence[str],
        outputs: Sequence[str],
    ) -> ExecutionNode:
        if operation is OperationKind.IMAGE_GENERATION:
            provider = self.profile.image_provider
            model = self.profile.image_model
            resource_id = "openai-image"
            duration_seconds = 120.0
            cost_low, cost_high = 0.04, 0.20
        elif operation is OperationKind.STRUCTURED_GENERATION:
            provider = self.profile.structured_provider
            model = self.profile.structured_model
            resource_id = "openrouter-structured"
            duration_seconds = 30.0
            cost_low, cost_high = 0.005, 0.08
        elif operation is OperationKind.MUSIC_GENERATION:
            provider = self.profile.music_provider
            model = self.profile.music_model
            resource_id = "openrouter-music"
            duration_seconds = 180.0
            cost_low, cost_high = 0.10, 0.80
        else:
            raise ValueError("add_external requires a provider operation")
        return self.add(
            node_id,
            domain=domain,
            description=description,
            operation=operation,
            depends_on=depends_on,
            cache_depends_on=cache_depends_on,
            input_digests=input_digests,
            outputs=outputs,
            provider=provider,
            model=model,
            resource_id=resource_id,
            retry_owner=RetryOwner.COMPONENT,
            max_attempts=6,
            duration_seconds=duration_seconds,
            cost_low=cost_low,
            cost_high=cost_high,
        )

    def add(
        self,
        node_id: str,
        *,
        domain: str,
        description: str,
        operation: OperationKind,
        depends_on: Sequence[str] = (),
        cache_depends_on: Sequence[str] | None = None,
        input_digests: Sequence[str] = (),
        outputs: Sequence[str] = (),
        provider: str | None = None,
        model: str | None = None,
        resource_id: str = "local",
        retry_owner: RetryOwner = RetryOwner.NONE,
        max_attempts: int = 1,
        duration_seconds: float = 0.25,
        cost_low: float = 0.0,
        cost_high: float = 0.0,
    ) -> ExecutionNode:
        if node_id in self._by_id:
            raise ValueError(f"duplicate package graph node: {node_id}")
        dependency_cache_keys: list[str] = []
        for dependency in depends_on if cache_depends_on is None else cache_depends_on:
            if dependency not in depends_on:
                raise ValueError(
                    "cache dependency must also be a scheduling dependency: "
                    f"{node_id}->{dependency}"
                )
            try:
                dependency_cache_keys.append(self._by_id[dependency].cache_key)
            except KeyError as error:
                raise ValueError(
                    f"package graph dependency must be added first: {node_id}->{dependency}"
                ) from error
        unique_input_digests = tuple(dict.fromkeys(input_digests))
        node = ExecutionNode(
            node_id=node_id,
            domain=domain,
            description=description,
            depends_on=tuple(depends_on),
            operation=operation,
            resource_id=resource_id,
            provider=provider,
            model=model,
            retry_owner=retry_owner,
            max_attempts=max_attempts,
            input_sha256=unique_input_digests,
            cache_key=build_node_cache_key(
                node_id=node_id,
                operation=operation,
                provider=provider,
                model=model,
                input_sha256=unique_input_digests,
                dependency_cache_keys=dependency_cache_keys,
                contract_version=PACKAGE_GRAPH_CONTRACT_VERSION,
            ),
            outputs=tuple(outputs),
            estimated_duration_seconds=float(duration_seconds),
            estimated_cost_low_usd=float(cost_low),
            estimated_cost_high_usd=float(cost_high),
        )
        self.nodes.append(node)
        self._by_id[node_id] = node
        return node


def _visual_direction(package: ResolvedGamePackage) -> dict[str, object]:
    return {
        "universe_sha256": package.file(package.game.universe.source).sha256,
        "style": package.game.style.model_dump(mode="json"),
        "proportion": package.game.proportion.model_dump(mode="json"),
        # Runtime contact shadows are deliberately absent: changing them must not invalidate any
        # paid generation node. These two fields remain provider-facing visual direction.
        "presentation": {
            "view_profile": package.game.presentation.view_profile,
            "gameplay_space": package.game.presentation.gameplay_space,
        },
    }


def _visual_direction_digest(package: ResolvedGamePackage) -> str:
    return _object_sha256(_visual_direction(package))


def _map_without_runtime_presentation(game_map: PreparedGameMap) -> dict[str, object]:
    """Project the map identity consumed before runtime integration."""

    return game_map.model_dump(
        mode="json",
        exclude={"layers": {"__all__": set(RUNTIME_ONLY_LAYER_FIELDS)}},
    )


def _reference_digests(
    references: dict[str, ContentReference] | dict[str, PreparedMapReference],
    reference_ids: Iterable[str],
) -> tuple[str, ...]:
    return tuple(references[reference_id].source_sha256 for reference_id in reference_ids)


def _file_digests(package: ResolvedGamePackage, paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(package.file(path).sha256 for path in paths)


def _object_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _motion_repack_identity(motion: MotionPresentation) -> dict[str, object]:
    """Everything that decides how a validated strip is registered.

    The anchor is carried only when it leaves the default, so every grounded motion keeps the digest
    it already had while a motion whose registration changed is not served its superseded artwork
    from cache. Authored, so unlike the state name it is not derivable from anything else here.
    """

    identity: dict[str, object] = {"state": motion.state}
    if motion.anchor != DEFAULT_MOTION_ANCHOR:
        identity["anchor"] = motion.anchor
    return identity


def _motion_identity(kind: MotionActorKind, state: str, source_facing: str) -> dict[str, object]:
    """Everything that decides what a motion atlas is asked to depict.

    The requested motion is part of a strip's identity, so a strip generated under a superseded
    directive must not be reused: the player climb strip was regenerated precisely because its
    directive changed, and without this the cached artwork answered the old question forever.
    Only a recipe-owned override is carried. The default directive is a pure function of `state`,
    which is already here, so adding it would change every existing digest to say nothing new.
    The geometry is carried for the same reason as the override: it decides how many cells the
    provider is asked for and on what canvas, so a strip drawn to a superseded shape is not a
    valid answer to the current question. Only a non-default geometry is hashed, so the states
    that never move off the default keep the digests they already have.
    """

    identity: dict[str, object] = {"state": state, "source_facing": source_facing}
    override = recipe_owned_motion_direction(kind, state)
    if override is not None:
        identity["motion_direction"] = override
    geometry = motion_atlas_geometry(kind, state)
    if geometry != DEFAULT_MOTION_ATLAS_GEOMETRY:
        identity["atlas_geometry"] = {
            "columns": geometry.columns,
            "rows": geometry.rows,
            "required_cells": geometry.required_cells,
            "size": geometry.provider_size,
        }
    return identity


__all__ = [
    "PACKAGE_GRAPH_CONTRACT_VERSION",
    "PackageGraphProfile",
    "build_package_execution_graph",
    "package_graph_profile",
]

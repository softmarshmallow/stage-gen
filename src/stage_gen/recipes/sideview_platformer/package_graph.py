"""Build the exact side-view platformer asset DAG from one resolved game package."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from typing import Any

from gnode import Binding, BindingTable, GraphBuilder, ModelRef, NodeCard, PortRef
from stage_gen.components.game_soundtrack.nodes import (
    SoundtrackNodeTypes,
    add_soundtrack_nodes,
)
from stage_gen.components.game_soundtrack.prompt import music_track_prompt
from stage_gen.components.game_ui.nodes import add_ui_atlas_nodes
from stage_gen.components.painted_terrain import (
    PAINTED_TERRAIN_CANONICALIZE,
    PAINTED_TERRAIN_CANONICALIZER_ID,
    PAINTED_TERRAIN_COMPOSE,
    PAINTED_TERRAIN_GENERATE,
    PAINTED_TERRAIN_GROUND_VALIDATION_KIND,
    PAINTED_TERRAIN_GUIDE,
    PAINTED_TERRAIN_GUIDE_ID,
    PAINTED_TERRAIN_GUIDE_KIND,
    PAINTED_TERRAIN_GUIDE_REPORT_KIND,
    PAINTED_TERRAIN_KIND,
    PAINTED_TERRAIN_PLATE_KIND,
    PAINTED_TERRAIN_RAW_KIND,
    PAINTED_TERRAIN_VALIDATION_KIND,
    PaintedTerrainGround,
    painted_silhouette_tolerance,
    painted_terrain_generation_prompt,
    painted_terrain_segments,
)
from stage_gen.components.platformer_content import (
    DEFAULT_MOTION_ANCHOR,
    ContentReference,
    MotionPresentation,
)
from stage_gen.components.platformer_map import PreparedGameMap, PreparedMapReference
from stage_gen.components.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from stage_gen.components.sideview_actor.motion_rebase import MOTION_REBASE_SCHEMA_NAME
from stage_gen.components.sideview_layers.contract import (
    LAYER_PLACEMENT_CANONICALIZER,
    NON_GENERATIVE_LAYER_FIELDS,
    PLACEMENT_ONLY_CLIMBABLE_FIELDS,
    PLACEMENT_ONLY_GROUND_FIELDS,
    RUNTIME_ONLY_LAYER_FIELDS,
    loop_method_identity,
)
from stage_gen.components.sideview_terrain.atlas import (
    MATERIAL_ASSEMBLER_ID,
    MATERIAL_SOURCE_CONTRACT_ID,
)
from stage_gen.config import StageGenConfig
from stage_gen.media import (
    LOOP_METHODS,
)
from stage_gen.orchestration.game_package import ResolvedGamePackage
from stage_gen.recipes.ports import artifact_port, object_digest, record_port, text_digest
from stage_gen.recipes.sideview_platformer.execution_graph import (
    ExecutionGraph,
    OperationKind,
)
from stage_gen.recipes.sideview_platformer.motion_contract import (
    MotionActorKind,
    motion_atlas_geometry,
    motion_source_facing,
    recipe_owned_motion_direction,
)
from stage_gen.recipes.sideview_platformer.package_types import (
    ACTOR_CONCEPT_GENERATE,
    ACTOR_CONTACT_SHEET,
    ACTOR_REVIEW,
    CATALOG_ASSET_GENERATE,
    CATALOG_ASSET_VALIDATE,
    CATALOG_CONTACT_SHEET,
    CATALOG_REVIEW,
    DIALOGUE_ATLAS_GENERATE,
    DIALOGUE_ATLAS_VALIDATE,
    GAMEPLAY_BINDINGS_VALIDATE,
    IMAGE_FEATURES,
    MANIFEST_ASSEMBLE,
    MAP_CLIMBABLE_GENERATE,
    MAP_CLIMBABLE_VALIDATE,
    MAP_COMPOSITE,
    MAP_GROUND_GENERATE,
    MAP_GROUND_VALIDATE,
    MAP_LAYER_GENERATE,
    MAP_LAYER_LOOP_CONSTRUCT,
    MAP_LAYER_LOOP_PAINT,
    MAP_LAYER_VALIDATE,
    MAP_PORTAL_GENERATE,
    MAP_PORTAL_VALIDATE,
    MAP_REVIEW,
    MAP_TERRAIN_DESIGN,
    MOTION_ATLAS_GENERATE,
    MOTION_ATLAS_VALIDATE,
    MOTION_REBASE_JUDGE,
    MOTION_REBASE_VERIFY,
    MUSIC_FEATURES,
    PACKAGE_RESOLVE,
    PREPARED_RUNTIME_MANIFEST_KIND,
    SOUNDTRACK_GENERATE,
    SOUNDTRACK_VALIDATE,
    STRUCTURED_FEATURES,
    UI_INVENTORY_GENERATE,
    UI_INVENTORY_REVIEW,
    UI_INVENTORY_VALIDATE,
    WORLD_SPRITE_GENERATE,
    WORLD_SPRITE_VALIDATE,
)
from stage_gen.resources import (
    inventory_template_path,
    terrain_atlas_lookup_path,
    terrain_atlas_template_path,
    terrain_atlas_topology_reference_path,
)

#: The cache trees this recipe's checkpoint handlers write under. Renaming one
#: is that checkpoint's whole-cache invalidation lever; per-type levers are the
#: node types' own ``contract_version`` values (package_types.py).
WORLD_CACHE_NAMESPACE = "sideview-platformer-world-v1"
CONTENT_CACHE_NAMESPACE = "sideview-platformer-content-v1"
CACHE_RECORD_KIND = "sideview-platformer-node-cache-v1"

CONTENT_CONCEPT_CONTRACT_VERSION = "prepared-content-concept-v1"
CONTENT_MOTION_CONTRACT_VERSION = "prepared-content-motion-atlas-v3"
CONTENT_DIALOGUE_CONTRACT_VERSION = "prepared-content-dialogue-atlas-v1"
CONTENT_ALPHA_REPACK_CONTRACT_VERSION = "alpha-component-repack-v3"
CONTENT_CATALOG_CONTRACT_VERSION = "prepared-content-isolated-catalog-v1"
CONTENT_PROP_CONTACT_VALIDATION_VERSION = "prepared-content-prop-contact-v1"
CONTENT_REVIEW_CONTRACT_VERSION = "prepared-content-review-v4"
CONTENT_ACTOR_PLAYBACK_REVIEW_CONTRACT_VERSION = "prepared-content-actor-playback-review-v1"
CONTENT_PLAYER_REVIEW_CONTRACT_VERSION = "prepared-content-player-review-v6"
#: Bumped whenever the plate layout, the judge prompt, or admission changes, so a cached
#: reading cannot outlive the composition it was taken from.
CONTENT_MOTION_REBASE_CONTRACT_VERSION = "prepared-content-motion-rebase-v3"
CONTENT_BINDING_CONTRACT_VERSION = "prepared-content-binding-report-v1"
CONTENT_SOUNDTRACK_CONTRACT_VERSION = "prepared-content-soundtrack-v1"
UI_INVENTORY_PANEL_CONTRACT_VERSION = "prepared-ui-inventory-panel-v2"
UI_INVENTORY_PANEL_REVIEW_VERSION = "prepared-ui-inventory-panel-review-v1"
MAP_CLIMBABLE_CONTRACT_VERSION = "prepared-map-climbable-atlas-v1"
MAP_PORTAL_CONTRACT_VERSION = "prepared-map-portal-pair-1x2-v1"


def package_graph_profile(config: StageGenConfig) -> BindingTable:
    """Declare the provider routes this plan may use, credentials untouched.

    Each entry is one ``model@provider`` route with the features it is known to
    support. ``verified_on`` records when that claim was last checked against
    the provider; see docs/providers.md.
    """

    return BindingTable(
        [
            Binding(
                operation=OperationKind.IMAGE_GENERATION,
                model=ModelRef(model=config.openai_image_model, provider="openai"),
                features=frozenset(IMAGE_FEATURES),
                resource_id="openai-image",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.04,
                estimated_cost_high_usd=0.20,
                requests_per_minute=config.openai_image_ipm,
                rate_limit_owner="provider_adapter",
                verified_on="2026-08-25",
            ),
            Binding(
                operation=OperationKind.STRUCTURED_GENERATION,
                model=ModelRef(model=config.text_model, provider="openrouter"),
                features=frozenset(STRUCTURED_FEATURES),
                resource_id="openrouter-structured",
                estimated_duration_seconds=30.0,
                estimated_cost_low_usd=0.005,
                estimated_cost_high_usd=0.08,
                verified_on="2026-08-20",
            ),
            Binding(
                operation=OperationKind.MUSIC_GENERATION,
                model=ModelRef(model=config.music_model, provider="openrouter"),
                features=frozenset(MUSIC_FEATURES),
                resource_id="openrouter-music",
                estimated_duration_seconds=180.0,
                estimated_cost_low_usd=0.10,
                estimated_cost_high_usd=0.80,
                verified_on="2026-08-14",
            ),
        ]
    )


def build_package_execution_graph(
    package: ResolvedGamePackage,
    *,
    profile: BindingTable,
) -> ExecutionGraph:
    """Expand every authored map and content entry into stable executable nodes."""

    builder = _GraphBuilder(package, profile)
    package_node = builder.add(
        PACKAGE_RESOLVE,
        "package-resolve",
        domain="package",
        description="validate and capture the complete prepared package",
        input_digests=(package.closure_sha256,),
        ports=(record_port("identity", "package.identity.json", "package-identity-v1"),),
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
    projectiles = _add_projectile_nodes(builder, package_root)
    if projectiles is not None:
        terminal_nodes.append(projectiles)
    terminal_nodes.extend(_add_ui_nodes(builder, package_root))
    terminal_nodes.extend(_add_soundtrack_nodes(builder, package_root))

    binding = builder.add(
        GAMEPLAY_BINDINGS_VALIDATE,
        "gameplay-bindings-validate",
        domain="gameplay",
        description="validate gameplay, scenario, placement, drop, and stable-ID bindings",
        depends_on=(package_root,),
        cache_depends_on=(),
        input_digests=(
            object_digest({"contract": CONTENT_BINDING_CONTRACT_VERSION}),
            *_file_digests(
                package,
                (
                    "gameplay.toml",
                    *(entry.source for entry in package.platformer.maps),
                    "scenarios/index.toml",
                    # Both halves: the declarations and the prose they sign for.
                    *(
                        member
                        for entry in package.scenario_catalog.scenarios
                        for member in (
                            f"scenarios/{entry.scenario_id}.toml",
                            f"scenarios/{entry.scenario_id}.scenario",
                        )
                    ),
                ),
            ),
        ),
        ports=(
            record_port("bindings", "gameplay.bindings.json", "gameplay-bindings-v1"),
            record_port("coverage", "content/coverage-matrix.json", "coverage-matrix-v1"),
        ),
        duration_seconds=0.5,
    )
    terminal_nodes.append(binding.node_id)

    manifest = builder.add(
        MANIFEST_ASSEMBLE,
        "manifest-assemble",
        domain="manifest",
        description="assemble the terminal game manifest from validated artifact bindings",
        depends_on=tuple(terminal_nodes),
        # The canonical projection alone does not reach the members the manifest reads, such as
        # authored playback, so the assembled manifest keys on the whole captured closure.
        input_digests=(package.canonical_game_sha256, package.closure_sha256),
        ports=(record_port("manifest", "manifest.json", PREPARED_RUNTIME_MANIFEST_KIND),),
        duration_seconds=1.0,
    )
    return ExecutionGraph.seal(
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id=manifest.node_id,
        game_id=package.game.game_id,
        package_sha256=package.package_sha256,
    )


def _add_map_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    terminals: list[str] = []
    for game_map in builder.package.maps:
        references = {entry.reference_id: entry for entry in game_map.references}
        # Both loop fields are consumed after generation, so they are excluded here for the same
        # reason placement is: changing which construction a map selects, or which one it falls
        # back to, must re-run the loop node only and never re-bill every layer image.
        map_direction = object_digest(
            {
                "game": _visual_direction(builder.package),
                "view": game_map.view.model_dump(mode="json"),
                "continuity": game_map.continuity.model_dump(
                    mode="json", exclude={"loop_construction", "loop_fallback"}
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
                object_digest(
                    layer.model_dump(mode="json", exclude=set(NON_GENERATIVE_LAYER_FIELDS))
                ),
                *_reference_digests(references, layer.reference_ids),
            )
            generated = builder.add(
                MAP_LAYER_GENERATE,
                f"map-{game_map.map_id}-layer-{layer.layer_id}-generate",
                domain=f"map-{game_map.map_id}",
                description=f"generate map layer {game_map.map_id}/{layer.layer_id}",
                params={"map_id": game_map.map_id, "layer_id": layer.layer_id},
                depends_on=(package_root,),
                cache_depends_on=(),
                input_digests=input_digests,
                ports=(
                    artifact_port(
                        "image",
                        f"maps/{game_map.map_id}/layers/{layer.layer_id}.raw.png",
                        "map-layer-raw-v1",
                    ),
                ),
            )
            # Loop construction sits between generation and validation because the generative
            # constructions need a provider call while the deterministic ones are purely local.
            # Which node kind this is follows from the construction's own declaration rather than
            # from a name comparison here. Admission runs first inside the node either way, so a
            # layer the model already returned as a clean repeat unit costs nothing on any route.
            # The layer may override the map's construction, so resolve before anything reads it.
            construction = layer.loop_construction or game_map.continuity.loop_construction
            method = LOOP_METHODS[construction]
            # Identity is scoped to the construction this layer actually selected. Binding every
            # construction's version here, as this once did, meant revising any one of them
            # re-ran the loop node for every layer in every map regardless of what it selected.
            loop_digests = (
                object_digest(
                    {
                        **loop_method_identity(
                            construction, fallback=game_map.continuity.loop_fallback
                        ),
                        "alpha_mode": layer.alpha_mode,
                    }
                ),
            )
            layer_root = f"maps/{game_map.map_id}/layers/{layer.layer_id}"
            layer_params = {"map_id": game_map.map_id, "layer_id": layer.layer_id}
            loop_ports = (
                artifact_port("loop_image", f"{layer_root}.loop.png", "map-layer-loop-image-v1"),
                record_port("loop_report", f"{layer_root}.loop.json", "layer-loop-report-v1"),
                # The repaint intermediate exists only when admission escalates to
                # a provider edit; declaring it keeps that channel visible.
                artifact_port("edit_image", f"{layer_root}.edit.png", "map-layer-loop-edit-v1"),
            )
            loop_card = NodeCard(
                reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)
            )
            if method.is_generative:
                looped = builder.add(
                    MAP_LAYER_LOOP_PAINT,
                    f"map-{game_map.map_id}-layer-{layer.layer_id}-loop",
                    domain=f"map-{game_map.map_id}",
                    description=(
                        f"admit the x-axis loop for {layer.layer_id}, else {construction}"
                    ),
                    params=layer_params,
                    # The generated raster is this node's content input, so the
                    # edge is cache lineage: a repainted layer must never be
                    # served a loop derived from the discarded image.
                    depends_on=(generated.node_id,),
                    input_digests=loop_digests,
                    ports=loop_ports,
                    card=loop_card,
                )
            else:
                looped = builder.add(
                    MAP_LAYER_LOOP_CONSTRUCT,
                    f"map-{game_map.map_id}-layer-{layer.layer_id}-loop",
                    domain=f"map-{game_map.map_id}",
                    description=(
                        f"admit the x-axis loop for {layer.layer_id}, else {construction}"
                    ),
                    params=layer_params,
                    depends_on=(generated.node_id,),
                    input_digests=loop_digests,
                    ports=loop_ports[:2],
                    card=loop_card,
                    duration_seconds=1.0,
                )
            validated = builder.add(
                MAP_LAYER_VALIDATE,
                f"map-{game_map.map_id}-layer-{layer.layer_id}-validate",
                domain=f"map-{game_map.map_id}",
                description=f"validate alpha and x-axis repeat admission for {layer.layer_id}",
                params=layer_params,
                depends_on=(looped.node_id,),
                input_digests=(
                    object_digest(
                        layer.model_dump(mode="json", exclude=set(RUNTIME_ONLY_LAYER_FIELDS))
                    ),
                    object_digest(
                        {
                            "canonicalizer": "prepared-map-loop-construction-v1",
                            "placement": LAYER_PLACEMENT_CANONICALIZER,
                        }
                    ),
                ),
                ports=(
                    artifact_port("image", f"{layer_root}.png", "map-layer-v1"),
                    record_port(
                        "validation", f"{layer_root}.validation.json", "layer-validation-v1"
                    ),
                    record_port("repeat_preview", f"{layer_root}.repeat.png", "repeat-preview-v1"),
                ),
                card=NodeCard(
                    reference_inputs=(PortRef(node_id=looped.node_id, port_id="loop_image"),)
                ),
                duration_seconds=1.0,
            )
            layer_validations.append(validated.node_id)

        # Terrain shape is generated the way artwork is generated: the map states a generator and
        # a brief, this node produces geometry, and the result is an artifact with provenance.
        # It depends only on the request, so re-painting a material atlas never reshapes a level
        # and reshaping a level never repaints an atlas.
        terrain = builder.add(
            MAP_TERRAIN_DESIGN,
            f"map-{game_map.map_id}-terrain-generate",
            domain=f"map-{game_map.map_id}",
            description=f"compose {game_map.terrain.mode} terrain for {game_map.map_id}",
            params={"map_id": game_map.map_id},
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=(
                map_direction,
                object_digest(game_map.terrain.model_dump(mode="json")),
                # The camera bounds what the designer may build: a surface the runtime cannot
                # frame is unplayable, so the framing ceiling in terrain_design reads the same
                # declaration the scene does. That makes the camera a real geometry input.
                object_digest(game_map.camera.model_dump(mode="json")),
                object_digest(
                    {}
                    if game_map.climbable is None
                    else {"variants": [entry.variant_id for entry in game_map.climbable.variants]}
                ),
            ),
            ports=(
                record_port("terrain", f"maps/{game_map.map_id}/terrain.json", "map-terrain-v1"),
            ),
        )

        ground_direction = game_map.ground.model_dump(
            mode="json", exclude=set(PLACEMENT_ONLY_GROUND_FIELDS)
        )
        # Which discipline draws this map's terrain. The atlas is the default and stays it;
        # painted terrain is the opt-in, and it fans out per derived segment rather than
        # producing one repeating material sheet. Both read the same generated occupancy and
        # neither owns collision, so everything downstream of this branch is identical.
        if isinstance(game_map.ground, PaintedTerrainGround):
            ground_validation_id = _add_painted_terrain_nodes(
                builder,
                game_map,
                package_root=package_root,
                terrain_node_id=terrain.node_id,
                map_direction=map_direction,
                ground_direction=ground_direction,
                references=references,
            )
        else:
            ground = builder.add(
                MAP_GROUND_GENERATE,
                f"map-{game_map.map_id}-ground-generate",
                domain=f"map-{game_map.map_id}",
                description=f"paint the declared 47-mask ground atlas for {game_map.map_id}",
                params={"map_id": game_map.map_id},
                depends_on=(package_root,),
                cache_depends_on=(),
                input_digests=(
                    map_direction,
                    object_digest(ground_direction),
                    *_reference_digests(references, game_map.ground.reference_ids),
                    hashlib.sha256(terrain_atlas_template_path().read_bytes()).hexdigest(),
                    hashlib.sha256(
                        terrain_atlas_topology_reference_path().read_bytes()
                    ).hexdigest(),
                    object_digest({"generation_contract": MATERIAL_SOURCE_CONTRACT_ID}),
                ),
                ports=(
                    artifact_port(
                        "image", f"maps/{game_map.map_id}/ground.raw.png", "ground-atlas-raw-v1"
                    ),
                ),
                card=NodeCard(template_ref="terrain_atlas_12x4_template_v1"),
            )
            ground_validation = builder.add(
                MAP_GROUND_VALIDATE,
                f"map-{game_map.map_id}-ground-validate",
                domain=f"map-{game_map.map_id}",
                description=f"validate the {game_map.ground.mode} ground contract",
                params={"map_id": game_map.map_id},
                # The validator composes its evidence plate over the generated occupancy, so the
                # terrain node is a real input: without the edge the scheduler may run this before
                # terrain.json exists, and a cached verdict would survive a reshaped level.
                depends_on=(ground.node_id, terrain.node_id),
                input_digests=(
                    object_digest(ground_direction),
                    object_digest({"canonicalizer": MATERIAL_ASSEMBLER_ID}),
                    hashlib.sha256(terrain_atlas_lookup_path().read_bytes()).hexdigest(),
                    hashlib.sha256(terrain_atlas_template_path().read_bytes()).hexdigest(),
                ),
                ports=(
                    artifact_port("image", f"maps/{game_map.map_id}/ground.png", "ground-atlas-v1"),
                    record_port(
                        "validation",
                        f"maps/{game_map.map_id}/ground.validation.json",
                        "ground-validation-v1",
                    ),
                    artifact_port(
                        "evidence",
                        f"maps/{game_map.map_id}/ground.evidence.png",
                        "ground-evidence-v1",
                    ),
                ),
                card=NodeCard(reference_inputs=(PortRef(node_id=ground.node_id, port_id="image"),)),
                duration_seconds=1.5,
            )
            ground_validation_id = ground_validation.node_id
        presentation_validations: list[str] = []
        if game_map.climbable is not None:
            # The atlas is appearance only, exactly like the ground paintover: it draws every
            # declared variant once, so where an instance stands cannot change how it is drawn.
            # Moving a ladder must re-run local geometry, never re-bill the atlas image. The
            # ladders and ropes stay in the key because their count is the atlas cell count and
            # their prompts are the request.
            climbable_direction = game_map.climbable.model_dump(
                mode="json", exclude=set(PLACEMENT_ONLY_CLIMBABLE_FIELDS)
            )
            climbable = builder.add(
                MAP_CLIMBABLE_GENERATE,
                f"map-{game_map.map_id}-climbable-generate",
                domain=f"map-{game_map.map_id}",
                description=f"generate map-local climbable atlas for {game_map.map_id}",
                params={"map_id": game_map.map_id, "asset": "climbable"},
                depends_on=(package_root,),
                cache_depends_on=(),
                input_digests=(
                    map_direction,
                    object_digest({"contract": MAP_CLIMBABLE_CONTRACT_VERSION}),
                    object_digest(climbable_direction),
                    *_reference_digests(references, game_map.climbable.reference_ids),
                ),
                ports=(
                    artifact_port(
                        "image",
                        f"maps/{game_map.map_id}/climbable.raw.png",
                        "climbable-atlas-raw-v1",
                    ),
                ),
            )
            # The validator keeps the whole block, placements included. It is local and free, and
            # it is the last map-local node a moved climbable reaches before the review that
            # judges the placed result, so it stays conservative rather than mirroring the
            # generation exclusion it does not need.
            climbable_validation = builder.add(
                MAP_CLIMBABLE_VALIDATE,
                f"map-{game_map.map_id}-climbable-validate",
                domain=f"map-{game_map.map_id}",
                description=f"isolate and validate the climbable atlas for {game_map.map_id}",
                params={"map_id": game_map.map_id, "asset": "climbable"},
                depends_on=(climbable.node_id,),
                input_digests=(
                    object_digest({"contract": MAP_CLIMBABLE_CONTRACT_VERSION}),
                    object_digest({"repack_contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                    object_digest(game_map.climbable.model_dump(mode="json")),
                ),
                ports=(
                    artifact_port(
                        "image", f"maps/{game_map.map_id}/climbable.png", "climbable-atlas-v1"
                    ),
                    record_port(
                        "validation",
                        f"maps/{game_map.map_id}/climbable.validation.json",
                        "presentation-validation-v1",
                    ),
                ),
                card=NodeCard(
                    reference_inputs=(PortRef(node_id=climbable.node_id, port_id="image"),)
                ),
                duration_seconds=0.75,
            )
            presentation_validations.append(climbable_validation.node_id)
        if game_map.portal is not None:
            portal = builder.add(
                MAP_PORTAL_GENERATE,
                f"map-{game_map.map_id}-portal-generate",
                domain=f"map-{game_map.map_id}",
                description=f"generate map-local portal pair for {game_map.map_id}",
                params={"map_id": game_map.map_id, "asset": "portal"},
                depends_on=(package_root,),
                cache_depends_on=(),
                input_digests=(
                    map_direction,
                    object_digest({"contract": MAP_PORTAL_CONTRACT_VERSION}),
                    object_digest(game_map.portal.model_dump(mode="json")),
                    *_reference_digests(references, game_map.portal.reference_ids),
                ),
                ports=(
                    artifact_port(
                        "image", f"maps/{game_map.map_id}/portal.raw.png", "portal-pair-raw-v1"
                    ),
                ),
            )
            portal_validation = builder.add(
                MAP_PORTAL_VALIDATE,
                f"map-{game_map.map_id}-portal-validate",
                domain=f"map-{game_map.map_id}",
                description=f"isolate and validate the portal pair for {game_map.map_id}",
                params={"map_id": game_map.map_id, "asset": "portal"},
                depends_on=(portal.node_id,),
                input_digests=(
                    object_digest({"contract": MAP_PORTAL_CONTRACT_VERSION}),
                    object_digest({"repack_contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                    object_digest(game_map.portal.model_dump(mode="json")),
                ),
                ports=(
                    artifact_port("image", f"maps/{game_map.map_id}/portal.png", "portal-pair-v1"),
                    record_port(
                        "validation",
                        f"maps/{game_map.map_id}/portal.validation.json",
                        "presentation-validation-v1",
                    ),
                ),
                card=NodeCard(reference_inputs=(PortRef(node_id=portal.node_id, port_id="image"),)),
                duration_seconds=0.75,
            )
            presentation_validations.append(portal_validation.node_id)
        composite = builder.add(
            MAP_COMPOSITE,
            f"map-{game_map.map_id}-composite",
            domain=f"map-{game_map.map_id}",
            description=f"compose all declared layers and ground for {game_map.map_id}",
            params={"map_id": game_map.map_id},
            depends_on=(*layer_validations, ground_validation_id, terrain.node_id),
            input_digests=(
                object_digest(_map_without_runtime_presentation(game_map)),
                object_digest({"compositor": "prepared-map-placed-compositor-v6"}),
            ),
            ports=(
                artifact_port("image", f"maps/{game_map.map_id}/composite.png", "map-composite-v1"),
            ),
            duration_seconds=2.0,
        )
        review = builder.add(
            MAP_REVIEW,
            f"map-{game_map.map_id}-review",
            domain=f"map-{game_map.map_id}",
            description=f"review complete map composition {game_map.map_id}",
            params={"map_id": game_map.map_id},
            depends_on=(composite.node_id, *presentation_validations),
            input_digests=(
                map_direction,
                # v5: judge references are transported as bounded recognition plates;
                # an unbounded payload broke a large map's review in production.
                object_digest({"review_contract": "prepared-map-review-v5"}),
            ),
            ports=(
                artifact_port(
                    "verdict", f"maps/{game_map.map_id}/review.json", "review-verdict-v1"
                ),
            ),
            card=NodeCard(
                schema_name="prepared_map_review",
                reference_inputs=(PortRef(node_id=composite.node_id, port_id="image"),),
            ),
        )
        terminals.append(review.node_id)
    return terminals


def _add_player_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    terminals: list[str] = []
    references = {entry.reference_id: entry for entry in builder.package.player.references}
    for player in builder.package.player.players:
        identity = (
            _visual_direction_digest(builder.package),
            object_digest({"contract": CONTENT_CONCEPT_CONTRACT_VERSION}),
            object_digest(player.model_dump(mode="json", exclude={"motions"})),
            *_reference_digests(references, player.reference_ids),
        )
        actor_root = f"content/players/{player.player_id}"
        actor_params = {"actor_kind": "player", "actor_id": player.player_id}
        concept = builder.add(
            ACTOR_CONCEPT_GENERATE,
            f"player-{player.player_id}-concept-generate",
            domain=f"player-{player.player_id}",
            description=f"generate identity concept for player {player.player_id}",
            params=actor_params,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=identity,
            ports=(artifact_port("image", f"{actor_root}/concept.png", "actor-concept-v1"),),
        )
        concept_ref = PortRef(node_id=concept.node_id, port_id="image")
        validations: list[str] = []
        for motion in player.motions:
            state = motion.state
            source_facing = motion_source_facing("player", state)
            generated = builder.add(
                MOTION_ATLAS_GENERATE,
                f"player-{player.player_id}-state-{state}-generate",
                domain=f"player-{player.player_id}",
                description=f"generate {state} state from one {source_facing}-facing source strip",
                params={**actor_params, "state": state},
                depends_on=(concept.node_id,),
                input_digests=(
                    object_digest({"contract": CONTENT_MOTION_CONTRACT_VERSION}),
                    object_digest(_motion_identity("player", state, source_facing)),
                ),
                ports=(
                    artifact_port(
                        "image", f"{actor_root}/states/{state}.source.png", "motion-source-v1"
                    ),
                ),
                card=NodeCard(reference_inputs=(concept_ref,)),
            )
            validations.append(
                builder.add(
                    MOTION_ATLAS_VALIDATE,
                    f"player-{player.player_id}-state-{state}-validate",
                    domain=f"player-{player.player_id}",
                    description=(
                        f"validate player {state} geometry, alpha, source facing, and registration"
                    ),
                    params={**actor_params, "state": state},
                    depends_on=(generated.node_id,),
                    input_digests=(
                        object_digest({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                        object_digest(_motion_repack_identity(motion)),
                    ),
                    ports=(
                        artifact_port(
                            "image", f"{actor_root}/states/{state}.png", "motion-atlas-v1"
                        ),
                        record_port(
                            "validation",
                            f"{actor_root}/states/{state}.validation.json",
                            "atlas-validation-v1",
                        ),
                    ),
                    card=NodeCard(
                        reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)
                    ),
                    duration_seconds=0.75,
                ).node_id
            )
        dialogue = builder.add(
            DIALOGUE_ATLAS_GENERATE,
            f"player-{player.player_id}-dialogue-generate",
            domain=f"player-{player.player_id}",
            description=f"generate declared dialogue expressions for player {player.player_id}",
            params=actor_params,
            depends_on=(concept.node_id,),
            input_digests=(
                object_digest({"contract": CONTENT_DIALOGUE_CONTRACT_VERSION}),
                object_digest(player.dialogue_art.model_dump(mode="json")),
            ),
            ports=(
                artifact_port("image", f"{actor_root}/dialogue.source.png", "dialogue-source-v1"),
            ),
            card=NodeCard(reference_inputs=(concept_ref,)),
        )
        dialogue_validation = builder.add(
            DIALOGUE_ATLAS_VALIDATE,
            f"player-{player.player_id}-dialogue-validate",
            domain=f"player-{player.player_id}",
            description="validate player dialogue expression coverage",
            params=actor_params,
            depends_on=(dialogue.node_id,),
            input_digests=(
                object_digest({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                object_digest(player.dialogue_art.model_dump(mode="json")),
            ),
            ports=(
                artifact_port("image", f"{actor_root}/dialogue.png", "dialogue-atlas-v1"),
                record_port(
                    "validation", f"{actor_root}/dialogue.validation.json", "atlas-validation-v1"
                ),
            ),
            card=NodeCard(reference_inputs=(PortRef(node_id=dialogue.node_id, port_id="image"),)),
            duration_seconds=0.75,
        )
        rebase = builder.add(
            MOTION_REBASE_JUDGE,
            f"player-{player.player_id}-motion-rebase",
            domain=f"player-{player.player_id}",
            description=(
                "judge every motion atlas against the idle baseline on one comparison plate "
                f"for {player.player_id}"
            ),
            params=actor_params,
            # Every published atlas, because the plate carries every frame of every state: a
            # reading taken against a partial plate would rebase onto a baseline the judge
            # could not see beside the states it was rating.
            depends_on=validations,
            input_digests=(
                *identity,
                object_digest({"contract": CONTENT_MOTION_REBASE_CONTRACT_VERSION}),
                object_digest({"schema": MOTION_REBASE_SCHEMA_NAME}),
            ),
            ports=(
                artifact_port(
                    "reading", f"{actor_root}/motion-rebase-first-pass.json", "rebase-reading-v1"
                ),
                artifact_port("plate", f"{actor_root}/motion-rebase-plate.png", "rebase-plate-v1"),
            ),
            card=NodeCard(schema_name="motion_rebase"),
        )
        rebase_verify = builder.add(
            MOTION_REBASE_VERIFY,
            f"player-{player.player_id}-motion-rebase-verify",
            domain=f"player-{player.player_id}",
            description=(
                "close the loop on the rebase: judge the residual on a plate composed with "
                f"the first-pass multipliers applied for {player.player_id}"
            ),
            params=actor_params,
            # The first reading is taken across atlases that disagree by up to a factor of
            # three, which is the hard form of the task. This node applies that reading, so the
            # judge only reads the small residual - the easy form - and the two multiply into
            # the published record.
            depends_on=(rebase.node_id,),
            input_digests=(
                *identity,
                object_digest({"contract": CONTENT_MOTION_REBASE_CONTRACT_VERSION}),
                object_digest({"schema": MOTION_REBASE_SCHEMA_NAME}),
            ),
            ports=(
                artifact_port("reading", f"{actor_root}/motion-rebase.json", "rebase-reading-v1"),
                artifact_port(
                    "plate",
                    f"{actor_root}/motion-rebase-verification-plate.png",
                    "rebase-plate-v1",
                ),
            ),
            card=NodeCard(
                schema_name="motion_rebase",
                reference_inputs=(PortRef(node_id=rebase.node_id, port_id="reading"),),
            ),
        )
        contact = builder.add(
            ACTOR_CONTACT_SHEET,
            f"player-{player.player_id}-contact-sheet",
            domain=f"player-{player.player_id}",
            description=f"assemble complete player review board for {player.player_id}",
            params=actor_params,
            depends_on=(*validations, dialogue_validation.node_id),
            input_digests=(object_digest(player.model_dump(mode="json", exclude={"motions"})),),
            ports=(artifact_port("sheet", f"{actor_root}/contact-sheet.png", "contact-sheet-v1"),),
            duration_seconds=1.0,
        )
        review = builder.add(
            ACTOR_REVIEW,
            f"player-{player.player_id}-review",
            domain=f"player-{player.player_id}",
            description=(
                "review identity, motion, facing, scale, and expression continuity for "
                f"{player.player_id}"
            ),
            params=actor_params,
            depends_on=(contact.node_id,),
            input_digests=(
                *identity,
                object_digest({"contract": CONTENT_REVIEW_CONTRACT_VERSION}),
                object_digest({"contract": CONTENT_ACTOR_PLAYBACK_REVIEW_CONTRACT_VERSION}),
                object_digest({"contract": CONTENT_PLAYER_REVIEW_CONTRACT_VERSION}),
            ),
            ports=(artifact_port("verdict", f"{actor_root}/review.json", "review-verdict-v1"),),
            card=NodeCard(
                schema_name="prepared_content_review",
                reference_inputs=(PortRef(node_id=contact.node_id, port_id="sheet"),),
            ),
        )
        terminals.extend((rebase_verify.node_id, review.node_id))
    return terminals


#: Fields that describe a subject's world size rather than its appearance. The image model owns
#: appearance only, so a magnitude never reaches a prompt and must not invalidate generated
#: artwork: authoring one would otherwise force a full re-render of pixels that cannot change.
#: Magnitude still reaches the manifest, which binds the whole package closure.
#:
#: The same argument covers a projectile's `length_units`, and extends to `flight` and `impact`:
#: those name how an object moves and what its arrival resolves against, neither of which an image
#: model can draw. Excluding them is what makes a gameplay retune free — a director who decides a
#: dart should arc instead of fly flat would otherwise pay a full high-quality re-render for pixels
#: that cannot change. This is also the concrete reason those facets are separate fields rather than
#: one conflated class name: half of a single string cannot be excluded from a digest.
_MAGNITUDE_FIELDS: set[str] = {"height_units", "length_units", "flight", "impact"}


def _without_magnitude(catalog: dict[str, object], key: str) -> dict[str, object]:
    """One catalog dump with every entry's magnitude removed, for a generation cache key."""

    entries = catalog.get(key)
    if not isinstance(entries, list):
        return catalog
    return {
        **catalog,
        key: [
            {name: value for name, value in entry.items() if name not in _MAGNITUDE_FIELDS}
            if isinstance(entry, dict)
            else entry
            for entry in entries
        ],
    }


def _add_mob_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    terminals: list[str] = []
    references = {entry.reference_id: entry for entry in builder.package.mobs.references}
    for mob in builder.package.mobs.mobs:
        identity = (
            _visual_direction_digest(builder.package),
            object_digest({"contract": CONTENT_CONCEPT_CONTRACT_VERSION}),
            object_digest(mob.model_dump(mode="json", exclude={"motions", *_MAGNITUDE_FIELDS})),
            *_reference_digests(references, mob.reference_ids),
        )
        actor_root = f"content/mobs/{mob.mob_id}"
        actor_params = {"actor_kind": "mob", "actor_id": mob.mob_id}
        concept = builder.add(
            ACTOR_CONCEPT_GENERATE,
            f"mob-{mob.mob_id}-concept-generate",
            domain=f"mob-{mob.mob_id}",
            description=f"generate identity concept for mob {mob.mob_id}",
            params=actor_params,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=identity,
            ports=(artifact_port("image", f"{actor_root}/concept.png", "actor-concept-v1"),),
        )
        concept_ref = PortRef(node_id=concept.node_id, port_id="image")
        validations: list[str] = []
        for motion in mob.motions:
            state = motion.state
            source_facing = motion_source_facing("mob", state)
            generated = builder.add(
                MOTION_ATLAS_GENERATE,
                f"mob-{mob.mob_id}-state-{state}-generate",
                domain=f"mob-{mob.mob_id}",
                description=(
                    f"generate {state} state for mob {mob.mob_id} from one "
                    f"{source_facing}-facing source strip"
                ),
                params={**actor_params, "state": state},
                depends_on=(concept.node_id,),
                input_digests=(
                    object_digest({"contract": CONTENT_MOTION_CONTRACT_VERSION}),
                    object_digest(_motion_identity("mob", state, source_facing)),
                ),
                ports=(
                    artifact_port(
                        "image", f"{actor_root}/states/{state}.source.png", "motion-source-v1"
                    ),
                ),
                card=NodeCard(reference_inputs=(concept_ref,)),
            )
            validations.append(
                builder.add(
                    MOTION_ATLAS_VALIDATE,
                    f"mob-{mob.mob_id}-state-{state}-validate",
                    domain=f"mob-{mob.mob_id}",
                    description=f"validate mob {mob.mob_id} {state} state",
                    params={**actor_params, "state": state},
                    depends_on=(generated.node_id,),
                    input_digests=(
                        object_digest({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                        object_digest(_motion_repack_identity(motion)),
                    ),
                    ports=(
                        artifact_port(
                            "image", f"{actor_root}/states/{state}.png", "motion-atlas-v1"
                        ),
                        record_port(
                            "validation",
                            f"{actor_root}/states/{state}.validation.json",
                            "atlas-validation-v1",
                        ),
                    ),
                    card=NodeCard(
                        reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)
                    ),
                    duration_seconds=0.75,
                ).node_id
            )
        contact = builder.add(
            ACTOR_CONTACT_SHEET,
            f"mob-{mob.mob_id}-contact-sheet",
            domain=f"mob-{mob.mob_id}",
            description=f"assemble complete mob review board for {mob.mob_id}",
            params=actor_params,
            depends_on=tuple(validations),
            input_digests=(
                object_digest(mob.model_dump(mode="json", exclude={"motions", *_MAGNITUDE_FIELDS})),
            ),
            ports=(artifact_port("sheet", f"{actor_root}/contact-sheet.png", "contact-sheet-v1"),),
            duration_seconds=1.0,
        )
        review = builder.add(
            ACTOR_REVIEW,
            f"mob-{mob.mob_id}-review",
            domain=f"mob-{mob.mob_id}",
            description=f"review identity and state continuity for mob {mob.mob_id}",
            params=actor_params,
            depends_on=(contact.node_id,),
            input_digests=(
                *identity,
                object_digest({"contract": CONTENT_REVIEW_CONTRACT_VERSION}),
                object_digest({"contract": CONTENT_ACTOR_PLAYBACK_REVIEW_CONTRACT_VERSION}),
            ),
            ports=(artifact_port("verdict", f"{actor_root}/review.json", "review-verdict-v1"),),
            card=NodeCard(
                schema_name="prepared_content_review",
                reference_inputs=(PortRef(node_id=contact.node_id, port_id="sheet"),),
            ),
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
            object_digest({"contract": CONTENT_CONCEPT_CONTRACT_VERSION}),
            object_digest(npc.model_dump(mode="json", exclude={"motions", *_MAGNITUDE_FIELDS})),
            *_reference_digests(references, npc.reference_ids),
        )
        actor_root = f"content/npcs/{npc.npc_id}"
        actor_params = {"actor_kind": "npc", "actor_id": npc.npc_id}
        concept = builder.add(
            ACTOR_CONCEPT_GENERATE,
            f"npc-{npc.npc_id}-concept-generate",
            domain=f"npc-{npc.npc_id}",
            description=f"generate identity concept for NPC {npc.npc_id}",
            params=actor_params,
            depends_on=(package_root,),
            cache_depends_on=(),
            input_digests=identity,
            ports=(artifact_port("image", f"{actor_root}/concept.png", "actor-concept-v1"),),
        )
        concept_ref = PortRef(node_id=concept.node_id, port_id="image")
        world = builder.add(
            WORLD_SPRITE_GENERATE,
            f"npc-{npc.npc_id}-world-generate",
            domain=f"npc-{npc.npc_id}",
            description=(
                f"generate NPC {npc.npc_id} world sprite from one "
                f"{source_facing}-facing source strip"
            ),
            params=actor_params,
            depends_on=(concept.node_id,),
            input_digests=(
                object_digest({"contract": CONTENT_MOTION_CONTRACT_VERSION}),
                object_digest(
                    {
                        "states": [motion.state for motion in npc.motions],
                        "source_facing": source_facing,
                    }
                ),
            ),
            ports=(artifact_port("image", f"{actor_root}/world.source.png", "motion-source-v1"),),
            card=NodeCard(reference_inputs=(concept_ref,)),
        )
        world_validation = builder.add(
            WORLD_SPRITE_VALIDATE,
            f"npc-{npc.npc_id}-world-validate",
            domain=f"npc-{npc.npc_id}",
            description=f"validate NPC {npc.npc_id} world sprite",
            params=actor_params,
            depends_on=(world.node_id,),
            input_digests=(
                object_digest({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                object_digest([_motion_repack_identity(motion) for motion in npc.motions]),
            ),
            ports=(
                artifact_port("image", f"{actor_root}/world.png", "motion-atlas-v1"),
                record_port(
                    "validation", f"{actor_root}/world.validation.json", "atlas-validation-v1"
                ),
            ),
            card=NodeCard(reference_inputs=(PortRef(node_id=world.node_id, port_id="image"),)),
            duration_seconds=0.75,
        )
        dialogue = builder.add(
            DIALOGUE_ATLAS_GENERATE,
            f"npc-{npc.npc_id}-dialogue-generate",
            domain=f"npc-{npc.npc_id}",
            description=f"generate NPC {npc.npc_id} dialogue expressions",
            params=actor_params,
            depends_on=(concept.node_id,),
            input_digests=(
                object_digest({"contract": CONTENT_DIALOGUE_CONTRACT_VERSION}),
                object_digest(npc.dialogue_expressions),
            ),
            ports=(
                artifact_port("image", f"{actor_root}/dialogue.source.png", "dialogue-source-v1"),
            ),
            card=NodeCard(reference_inputs=(concept_ref,)),
        )
        dialogue_validation = builder.add(
            DIALOGUE_ATLAS_VALIDATE,
            f"npc-{npc.npc_id}-dialogue-validate",
            domain=f"npc-{npc.npc_id}",
            description=f"validate NPC {npc.npc_id} dialogue expression coverage",
            params=actor_params,
            depends_on=(dialogue.node_id,),
            input_digests=(
                object_digest({"contract": CONTENT_ALPHA_REPACK_CONTRACT_VERSION}),
                object_digest(npc.dialogue_expressions),
            ),
            ports=(
                artifact_port("image", f"{actor_root}/dialogue.png", "dialogue-atlas-v1"),
                record_port(
                    "validation", f"{actor_root}/dialogue.validation.json", "atlas-validation-v1"
                ),
            ),
            card=NodeCard(reference_inputs=(PortRef(node_id=dialogue.node_id, port_id="image"),)),
            duration_seconds=0.75,
        )
        contact = builder.add(
            ACTOR_CONTACT_SHEET,
            f"npc-{npc.npc_id}-contact-sheet",
            domain=f"npc-{npc.npc_id}",
            description=f"assemble NPC {npc.npc_id} review board",
            params=actor_params,
            depends_on=(world_validation.node_id, dialogue_validation.node_id),
            input_digests=(
                object_digest(npc.model_dump(mode="json", exclude={"motions", *_MAGNITUDE_FIELDS})),
            ),
            ports=(artifact_port("sheet", f"{actor_root}/contact-sheet.png", "contact-sheet-v1"),),
            duration_seconds=1.0,
        )
        review = builder.add(
            ACTOR_REVIEW,
            f"npc-{npc.npc_id}-review",
            domain=f"npc-{npc.npc_id}",
            description=f"review world and dialogue identity for NPC {npc.npc_id}",
            params=actor_params,
            depends_on=(contact.node_id,),
            input_digests=(
                *identity,
                object_digest({"contract": CONTENT_REVIEW_CONTRACT_VERSION}),
                object_digest({"contract": CONTENT_ACTOR_PLAYBACK_REVIEW_CONTRACT_VERSION}),
            ),
            ports=(artifact_port("verdict", f"{actor_root}/review.json", "review-verdict-v1"),),
            card=NodeCard(
                schema_name="prepared_content_review",
                reference_inputs=(PortRef(node_id=contact.node_id, port_id="sheet"),),
            ),
        )
        terminals.append(review.node_id)
    return terminals


def _add_catalog_family(
    builder: _GraphBuilder,
    package_root: str,
    *,
    family: str,
    plural: str,
    entries: Sequence[tuple[str, Any]],
    references: dict[str, ContentReference],
    catalog_digest: str,
    validate_description: str,
    validate_extra_digests: tuple[str, ...],
    review_description: str,
) -> str:
    """The packaged catalog pipeline: generate -> validate per entry, then board + review.

    Props, items, and projectiles used to carry three hand-copied instances of
    this shape. The template holds the shape once; what stays per-family — the
    validation wording, the extra contact-validation contract, the axis clause a
    projectile's judge reads — arrives as parameters, because that residue is
    the content of an asset family, not noise to erase.
    """

    validations: list[str] = []
    with builder.within_template(f"catalog-pipeline@v1:{plural}"):
        for entity_id, entry in entries:
            entry_digest = object_digest(_entry_dump(entry))
            generated = builder.add(
                CATALOG_ASSET_GENERATE,
                f"{family}-{entity_id}-generate",
                domain=plural,
                description=f"generate isolated {family} {entity_id}",
                params={"family": family, "entity_id": entity_id},
                depends_on=(package_root,),
                cache_depends_on=(),
                input_digests=(
                    _visual_direction_digest(builder.package),
                    object_digest({"contract": CONTENT_CATALOG_CONTRACT_VERSION}),
                    entry_digest,
                    *_reference_digests(references, _entry_reference_ids(entry)),
                ),
                ports=(
                    artifact_port(
                        "image", f"content/{plural}/{entity_id}.png", "catalog-sprite-v1"
                    ),
                ),
            )
            validations.append(
                builder.add(
                    CATALOG_ASSET_VALIDATE,
                    f"{family}-{entity_id}-validate",
                    domain=plural,
                    description=validate_description.format(entity_id=entity_id),
                    params={"family": family, "entity_id": entity_id},
                    depends_on=(generated.node_id,),
                    input_digests=(entry_digest, *validate_extra_digests),
                    ports=(
                        record_port(
                            "validation",
                            f"content/{plural}/{entity_id}.validation.json",
                            "catalog-validation-v1",
                        ),
                    ),
                    card=NodeCard(
                        reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)
                    ),
                    duration_seconds=0.5,
                ).node_id
            )
        contact = builder.add(
            CATALOG_CONTACT_SHEET,
            f"{plural}-contact-sheet",
            domain=plural,
            description=f"assemble the complete {family} catalog review board",
            params={"family": family},
            depends_on=tuple(validations),
            input_digests=(
                catalog_digest,
                object_digest({"contract": CONTENT_REVIEW_CONTRACT_VERSION}),
            ),
            ports=(
                artifact_port("sheet", f"content/{plural}/contact-sheet.png", "contact-sheet-v1"),
            ),
            duration_seconds=1.0,
        )
        return builder.add(
            CATALOG_REVIEW,
            f"{plural}-review",
            domain=plural,
            description=review_description,
            params={"family": family},
            depends_on=(contact.node_id,),
            input_digests=(catalog_digest,),
            ports=(artifact_port("verdict", f"content/{plural}/review.json", "review-verdict-v1"),),
            card=NodeCard(
                schema_name="prepared_content_review",
                reference_inputs=(PortRef(node_id=contact.node_id, port_id="sheet"),),
            ),
        ).node_id


def _entry_dump(entry: Any) -> object:
    return entry.model_dump(mode="json", exclude=_MAGNITUDE_FIELDS)


def _entry_reference_ids(entry: Any) -> tuple[str, ...]:
    return tuple(entry.reference_ids)


def _add_prop_nodes(builder: _GraphBuilder, package_root: str) -> str:
    catalog = builder.package.props
    return _add_catalog_family(
        builder,
        package_root,
        family="prop",
        plural="props",
        entries=[(prop.prop_id, prop) for prop in catalog.props],
        references={entry.reference_id: entry for entry in catalog.references},
        catalog_digest=object_digest(_without_magnitude(catalog.model_dump(mode="json"), "props")),
        validate_description="validate isolated alpha and framing for prop {entity_id}",
        validate_extra_digests=(
            object_digest({"contract": CONTENT_PROP_CONTACT_VALIDATION_VERSION}),
        ),
        review_description="review complete prop identity and isolation coverage",
    )


def _add_item_nodes(builder: _GraphBuilder, package_root: str) -> str:
    catalog = builder.package.items
    return _add_catalog_family(
        builder,
        package_root,
        family="item",
        plural="items",
        entries=[(item.item_id, item) for item in catalog.items],
        references={entry.reference_id: entry for entry in catalog.references},
        catalog_digest=object_digest(_without_magnitude(catalog.model_dump(mode="json"), "items")),
        validate_description="validate isolated alpha and framing for item {entity_id}",
        validate_extra_digests=(),
        review_description="review complete item identity and isolation coverage",
    )


def _add_projectile_nodes(builder: _GraphBuilder, package_root: str) -> str | None:
    """One more catalog-pipeline instance, or nothing for a package that fires nothing.

    The projectile residue: validation additionally demands a single connected
    subject and the declared axis, and the review reads axis coverage.
    """

    catalog = builder.package.projectiles
    if catalog is None:
        return None
    return _add_catalog_family(
        builder,
        package_root,
        family="projectile",
        plural="projectiles",
        entries=[(projectile.projectile_id, projectile) for projectile in catalog.projectiles],
        references={entry.reference_id: entry for entry in catalog.references},
        catalog_digest=object_digest(
            _without_magnitude(catalog.model_dump(mode="json"), "projectiles")
        ),
        validate_description=(
            "validate isolated alpha, single-subject framing, and axis for projectile {entity_id}"
        ),
        validate_extra_digests=(),
        review_description="review complete projectile identity, isolation, and axis coverage",
    )


def _add_soundtrack_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    package = builder.package
    return add_soundtrack_nodes(
        builder,
        types=SoundtrackNodeTypes(generate=SOUNDTRACK_GENERATE, validate=SOUNDTRACK_VALIDATE),
        tracks=package.soundtrack.tracks,
        depends_on=(package_root,),
        node_id=lambda track, stage: f"track-{track.track_id}-{stage}",
        prompt=lambda track: music_track_prompt(
            medium="a 2D game",
            game_id=package.game.game_id,
            track_id=track.track_id,
            creative_brief=track.creative_brief,
            generation=track.generation,
        ),
        # Keyed on the authored track and this recipe's contract, as it always was; the
        # prompt is on the card for the handler, not in the key.
        generate_digests=lambda track, _prompt: (
            object_digest({"contract": CONTENT_SOUNDTRACK_CONTRACT_VERSION}),
            object_digest(track.model_dump(mode="json")),
        ),
    )


def _add_ui_nodes(builder: _GraphBuilder, package_root: str) -> list[str]:
    """The recipe's own inventory panel plus the shared nine-slice atlas roles.

    The atlas triplet belongs to no genre, so the fan-out is the component's; this
    recipe supplies only what it alone knows — its art direction, as the prompt
    wrapper and as the digest that re-bills a sheet when the look changes.
    """

    return [
        _add_inventory_panel_nodes(builder, package_root),
        *add_ui_atlas_nodes(
            builder,
            root=package_root,
            ui=builder.package.ui,
            style_prompt=lambda task: visual_prompt(builder.package, task),
            direction_digests=(_visual_direction_digest(builder.package),),
        ),
    ]


def _add_inventory_panel_nodes(builder: _GraphBuilder, package_root: str) -> str:
    panel = builder.package.ui.required_inventory_panel()
    references = {entry.reference_id: entry for entry in builder.package.ui.references}
    generated = builder.add(
        UI_INVENTORY_GENERATE,
        "ui-inventory-panel-generate",
        domain="ui",
        description="generate the authored inventory panel presentation",
        depends_on=(package_root,),
        cache_depends_on=(),
        input_digests=(
            _visual_direction_digest(builder.package),
            object_digest({"contract": UI_INVENTORY_PANEL_CONTRACT_VERSION}),
            object_digest(panel.model_dump(mode="json")),
            *(references[reference_id].source_sha256 for reference_id in panel.reference_ids),
            hashlib.sha256(inventory_template_path().read_bytes()).hexdigest(),
        ),
        ports=(artifact_port("image", "ui/inventory_panel.raw.png", "ui-panel-raw-v1"),),
        card=NodeCard(template_ref="inventory_grid_4x2_template_v1"),
    )
    validated = builder.add(
        UI_INVENTORY_VALIDATE,
        "ui-inventory-panel-validate",
        domain="ui",
        description="validate opaque panel and slot interiors on a transparent exterior",
        depends_on=(generated.node_id,),
        input_digests=(
            object_digest({"contract": UI_INVENTORY_PANEL_CONTRACT_VERSION}),
            object_digest(panel.model_dump(mode="json")),
        ),
        ports=(
            artifact_port("image", "ui/inventory_panel.png", "ui-panel-v1"),
            record_port("validation", "ui/inventory_panel.validation.json", "ui-validation-v1"),
            artifact_port("evidence", "ui/inventory_panel.evidence.png", "ui-evidence-v1"),
        ),
        card=NodeCard(reference_inputs=(PortRef(node_id=generated.node_id, port_id="image"),)),
        duration_seconds=0.75,
    )
    return builder.add(
        UI_INVENTORY_REVIEW,
        "ui-inventory-panel-review",
        domain="ui",
        description="review inventory readability, style, and filled slot surfaces",
        depends_on=(validated.node_id,),
        input_digests=(
            object_digest({"contract": UI_INVENTORY_PANEL_REVIEW_VERSION}),
            object_digest(panel.model_dump(mode="json")),
        ),
        ports=(artifact_port("verdict", "ui/inventory_panel.review.json", "review-verdict-v1"),),
        card=NodeCard(
            schema_name="prepared_ui_inventory_review",
            reference_inputs=(PortRef(node_id=validated.node_id, port_id="image"),),
        ),
    ).node_id


class _GraphBuilder(GraphBuilder):
    """The engine builder plus this recipe's package handle."""

    def __init__(self, package: ResolvedGamePackage, profile: BindingTable) -> None:
        super().__init__(profile=profile, local_max_in_flight=32)
        self.package = package


def _add_painted_terrain_nodes(
    builder: _GraphBuilder,
    game_map: PreparedGameMap,
    *,
    package_root: str,
    terrain_node_id: str,
    map_direction: str,
    ground_direction: dict[str, object],
    references: dict[str, PreparedMapReference],
) -> str:
    """Fan one map out into its derived segments, and return the node that composes them.

    Every node here declares an edge to the terrain node, and none of them opts out of
    cache inheritance the way the atlas image does. That is the honest cost of the mode and
    it is the inverse of the atlas's designed property: the atlas paints a material that
    knows nothing about the level, so reshaping a level never re-bills it, while a painting
    OF the occupancy must be repainted when the occupancy moves. The partition is what
    bounds it -- a deck edited in the middle of one segment re-bills that segment alone.
    """

    segments = painted_terrain_segments(game_map.terrain.columns, game_map.terrain.rows)
    prompt_direction = _painted_terrain_material_direction(builder.package, game_map)
    canonical_ids: list[str] = []
    with builder.within_template("painted-terrain-segment-pipeline@v1"):
        for segment in segments:
            segment_identity = object_digest(
                {
                    "index": segment.index,
                    "start_column": segment.start_column,
                    "columns": segment.columns,
                    "count": len(segments),
                    "guide": PAINTED_TERRAIN_GUIDE_ID,
                }
            )
            base = f"map-{game_map.map_id}-ground-{segment.segment_id}"
            guide = builder.add(
                PAINTED_TERRAIN_GUIDE,
                f"{base}-guide",
                domain=f"map-{game_map.map_id}",
                description=(f"draw the {segment.segment_id} terrain guide for {game_map.map_id}"),
                params={"map_id": game_map.map_id, "segment_id": segment.segment_id},
                # Terrain is a real input, not a scheduling nicety: without the edge the
                # scheduler may draw a guide before terrain.json exists.
                depends_on=(package_root, terrain_node_id),
                input_digests=(
                    map_direction,
                    object_digest(ground_direction),
                    segment_identity,
                    *_reference_digests(references, game_map.ground.reference_ids),
                ),
                ports=(
                    artifact_port(
                        "guide",
                        f"maps/{game_map.map_id}/ground/{segment.segment_id}.guide.png",
                        PAINTED_TERRAIN_GUIDE_KIND,
                    ),
                    record_port(
                        "guide_report",
                        f"maps/{game_map.map_id}/ground/{segment.segment_id}.guide.json",
                        PAINTED_TERRAIN_GUIDE_REPORT_KIND,
                    ),
                ),
            )
            generated = builder.add(
                PAINTED_TERRAIN_GENERATE,
                f"{base}-generate",
                domain=f"map-{game_map.map_id}",
                description=f"paint {segment.segment_id} of {game_map.map_id}",
                params={"map_id": game_map.map_id, "segment_id": segment.segment_id},
                depends_on=(guide.node_id,),
                input_digests=(
                    text_digest(
                        painted_terrain_generation_prompt(
                            prompt_direction,
                            segment=segment,
                            columns=segment.columns,
                            rows=game_map.terrain.rows,
                        )
                    ),
                ),
                ports=(
                    artifact_port(
                        "image",
                        f"maps/{game_map.map_id}/ground/{segment.segment_id}.raw.png",
                        PAINTED_TERRAIN_RAW_KIND,
                    ),
                ),
                card=NodeCard(reference_inputs=(PortRef(node_id=guide.node_id, port_id="guide"),)),
            )
            canonical = builder.add(
                PAINTED_TERRAIN_CANONICALIZE,
                f"{base}-canonicalize",
                domain=f"map-{game_map.map_id}",
                description=(
                    f"admit {segment.segment_id} of {game_map.map_id} to its authored geometry"
                ),
                params={"map_id": game_map.map_id, "segment_id": segment.segment_id},
                depends_on=(guide.node_id, generated.node_id),
                input_digests=(
                    object_digest({"canonicalizer": PAINTED_TERRAIN_CANONICALIZER_ID}),
                    object_digest(painted_silhouette_tolerance().model_dump(mode="json")),
                ),
                ports=(
                    artifact_port(
                        "image",
                        f"maps/{game_map.map_id}/ground/{segment.segment_id}.png",
                        PAINTED_TERRAIN_KIND,
                    ),
                    record_port(
                        "validation",
                        f"maps/{game_map.map_id}/ground/{segment.segment_id}.validation.json",
                        PAINTED_TERRAIN_VALIDATION_KIND,
                    ),
                ),
                duration_seconds=2.0,
            )
            canonical_ids.append(canonical.node_id)
    compose = builder.add(
        PAINTED_TERRAIN_COMPOSE,
        f"map-{game_map.map_id}-ground-compose",
        domain=f"map-{game_map.map_id}",
        description=f"stitch the painted terrain of {game_map.map_id} into one plate",
        params={"map_id": game_map.map_id},
        depends_on=(*canonical_ids, terrain_node_id),
        input_digests=(object_digest({"segments": len(segments)}),),
        ports=(
            # The plate is evidence, a composite input and a review subject. It is never a
            # runtime asset: fifty-six columns fit inside a 4096-pixel texture and
            # sixty-five do not, so the consumer always loads segments.
            artifact_port(
                "evidence",
                f"maps/{game_map.map_id}/ground.evidence.png",
                PAINTED_TERRAIN_PLATE_KIND,
            ),
            record_port(
                "validation",
                f"maps/{game_map.map_id}/ground.validation.json",
                PAINTED_TERRAIN_GROUND_VALIDATION_KIND,
            ),
        ),
        duration_seconds=1.5,
    )
    return compose.node_id


def _painted_terrain_material_direction(
    package: ResolvedGamePackage, game_map: PreparedGameMap
) -> str:
    style = package.game.style
    return (
        f"{game_map.ground.prompt.strip()} Target style: {style.label}; "
        f"{', '.join(style.keywords)}."
    )


def _visual_direction(package: ResolvedGamePackage) -> dict[str, object]:
    return {
        "universe_sha256": package.file(package.game.universe.source).sha256,
        "style": package.game.style.model_dump(mode="json"),
        "proportion": package.game.proportion.model_dump(mode="json"),
        # Runtime contact shadows are deliberately absent: changing them must not invalidate any
        # paid generation node. These two fields remain provider-facing visual direction.
        "presentation": {
            "view_profile": package.platformer.presentation.view_profile,
            "gameplay_space": package.platformer.presentation.gameplay_space,
        },
    }


def _visual_direction_digest(package: ResolvedGamePackage) -> str:
    return object_digest(_visual_direction(package))


def visual_prompt(package: ResolvedGamePackage, specific: str) -> str:
    """This recipe's art direction wrapped around one content task.

    Plan-time, because a card that states the exact instruction a provider will be
    given is the difference between a readable plan and a promise. The handler reads
    it back off the card rather than recomposing it.
    """

    universe = package.file(package.game.universe.source).data.decode("utf-8")
    style = package.game.style
    return (
        f"Game universe:\n{universe}\n\nVisual style: {style.label}. "
        f"Use: {', '.join(style.keywords)}. Avoid: {', '.join(style.avoid)}.\n\n"
        f"Content task:\n{specific}"
    )


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
    "CACHE_RECORD_KIND",
    "CONTENT_CACHE_NAMESPACE",
    "WORLD_CACHE_NAMESPACE",
    "build_package_execution_graph",
    "package_graph_profile",
]

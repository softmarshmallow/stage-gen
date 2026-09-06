"""The oblique-survival execution graph: the routes it may use and the plan it seals.

One graph serves every scope. A scope selects a subset of nodes and changes nothing
about the ones it keeps -- same node id, same cache key, same input digests -- so a
narrow run's artifacts restore into a wider one instead of being paid for twice. That is
the whole reason the ladder exists: minimal proves the oblique prop clause for about a
dollar, and everything after it builds on the run that proved it.

One image route, not two. gnode's binding table declares at most one route per
operation, so binding a transparent route and an opaque route would mean two operation
names, two services and two retry owners for one modality. Instead every image goes
through OpenAI direct, which is the only route with native alpha, and the ground and the
flame strip ask it for an opaque background.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import Final, Literal

from pydantic import BaseModel, Field

from gnode import Binding, BindingTable, GraphBuilder, ModelRef, Node, NodeCard, NodeType, Port
from stage_gen.config import StageGenConfig
from stage_gen.recipes.graph_document import RecipeGraph
from stage_gen.recipes.oblique_survival import manifest as manifest_module
from stage_gen.recipes.oblique_survival import survival_prompts as prompts
from stage_gen.recipes.oblique_survival import templates
from stage_gen.recipes.oblique_survival.models import Package, strip_key
from stage_gen.recipes.oblique_survival.survival_types import (
    ACTOR_CONCEPT,
    CLUTTER_ADOPT,
    CLUTTER_GENERATE,
    CLUTTER_VALIDATE,
    DECAL_GENERATE,
    DECAL_VALIDATE,
    DUST_GENERATE,
    DUST_VALIDATE,
    FIRE_GENERATE,
    FIRE_VALIDATE,
    FORAGE_ADOPT,
    FORAGE_GENERATE,
    FORAGE_VALIDATE,
    GROUND_ADOPT,
    GROUND_CANONICALIZE,
    GROUND_GENERATE,
    ICONS_ADOPT,
    ICONS_GENERATE,
    ICONS_VALIDATE,
    IMAGE_FEATURES,
    ITEM_GENERATE,
    ITEM_VALIDATE,
    MACRO_CANONICALIZE,
    MACRO_GENERATE,
    MOTION_GENERATE,
    MOTION_VALIDATE,
    MUSIC_ADOPT,
    MUSIC_FEATURES,
    MUSIC_GENERATE,
    MUSIC_VALIDATE,
    PACKAGE_MANIFEST,
    PLANTS_ADOPT,
    PLANTS_GENERATE,
    PLANTS_LOOK_GENERATE,
    PLANTS_LOOK_VALIDATE,
    PLANTS_VALIDATE,
    PRESENTATION_PROFILE,
    PROP_ANCHOR,
    PROP_GENERATE,
    PROP_SHEET_GENERATE,
    PROP_SHEET_VALIDATE,
    PROP_VALIDATE,
    REBASE_JUDGE,
    REBASE_PLATE,
    REBASE_VERIFY,
    REBASE_VERIFY_PLATE,
    REVIEW_FAMILIES,
    REVIEW_JUDGE,
    REVIEW_SHEET,
    ROAD_CANONICALIZE,
    ROAD_GENERATE,
    SCOPE_RANK,
    SEASON_LOOK_GENERATE,
    SEASON_LOOK_VALIDATE,
    SOUND_ADOPT,
    SOUND_FEATURES,
    SOUND_GENERATE,
    SOUND_VALIDATE,
    SOURCE_LOCK,
    STRUCTURED_FEATURES,
    TEMPLATES_DRAW,
    TOOL_LOOP_FEATURES,
    WATER_CANONICALIZE,
    WATER_GENERATE,
    WEATHER_COVER_CANONICALIZE,
    WEATHER_COVER_GENERATE,
    WEATHER_DROPS_GENERATE,
    WEATHER_DROPS_VALIDATE,
    WEATHER_GROUND_GENERATE,
    WEATHER_GROUND_VALIDATE,
    WEATHER_ICE_ADOPT,
    WEATHER_ICE_CANONICALIZE,
    WEATHER_ICE_GENERATE,
    WEATHER_SOUND_GENERATE,
    WEATHER_SOUND_VALIDATE,
    WEATHER_STRIKE_GENERATE,
    WEATHER_STRIKE_VALIDATE,
    WORLD_LAYOUT,
    ObliqueSurvivalOperationKind,
)
from stage_gen.recipes.ports import artifact_port, attempts_port, text_digest

#: The graph document's own version, read by the recipe-substrate contract test.
OBLIQUE_SURVIVAL_GRAPH_SCHEMA_VERSION = 1
OBLIQUE_SURVIVAL_CACHE_NAMESPACE = "oblique-survival-nodes-v1"
OBLIQUE_SURVIVAL_CACHE_RECORD_KIND = "oblique-survival-node-cache-v1"
#: The kind every attempt ledger carries, structured and image alike.
OBLIQUE_SURVIVAL_ATTEMPT_LEDGER_KIND = "oblique-survival-attempt-ledger-v1"

#: The props a minimal run draws. It began as three -- one tall, one squat, one
#: soft -- to prove the oblique clause cheaply. The vegetation set joined them
#: because a wood of one repeated conifer is the demo's most visible flaw, and
#: judging that needs the mix on screen, not a second scope. Any
#: pitch or floor-plate problem shows up across those three or not at all.
MINIMAL_PROPS: Final = (
    "pine",
    "moss_boulder",
    "thorn_bush",
    "birch",
    "dead_snag",
    "fern_clump",
)


def _safe(value: str) -> str:
    """A node id segment: authored ids use underscores, node ids use hyphens."""

    return value.replace("_", "-")


#: Run-relative refs the executor and the run view read back by name.
SOURCE_LOCK_REF: Final = "production/source-lock.json"
MANIFEST_REF: Final = "manifest.json"
#: Where a refused image attempt's bytes are kept, per node.
REJECTS_ROOT: Final = "production/rejected"


def oblique_survival_graph_profile(config: StageGenConfig) -> BindingTable:
    """Every provider route this plan may use, declared before anything runs."""

    return BindingTable(
        [
            Binding(
                operation=ObliqueSurvivalOperationKind.IMAGE_GENERATION,
                model=ModelRef(model=config.openai_image_model, provider="openai"),
                resource_id="survival-openai-image",
                estimated_duration_seconds=90.0,
                estimated_cost_low_usd=0.04,
                estimated_cost_high_usd=0.20,
                features=frozenset(IMAGE_FEATURES),
                requests_per_minute=config.openai_image_ipm,
                rate_limit_owner="provider_adapter",
                verified_on="2026-09-03",
            ),
            Binding(
                operation=ObliqueSurvivalOperationKind.STRUCTURED_GENERATION,
                model=ModelRef(model=config.text_model, provider="openrouter"),
                resource_id="survival-openrouter-structured",
                estimated_duration_seconds=45.0,
                estimated_cost_low_usd=0.005,
                estimated_cost_high_usd=0.08,
                features=frozenset(STRUCTURED_FEATURES),
                max_in_flight=4,
                rate_limit_owner="none",
                verified_on="2026-09-03",
            ),
            Binding(
                operation=ObliqueSurvivalOperationKind.TOOL_LOOP,
                model=ModelRef(model=config.text_model, provider="openrouter"),
                resource_id="survival-openrouter-tool-loop",
                estimated_duration_seconds=120.0,
                estimated_cost_low_usd=0.02,
                estimated_cost_high_usd=0.30,
                features=frozenset(TOOL_LOOP_FEATURES),
                max_in_flight=2,
                rate_limit_owner="none",
                verified_on="2026-09-03",
            ),
            Binding(
                operation=ObliqueSurvivalOperationKind.MUSIC_GENERATION,
                model=ModelRef(model=config.music_model, provider="openrouter"),
                resource_id="survival-openrouter-music",
                estimated_duration_seconds=300.0,
                estimated_cost_low_usd=0.05,
                estimated_cost_high_usd=0.50,
                features=frozenset(MUSIC_FEATURES),
                max_in_flight=2,
                rate_limit_owner="none",
                verified_on="2026-09-04",
            ),
            Binding(
                operation=ObliqueSurvivalOperationKind.SOUND_EFFECT_GENERATION,
                model=ModelRef(model=config.sound_effect_model, provider="elevenlabs"),
                resource_id="survival-elevenlabs-sound",
                estimated_duration_seconds=30.0,
                estimated_cost_low_usd=0.02,
                estimated_cost_high_usd=0.10,
                features=frozenset(SOUND_FEATURES),
                max_in_flight=2,
                rate_limit_owner="none",
                verified_on="2026-09-04",
            ),
        ]
    )


class _LedgerGraphBuilder(GraphBuilder):
    """Every provider node declares the ledger its refused attempts ride.

    The spike wrote refused image attempts into an undeclared ``production/rejected``
    tree and refused structured attempts into an undeclared ``.attempts`` directory:
    files no port named, so a cache restore lost them and no run view ever showed them.
    Here one more port carries the ledger, written whether or not anything was refused,
    because a node whose declared ports are not all present cannot be cached at all.
    Ports are not a cache-key input, so this moves ``topology_sha256`` and not one key.
    """

    def add(
        self,
        node_type: NodeType,
        node_id: str,
        *,
        domain: str,
        description: str,
        params: dict[str, str] | None = None,
        depends_on: Sequence[str] = (),
        cache_depends_on: Sequence[str] | None = None,
        input_digests: Sequence[str] = (),
        ports: Sequence[Port] = (),
        card: NodeCard | None = None,
        duration_seconds: float | None = None,
    ) -> Node:
        declared = tuple(ports)
        if not node_type.is_local:
            declared = (
                *declared,
                attempts_port(node_id, OBLIQUE_SURVIVAL_ATTEMPT_LEDGER_KIND),
            )
        return super().add(
            node_type,
            node_id,
            domain=domain,
            description=description,
            params=params,
            depends_on=depends_on,
            cache_depends_on=cache_depends_on,
            input_digests=input_digests,
            ports=declared,
            card=card,
            duration_seconds=duration_seconds,
        )


class ObliqueSurvivalGraph(RecipeGraph):
    """One authored survival world's plan of record, for one scope of the ladder."""

    OPERATIONS = ObliqueSurvivalOperationKind
    # Only the scope is in topology identity: it genuinely changes the node set. The
    # package id, the presentation profile and the source digest ride the whole
    # document through ``graph_sha256``; putting them in the identity header would move
    # the topology digest every time an authored word changed, which is the mistake the
    # base class exists to stop.
    IDENTITY_FIELDS = ("scope",)
    VIEW_FIELDS = ("scope", "package_id", "presentation_profile", "source_digest")

    schema_version: Literal[1]
    kind: Literal["oblique-survival-execution-graph-v1"]
    recipe: Literal["oblique-survival"]
    package_id: str
    scope: str
    presentation_profile: str
    source_digest: str
    publication_authorized: Literal[False]

    def estimated_cost_usd(self) -> tuple[float, float]:
        return (
            round(sum(node.estimated_cost_low_usd for node in self.nodes), 2),
            round(sum(node.estimated_cost_high_usd for node in self.nodes), 2),
        )


# --- structured contracts ------------------------------------------------------------


class ReviewFinding(BaseModel):
    subject: str = Field(description="the labelled sprite the finding is about")
    problem: str = Field(description="what is wrong with it, in one sentence")
    blocking: bool = Field(description="true when this makes the sprite unusable in the scene")


class FamilyReview(BaseModel):
    consistent_pitch: bool
    consistent_style: bool
    clean_cutouts: bool
    consistent_state_pairs: bool
    readable_at_play_size: bool
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=24)
    summary: str = Field(min_length=1, max_length=1200)

    @property
    def blocking(self) -> list[ReviewFinding]:
        return [finding for finding in self.findings if finding.blocking]


class AnchorPlacement(BaseModel):
    anchor_x: float = Field(ge=0.0, le=1.0)
    anchor_y: float = Field(ge=0.0, le=1.0)
    footprint_radius_units: float = Field(ge=0.02, le=2.5)
    motion_hint: Literal["sway_top", "bob", "flicker", "none"]
    rationale: str = Field(min_length=1, max_length=600)


def evaluate_review(review: FamilyReview) -> list[str]:
    problems: list[str] = []
    for finding in review.findings:
        if not finding.subject.strip() or not finding.problem.strip():
            problems.append("every finding needs a subject and a problem")
            break
    flags = (
        review.consistent_pitch,
        review.consistent_style,
        review.clean_cutouts,
        review.consistent_state_pairs,
        review.readable_at_play_size,
    )
    if not all(flags) and not review.findings:
        problems.append("a review that reports a failed check must name at least one finding")
    return problems


# --- the graph ------------------------------------------------------------------------


def build_graph(config: StageGenConfig, package: Package, scope: str) -> ObliqueSurvivalGraph:
    """Build the whole graph for one scope. Node identity never depends on scope."""

    rank = SCOPE_RANK[scope]
    bindings = oblique_survival_graph_profile(config)
    builder = _LedgerGraphBuilder(profile=bindings)
    source_digest = package.source_digest()
    # Every node that carries the style plate digests its bytes, not just its
    # prompt: redrawing the plate must re-bill them, and the prompt text does
    # not change when the picture does.
    style_digests = (
        [text_digest(package.style_reference_digest or "")]
        if package.style_reference is not None
        else []
    )
    fire = package.fire

    lock = builder.add(
        SOURCE_LOCK,
        "source-lock",
        domain="source",
        description="Digest every authored file and the presentation profile",
        input_digests=[source_digest],
        ports=[artifact_port("lock", "production/source-lock.json", "source-lock-v1")],
    )

    # One lattice per distinct grid shape. The flame strip and the litter sheet
    # both paint into a 4x4, so they share one template node and one digest.
    template_nodes: dict[tuple[int, int, int], Node] = {}
    transparent = templates.LATTICE_TRANSPARENT

    def template_for(columns: int, rows: int, cell_px: int = templates.LATTICE_CELL_PX) -> Node:
        key = (columns, rows, cell_px)
        # The 256-px magenta lattices keep the ids they had before cell size
        # or backing was a choice; the transparent lattice is its own node.
        suffix = "" if cell_px == templates.LATTICE_CELL_PX else f"-{cell_px}px"
        if transparent:
            suffix += "-alpha"
        if key not in template_nodes:
            template_nodes[key] = builder.add(
                TEMPLATES_DRAW,
                f"templates-draw-{columns}x{rows}{suffix}",
                domain="source",
                description=f"Draw the {columns}x{rows} cyan-and-magenta paintover lattice",
                params={
                    "columns": str(columns),
                    "rows": str(rows),
                    "cell_px": str(cell_px),
                    "transparent": "1" if transparent else "0",
                },
                depends_on=[lock.node_id],
                cache_depends_on=(),
                input_digests=[text_digest(templates.template_id(columns, rows, cell_px))],
                ports=[
                    artifact_port(
                        "template",
                        templates.template_ref(columns, rows, cell_px),
                        "paintover-template-v1",
                    )
                ],
            )
        return template_nodes[key]

    review_subjects: dict[str, list[tuple[str, str]]] = {family: [] for family in REVIEW_FAMILIES}
    review_inputs: dict[str, list[str]] = {family: [] for family in REVIEW_FAMILIES}
    # The node that publishes each summer sprite, by (prop, state): a season
    # look hangs off it.
    summer_validates: dict[tuple[str, str], str] = {}

    # --- props and items
    # The minimal scope draws what the demo needs on screen to be played: each
    # minimal prop's baseline state, the state its interaction leaves behind
    # (a chopped pine is a stump, and without the stump the tree would simply
    # vanish), and the items those interactions yield. Everything else waits
    # for the props scope.
    minimal_items: set[str] = set()
    if package.forage is not None:
        # A minimal run plays the pick: what lies on the ground has a pickup
        # sprite to be once it is dropped again.
        minimal_items.update(cell.item_id for cell in package.forage.cells)
    for prop in package.props:
        minimal = prop.prop_id in MINIMAL_PROPS
        if rank < 1 and not minimal:
            continue
        if rank < 1 and prop.interaction is not None:
            minimal_items.update(produced.item_id for produced in prop.interaction.yields)
        if prop.sheet is not None:
            # A sheet is one op for every look, in every scope: there is no
            # narrower way to draw it. The validate node splits it into the
            # same per-look sprites and records the sprite path writes, so the
            # anchor loop, the manifest and the viewer see no difference.
            prompt = prompts.prop_sheet_prompt(package, prop)
            # The sprite route, one canvas wide: true alpha, the style plate
            # as reference image 1, no lattice. The sheet's cells are
            # arithmetic, and the gate refuses a look that crosses one.
            generate = builder.add(
                PROP_SHEET_GENERATE,
                f"prop-{_safe(prop.prop_id)}-sheet-generate",
                domain="props",
                description=f"Draw every look of {prop.prop_id} on one canvas",
                params={"prop_id": prop.prop_id},
                depends_on=[lock.node_id],
                cache_depends_on=(),
                input_digests=[text_digest(prompt), *style_digests],
                card=NodeCard(prompt=prompt),
                ports=[
                    artifact_port(
                        "image",
                        f"production/props/{prop.prop_id}.sheet.source.png",
                        "prop-sheet-source-v1",
                    )
                ],
            )
            ports = []
            for state in prop.states:
                ports.append(
                    artifact_port(
                        f"image_{_safe(state)}",
                        manifest_module.prop_ref(prop.prop_id, state),
                        "prop-sprite-v1",
                    )
                )
                ports.append(
                    artifact_port(
                        f"validation_{_safe(state)}",
                        f"production/validation/props/{prop.prop_id}-{state}.json",
                        "prop-validation-v1",
                    )
                )
            ports.append(
                artifact_port(
                    "sheet", f"production/props/{prop.prop_id}.sheet.png", "prop-sheet-v1"
                )
            )
            ports.append(
                artifact_port(
                    "sheet_validation",
                    f"production/validation/props/{prop.prop_id}-sheet.json",
                    "prop-sheet-validation-v1",
                )
            )
            validate = builder.add(
                PROP_SHEET_VALIDATE,
                f"prop-{_safe(prop.prop_id)}-sheet-validate",
                domain="props",
                description=f"Gate {prop.prop_id}'s sheet and split it into its looks",
                params={"prop_id": prop.prop_id},
                depends_on=[generate.node_id],
                ports=ports,
            )
            # One review label per published look, the node once: the contact
            # sheet lists one cell per look file and the judge numbers those.
            for state in prop.states:
                review_subjects["props"].append((f"{prop.prop_id} {state}", validate.node_id))
                summer_validates[(prop.prop_id, state)] = validate.node_id
            review_inputs["props"].append(validate.node_id)
            builder.add(
                PROP_ANCHOR,
                f"prop-{_safe(prop.prop_id)}-anchor",
                domain="props",
                description=f"Place {prop.prop_id}'s ground anchor and pick its motion hint",
                params={"prop_id": prop.prop_id},
                depends_on=[validate.node_id],
                input_digests=[text_digest(prop.motion_hint)],
                ports=[
                    artifact_port(
                        "anchor", manifest_module.anchor_ref(prop.prop_id), "prop-anchor-v1"
                    ),
                ],
            )
            continue
        states = list(prop.states) if rank >= 1 else [prop.baseline_state]
        if rank < 1:
            # What a played demo needs of a sprite prop: the baseline, the
            # look each interaction leaves and passes through, and the looks
            # the layout may place.
            wanted: list[str] = []
            if prop.interaction is not None:
                wanted.extend([*prop.interaction.progress, prop.interaction.next_state])
            if prop.variants is not None:
                wanted.extend(prop.variants.states)
            for candidate in wanted:
                if candidate in prop.states and candidate not in states:
                    states.append(candidate)
        baseline_validate = ""
        for state in states:
            prompt = prompts.prop_prompt(package, prop, state)
            generate = builder.add(
                PROP_GENERATE,
                f"prop-{_safe(prop.prop_id)}-{_safe(state)}-generate",
                domain="props",
                description=f"Draw {prop.prop_id} in its {state} state",
                params={"prop_id": prop.prop_id, "state": state},
                depends_on=[lock.node_id],
                cache_depends_on=(),
                input_digests=[text_digest(prompt), *style_digests],
                card=NodeCard(prompt=prompt),
                ports=[
                    artifact_port(
                        "image",
                        f"production/props/{prop.prop_id}-{state}.source.png",
                        "prop-sprite-source-v1",
                    )
                ],
            )
            validate = builder.add(
                PROP_VALIDATE,
                f"prop-{_safe(prop.prop_id)}-{_safe(state)}-validate",
                domain="props",
                description=f"Gate {prop.prop_id} {state} and measure its footprint",
                params={"prop_id": prop.prop_id, "state": state},
                depends_on=[generate.node_id],
                ports=[
                    artifact_port(
                        "image", manifest_module.prop_ref(prop.prop_id, state), "prop-sprite-v1"
                    ),
                    artifact_port(
                        "validation",
                        f"production/validation/props/{prop.prop_id}-{state}.json",
                        "prop-validation-v1",
                    ),
                ],
            )
            if state == prop.baseline_state:
                baseline_validate = validate.node_id
            summer_validates[(prop.prop_id, state)] = validate.node_id
            review_subjects["props"].append((f"{prop.prop_id} {state}", validate.node_id))
            review_inputs["props"].append(validate.node_id)
        # The anchor is placed on the baseline state alone and applies to every
        # state, so it depends on the baseline alone. Depending on all of them
        # would move its cache key the moment a wider scope adds a second state,
        # and the ladder would pay for the same placement twice.
        builder.add(
            PROP_ANCHOR,
            f"prop-{_safe(prop.prop_id)}-anchor",
            domain="props",
            description=f"Place {prop.prop_id}'s ground anchor and pick its motion hint",
            params={"prop_id": prop.prop_id},
            depends_on=[baseline_validate],
            input_digests=[text_digest(prop.motion_hint)],
            ports=[
                artifact_port("anchor", manifest_module.anchor_ref(prop.prop_id), "prop-anchor-v1"),
            ],
        )

    # --- season looks
    # A look is a set of paintovers of the summer sprites (seasons.toml): one
    # op per prop state, the summer sprite as reference image 1 and the style
    # plate as image 2. Each hangs off its summer validate, so the summer
    # sprite's digest is in its key: redrawing a summer state redraws its
    # season twin, and a clause edit moves the looks alone. From the props
    # scope up, like every non-baseline state. The review pairs each look
    # with its twin, the summer first.
    if rank >= 1 and package.seasons is not None:
        for season_look in package.seasons.looks:
            for prop in package.props:
                for state in prop.states:
                    summer = summer_validates.get((prop.prop_id, state))
                    if summer is None:
                        continue
                    prompt = prompts.season_look_prompt(package, prop, state, season_look)
                    params = {
                        "prop_id": prop.prop_id,
                        "state": state,
                        "look": season_look.look_id,
                    }
                    stem = f"prop-{_safe(prop.prop_id)}-{_safe(state)}-{_safe(season_look.look_id)}"
                    generate = builder.add(
                        SEASON_LOOK_GENERATE,
                        f"{stem}-generate",
                        domain="seasons",
                        description=(
                            f"Repaint {prop.prop_id} {state} in its {season_look.look_id} look"
                        ),
                        params=params,
                        depends_on=[summer],
                        input_digests=[text_digest(prompt), *style_digests],
                        card=NodeCard(prompt=prompt),
                        ports=[
                            artifact_port(
                                "image",
                                f"production/props/{prop.prop_id}-{state}.{season_look.look_id}.source.png",
                                "season-look-source-v1",
                            )
                        ],
                    )
                    validate = builder.add(
                        SEASON_LOOK_VALIDATE,
                        f"{stem}-validate",
                        domain="seasons",
                        description=(
                            f"Gate {prop.prop_id} {state} {season_look.look_id}"
                            " against its summer twin"
                        ),
                        params=params,
                        depends_on=[generate.node_id],
                        # The normalisation is part of the answer: a new
                        # version re-does every season_look off its kept source.
                        input_digests=[text_digest("season-look-normalise-v1")],
                        ports=[
                            artifact_port(
                                "image",
                                manifest_module.prop_look_ref(
                                    prop.prop_id, state, season_look.look_id
                                ),
                                "season-look-v1",
                            ),
                            artifact_port(
                                "validation",
                                f"production/validation/props/{prop.prop_id}-{state}.{season_look.look_id}.json",
                                "season-look-validation-v1",
                            ),
                        ],
                    )
                    review_subjects["seasons"].append((f"{prop.prop_id} {state}", summer))
                    review_subjects["seasons"].append(
                        (f"{prop.prop_id} {state} {season_look.look_id}", validate.node_id)
                    )
                    if summer not in review_inputs["seasons"]:
                        review_inputs["seasons"].append(summer)
                    review_inputs["seasons"].append(validate.node_id)

    for item in package.items:
        if rank < 1 and item.item_id not in minimal_items:
            continue
        prompt = prompts.item_prompt(package, item.item_id, item.prompt)
        generate = builder.add(
            ITEM_GENERATE,
            f"item-{_safe(item.item_id)}-generate",
            domain="items",
            description=f"Draw the {item.item_id} pickup",
            params={"item_id": item.item_id},
            depends_on=[lock.node_id],
            cache_depends_on=(),
            input_digests=[text_digest(prompt), *style_digests],
            card=NodeCard(prompt=prompt),
            ports=[
                artifact_port(
                    "image",
                    f"production/items/{item.item_id}.source.png",
                    "item-sprite-source-v1",
                )
            ],
        )
        builder.add(
            ITEM_VALIDATE,
            f"item-{_safe(item.item_id)}-validate",
            domain="items",
            description=f"Gate the {item.item_id} pickup",
            params={"item_id": item.item_id},
            depends_on=[generate.node_id],
            ports=[
                artifact_port("image", manifest_module.item_ref(item.item_id), "item-sprite-v1"),
                artifact_port(
                    "validation",
                    f"production/validation/items/{item.item_id}.json",
                    "item-validation-v1",
                ),
            ],
        )

    # --- the inventory icons: one lattice for every item, in every scope, so
    # the pack has a picture for whatever it holds.
    icons = package.icons
    icons_template = template_for(icons.columns, icons.rows, icons.cell_px)
    icons_template_digest = text_digest(
        templates.template_id(icons.columns, icons.rows, icons.cell_px)
    )
    icons_prompt = prompts.icon_sheet_prompt(package, icons, package.items)
    icons_port = artifact_port("image", "production/items/icons.source.png", "item-icons-source-v1")
    if icons.take is not None:
        icons_generate = builder.add(
            ICONS_ADOPT,
            "items-icons-adopt",
            domain="items",
            description="Adopt the auditioned icon sheet through the lattice gate",
            depends_on=[icons_template.node_id],
            input_digests=[
                text_digest(icons_prompt),
                text_digest(package.digests[icons.take]),
                icons_template_digest,
            ],
            card=NodeCard(
                prompt=icons_prompt,
                template_ref=templates.template_id(icons.columns, icons.rows, icons.cell_px),
            ),
            ports=[icons_port],
        )
    else:
        icons_generate = builder.add(
            ICONS_GENERATE,
            "items-icons-generate",
            domain="items",
            description=f"Paint {icons.cell_count} inventory icons into the lattice",
            depends_on=[icons_template.node_id],
            input_digests=[text_digest(icons_prompt), icons_template_digest],
            card=NodeCard(
                prompt=icons_prompt,
                template_ref=templates.template_id(icons.columns, icons.rows, icons.cell_px),
            ),
            ports=[icons_port],
        )
    icons_validate = builder.add(
        ICONS_VALIDATE,
        "items-icons-validate",
        domain="items",
        description="Recover the icon cells and refuse any glyph on a guide line",
        depends_on=[icons_generate.node_id],
        ports=[
            artifact_port("image", manifest_module.icons_ref(), "item-icons-v1"),
            artifact_port(
                "validation", "production/validation/items/icons.json", "item-icons-validation-v1"
            ),
        ],
    )
    review_subjects["props"].append(("inventory icons", icons_validate.node_id))
    review_inputs["props"].append(icons_validate.node_id)

    # --- ground
    # Every scope draws every biome. The minimal scope once drew only the base,
    # and the ground was one material edge to edge in every run anybody looked
    # at; a plate is one operation, and the biomes are the ground's variety.
    for biome in package.biomes:
        prompt = prompts.ground_prompt(package, biome)
        source_port = artifact_port(
            "image", f"production/ground/{biome.biome_id}.source.png", "ground-plate-source-v1"
        )
        if biome.take is not None:
            # An auditioned draw of this brief, adopted through the plate gate:
            # the picture plus the brief it answers are the identity, so a new
            # file or a new brief re-adopts and nothing else moves (0 ops).
            generate = builder.add(
                GROUND_ADOPT,
                f"ground-{_safe(biome.biome_id)}-adopt",
                domain="ground",
                description=f"Adopt the auditioned {biome.biome_id} plate through the gate",
                params={"biome_id": biome.biome_id},
                depends_on=[lock.node_id],
                cache_depends_on=(),
                input_digests=[
                    text_digest(prompt),
                    text_digest(package.digests[biome.take]),
                    *style_digests,
                ],
                card=NodeCard(prompt=prompt),
                ports=[source_port],
            )
        else:
            generate = builder.add(
                GROUND_GENERATE,
                f"ground-{_safe(biome.biome_id)}-generate",
                domain="ground",
                description=f"Draw the {biome.biome_id} ground plate",
                params={"biome_id": biome.biome_id},
                depends_on=[lock.node_id],
                cache_depends_on=(),
                input_digests=[text_digest(prompt), *style_digests],
                card=NodeCard(prompt=prompt),
                ports=[source_port],
            )
        canonicalize = builder.add(
            GROUND_CANONICALIZE,
            f"ground-{_safe(biome.biome_id)}-canonicalize",
            domain="ground",
            description=f"Gate {biome.biome_id} for uniformity and mirror it on both axes",
            params={"biome_id": biome.biome_id},
            depends_on=[generate.node_id],
            ports=[
                artifact_port(
                    "image", manifest_module.ground_ref(biome.biome_id), "ground-plate-v1"
                ),
                artifact_port(
                    "validation",
                    f"production/validation/ground/{biome.biome_id}.json",
                    "ground-validation-v1",
                ),
            ],
        )
        review_subjects["ground"].append((biome.biome_id, canonicalize.node_id))
        review_inputs["ground"].append(canonicalize.node_id)

    # The rest of the ground: the abstract layer, the track, and the litter.
    # All three belong to the minimal scope, because the ground verdict is
    # about the ground as it is seen, not about one plate.
    if package.macro is not None:
        prompt = prompts.macro_prompt(package.macro)
        generate = builder.add(
            MACRO_GENERATE,
            "ground-macro-generate",
            domain="ground",
            description="Draw the macro colour field, no drawing allowed",
            depends_on=[lock.node_id],
            cache_depends_on=(),
            input_digests=[text_digest(prompt)],
            card=NodeCard(prompt=prompt),
            ports=[
                artifact_port(
                    "image", "production/ground/macro.source.png", "ground-macro-source-v1"
                )
            ],
        )
        canonicalize = builder.add(
            MACRO_CANONICALIZE,
            "ground-macro-canonicalize",
            domain="ground",
            description="Gate the macro field for ink and mirror it on both axes",
            depends_on=[generate.node_id],
            ports=[
                artifact_port("image", manifest_module.macro_ref(), "ground-macro-v1"),
                artifact_port(
                    "validation",
                    "production/validation/ground/macro.json",
                    "ground-macro-validation-v1",
                ),
            ],
        )
        review_subjects["ground"].append(("macro colour field", canonicalize.node_id))
        review_inputs["ground"].append(canonicalize.node_id)

    if package.road is not None:
        road = package.road
        prompt = prompts.road_prompt(package, road)
        generate = builder.add(
            ROAD_GENERATE,
            f"ground-road-{_safe(road.road_id)}-generate",
            domain="ground",
            description=f"Draw the {road.road_id} track plate",
            params={"road_id": road.road_id},
            depends_on=[lock.node_id],
            cache_depends_on=(),
            input_digests=[text_digest(prompt), *style_digests],
            card=NodeCard(prompt=prompt),
            ports=[
                artifact_port(
                    "image",
                    f"production/ground/road-{road.road_id}.source.png",
                    "ground-road-source-v1",
                )
            ],
        )
        canonicalize = builder.add(
            ROAD_CANONICALIZE,
            f"ground-road-{_safe(road.road_id)}-canonicalize",
            domain="ground",
            description=f"Gate {road.road_id} for uniformity and mirror it on both axes",
            params={"road_id": road.road_id},
            depends_on=[generate.node_id],
            ports=[
                artifact_port("image", manifest_module.road_ref(road.road_id), "ground-road-v1"),
                artifact_port(
                    "validation",
                    f"production/validation/ground/road-{road.road_id}.json",
                    "ground-road-validation-v1",
                ),
            ],
        )
        review_subjects["ground"].append((f"{road.road_id} track", canonicalize.node_id))
        review_inputs["ground"].append(canonicalize.node_id)

    if package.water is not None:
        prompt = prompts.water_prompt(package, package.water)
        generate = builder.add(
            WATER_GENERATE,
            "ground-water-generate",
            domain="ground",
            description="Draw the water plate beyond the coast",
            depends_on=[lock.node_id],
            cache_depends_on=(),
            input_digests=[text_digest(prompt), *style_digests],
            card=NodeCard(prompt=prompt),
            ports=[
                artifact_port(
                    "image", "production/ground/water.source.png", "ground-water-source-v1"
                )
            ],
        )
        canonicalize = builder.add(
            WATER_CANONICALIZE,
            "ground-water-canonicalize",
            domain="ground",
            description="Gate the water plate and mirror it on both axes",
            depends_on=[generate.node_id],
            ports=[
                artifact_port("image", manifest_module.water_ref(), "ground-water-v1"),
                artifact_port(
                    "validation",
                    "production/validation/ground/water.json",
                    "ground-water-validation-v1",
                ),
            ],
        )
        review_subjects["ground"].append(("water", canonicalize.node_id))
        review_inputs["ground"].append(canonicalize.node_id)

    if package.clutter is not None:
        clutter = package.clutter
        template = template_for(clutter.columns, clutter.rows)
        clutter_template_digest = text_digest(templates.template_id(clutter.columns, clutter.rows))
        prompt = prompts.clutter_prompt(package, clutter)
        clutter_port = artifact_port(
            "image", "production/ground/clutter.source.png", "ground-clutter-source-v1"
        )
        if clutter.take is not None:
            generate = builder.add(
                CLUTTER_ADOPT,
                "ground-clutter-adopt",
                domain="ground",
                description="Adopt the auditioned litter sheet through the lattice gate",
                depends_on=[template.node_id],
                input_digests=[
                    text_digest(prompt),
                    text_digest(package.digests[clutter.take]),
                    clutter_template_digest,
                ],
                card=NodeCard(
                    prompt=prompt, template_ref=templates.template_id(clutter.columns, clutter.rows)
                ),
                ports=[clutter_port],
            )
        else:
            generate = builder.add(
                CLUTTER_GENERATE,
                "ground-clutter-generate",
                domain="ground",
                description=f"Paint {clutter.cell_count} litter cutouts into the lattice",
                depends_on=[template.node_id],
                input_digests=[text_digest(prompt), clutter_template_digest],
                card=NodeCard(
                    prompt=prompt, template_ref=templates.template_id(clutter.columns, clutter.rows)
                ),
                ports=[clutter_port],
            )
        validate = builder.add(
            CLUTTER_VALIDATE,
            "ground-clutter-validate",
            domain="ground",
            description="Recover the cells and refuse any piece on a guide line",
            depends_on=[generate.node_id],
            ports=[
                artifact_port("image", manifest_module.clutter_ref(), "ground-clutter-v1"),
                artifact_port(
                    "validation",
                    "production/validation/ground/clutter.json",
                    "ground-clutter-validation-v1",
                ),
            ],
        )
        review_subjects["ground"].append(("litter sheet", validate.node_id))
        review_inputs["ground"].append(validate.node_id)

    if package.forage is not None:
        # The forage: the litter's twin, one lattice of pickups lying on the
        # ground. Same template node, same gate, its own identity.
        forage = package.forage
        template = template_for(forage.columns, forage.rows)
        forage_template_digest = text_digest(templates.template_id(forage.columns, forage.rows))
        prompt = prompts.forage_prompt(package, forage)
        forage_port = artifact_port(
            "image", "production/ground/forage.source.png", "ground-forage-source-v1"
        )
        if forage.take is not None:
            generate = builder.add(
                FORAGE_ADOPT,
                "ground-forage-adopt",
                domain="ground",
                description="Adopt the auditioned forage sheet through the lattice gate",
                depends_on=[template.node_id],
                input_digests=[
                    text_digest(prompt),
                    text_digest(package.digests[forage.take]),
                    forage_template_digest,
                ],
                card=NodeCard(
                    prompt=prompt, template_ref=templates.template_id(forage.columns, forage.rows)
                ),
                ports=[forage_port],
            )
        else:
            generate = builder.add(
                FORAGE_GENERATE,
                "ground-forage-generate",
                domain="ground",
                description=f"Paint {forage.cell_count} forage pickups into the lattice",
                depends_on=[template.node_id],
                input_digests=[text_digest(prompt), forage_template_digest],
                card=NodeCard(
                    prompt=prompt, template_ref=templates.template_id(forage.columns, forage.rows)
                ),
                ports=[forage_port],
            )
        validate = builder.add(
            FORAGE_VALIDATE,
            "ground-forage-validate",
            domain="ground",
            description="Recover the forage cells and refuse any piece on a guide line",
            depends_on=[generate.node_id],
            ports=[
                artifact_port("image", manifest_module.forage_ref(), "ground-forage-v1"),
                artifact_port(
                    "validation",
                    "production/validation/ground/forage.json",
                    "ground-forage-validation-v1",
                ),
            ],
        )
        review_subjects["ground"].append(("forage sheet", validate.node_id))
        review_inputs["ground"].append(validate.node_id)

    if package.plants is not None:
        # The mid-scale: the litter's standing twin, one lattice of plants
        # scattered by the layout and stood up by the viewer. Judged on the
        # ground sheet, where the turf it stands in is. A season look
        # repaints the whole sheet at once, one op, off the summer sheet's
        # validate (its digest is in the key), and the seasons review sees
        # the pair the way it sees a prop and its twin.
        plants = package.plants
        template = template_for(plants.columns, plants.rows)
        plants_template_digest = text_digest(templates.template_id(plants.columns, plants.rows))
        prompt = prompts.plants_prompt(package, plants)
        plants_port = artifact_port(
            "image", "production/ground/plants.source.png", "ground-plants-source-v1"
        )
        if plants.take is not None:
            source = builder.add(
                PLANTS_ADOPT,
                "ground-plants-adopt",
                domain="ground",
                description="Adopt the auditioned plant sheet through the lattice gate",
                depends_on=[template.node_id],
                input_digests=[
                    text_digest(prompt),
                    text_digest(package.digests[plants.take]),
                    plants_template_digest,
                ],
                card=NodeCard(
                    prompt=prompt, template_ref=templates.template_id(plants.columns, plants.rows)
                ),
                ports=[plants_port],
            )
        else:
            source = builder.add(
                PLANTS_GENERATE,
                "ground-plants-generate",
                domain="ground",
                description=f"Paint {plants.cell_count} standing plants into the lattice",
                depends_on=[template.node_id],
                input_digests=[text_digest(prompt), plants_template_digest],
                card=NodeCard(
                    prompt=prompt, template_ref=templates.template_id(plants.columns, plants.rows)
                ),
                ports=[plants_port],
            )
        validate = builder.add(
            PLANTS_VALIDATE,
            "ground-plants-validate",
            domain="ground",
            description="Recover the plant cells and refuse any plant on a guide line",
            depends_on=[source.node_id],
            ports=[
                artifact_port("image", manifest_module.plants_ref(), "ground-plants-v1"),
                artifact_port(
                    "validation",
                    "production/validation/ground/plants.json",
                    "ground-plants-validation-v1",
                ),
            ],
        )
        review_subjects["ground"].append(("plant sheet", validate.node_id))
        review_inputs["ground"].append(validate.node_id)
        if rank >= 1 and package.seasons is not None:
            for season_look in package.seasons.looks:
                look_prompt = prompts.plants_look_prompt(package, plants, season_look)
                look_params = {"look": season_look.look_id}
                stem = f"ground-plants-{_safe(season_look.look_id)}"
                look_generate = builder.add(
                    PLANTS_LOOK_GENERATE,
                    f"{stem}-generate",
                    domain="seasons",
                    description=f"Repaint the plant sheet in its {season_look.look_id} look",
                    params=look_params,
                    depends_on=[validate.node_id],
                    input_digests=[text_digest(look_prompt), *style_digests],
                    card=NodeCard(prompt=look_prompt),
                    ports=[
                        artifact_port(
                            "image",
                            f"production/ground/plants.{season_look.look_id}.source.png",
                            "plants-look-source-v1",
                        )
                    ],
                )
                look_validate = builder.add(
                    PLANTS_LOOK_VALIDATE,
                    f"{stem}-validate",
                    domain="seasons",
                    description=f"Gate the {season_look.look_id} plant sheet on its lattice",
                    params=look_params,
                    depends_on=[look_generate.node_id],
                    ports=[
                        artifact_port(
                            "image",
                            manifest_module.plants_look_ref(season_look.look_id),
                            "plants-look-v1",
                        ),
                        artifact_port(
                            "validation",
                            f"production/validation/ground/plants.{season_look.look_id}.json",
                            "plants-look-validation-v1",
                        ),
                    ],
                )
                review_subjects["seasons"].append(("plant sheet", validate.node_id))
                review_subjects["seasons"].append(
                    (f"plant sheet {season_look.look_id}", look_validate.node_id)
                )
                if validate.node_id not in review_inputs["seasons"]:
                    review_inputs["seasons"].append(validate.node_id)
                review_inputs["seasons"].append(look_validate.node_id)

    # Decals sit in the minimal scope: the pads and the skirts are the seam
    # between billboard and ground, and the seam is the ground verdict.
    if rank >= 0:
        for decal in package.decals:
            prompt = prompts.decal_prompt(package, decal)
            generate = builder.add(
                DECAL_GENERATE,
                f"decal-{_safe(decal.decal_id)}-generate",
                domain="ground",
                description=f"Draw the {decal.decal_id} ground decal",
                params={"decal_id": decal.decal_id},
                depends_on=[lock.node_id],
                cache_depends_on=(),
                input_digests=[text_digest(prompt), *style_digests],
                card=NodeCard(prompt=prompt),
                ports=[
                    artifact_port(
                        "image",
                        f"production/ground/decals/{decal.decal_id}.source.png",
                        "ground-decal-source-v1",
                    )
                ],
            )
            validate = builder.add(
                DECAL_VALIDATE,
                f"decal-{_safe(decal.decal_id)}-validate",
                domain="ground",
                description=f"Gate the {decal.decal_id} decal for soft edges",
                params={"decal_id": decal.decal_id},
                depends_on=[generate.node_id],
                ports=[
                    artifact_port(
                        "image", manifest_module.decal_ref(decal.decal_id), "ground-decal-v1"
                    ),
                    artifact_port(
                        "validation",
                        f"production/validation/ground/decal-{decal.decal_id}.json",
                        "decal-validation-v1",
                    ),
                ],
            )
            review_subjects["ground"].append((decal.decal_id, validate.node_id))
            review_inputs["ground"].append(validate.node_id)

    # --- actors
    if rank >= 2:
        for actor in package.actors:
            concept_prompt = prompts.actor_concept_prompt(package, actor)
            concept = builder.add(
                ACTOR_CONCEPT,
                f"actor-{_safe(actor.actor_id)}-concept",
                domain="actors",
                description=f"Draw {actor.display_name}'s appearance sheet",
                params={"actor_id": actor.actor_id},
                depends_on=[lock.node_id],
                cache_depends_on=(),
                input_digests=[
                    text_digest(concept_prompt),
                    *style_digests,
                    # The authored appearance picture is part of the answer,
                    # so it is part of the identity.
                    *(
                        [text_digest(actor.appearance_reference_digest)]
                        if actor.appearance_reference_digest
                        else []
                    ),
                ],
                card=NodeCard(prompt=concept_prompt),
                ports=[
                    artifact_port(
                        "image", manifest_module.concept_ref(actor.actor_id), "actor-concept-v1"
                    )
                ],
            )
            state_validates: list[str] = []
            # A single mirrored card keeps the node ids and ports it always
            # had. A four-way actor draws one strip per facing: the front
            # first, off the concept alone, and the other three off the front
            # as well, so they match it pose for pose rather than each
            # re-inventing the action's timing.
            front_validates: dict[str, str] = {}
            ordered = sorted(actor.strips, key=lambda entry: (entry[0], entry[1] != "front"))
            for state_name, facing in ordered:
                motion = actor.state(state_name)
                key = strip_key(motion.state, facing)
                suffix = "" if facing is None else f"-{facing}"
                label = motion.state if facing is None else f"{motion.state} {facing}"
                prompt = prompts.actor_motion_prompt(package, actor, motion.state, facing=facing)
                strip_params: dict[str, str] = {"actor_id": actor.actor_id, "state": motion.state}
                if facing is not None:
                    strip_params["facing"] = facing
                upstream = [concept.node_id]
                if facing not in (None, "front"):
                    upstream.append(front_validates[motion.state])
                generate = builder.add(
                    MOTION_GENERATE,
                    f"actor-{_safe(actor.actor_id)}-state-{_safe(motion.state)}{suffix}-generate",
                    domain="actors",
                    description=f"Draw {actor.actor_id}'s {label} strip",
                    params=strip_params,
                    depends_on=upstream,
                    input_digests=[text_digest(prompt)],
                    card=NodeCard(prompt=prompt),
                    ports=[
                        artifact_port(
                            "image",
                            f"production/actors/{actor.actor_id}-{key}.source.png",
                            "motion-strip-source-v1",
                        )
                    ],
                )
                validate = builder.add(
                    MOTION_VALIDATE,
                    f"actor-{_safe(actor.actor_id)}-state-{_safe(motion.state)}{suffix}-validate",
                    domain="actors",
                    description=f"Gate and repack {actor.actor_id}'s {label} strip",
                    params=strip_params,
                    depends_on=[generate.node_id],
                    ports=[
                        artifact_port(
                            "image",
                            manifest_module.state_ref(actor.actor_id, motion.state, facing),
                            "motion-strip-v1",
                        ),
                        artifact_port(
                            "validation",
                            f"production/validation/actors/{actor.actor_id}-{key}.json",
                            "motion-validation-v1",
                        ),
                    ],
                )
                if facing == "front":
                    front_validates[motion.state] = validate.node_id
                state_validates.append(validate.node_id)
                review_subjects["actors"].append((f"{actor.actor_id} {label}", validate.node_id))
                review_inputs["actors"].append(validate.node_id)

            # Every state is a separate provider call, so nothing in the pixels
            # ties their draw scales together. The plate makes the mismatch
            # visible and the judge reads it off; the verify pass re-reads the
            # residual after the first reading is applied.
            if len(actor.strips) > 1:
                plate = builder.add(
                    REBASE_PLATE,
                    f"actor-{_safe(actor.actor_id)}-rebase-plate",
                    domain="actors",
                    description=f"Composite every {actor.actor_id} state at one source scale",
                    params={"actor_id": actor.actor_id},
                    depends_on=state_validates,
                    ports=[
                        artifact_port(
                            "plate",
                            f"production/rebase/{actor.actor_id}-first-pass.png",
                            "rebase-plate-v1",
                        )
                    ],
                )
                judge = builder.add(
                    REBASE_JUDGE,
                    f"actor-{_safe(actor.actor_id)}-rebase-judge",
                    domain="actors",
                    description=f"Read {actor.actor_id}'s per-state scale multipliers",
                    params={"actor_id": actor.actor_id},
                    depends_on=[plate.node_id],
                    ports=[
                        artifact_port(
                            "reading",
                            f"production/rebase/{actor.actor_id}-first-pass.json",
                            "rebase-reading-v1",
                        )
                    ],
                )
                verify_plate = builder.add(
                    REBASE_VERIFY_PLATE,
                    f"actor-{_safe(actor.actor_id)}-rebase-verify-plate",
                    domain="actors",
                    description=f"Re-composite {actor.actor_id} with the first reading applied",
                    params={"actor_id": actor.actor_id},
                    depends_on=[judge.node_id],
                    ports=[
                        artifact_port(
                            "plate",
                            f"production/rebase/{actor.actor_id}-verify.png",
                            "rebase-plate-v1",
                        )
                    ],
                )
                builder.add(
                    REBASE_VERIFY,
                    f"actor-{_safe(actor.actor_id)}-rebase-verify",
                    domain="actors",
                    description=f"Read the residual and publish {actor.actor_id}'s rebase record",
                    params={"actor_id": actor.actor_id},
                    depends_on=[verify_plate.node_id],
                    ports=[
                        artifact_port(
                            "rebase",
                            manifest_module.rebase_ref(actor.actor_id),
                            "rebase-reading-v1",
                        )
                    ],
                )

    # --- effects
    if rank >= 3:
        fire_prompt = prompts.fire_strip_prompt(package, fire.columns, fire.rows)
        template = template_for(fire.columns, fire.rows)
        template_digest = text_digest(templates.template_id(fire.columns, fire.rows))
        fire_generate = builder.add(
            FIRE_GENERATE,
            "fx-fire-generate",
            domain="fx",
            description=f"Paint a {fire.frames}-frame flame cycle into the lattice",
            depends_on=[template.node_id],
            input_digests=[text_digest(fire_prompt), template_digest],
            card=NodeCard(
                prompt=fire_prompt, template_ref=templates.template_id(fire.columns, fire.rows)
            ),
            ports=[artifact_port("image", "production/fx/fire.source.png", "fx-strip-source-v1")],
        )
        fire_validate = builder.add(
            FIRE_VALIDATE,
            "fx-fire-validate",
            domain="fx",
            description="Recover the cells and measure whether the cycle closes",
            depends_on=[fire_generate.node_id],
            ports=[
                artifact_port("image", manifest_module.fire_ref(), "fx-strip-v1"),
                artifact_port(
                    "validation", "production/validation/fx-fire.json", "fx-strip-validation-v1"
                ),
            ],
        )
        dust_prompt = prompts.dust_prompt(package)
        dust_generate = builder.add(
            DUST_GENERATE,
            "fx-dust-generate",
            domain="fx",
            description="Draw the four impact puffs on one sheet",
            depends_on=[lock.node_id],
            cache_depends_on=(),
            input_digests=[text_digest(dust_prompt), *style_digests],
            card=NodeCard(prompt=dust_prompt),
            ports=[artifact_port("image", "production/fx/dust.source.png", "fx-dust-source-v1")],
        )
        dust_validate = builder.add(
            DUST_VALIDATE,
            "fx-dust-validate",
            domain="fx",
            description="Check the four puffs came back separable",
            depends_on=[dust_generate.node_id],
            ports=[
                artifact_port("image", manifest_module.dust_ref(), "fx-dust-atlas-v1"),
                artifact_port(
                    "validation", "production/validation/fx-dust.json", "fx-dust-validation-v1"
                ),
            ],
        )
        review_subjects["fx"].extend(
            [("fire strip", fire_validate.node_id), ("dust sheet", dust_validate.node_id)]
        )
        review_inputs["fx"].extend([fire_validate.node_id, dust_validate.node_id])

    # --- music
    # Two loops, one per clock cue. They hang off the lock like the dust sheet
    # and digest only their own prompt, so a re-brief of the night theme never
    # re-bills the day theme, and no picture re-bills either. A track with an
    # auditioned take is adopted locally through the same gate instead: the
    # route has no seed, and a re-draw of a brief the user already picked by
    # ear is a different song.
    if rank >= 3:
        for track in package.music:
            music_prompt = prompts.music_prompt(track)
            source_port = artifact_port(
                "audio", f"production/music/{track.track_id}.source.mp3", "music-track-source-v1"
            )
            if track.take is not None:
                music_generate = builder.add(
                    MUSIC_ADOPT,
                    f"music-{_safe(track.track_id)}-adopt",
                    domain="music",
                    description=f"Adopt the auditioned {track.cue} take, chosen by ear",
                    params={"track_id": track.track_id, "cue": track.cue},
                    depends_on=[lock.node_id],
                    cache_depends_on=(),
                    input_digests=[
                        text_digest(music_prompt),
                        text_digest(package.digests[track.take]),
                    ],
                    card=NodeCard(prompt=music_prompt),
                    ports=[source_port],
                )
            else:
                music_generate = builder.add(
                    MUSIC_GENERATE,
                    f"music-{_safe(track.track_id)}-generate",
                    domain="music",
                    description=(
                        f"Compose the {track.cue} loop, about {track.target_duration_seconds:.0f} s"
                    ),
                    params={"track_id": track.track_id, "cue": track.cue},
                    depends_on=[lock.node_id],
                    cache_depends_on=(),
                    input_digests=[
                        text_digest(music_prompt),
                        text_digest(
                            json.dumps({"target_duration_seconds": track.target_duration_seconds})
                        ),
                    ],
                    card=NodeCard(prompt=music_prompt),
                    ports=[source_port],
                )
            builder.add(
                MUSIC_VALIDATE,
                f"music-{_safe(track.track_id)}-validate",
                domain="music",
                description="Measure the loop's length and peak, then publish it",
                params={"track_id": track.track_id, "cue": track.cue},
                depends_on=[music_generate.node_id],
                ports=[
                    artifact_port(
                        "audio", manifest_module.music_ref(track.track_id), "music-track-v1"
                    ),
                    artifact_port(
                        "validation",
                        f"production/validation/music-{track.track_id}.json",
                        "music-track-validation-v1",
                    ),
                ],
            )

    # --- weather
    # A condition of the world, not a moment on the screen (weather.toml's
    # header). Each layer is one node pair hanging off the lock and digesting
    # only its own brief, so re-briefing the bolts never re-bills the drops,
    # and no prop or ground plate re-bills for any of it. The wet layer is an
    # ordinary decal, drawn in the ground family in every scope; the pictures
    # and sounds here are full-scope, like the flame strip and the music.
    if rank >= 3:
        for condition in package.weather:
            cid = _safe(condition.condition_id)
            params = {"condition_id": condition.condition_id}
            if condition.drops is not None:
                drops_prompt = prompts.drops_sheet_prompt(package, condition.drops)
                drops_generate = builder.add(
                    WEATHER_DROPS_GENERATE,
                    f"weather-{cid}-drops-generate",
                    domain="weather",
                    description=f"Draw the {condition.condition_id} streak and drop on one sheet",
                    params=params,
                    depends_on=[lock.node_id],
                    cache_depends_on=(),
                    input_digests=[text_digest(drops_prompt)],
                    card=NodeCard(prompt=drops_prompt),
                    ports=[
                        artifact_port(
                            "image",
                            f"production/weather/{condition.condition_id}-drops.source.png",
                            "weather-drops-source-v1",
                        )
                    ],
                )
                drops_validate = builder.add(
                    WEATHER_DROPS_VALIDATE,
                    f"weather-{cid}-drops-validate",
                    domain="weather",
                    description="Check the streak and the drop came back in their halves; publish",
                    params=params,
                    depends_on=[drops_generate.node_id],
                    ports=[
                        artifact_port(
                            "image",
                            manifest_module.weather_ref(condition.condition_id, "drops"),
                            "weather-drops-v1",
                        ),
                        artifact_port(
                            "validation",
                            f"production/validation/weather-{condition.condition_id}-drops.json",
                            "weather-drops-validation-v1",
                        ),
                    ],
                )
                review_subjects["fx"].append(
                    (f"{condition.condition_id} drops sheet", drops_validate.node_id)
                )
                review_inputs["fx"].append(drops_validate.node_id)
            if condition.cover is not None:
                # A ground plate for the condition, on the ground plate route
                # with a pale band; the ground shader lays it over every biome
                # by coverage through the same torn erosion a biome edge gets.
                cover_prompt = prompts.cover_prompt(package, condition.cover)
                cover_generate = builder.add(
                    WEATHER_COVER_GENERATE,
                    f"weather-{cid}-cover-generate",
                    domain="weather",
                    description=f"Draw the {condition.condition_id} cover plate",
                    params=params,
                    depends_on=[lock.node_id],
                    cache_depends_on=(),
                    input_digests=[text_digest(cover_prompt), *style_digests],
                    card=NodeCard(prompt=cover_prompt),
                    ports=[
                        artifact_port(
                            "image",
                            f"production/weather/{condition.condition_id}-cover.source.png",
                            "weather-cover-source-v1",
                        )
                    ],
                )
                cover_canonicalize = builder.add(
                    WEATHER_COVER_CANONICALIZE,
                    f"weather-{cid}-cover-canonicalize",
                    domain="weather",
                    description="Gate the cover plate for uniformity and mirror it on both axes",
                    params=params,
                    depends_on=[cover_generate.node_id],
                    ports=[
                        artifact_port(
                            "image",
                            manifest_module.weather_ref(condition.condition_id, "cover"),
                            "weather-cover-v1",
                        ),
                        artifact_port(
                            "validation",
                            f"production/validation/weather-{condition.condition_id}-cover.json",
                            "weather-cover-validation-v1",
                        ),
                    ],
                )
                review_subjects["ground"].append(
                    (f"{condition.condition_id} cover plate", cover_canonicalize.node_id)
                )
                review_inputs["ground"].append(cover_canonicalize.node_id)
            if condition.ice is not None:
                # The water frozen: a plate on the water route with the
                # cover's pale band; the water shader mixes it in by the
                # condition's factor. Judged with the ground's plates.
                ice_prompt = prompts.ice_prompt(package, condition.ice)
                ice_port = artifact_port(
                    "image",
                    f"production/weather/{condition.condition_id}-ice.source.png",
                    "weather-ice-source-v1",
                )
                if condition.ice.take is not None:
                    ice_generate = builder.add(
                        WEATHER_ICE_ADOPT,
                        f"weather-{cid}-ice-adopt",
                        domain="weather",
                        description=(
                            f"Adopt the auditioned {condition.condition_id}"
                            " ice plate through the gate"
                        ),
                        params=params,
                        depends_on=[lock.node_id],
                        cache_depends_on=(),
                        input_digests=[
                            text_digest(ice_prompt),
                            text_digest(package.digests[condition.ice.take]),
                            *style_digests,
                        ],
                        card=NodeCard(prompt=ice_prompt),
                        ports=[ice_port],
                    )
                else:
                    ice_generate = builder.add(
                        WEATHER_ICE_GENERATE,
                        f"weather-{cid}-ice-generate",
                        domain="weather",
                        description=f"Draw the {condition.condition_id} ice plate",
                        params=params,
                        depends_on=[lock.node_id],
                        cache_depends_on=(),
                        input_digests=[text_digest(ice_prompt), *style_digests],
                        card=NodeCard(prompt=ice_prompt),
                        ports=[ice_port],
                    )
                ice_canonicalize = builder.add(
                    WEATHER_ICE_CANONICALIZE,
                    f"weather-{cid}-ice-canonicalize",
                    domain="weather",
                    description="Gate the ice plate for uniformity and mirror it on both axes",
                    params=params,
                    depends_on=[ice_generate.node_id],
                    ports=[
                        artifact_port(
                            "image",
                            manifest_module.weather_ref(condition.condition_id, "ice"),
                            "weather-ice-v1",
                        ),
                        artifact_port(
                            "validation",
                            f"production/validation/weather-{condition.condition_id}-ice.json",
                            "weather-ice-validation-v1",
                        ),
                    ],
                )
                # A plate is judged with the plates: the ground review asks
                # the material question, the seasons review asks a sprite's.
                review_subjects["ground"].append(
                    (f"{condition.condition_id} ice plate", ice_canonicalize.node_id)
                )
                review_inputs["ground"].append(ice_canonicalize.node_id)
            if condition.ground is not None:
                splash_prompt = prompts.splash_sheet_prompt(package, condition.ground)
                ground_generate = builder.add(
                    WEATHER_GROUND_GENERATE,
                    f"weather-{cid}-ground-generate",
                    domain="weather",
                    description=f"Draw the four {condition.condition_id} splashes on one sheet",
                    params=params,
                    depends_on=[lock.node_id],
                    cache_depends_on=(),
                    input_digests=[text_digest(splash_prompt), *style_digests],
                    card=NodeCard(prompt=splash_prompt),
                    ports=[
                        artifact_port(
                            "image",
                            f"production/weather/{condition.condition_id}-ground.source.png",
                            "weather-ground-source-v1",
                        )
                    ],
                )
                ground_validate = builder.add(
                    WEATHER_GROUND_VALIDATE,
                    f"weather-{cid}-ground-validate",
                    domain="weather",
                    description="Check the four splashes came back separable; publish",
                    params=params,
                    depends_on=[ground_generate.node_id],
                    ports=[
                        artifact_port(
                            "image",
                            manifest_module.weather_ref(condition.condition_id, "ground"),
                            "weather-ground-v1",
                        ),
                        artifact_port(
                            "validation",
                            f"production/validation/weather-{condition.condition_id}-ground.json",
                            "weather-ground-validation-v1",
                        ),
                    ],
                )
                review_subjects["fx"].append(
                    (f"{condition.condition_id} splash sheet", ground_validate.node_id)
                )
                review_inputs["fx"].append(ground_validate.node_id)
            if condition.strike is not None:
                bolt_prompt = prompts.strike_sheet_prompt(package, condition.strike)
                strike_generate = builder.add(
                    WEATHER_STRIKE_GENERATE,
                    f"weather-{cid}-strike-generate",
                    domain="weather",
                    description="Draw four lightning bolts on one sheet",
                    params=params,
                    depends_on=[lock.node_id],
                    cache_depends_on=(),
                    input_digests=[text_digest(bolt_prompt), *style_digests],
                    card=NodeCard(prompt=bolt_prompt),
                    ports=[
                        artifact_port(
                            "image",
                            f"production/weather/{condition.condition_id}-strike.source.png",
                            "weather-strike-source-v1",
                        )
                    ],
                )
                strike_validate = builder.add(
                    WEATHER_STRIKE_VALIDATE,
                    f"weather-{cid}-strike-validate",
                    domain="weather",
                    description="Check the four bolts are separable and tall; publish",
                    params=params,
                    depends_on=[strike_generate.node_id],
                    ports=[
                        artifact_port(
                            "image",
                            manifest_module.weather_ref(condition.condition_id, "strike"),
                            "weather-strike-v1",
                        ),
                        artifact_port(
                            "validation",
                            f"production/validation/weather-{condition.condition_id}-strike.json",
                            "weather-strike-validation-v1",
                        ),
                    ],
                )
                review_subjects["fx"].append(
                    (f"{condition.condition_id} bolt sheet", strike_validate.node_id)
                )
                review_inputs["fx"].append(strike_validate.node_id)
            for name, cue in condition.sound_cues:
                sound_generate = builder.add(
                    WEATHER_SOUND_GENERATE,
                    f"weather-{cid}-sound-{_safe(name)}-generate",
                    domain="weather",
                    description=f"Generate the {condition.condition_id} {name} clip",
                    params={**params, "cue": name},
                    depends_on=[lock.node_id],
                    cache_depends_on=(),
                    # The brief verbatim, its exact length and whether it loops:
                    # all three change the answer, so all three are identity.
                    input_digests=[
                        text_digest(cue.prompt),
                        text_digest(
                            json.dumps({"duration_seconds": cue.duration_seconds, "loop": cue.loop})
                        ),
                    ],
                    card=NodeCard(prompt=cue.prompt),
                    ports=[
                        artifact_port(
                            "audio",
                            f"production/weather/{condition.condition_id}-sound-{name}.source.mp3",
                            "weather-sound-source-v1",
                        )
                    ],
                )
                builder.add(
                    WEATHER_SOUND_VALIDATE,
                    f"weather-{cid}-sound-{_safe(name)}-validate",
                    domain="weather",
                    description="Record the clip's length and peak; publish",
                    params={**params, "cue": name},
                    depends_on=[sound_generate.node_id],
                    ports=[
                        artifact_port(
                            "audio",
                            manifest_module.weather_ref(
                                condition.condition_id, f"sound-{name}", "mp3"
                            ),
                            "weather-sound-v1",
                        ),
                        artifact_port(
                            "validation",
                            f"production/validation/weather-{condition.condition_id}-sound-{name}.json",
                            "weather-sound-validation-v1",
                        ),
                    ],
                )

    # --- sound effects
    # One clip per thing the player does (sounds.toml). Each hangs off the
    # lock and digests only its own brief, its exact length and whether it
    # loops, so re-briefing the chop never re-bills the footstep and no
    # picture re-bills any of them; gain and pitch_jitter are mixing and are
    # digested by nothing. An auditioned take is adopted locally through the
    # same clip gate, as a music take is: the route has no seed.
    if rank >= 3:
        for clip in package.sounds:
            clip_cue = clip.cue
            source_port = artifact_port(
                "audio", f"production/sounds/{clip_cue}.source.mp3", "sound-effect-source-v1"
            )
            if clip.take is not None:
                sound_generate = builder.add(
                    SOUND_ADOPT,
                    f"sound-{_safe(clip_cue)}-adopt",
                    domain="sounds",
                    description=f"Adopt the auditioned {clip_cue} clip, chosen by ear",
                    params={"cue": clip_cue},
                    depends_on=[lock.node_id],
                    cache_depends_on=(),
                    # The gate reads the length and the loop flag, so they are
                    # identity for an adopted file as much as for a drawn one.
                    input_digests=[
                        text_digest(clip.prompt),
                        text_digest(package.digests[clip.take]),
                        text_digest(
                            json.dumps(
                                {"duration_seconds": clip.duration_seconds, "loop": clip.loop}
                            )
                        ),
                    ],
                    card=NodeCard(prompt=clip.prompt),
                    ports=[source_port],
                )
            else:
                sound_generate = builder.add(
                    SOUND_GENERATE,
                    f"sound-{_safe(clip_cue)}-generate",
                    domain="sounds",
                    description=f"Generate the {clip_cue} clip, {clip.duration_seconds:.1f} s",
                    params={"cue": clip_cue},
                    depends_on=[lock.node_id],
                    cache_depends_on=(),
                    input_digests=[
                        text_digest(clip.prompt),
                        text_digest(
                            json.dumps(
                                {"duration_seconds": clip.duration_seconds, "loop": clip.loop}
                            )
                        ),
                    ],
                    card=NodeCard(prompt=clip.prompt),
                    ports=[source_port],
                )
            builder.add(
                SOUND_VALIDATE,
                f"sound-{_safe(clip_cue)}-validate",
                domain="sounds",
                description="Record the clip's length and peak; publish",
                params={"cue": clip_cue},
                depends_on=[sound_generate.node_id],
                ports=[
                    artifact_port("audio", manifest_module.sound_ref(clip_cue), "sound-effect-v1"),
                    artifact_port(
                        "validation",
                        f"production/validation/sound-{clip_cue}.json",
                        "sound-effect-validation-v1",
                    ),
                ],
            )

    # --- reviews
    review_minimum = {"props": 1, "ground": 1, "actors": 2, "fx": 3, "seasons": 1}
    for family in REVIEW_FAMILIES:
        if rank < review_minimum[family] or not review_inputs[family]:
            continue
        subjects = [label for label, _ in review_subjects[family]]
        review_sheet = builder.add(
            REVIEW_SHEET,
            f"review-{family}-sheet",
            domain="review",
            description=f"Lay out every {family} asset on one labelled contact sheet",
            params={"family": family},
            depends_on=review_inputs[family],
            ports=[
                artifact_port(
                    "sheet",
                    f"production/review/{family}-contact-sheet.png",
                    "contact-sheet-v1",
                )
            ],
        )
        judge_prompt = prompts.family_review_prompt(family, subjects, package.ground_contact)
        builder.add(
            REVIEW_JUDGE,
            f"review-{family}-judge",
            domain="review",
            description=f"Judge the {family} set for pitch, style and clean cutouts",
            params={"family": family},
            depends_on=[review_sheet.node_id],
            input_digests=[text_digest(judge_prompt)],
            card=NodeCard(prompt=judge_prompt, schema_name="FamilyReview"),
            ports=[
                artifact_port("review", manifest_module.review_ref(family), "review-verdict-v1")
            ],
        )

    # --- close
    # The layout reads authored dimensions and the world seed, never a generated
    # pixel, so its only honest dependency is the source lock. Hanging it off the
    # sprites would make its cache key grow with the scope and cost a redraw of
    # an identical world every time the ladder widens.
    builder.add(
        WORLD_LAYOUT,
        "world-layout",
        domain="world",
        description="Lay the world: site the set pieces, place the population, paint the plates",
        depends_on=[lock.node_id],
        cache_depends_on=(),
        input_digests=[
            text_digest(
                json.dumps(
                    {
                        # Everything the layout reads. The seam policy and the
                        # decals were missing once, and a run reused a layout
                        # with no skirts under a package that asked for them.
                        "world": asdict(package.world),
                        "ground_contact": package.ground_contact,
                        "look": asdict(package.look),
                        "decals": [asdict(decal) for decal in package.decals],
                        "props": [
                            (
                                prop.prop_id,
                                prop.footprint_radius_units,
                                prop.shadow_width_units,
                                asdict(prop.placement) if prop.placement is not None else None,
                                prop.canopy_radius_meters,
                                prop.baseline_state,
                                asdict(prop.variants) if prop.variants is not None else None,
                            )
                            for prop in package.props
                        ],
                        "mob": (
                            package.mob.actor_id,
                            package.mob.footprint_radius_units,
                            package.mob.shadow_width_units,
                            asdict(package.mob.placement)
                            if package.mob.placement is not None
                            else None,
                        ),
                        "biomes": [(biome.biome_id, biome.share) for biome in package.biomes],
                        "road": asdict(package.road) if package.road is not None else None,
                        # Only what the layout reads of a sheet: its lattice, its
                        # placement and its cells; the drawing direction and the
                        # take are the sheet's own.
                        "sheets": {
                            name: (
                                {
                                    "columns": sheet.columns,
                                    "rows": sheet.rows,
                                    "cell_meters": sheet.cell_meters,
                                    "placement": asdict(sheet.placement),
                                    "cells": [asdict(cell) for cell in sheet.cells],
                                }
                                if sheet is not None
                                else None
                            )
                            for name, sheet in (
                                ("clutter", package.clutter),
                                ("forage", package.forage),
                                ("plants", package.plants),
                            )
                        },
                        # The generator's own version: its rules are code, and a
                        # world laid by an earlier one is a different world.
                        "generator": "worldgen-1",
                        # The wet layer scatters puddles at generation; its
                        # density and decal are the layout's business.
                        "wet": [
                            (condition.condition_id, asdict(condition.wet))
                            for condition in package.weather
                            if condition.wet is not None
                        ],
                    },
                    sort_keys=True,
                    default=str,
                )
            )
        ],
        ports=[
            artifact_port("layout", manifest_module.layout_ref(), "world-layout-v2"),
            artifact_port("splat", manifest_module.splat_ref(), "world-splat-v2"),
            artifact_port("biome_splat", manifest_module.biome_splat_ref(), "world-biome-splat-v1"),
        ],
    )
    terminal = builder.add(
        PACKAGE_MANIFEST,
        "package-manifest",
        domain="package",
        description="Measure every published asset and write the runtime manifest",
        depends_on=[node.node_id for node in builder.nodes],
        ports=[artifact_port("manifest", "manifest.json", "oblique-survival-manifest-v1")],
    )

    return ObliqueSurvivalGraph.seal(
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id=terminal.node_id,
        package_id=package.package_id,
        scope=scope,
        presentation_profile=PRESENTATION_PROFILE,
        source_digest=source_digest,
        publication_authorized=False,
    )


__all__ = [
    "MANIFEST_REF",
    "OBLIQUE_SURVIVAL_ATTEMPT_LEDGER_KIND",
    "OBLIQUE_SURVIVAL_CACHE_NAMESPACE",
    "OBLIQUE_SURVIVAL_CACHE_RECORD_KIND",
    "OBLIQUE_SURVIVAL_GRAPH_SCHEMA_VERSION",
    "REJECTS_ROOT",
    "SOURCE_LOCK_REF",
    "AnchorPlacement",
    "FamilyReview",
    "ObliqueSurvivalGraph",
    "ReviewFinding",
    "build_graph",
    "evaluate_review",
    "oblique_survival_graph_profile",
]

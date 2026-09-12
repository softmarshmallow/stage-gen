"""Repository fixture projections owned by the legacy demos."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from gnode import Graph
from stage_gen.model_policy_maintenance import ModelPolicySnapshotV1, build_model_policy_snapshot


def load_active_model_policy_snapshot() -> ModelPolicySnapshotV1:
    """Read the historical fixture census packaged with the optional demo builder."""
    resource = files("stage_gen_legacy").joinpath("model_policy_snapshot.json")
    return ModelPolicySnapshotV1.model_validate_json(resource.read_text(encoding="utf-8"))


def build_repository_model_policy_projection(
    repository_root: Path,
    *,
    image_provider: str,
    recipe_id: str | None = None,
) -> ModelPolicySnapshotV1:
    """Plan canonical recipes under one explicit provider policy, offline."""

    from stage_gen.config import StageGenConfig
    from stage_gen.image_product import ImageProvider
    from stage_gen.model_routes import IMAGE_ROUTE_CATALOG, image_workload_policies
    from stage_gen.recipes.storefront.storefront_executor import StorefrontExecutor
    from stage_gen.recipes.universe.universe_graph import (
        build_universe_gallery_graph,
        build_universe_semantic_graph,
        universe_graph_profile,
    )
    from stage_gen.recipes.universe.universe_request import (
        admitted_universe_from_document,
        read_universe_document,
        resolve_sample_ledger,
        resolve_universe_source,
    )
    from stage_gen_legacy.recipes.dialogue_scene.scene_executor import DialogueSceneExecutor
    from stage_gen_legacy.recipes.oblique_survival.survival_executor import ObliqueSurvivalExecutor
    from stage_gen_legacy.recipes.pointclick_room.room_executor import PointClickRoomExecutor
    from stage_gen_legacy.recipes.sideview_platformer.package_executor import (
        PreparedPackageExecutor,
    )
    from stage_gen_legacy.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor

    root = repository_root.resolve()
    if not (root / "pyproject.toml").is_file():
        raise ValueError("model-policy provider projection requires a source checkout")
    provider = ImageProvider(image_provider)
    config = StageGenConfig(image_provider_override=provider)
    fixture_by_recipe = {
        "dialogue_scene": "godot/legacy/inputs/larkfield",
        "oblique_survival": "godot/legacy/inputs/ember-hollow",
        "pointclick_room": "godot/legacy/inputs/clockmakers_attic",
        "sideview_platformer": "godot/legacy/inputs/bellweather",
        "sideview_runner": "godot/legacy/inputs/iron-petal-unit",
        "storefront": "godot/legacy/inputs/ember-hollow",
        "universe_gallery": "src/stage_gen/recipes/universe/examples/lantern_ferry",
        "universe_semantic": "src/stage_gen/recipes/universe/examples/lantern_ferry",
    }
    available = tuple(sorted(fixture_by_recipe))
    if recipe_id is not None and recipe_id not in fixture_by_recipe:
        raise ValueError(
            f"unknown model-policy recipe {recipe_id!r}; available: {', '.join(available)}"
        )
    selected = set(available if recipe_id is None else (recipe_id,))
    graphs: dict[str, Graph] = {}
    if "dialogue_scene" in selected:
        graphs["dialogue_scene"] = (
            DialogueSceneExecutor(config).plan(root / fixture_by_recipe["dialogue_scene"]).graph
        )
    if "oblique_survival" in selected:
        graphs["oblique_survival"] = (
            ObliqueSurvivalExecutor(config)
            .plan(root / fixture_by_recipe["oblique_survival"], "full")
            .graph
        )
    if "pointclick_room" in selected:
        graphs["pointclick_room"] = (
            PointClickRoomExecutor(config).plan(root / fixture_by_recipe["pointclick_room"]).graph
        )
    if "sideview_platformer" in selected:
        graphs["sideview_platformer"] = (
            PreparedPackageExecutor(config)
            .plan(root / fixture_by_recipe["sideview_platformer"])
            .graph
        )
    if "sideview_runner" in selected:
        graphs["sideview_runner"] = (
            SideviewRunnerExecutor(config).plan(root / fixture_by_recipe["sideview_runner"]).graph
        )
    if "storefront" in selected:
        graphs["storefront"] = (
            StorefrontExecutor(config).plan(root / fixture_by_recipe["storefront"]).graph
        )
    if selected & {"universe_gallery", "universe_semantic"}:
        universe_root = root / fixture_by_recipe["universe_gallery"]
        universe = resolve_universe_source(
            read_universe_document(universe_root),
            root=universe_root,
        )
        if "universe_semantic" in selected:
            graphs["universe_semantic"] = build_universe_semantic_graph(
                universe,
                profile=universe_graph_profile(config, images=False),
            )
        if "universe_gallery" in selected:
            admitted = admitted_universe_from_document(
                root / "tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json",
                poster_sha256=universe.poster_sha256,
            )
            samples = resolve_sample_ledger(
                universe_id=admitted.universe_id,
                entity_ids=admitted.entity_ids(),
            )
            graphs["universe_gallery"] = build_universe_gallery_graph(
                universe,
                admitted,
                samples=samples,
                profile=universe_graph_profile(config, images=True),
                config=config,
            )
    policy_selections = {
        "default": image_workload_policies(),
        **{candidate.value: image_workload_policies(candidate) for candidate in ImageProvider},
    }
    return build_model_policy_snapshot(
        catalog=IMAGE_ROUTE_CATALOG,
        policy_selections=policy_selections,
        recipes=tuple(
            (recipe_id, fixture_by_recipe[recipe_id], graph) for recipe_id, graph in graphs.items()
        ),
    )

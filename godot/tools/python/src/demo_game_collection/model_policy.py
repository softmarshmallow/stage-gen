"""Repository fixture projections owned by the maintained game collection."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from gnode import Graph
from stage_gen.model_policy_maintenance import ModelPolicySnapshotV1, build_model_policy_snapshot


def load_active_model_policy_snapshot() -> ModelPolicySnapshotV1:
    """Read the historical fixture census packaged with the optional demo builder."""
    resource = files("demo_game_collection").joinpath("model_policy_snapshot.json")
    return ModelPolicySnapshotV1.model_validate_json(resource.read_text(encoding="utf-8"))


def build_repository_model_policy_projection(
    repository_root: Path,
    *,
    image_provider: str,
    recipe_id: str | None = None,
) -> ModelPolicySnapshotV1:
    """Plan canonical recipes under one explicit provider policy, offline."""

    from ember_hollow_pipeline.survival_executor import ObliqueSurvivalExecutor
    from stage_gen.config import StageGenConfig
    from stage_gen.image_product import ImageProvider
    from stage_gen.model_routes import IMAGE_ROUTE_CATALOG, image_workload_policies

    root = repository_root.resolve()
    if not (root / "pyproject.toml").is_file():
        raise ValueError("model-policy provider projection requires a source checkout")
    provider = ImageProvider(image_provider)
    config = StageGenConfig(image_provider_override=provider)
    fixture_by_recipe = {
        "oblique_survival": "godot/games/ember_hollow/inputs",
    }
    available = tuple(sorted(fixture_by_recipe))
    if recipe_id is not None and recipe_id not in fixture_by_recipe:
        raise ValueError(
            f"unknown model-policy recipe {recipe_id!r}; available: {', '.join(available)}"
        )
    selected = set(available if recipe_id is None else (recipe_id,))
    graphs: dict[str, Graph] = {}
    if "oblique_survival" in selected:
        graphs["oblique_survival"] = (
            ObliqueSurvivalExecutor(config)
            .plan(root / fixture_by_recipe["oblique_survival"], "full")
            .graph
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

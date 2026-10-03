"""Repository fixture projections owned by the maintained game collection."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

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
    """Project the route catalog under one explicit provider policy, offline.

    Every game now builds with gnode and declares its routes in its own ``gnode.yaml``, so
    no recipe graph is planned here: the census is the catalog and its policies.
    """

    from stage_gen.image_product import ImageProvider
    from stage_gen.model_routes import IMAGE_ROUTE_CATALOG, image_workload_policies

    root = repository_root.resolve()
    if not (root / "pyproject.toml").is_file():
        raise ValueError("model-policy provider projection requires a source checkout")
    ImageProvider(image_provider)
    if recipe_id is not None:
        raise ValueError(
            f"unknown model-policy recipe {recipe_id!r}: every game builds with gnode now, "
            "and its routes are in its own gnode.yaml"
        )
    policy_selections = {
        "default": image_workload_policies(),
        **{candidate.value: image_workload_policies(candidate) for candidate in ImageProvider},
    }
    return build_model_policy_snapshot(
        catalog=IMAGE_ROUTE_CATALOG, policy_selections=policy_selections, recipes=()
    )

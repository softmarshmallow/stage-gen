from __future__ import annotations

from pathlib import Path

from stage_gen.recipes.dialogue_scene.identity import (
    RECIPE_VERSION,
    canonical_sha256,
    run_identity,
    stage_identity,
)
from stage_gen.recipes.dialogue_scene.scene_request import read_scene_document

from .package import write_scene_package


def test_run_identity_binds_the_recipe_version_to_the_authored_document(
    tmp_path: Path,
) -> None:
    document = read_scene_document(write_scene_package(tmp_path / "pkg"))
    expected = canonical_sha256({"recipe_version": RECIPE_VERSION, "request": document})
    assert run_identity(document) == f"dialogue-{expected[:24]}"

    # Two documents that differ anywhere are two runs.
    other = {**document, "scene_brief": "A different evening entirely"}
    assert run_identity(other) != run_identity(document)


def test_stage_identity_moves_with_the_recipe_version() -> None:
    def identity(recipe_version: int) -> str:
        return stage_identity(
            run_id="scene",
            stage="prepare",
            dependencies={},
            generation=0,
            recipe_version=recipe_version,
        )

    assert identity(RECIPE_VERSION) == stage_identity(
        run_id="scene", stage="prepare", dependencies={}, generation=0
    )
    assert identity(RECIPE_VERSION) != identity(RECIPE_VERSION - 1)

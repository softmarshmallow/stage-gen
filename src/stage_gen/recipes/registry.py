"""Recipe registry."""

from __future__ import annotations

from collections.abc import Mapping

from stage_gen.recipes.base import JsonObject, Recipe
from stage_gen.recipes.dialogue_scene.recipe import dialogue_scene_recipe
from stage_gen.recipes.scrolling_preview.recipe import scrolling_preview_recipe

_RECIPES: dict[str, Recipe] = {
    scrolling_preview_recipe.id: scrolling_preview_recipe,
    dialogue_scene_recipe.id: dialogue_scene_recipe,
}


def list_recipes() -> list[dict[str, str]]:
    return [{"id": recipe.id, "description": recipe.description} for recipe in _RECIPES.values()]


def get_recipe(recipe_id: str) -> Recipe:
    try:
        return _RECIPES[recipe_id]
    except KeyError as error:
        raise ValueError(f"unknown recipe: {recipe_id}") from error


async def run_recipe_action(
    recipe_id: str, action_name: str, input_value: Mapping[str, object]
) -> JsonObject:
    """Dispatch an offline recipe-owned action without exposing recipe internals."""

    recipe = get_recipe(recipe_id)
    try:
        action = recipe.actions[action_name]
    except KeyError as error:
        raise ValueError(f"recipe {recipe_id} does not support action: {action_name}") from error
    return await action(input_value)

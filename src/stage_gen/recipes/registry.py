"""Recipe registry."""

from __future__ import annotations

from stage_gen.recipes.base import Recipe
from stage_gen.recipes.scrolling_preview.recipe import scrolling_preview_recipe

_RECIPES: dict[str, Recipe] = {scrolling_preview_recipe.id: scrolling_preview_recipe}


def list_recipes() -> list[dict[str, str]]:
    return [{"id": recipe.id, "description": recipe.description} for recipe in _RECIPES.values()]


def get_recipe(recipe_id: str) -> Recipe:
    try:
        return _RECIPES[recipe_id]
    except KeyError as error:
        raise ValueError(f"unknown recipe: {recipe_id}") from error

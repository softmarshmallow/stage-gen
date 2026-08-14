import { scrollingPreviewRecipe } from "../recipes/scrolling-preview/recipe.ts";
import type { JsonObject, Recipe } from "./types.ts";

const RECIPES: ReadonlyMap<string, Recipe<any>> = new Map([
  [scrollingPreviewRecipe.id, scrollingPreviewRecipe],
]);

export function listRecipes(): Array<{ id: string; description: string }> {
  return [...RECIPES.values()].map(({ id, description }) => ({ id, description }));
}

export function getRecipe(id: string): Recipe<JsonObject> {
  const recipe = RECIPES.get(id);
  if (!recipe) throw new Error(`unknown recipe: ${id}`);
  return recipe as Recipe<JsonObject>;
}

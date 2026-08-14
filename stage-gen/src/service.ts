import {
  assertCapabilities,
  parseTransparencyMode,
  transparencyCapabilities,
  type CapabilityName,
  type StageGenConfig,
  type TransparencyMode,
} from "./config.ts";
import { runRecipe } from "./orchestrator.ts";
import { getRecipe } from "./recipes.ts";
import { tagForTransparencyMode } from "./tag.ts";
import type { JsonObject, Recipe, RunSummary } from "./types.ts";

export interface GenerateRequest {
  recipe?: string;
  input: unknown;
  transparencyMode?: unknown;
}

export interface PreparedGenerateRequest {
  recipe: Recipe;
  input: JsonObject & { transparencyMode: TransparencyMode };
  tag: string;
  requiredCapabilities: readonly CapabilityName[];
}

/** Parse and canonicalize all public input before checking provider capability. */
export function prepareGenerateRequest(
  request: GenerateRequest,
  config: StageGenConfig,
): PreparedGenerateRequest {
  const recipe = getRecipe(request.recipe ?? "scrolling-preview");
  const nestedMode =
    request.input && typeof request.input === "object"
      ? (request.input as JsonObject).transparencyMode
      : undefined;
  const parsedInput = recipe.parseInput(request.input) as JsonObject;
  const explicitMode = request.transparencyMode;
  const parsedExplicit =
    explicitMode === undefined
      ? undefined
      : parseTransparencyMode(explicitMode, "transparencyMode");
  const parsedNested =
    nestedMode === undefined
      ? undefined
      : parseTransparencyMode(nestedMode, "input.transparencyMode");
  if (
    parsedExplicit !== undefined &&
    parsedNested !== undefined &&
    parsedExplicit !== parsedNested
  ) {
    throw new Error("transparencyMode conflicts with input.transparencyMode");
  }
  const transparencyMode = parsedExplicit ?? parsedNested ?? config.transparencyMode;
  const input = { ...parsedInput, transparencyMode };
  const requiredCapabilities = [
    ...recipe.requiredCapabilities,
    ...transparencyCapabilities(transparencyMode),
  ];
  assertCapabilities(config, requiredCapabilities);
  return {
    recipe,
    input,
    tag: tagForTransparencyMode(recipe.tagFor(input), transparencyMode),
    requiredCapabilities,
  };
}

export async function generatePrepared(
  prepared: PreparedGenerateRequest,
  config: StageGenConfig,
  log?: (line: string) => void,
  signal?: AbortSignal,
): Promise<RunSummary> {
  return runRecipe({
    recipe: prepared.recipe,
    input: prepared.input,
    tag: prepared.tag,
    config,
    log,
    signal,
  });
}

export async function generate(
  request: GenerateRequest,
  config: StageGenConfig,
  log?: (line: string) => void,
  signal?: AbortSignal,
): Promise<RunSummary> {
  return generatePrepared(prepareGenerateRequest(request, config), config, log, signal);
}

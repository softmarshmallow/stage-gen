// The platformer's instantiation of the `checkpoints` family.
//
// Where defeat sends the player, when they are asked about it, and who may
// answer. The rules are the family's now; what is left here is what this genre
// answers them with — the word it calls a safe place, and the three beats the
// death screen is paced to.
//
// Home is derived from the package rather than authored into it. The gameplay
// contract already says which maps are safe hubs and where the game starts, and
// those two facts are enough to name the village without asking every game to
// declare a respawn point it would have to keep in sync with its own entry
// spawn.

import {
  automatedConfirmDue,
  defeatPromptState as familyDefeatPromptState,
  parseCheckpointsBlock,
  resolveRespawnTarget,
  type CheckpointsBlockView,
  type DefeatPromptState,
  type DefeatPromptTiming,
  type RespawnSpawn,
} from "@/lib/families/checkpoints";
import type { BlockTable } from "@/lib/manifest/blocks";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import { DEATH_STRIP_DURATION_MS } from "./death-presentation";

/**
 * The map role a package uses for a settlement with no hostile population.
 *
 * This genre's word, handed to the family as a parameter. It used to be a
 * literal inside the resolver, which is what made the whole rule
 * platformer-only: a metroidvania's save room and a cinematic platformer's last
 * lit brazier are the same idea under other names.
 */
export const SAFE_HUB_MAP_ROLE = "safe_village_hub";

export type HomeSpawnInput = Readonly<{
  entry_map_id: string;
  entry_spawn_id: string;
  map_uses: readonly Readonly<{ map_id: string; role: string }>[];
  spawns: readonly RespawnSpawn[];
}>;

export type HomeSpawn = RespawnSpawn;

/** Resolve the spawn a defeated player wakes up at, under this genre's safe-place role. */
export function resolveHomeSpawn(input: HomeSpawnInput): HomeSpawn {
  return resolveRespawnTarget({
    entry_spawn_id: input.entry_spawn_id,
    map_uses: input.map_uses,
    spawns: input.spawns,
    safeRole: SAFE_HUB_MAP_ROLE,
  });
}

/**
 * How long a defeated player lies there before they are asked what to do next.
 *
 * Long enough for the authored terminal strip to finish and register as an ending rather than a
 * stutter. It is expressed against the strip duration so a change to the death artwork's frame
 * rate carries the beat with it, and a prompt raised over a still-playing death animation would
 * be talking over the one moment the artwork exists for.
 */
export const DEFEAT_PROMPT_DELAY_MS = DEATH_STRIP_DURATION_MS + 400;

/** How long the prompt takes to arrive, so it reads as an arrival rather than a cut. */
export const DEFEAT_PROMPT_FADE_MS = 260;

/**
 * How long an unattended run leaves the prompt standing before accepting it itself.
 *
 * A prompt is the right answer for a person, who wants to know what happened and to decide when to
 * carry on. It is the wrong answer for a run with nobody at the keyboard, which would otherwise
 * stop at its first death and stay stopped. The pause is deliberate rather than incidental: the
 * screen is worth seeing even when the thing reading it is going to press the button anyway.
 */
export const DEFEAT_AUTOMATED_CONFIRM_DELAY_MS = DEFEAT_PROMPT_DELAY_MS + 1400;

/** This genre's three beats, as the family's timing parameter. */
export const PLATFORMER_DEFEAT_TIMING: DefeatPromptTiming = Object.freeze({
  delayMs: DEFEAT_PROMPT_DELAY_MS,
  fadeMs: DEFEAT_PROMPT_FADE_MS,
});

export type { DefeatPromptState };

/** Whether the prompt is up yet, and how far in it has faded. */
export function defeatPromptState(
  input: Readonly<{
    defeatedAtMs: number;
    nowMs: number;
    delayMs?: number;
    fadeMs?: number;
  }>,
): DefeatPromptState {
  return familyDefeatPromptState(input, PLATFORMER_DEFEAT_TIMING);
}

/** Whether a run with nobody at the keyboard has waited long enough to accept the prompt. */
export function automatedDefeatConfirmDue(
  input: Readonly<{
    defeatedAtMs: number;
    nowMs: number;
    delayMs?: number;
  }>,
): boolean {
  return automatedConfirmDue(input, DEFEAT_AUTOMATED_CONFIRM_DELAY_MS);
}

export const PLATFORMER_CHECKPOINTS_BLOCK = Object.freeze({
  block: "gameplay",
  version: PREPARED_RUNTIME_BLOCKS.gameplay,
});

/** Gate the platformer's checkpoints block. Refuses by naming `gameplay`. */
export function parsePlatformerCheckpointsBlock(blocks: BlockTable): CheckpointsBlockView {
  return parseCheckpointsBlock(blocks, PLATFORMER_CHECKPOINTS_BLOCK);
}

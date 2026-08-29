// Where defeat sends the player, when they are asked about it, and who may answer.
//
// Defeat used to be terminal: control locked, the death strip played, and the run stopped there
// with nothing to restart it. That is survivable for a person with a reload button and fatal for
// anything meant to keep playing on its own, so recovery belongs to the runtime alongside the rest
// of the gameplay rules.
//
// Recovery is a decision rather than a timer. The player is told what happened and offered the way
// back, and the run resumes when they take it — which is what a death screen is for, and what a
// silent reload three seconds later cannot do. The timer that remains exists only for a run with
// nobody at the keyboard, which has to answer its own prompt or stop forever at its first death.
//
// Home is derived from the package rather than authored into it. The gameplay contract already
// says which maps are safe hubs and where the game starts, and those two facts are enough to name
// the village without asking every game to declare a respawn point it would have to keep in sync
// with its own entry spawn.

import { DEATH_STRIP_DURATION_MS } from "./death-presentation";

/** The map role a package uses for a settlement with no hostile population. */
export const SAFE_HUB_MAP_ROLE = "safe_village_hub";

export type HomeSpawnInput = Readonly<{
  entry_map_id: string;
  entry_spawn_id: string;
  map_uses: readonly Readonly<{ map_id: string; role: string }>[];
  spawns: readonly Readonly<{
    spawn_id: string;
    map_id: string;
    normalized_x: number;
  }>[];
}>;

export type HomeSpawn = Readonly<{
  spawn_id: string;
  map_id: string;
  normalized_x: number;
}>;

/**
 * Resolve the spawn a defeated player wakes up at.
 *
 * Preference order, and the reason for it: the game's own entry spawn wins when it stands in a
 * safe hub, because that is the arrival the package was authored and art-directed around. When the
 * game instead opens on a hostile route, the first safe hub it declares wins, because respawning
 * into the population that just killed the player is a death loop rather than a recovery. With no
 * safe hub declared at all the entry spawn is the only home a package has, and it is used as-is.
 */
export function resolveHomeSpawn(input: HomeSpawnInput): HomeSpawn {
  const entrySpawn = input.spawns.find(
    (spawn) => spawn.spawn_id === input.entry_spawn_id,
  );
  if (!entrySpawn) {
    throw new Error(
      `gameplay entry spawn ${input.entry_spawn_id} does not resolve to a spawn point`,
    );
  }
  const safeHubMapIds = new Set(
    input.map_uses
      .filter((use) => use.role === SAFE_HUB_MAP_ROLE)
      .map((use) => use.map_id),
  );
  if (safeHubMapIds.has(entrySpawn.map_id)) return frozenSpawn(entrySpawn);
  for (const use of input.map_uses) {
    if (!safeHubMapIds.has(use.map_id)) continue;
    const hubSpawn = input.spawns.find((spawn) => spawn.map_id === use.map_id);
    if (hubSpawn) return frozenSpawn(hubSpawn);
  }
  return frozenSpawn(entrySpawn);
}

function frozenSpawn(
  spawn: Readonly<{ spawn_id: string; map_id: string; normalized_x: number }>,
): HomeSpawn {
  return Object.freeze({
    spawn_id: spawn.spawn_id,
    map_id: spawn.map_id,
    normalized_x: spawn.normalized_x,
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

export type DefeatPromptState = Readonly<{
  visible: boolean;
  alpha: number;
}>;

/**
 * Whether the prompt is up yet, and how far in it has faded.
 *
 * Sampled from caller-supplied simulation time exactly like the stat log and floating combat text,
 * so normal play and fixed-frame automation follow the same path with no tween to drift between
 * them.
 */
export function defeatPromptState(
  input: Readonly<{
    defeatedAtMs: number;
    nowMs: number;
    delayMs?: number;
    fadeMs?: number;
  }>,
): DefeatPromptState {
  const delayMs = input.delayMs ?? DEFEAT_PROMPT_DELAY_MS;
  const fadeMs = input.fadeMs ?? DEFEAT_PROMPT_FADE_MS;
  assertFiniteTiming(input.defeatedAtMs, input.nowMs, delayMs);
  if (!Number.isFinite(fadeMs) || fadeMs < 0) {
    throw new Error("defeat prompt timing requires finite milliseconds");
  }
  const elapsed = input.nowMs - input.defeatedAtMs - delayMs;
  if (elapsed < 0) return Object.freeze({ visible: false, alpha: 0 });
  if (fadeMs === 0) return Object.freeze({ visible: true, alpha: 1 });
  return Object.freeze({
    visible: true,
    alpha: Math.max(0, Math.min(1, elapsed / fadeMs)),
  });
}

/** Whether a run with nobody at the keyboard has waited long enough to accept the prompt. */
export function automatedDefeatConfirmDue(
  input: Readonly<{
    defeatedAtMs: number;
    nowMs: number;
    delayMs?: number;
  }>,
): boolean {
  const delayMs = input.delayMs ?? DEFEAT_AUTOMATED_CONFIRM_DELAY_MS;
  assertFiniteTiming(input.defeatedAtMs, input.nowMs, delayMs);
  return input.nowMs - input.defeatedAtMs >= delayMs;
}

function assertFiniteTiming(defeatedAtMs: number, nowMs: number, delayMs: number): void {
  if (
    !Number.isFinite(defeatedAtMs) ||
    !Number.isFinite(nowMs) ||
    !Number.isFinite(delayMs) ||
    delayMs < 0
  ) {
    throw new Error("defeat prompt timing requires finite milliseconds");
  }
}

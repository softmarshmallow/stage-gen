// The `checkpoints` family, second half: being defeated, and being asked about it.
//
// The platformer kept this as a bare `defeatedAtMs: number | null` field on the
// scene, stamped inside `updatePlayer` and cleared in exactly one of the two
// places a world is replaced — which is the defect step 0 confirmed and could
// not measure. Here it is a small store with a lifetime, so "clear it when the
// world it describes is torn down" is one call at the teardown rather than a
// line somebody has to remember to write at each of the two exits.
//
// Recovery is a decision rather than a timer. The player is told what happened
// and offered the way back, and the run resumes when they take it — which is
// what a death screen is for, and what a silent reload three seconds later
// cannot do. The timer that remains exists only for a run with nobody at the
// keyboard, which has to answer its own prompt or stop forever at its first
// death.

export interface DefeatPromptTiming {
  /** How long a defeated body lies there before it is asked what to do next. */
  readonly delayMs: number;
  /** How long the prompt takes to arrive, so it reads as an arrival rather than a cut. */
  readonly fadeMs: number;
}

export interface DefeatPromptState {
  readonly visible: boolean;
  readonly alpha: number;
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

/**
 * Whether the prompt is up yet, and how far in it has faded.
 *
 * Sampled from caller-supplied simulation time, so normal play and a
 * fixed-frame replay follow the same path with no tween to drift between them.
 */
export function defeatPromptState(
  input: Readonly<{ defeatedAtMs: number; nowMs: number } & Partial<DefeatPromptTiming>>,
  timing: DefeatPromptTiming,
): DefeatPromptState {
  const delayMs = input.delayMs ?? timing.delayMs;
  const fadeMs = input.fadeMs ?? timing.fadeMs;
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
export function automatedConfirmDue(
  input: Readonly<{ defeatedAtMs: number; nowMs: number; delayMs?: number }>,
  defaultDelayMs: number,
): boolean {
  const delayMs = input.delayMs ?? defaultDelayMs;
  assertFiniteTiming(input.defeatedAtMs, input.nowMs, delayMs);
  return input.nowMs - input.defeatedAtMs >= delayMs;
}

/**
 * Whether a body is down, since when, and how many times it has been.
 *
 * The count is the family's because "trial and death" wants it and because it
 * is the one number that has to survive the world rebuild the recovery
 * performs — everything else about a defeat describes a world that is about to
 * be replaced.
 */
export class DefeatState {
  private at: number | null = null;
  private count = 0;

  /** Stamp a defeat. True the first time, false while the same one is still standing. */
  record(nowMs: number): boolean {
    if (this.at !== null) return false;
    this.at = nowMs;
    this.count += 1;
    return true;
  }

  /** When the current defeat began, or null while the body is alive. */
  since(): number | null {
    return this.at;
  }

  defeated(): boolean {
    return this.at !== null;
  }

  /** How many times this session has ended in a defeat. Survives the recovery's rebuild. */
  deaths(): number {
    return this.count;
  }

  /**
   * Get up.
   *
   * Called by the recovery *and* by the teardown of the world the defeat
   * happened in. That second caller is the one the scene's own field never had:
   * only `respawnAtHome` cleared it, so a rebuild reached any other way — the
   * developer kit switch — left the stamp behind describing a body that no
   * longer exists.
   */
  clear(): void {
    this.at = null;
  }
}

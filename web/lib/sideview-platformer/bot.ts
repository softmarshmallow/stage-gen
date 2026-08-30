// The bot as the scene sees it: hand it a view, get back an intent.
//
// A deliberately thin shell over `decideBot`. Everything that decides anything is a pure function
// in the kernel, the roster or the navigator; this class only holds the two frames' worth of state
// those functions need handed back to them, and turns the per-frame navigation queries into one
// call. Keeping it thin is what makes the system portable — a runtime with a different object model
// reimplements this file and reuses everything under it.

import {
  INITIAL_BOT_MEMORY,
  decideBot,
  type BotDecision,
  type BotMemory,
  type BotProfile,
} from "./bot-behavior";
import { locateNavNode, navReach, type NavReach } from "./bot-navigation";
import type { BotWorldView } from "./bot-view";
import { NEUTRAL_PLAYER_INTENT, type PlayerIntent } from "./player-intent";

/**
 * How long a human keeps the controls after their last input.
 *
 * Without a hold the bot would resume on the very first frame a key is released and drag the
 * character back to whatever it was doing, which makes manual inspection impossible. With one, a
 * touch of any key is a takeover that lasts as long as it takes to think, and walking away from the
 * keyboard returns control on its own — no mode to enter, none to remember to leave.
 */
export const BOT_HUMAN_OVERRIDE_HOLD_MS = 1500;

export function isNeutralIntent(intent: PlayerIntent): boolean {
  return (Object.keys(NEUTRAL_PLAYER_INTENT) as (keyof PlayerIntent)[]).every(
    (field) => intent[field] === NEUTRAL_PLAYER_INTENT[field],
  );
}

export type BotControlSource = "human" | "bot";

export type BotControl = Readonly<{
  source: BotControlSource;
  /** Carried forward as the next frame's `lastHumanInputAtMs`. */
  humanInputAtMs: number | null;
}>;

/**
 * Decide who is driving this frame, before either of them is asked for anything.
 *
 * The rule is one sentence — a human who is touching the keys, or who touched them recently, has
 * the controls; otherwise the bot does. It answers with a source rather than with an intent so the
 * bot is never asked to think on a frame it does not own: a decision it did not drive would still
 * advance its memory, and the next frame it did own would be reasoning from a move it never made.
 */
export function resolveBotControl(input: Readonly<{
  humanIntent: PlayerIntent;
  enabled: boolean;
  nowMs: number;
  lastHumanInputAtMs: number | null;
  holdMs?: number;
}>): BotControl {
  const holdMs = input.holdMs ?? BOT_HUMAN_OVERRIDE_HOLD_MS;
  const humanActing = !isNeutralIntent(input.humanIntent);
  const humanInputAtMs = humanActing ? input.nowMs : input.lastHumanInputAtMs;
  if (!input.enabled) return { source: "human", humanInputAtMs };
  const holding = humanInputAtMs !== null && input.nowMs - humanInputAtMs < holdMs;
  return { source: humanActing || holding ? "human" : "bot", humanInputAtMs };
}

export class Bot {
  private profile: BotProfile;
  private memory: BotMemory = INITIAL_BOT_MEMORY;
  private previousIntent: PlayerIntent = NEUTRAL_PLAYER_INTENT;
  private decision: BotDecision | null = null;

  constructor(profile: BotProfile) {
    this.profile = profile;
  }

  get lastDecision(): BotDecision | null {
    return this.decision;
  }

  get profileId(): string {
    return this.profile.id;
  }

  /** Swap the repertoire without losing the map bearings the memory holds. */
  setProfile(profile: BotProfile): void {
    this.profile = profile;
  }

  decide(view: BotWorldView): BotDecision {
    const standing = locateNavNode(view.navigation, view.self.x, view.self.y);
    const reach: readonly NavReach[] = standing
      ? navReach(view.navigation, standing.id)
      : Object.freeze([]);
    const decision = decideBot({
      view,
      memory: this.memory,
      previousIntent: this.previousIntent,
      profile: this.profile,
      reach,
      standingOn: standing?.id ?? null,
    });
    this.memory = decision.memory;
    this.previousIntent = decision.intent;
    this.decision = decision;
    return decision;
  }

  /**
   * Stand down for a frame a human owns.
   *
   * The stuck counter and the current target are cleared because both describe what *the bot* was
   * doing, and neither survives someone else walking the character somewhere. The patrol direction
   * survives on purpose: it is a fact about the map, and forgetting it makes a resumed bot walk
   * back into the wall it just turned away from.
   */
  suspend(): void {
    this.memory = Object.freeze({
      ...this.memory,
      targetId: null,
      stuckFrames: 0,
    });
    this.previousIntent = NEUTRAL_PLAYER_INTENT;
    this.decision = null;
  }

  /** Forget everything. Called when the world under the bot is replaced. */
  reset(): void {
    this.memory = INITIAL_BOT_MEMORY;
    this.previousIntent = NEUTRAL_PLAYER_INTENT;
    this.decision = null;
  }
}

// The bot kernel — what a behaviour is, and how one of them wins the frame.
//
// This file holds no opinions about hunting, healing, or any other thing a character might do. It
// defines the contract those opinions are written against and the rule that arbitrates between
// them, and nothing else. That separation is the whole reason the system can grow: a new behaviour
// is a new value implementing `BotBehavior`, added to a roster, and no existing line changes.
//
// Arbitration is a priority auction, not a state machine. Every behaviour is asked, every frame,
// what it would do and how badly it wants to; the loudest proposal wins and the rest are discarded.
// A state machine would need every behaviour to know its neighbours in order to name a transition,
// and adding the seventh state to a six-state machine means editing six states. Here the seventh
// behaviour is added by writing it. The cost of the auction is that behaviours cannot cooperate
// within a frame — one of them owns the intent — and that is a price worth paying at this size.
//
// Determinism is a hard requirement, not a preference: this runtime verifies itself by replaying a
// fixed-step transcript and comparing frame hashes. Nothing here may consult a clock it was not
// handed or a random number generator at all. Ties break on roster order, which is stable.

import type { BotWorldView } from "./bot-view";
import type { PlayerIntent } from "./player-intent";
import { NEUTRAL_PLAYER_INTENT } from "./player-intent";
import type { MovementCapabilities, NavReach, NavSteerTuning } from "./bot-navigation";

/**
 * What the bot is trying to accomplish, in one word.
 *
 * Goals are for the human reading the overlay, not for control flow — nothing branches on a goal.
 * Adding one costs a union member and a label.
 */
export type BotGoal =
  | "stand_down"
  | "heal"
  | "engage"
  | "collect"
  | "pursue"
  | "patrol";

/** Priorities the shipped behaviours bid at. Values are spaced so new ones can land between. */
export const BOT_PRIORITY = Object.freeze({
  standDown: 1000,
  heal: 900,
  engage: 700,
  collect: 500,
  pursue: 400,
  patrol: 100,
});

/**
 * Carried state, kept explicit and small.
 *
 * Anything a behaviour needs to remember between frames lives here rather than in a closure, so the
 * bot's entire mind is one serialisable value: it can be logged next to a frame, diffed when a run
 * diverges, and reconstructed exactly. A closure-held counter can do none of that.
 */
export type BotMemory = Readonly<{
  /** The threat or pickup currently being chased, so the bot does not swap targets every frame. */
  targetId: string | null;
  /** Frames spent asking to move horizontally while going nowhere. */
  stuckFrames: number;
  /** Which way an idle patrol is currently walking. */
  patrolSign: 1 | -1;
  lastGoal: BotGoal | null;
}>;

export const INITIAL_BOT_MEMORY: BotMemory = Object.freeze({
  targetId: null,
  stuckFrames: 0,
  patrolSign: 1,
  lastGoal: null,
});

/** Everything a behaviour is given. Read-only by construction; behaviours mutate nothing. */
export type BotContext = Readonly<{
  view: BotWorldView;
  memory: BotMemory;
  tuning: BotTuning;
  capabilities: MovementCapabilities;
  /** Cost and opening move to every node, computed once per frame from where the bot stands. */
  reach: readonly NavReach[];
  /** The node the bot is standing on, or null when the map has no navigable surface at all. */
  standingOn: string | null;
}>;

/**
 * Numbers a bot is tuned with.
 *
 * Deliberately all in one struct rather than scattered as module constants: tuning is the knob a
 * second bot personality turns, and a personality that has to fork constants is not a personality.
 */
export type BotTuning = Readonly<{
  /** Drink at or below this share of the health pool. */
  healAtHealthFraction: number;
  /** Horizontal reach a swing actually covers. */
  engageRangeUnits: number;
  /** How far apart two feet may stand and still trade blows. */
  footLevelToleranceUnits: number;
  /** How far the bot will travel to reach a mob. */
  pursuitRangeUnits: number;
  /** How far it will detour for a drop on the ground. */
  pickupRangeUnits: number;
  /** Below this speed while asking to move, the bot counts itself stuck. */
  stuckSpeedUnits: number;
  /** Consecutive stuck frames before it tries jumping out. */
  stuckFramesBeforeJump: number;
  /** How close to the map edge a patrol turns around. */
  patrolMarginUnits: number;
  navSteer: NavSteerTuning;
}>;

export type BotProposal = Readonly<{
  goal: BotGoal;
  priority: number;
  intent: PlayerIntent;
  /** What is being acted on, so the overlay and the next frame's memory agree about the target. */
  targetId: string | null;
  /** One short clause, for the debug overlay. Never parsed. */
  reason: string;
  /** Fields the winner wants carried into the next frame. Losers' patches are discarded. */
  memory?: Partial<BotMemory>;
}>;

export type BotBehavior = Readonly<{
  id: string;
  /** Returns null to decline the frame, which is the normal outcome for most behaviours. */
  consider: (context: BotContext) => BotProposal | null;
}>;

export type BotRoster = readonly BotBehavior[];

/**
 * A named bot: a repertoire, a temperament, and a body.
 *
 * Swapping a profile is how a second kind of bot exists — a cautious one that heals earlier and
 * refuses bosses, a courier that only collects — without a flag inside any behaviour.
 */
export type BotProfile = Readonly<{
  id: string;
  tuning: BotTuning;
  roster: BotRoster;
  capabilities: MovementCapabilities;
}>;

export type BotDecision = Readonly<{
  intent: PlayerIntent;
  goal: BotGoal;
  targetId: string | null;
  reason: string;
  memory: BotMemory;
}>;

const STAND_DOWN_DECISION_REASON = "no behaviour bid";

/**
 * Advance the bookkeeping every behaviour depends on but none of them owns.
 *
 * Stuck detection lives here rather than inside a movement behaviour because being stuck is a fact
 * about the last frame's outcome, not about this frame's plan, and because every behaviour that
 * moves would otherwise need its own copy of it. Patrol direction flips at the map edge for the
 * same reason: it is world state, not a decision.
 */
export function observeBotMemory(input: Readonly<{
  memory: BotMemory;
  view: BotWorldView;
  previousIntent: PlayerIntent;
  tuning: BotTuning;
}>): BotMemory {
  const { memory, view, previousIntent, tuning } = input;
  const askedToMove = previousIntent.left !== previousIntent.right;
  const movedSlowly = Math.abs(view.self.vx) < tuning.stuckSpeedUnits;
  const stuckFrames = askedToMove && movedSlowly && !view.self.airborne ? memory.stuckFrames + 1 : 0;
  const patrolSign =
    view.self.x <= view.bounds.left + tuning.patrolMarginUnits
      ? 1
      : view.self.x >= view.bounds.right - tuning.patrolMarginUnits
        ? -1
        : memory.patrolSign;
  const targetStillThere =
    memory.targetId !== null &&
    (view.threats.some((threat) => threat.id === memory.targetId) ||
      view.pickups.some((pickup) => pickup.id === memory.targetId));
  return Object.freeze({
    targetId: targetStillThere ? memory.targetId : null,
    stuckFrames,
    patrolSign,
    lastGoal: memory.lastGoal,
  });
}

/**
 * Pick the winning proposal.
 *
 * Strictly greater wins, so a tie leaves the earlier-declared behaviour in place. Roster order is
 * therefore a real tiebreak the author controls, and reordering the roster is a legitimate way to
 * express "when these two want the frame equally, prefer this one".
 */
export function arbitrate(proposals: readonly (BotProposal | null)[]): BotProposal | null {
  let winner: BotProposal | null = null;
  for (const proposal of proposals) {
    if (!proposal) continue;
    if (!winner || proposal.priority > winner.priority) winner = proposal;
  }
  return winner;
}

/**
 * One frame of thought: observe, poll the roster, arbitrate, remember.
 *
 * Pure, and pure on purpose. The whole decision is a function of the view and the memory handed in,
 * so a divergence between two runs is reproducible from two values rather than from a scene.
 */
export function decideBot(input: Readonly<{
  view: BotWorldView;
  memory: BotMemory;
  previousIntent: PlayerIntent;
  profile: BotProfile;
  reach: readonly NavReach[];
  standingOn: string | null;
}>): BotDecision {
  const memory = observeBotMemory({
    memory: input.memory,
    view: input.view,
    previousIntent: input.previousIntent,
    tuning: input.profile.tuning,
  });
  const context: BotContext = Object.freeze({
    view: input.view,
    memory,
    tuning: input.profile.tuning,
    capabilities: input.profile.capabilities,
    reach: input.reach,
    standingOn: input.standingOn,
  });
  const winner = arbitrate(input.profile.roster.map((behavior) => behavior.consider(context)));
  if (!winner) {
    return Object.freeze({
      intent: NEUTRAL_PLAYER_INTENT,
      goal: "stand_down",
      targetId: null,
      reason: STAND_DOWN_DECISION_REASON,
      memory: Object.freeze({ ...memory, lastGoal: "stand_down" as BotGoal }),
    });
  }
  return Object.freeze({
    intent: winner.intent,
    goal: winner.goal,
    targetId: winner.targetId,
    reason: winner.reason,
    memory: Object.freeze({
      ...memory,
      ...winner.memory,
      targetId: winner.targetId,
      lastGoal: winner.goal,
    }),
  });
}

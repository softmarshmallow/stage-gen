// The hunter — the first bot personality, written against the kernel like any other.
//
// Its loop is the one an idle RPG runs: stay alive, hit what is in front of you, pick up what falls
// out of it, walk to the next thing, and if there is nothing at all, keep moving so the character
// does not read as broken. Six behaviours, each declining most frames.
//
// Every behaviour that has somewhere to be delegates the getting there to navigation and never
// mentions a jump. That is the arrangement worth protecting: when the graph learns a new move, the
// hunter starts using it without being touched, and a bot written next week inherits it too.
//
// Targets are chosen by travel cost rather than by distance on screen, so a mob two paces away
// behind a wall loses to one across the shelf that can actually be reached. A target that cannot be
// reached at all is not a target — the behaviour declines, and something else takes the frame.

import {
  BOT_PRIORITY,
  type BotBehavior,
  type BotContext,
  type BotProfile,
  type BotProposal,
  type BotTuning,
} from "./bot-behavior";
import {
  DEFAULT_MOVEMENT_CAPABILITIES,
  DEFAULT_NAV_STEER_TUNING,
  locateNavNode,
  reachOf,
  steerNav,
  type NavAgentState,
} from "./bot-navigation";
import {
  facingToward,
  healthFraction,
  horizontalDistance,
  lineOfFireClear,
  sameFootLevel,
} from "./bot-view";
import { NEUTRAL_PLAYER_INTENT, playerIntent, type PlayerIntent } from "./player-intent";

export const HUNTER_BOT_TUNING: BotTuning = Object.freeze({
  healAtHealthFraction: 0.45,
  // How far a swing reaches, how far off the level it still connects, and how close the bot walks
  // in used to live here as `engageRangeUnits` and `footLevelToleranceUnits`, restated from the
  // scene's own constants with a comment saying they had to agree. They are the weapon class's
  // numbers, so they arrive on the view as `weaponBand` and no personality forks them.
  pursuitRangeUnits: 1400,
  pickupRangeUnits: 520,
  stuckSpeedUnits: 12,
  stuckFramesBeforeJump: 12,
  patrolMarginUnits: 96,
  navSteer: DEFAULT_NAV_STEER_TUNING,
});

function agentState(context: BotContext): NavAgentState {
  const self = context.view.self;
  return {
    x: self.x,
    footY: self.y,
    vx: self.vx,
    vy: self.vy,
    airborne: self.airborne,
    support: self.support,
    airJumpsUsed: self.airJumpsUsed,
  };
}

/**
 * A jump as a last resort, when the world disagrees with the graph.
 *
 * The graph models terrain, decks and declared climbables — not props, not other actors, not a
 * corner the collision resolver rounds differently than the derivation did. Something the model
 * does not contain can still wedge the character against it, and no amount of replanning helps,
 * because the plan is correct and the world is the surprise. A hop costs a fraction of a second
 * when it was unnecessary and frees the character when it was.
 */
function unstick(intent: PlayerIntent, context: BotContext): PlayerIntent {
  if (context.memory.stuckFrames < context.tuning.stuckFramesBeforeJump) return intent;
  if (intent.left === intent.right) return intent;
  return playerIntent({ ...intent, jump: true });
}

export type BotTravelPlan = Readonly<{
  intent: PlayerIntent;
  /** Seconds of travel, by the navigation model's own reckoning. */
  cost: number;
}>;

/**
 * How to move one step toward a point, or null when there is no way there at all.
 *
 * The plan is recomputed from scratch every frame. There is no stored path to invalidate when the
 * target moves, the character is knocked back, or the shelf it was heading for turns out to be the
 * wrong one — which for a graph this size is both simpler and cheaper than keeping one honest.
 */
export function planTravel(
  context: BotContext,
  target: Readonly<{ x: number; y: number }>,
): BotTravelPlan | null {
  const destination = locateNavNode(context.view.navigation, target.x, target.y);
  if (!destination || context.standingOn === null) return null;
  const reach = reachOf(context.reach, destination.id);
  if (!reach) return null;
  const link = destination.id === context.standingOn ? null : reach.firstLink;
  const approach = Math.abs(target.x - context.view.self.x) / context.capabilities.runSpeed;
  return {
    intent: unstick(
      steerNav({
        self: agentState(context),
        link,
        targetX: target.x,
        capabilities: context.capabilities,
        tuning: context.tuning.navSteer,
      }),
      context,
    ),
    cost: reach.cost + approach,
  };
}

/**
 * The cheapest candidate to travel to, keeping the current one when it is still worth keeping.
 *
 * Stickiness matters more than it looks: two mobs at nearly equal cost would otherwise swap the
 * lead every few frames as the character moves, and a bot that turns around twice a second never
 * arrives anywhere. The incumbent is dropped only when it is gone or out of range.
 */
function selectTarget<T extends Readonly<{ id: string; x: number; y: number }>>(
  context: BotContext,
  candidates: readonly T[],
  rangeUnits: number,
): Readonly<{ target: T; plan: BotTravelPlan }> | null {
  const inRange = candidates.filter(
    (candidate) => horizontalDistance(context.view.self, candidate) <= rangeUnits,
  );
  const incumbent = inRange.find((candidate) => candidate.id === context.memory.targetId);
  if (incumbent) {
    const plan = planTravel(context, incumbent);
    if (plan) return { target: incumbent, plan };
  }
  let best: Readonly<{ target: T; plan: BotTravelPlan }> | null = null;
  for (const candidate of inRange) {
    const plan = planTravel(context, candidate);
    if (!plan) continue;
    if (
      !best ||
      plan.cost < best.plan.cost ||
      (plan.cost === best.plan.cost && candidate.id < best.target.id)
    ) {
      best = { target: candidate, plan };
    }
  }
  return best;
}

/**
 * Do nothing, loudly.
 *
 * Defeat is not a state the other behaviours are asked to know about; this one outbids all of them
 * so they never see it. The scene owns what happens next — the death animation runs, recovery is
 * timed, and the world is rebuilt around a fresh character — and a bot pressing keys through any of
 * that would be arguing with it.
 */
export const standDownBehavior: BotBehavior = Object.freeze({
  id: "stand_down",
  consider(context: BotContext): BotProposal | null {
    const blocked =
      context.view.self.defeated ||
      context.standingOn === null ||
      context.view.navigation.nodes.length === 0;
    if (!blocked) return null;
    return {
      goal: "stand_down",
      priority: BOT_PRIORITY.standDown,
      intent: NEUTRAL_PLAYER_INTENT,
      targetId: null,
      reason: context.view.self.defeated ? "defeated" : "nowhere to stand",
    };
  },
});

/**
 * Drink when low, and only when a drink would land.
 *
 * The request is refused by the health pool at full health and while defeated, and the scene only
 * opens the bag once the restore connects, so a mistimed bid costs nothing. Bidding above combat
 * rather than below it is the whole reason the bot survives a hunting ground: a heal deferred until
 * the mob in front is dead is a heal that arrives after the character does.
 */
export const healBehavior: BotBehavior = Object.freeze({
  id: "heal",
  consider(context: BotContext): BotProposal | null {
    const self = context.view.self;
    if (!context.view.healingCarried || self.hp >= self.maxHp) return null;
    if (healthFraction(self) > context.tuning.healAtHealthFraction) return null;
    return {
      goal: "heal",
      priority: BOT_PRIORITY.heal,
      intent: playerIntent({ useHealing: true }),
      targetId: null,
      reason: `hp ${self.hp}/${self.maxHp}`,
    };
  },
});

/**
 * Attack what is already in range, and hold the distance the weapon wants.
 *
 * `attack` is edge-triggered and the controller refuses a fresh action while one is running, so
 * asking every frame is not mashing: it produces exactly the animation's own rate, the same cap a
 * human hits. Facing is corrected by pressing a direction for a frame, because facing follows
 * movement in this controller and there is no other way to turn on the spot.
 *
 * The three distances come from the weapon class on the view, not from this behaviour. A swinging
 * class has no minimum, so its back-off branch can never fire and it walks all the way in exactly
 * as it always has; a throwing class stops at arm's length of the creature it is killing. Nothing
 * here knows which class it is holding, which is what makes a third one free.
 */
export const engageBehavior: BotBehavior = Object.freeze({
  id: "engage",
  consider(context: BotContext): BotProposal | null {
    const self = context.view.self;
    if (!context.view.combatEnabled) return null;
    const band = context.view.weaponBand;
    // A class that spends a round and is carrying none does not stand there pressing the key. It
    // declines outright, so collect, pursue and patrol can win the auction instead — otherwise an
    // unattended run stops forever the moment the bag empties, with nothing logged and no gate red.
    if (band.requiresAmmo && !context.view.ammoCarried) return null;
    const reachable = context.view.threats.filter(
      (threat) =>
        horizontalDistance(self, threat) <= band.maximumUnits &&
        sameFootLevel(self, threat, band.verticalToleranceUnits) &&
        // Distance and foot level say a creature is worth attacking; they say nothing about what
        // is between the two. A creature on a ledge satisfies both while the ledge face stands in
        // the way, and every throw dies in it — so a class that throws asks the terrain too.
        // Melee declares no release height and skips the test: a swing has no flight path.
        (band.releaseHeightUnits === null ||
          lineOfFireClear(
            context.view.terrain,
            self.x,
            threat.x,
            self.y - band.releaseHeightUnits,
          )),
    );
    const target =
      reachable.find((threat) => threat.id === context.memory.targetId) ??
      [...reachable].sort(
        (left, right) =>
          horizontalDistance(self, left) - horizontalDistance(self, right) ||
          left.id.localeCompare(right.id),
      )[0];
    if (!target) return null;
    const distance = horizontalDistance(self, target);
    const wantFacing = facingToward(self, target.x);
    const turning = wantFacing !== self.facing;
    const closing = distance > band.approachUnits;
    const backing = distance < band.minimumUnits;
    // The step and the facing are separate requests, and they disagree while backing away. Facing
    // otherwise follows the movement key, so pressing away from the target would turn the character
    // around — and the scene reads facing at the frame the blow leaves, so the whole retreat would
    // be spent attacking in the wrong direction. `face` is what keeps the target in front.
    const stepFacing = backing ? (wantFacing === "left" ? "right" : "left") : wantFacing;
    const stepping = turning || closing || backing;
    return {
      goal: "engage",
      priority: BOT_PRIORITY.engage,
      intent: playerIntent({
        left: stepping && stepFacing === "left",
        right: stepping && stepFacing === "right",
        face: wantFacing,
        attack: true,
      }),
      targetId: target.id,
      reason: turning ? "turning onto target" : backing ? "holding distance" : "in reach",
    };
  },
});

/**
 * Walk over what fell out of the last kill.
 *
 * Above pursuit and below combat, which is the order that actually banks loot: finish the mob in
 * front, sweep up what it dropped, then go find the next one. Ranked below combat the drops would
 * pile up and the bot would spend the fight standing on them; ranked below pursuit it would walk
 * away from every one of them.
 */
export const collectBehavior: BotBehavior = Object.freeze({
  id: "collect",
  consider(context: BotContext): BotProposal | null {
    const selection = selectTarget(
      context,
      context.view.pickups,
      context.tuning.pickupRangeUnits,
    );
    if (!selection) return null;
    return {
      goal: "collect",
      priority: BOT_PRIORITY.collect,
      intent: selection.plan.intent,
      targetId: selection.target.id,
      reason: `drop ${Math.round(selection.plan.cost * 100) / 100}s away`,
    };
  },
});

/** Go to the cheapest mob that can actually be reached from here. */
export const pursueBehavior: BotBehavior = Object.freeze({
  id: "pursue",
  consider(context: BotContext): BotProposal | null {
    if (!context.view.combatEnabled) return null;
    const selection = selectTarget(
      context,
      context.view.threats,
      context.tuning.pursuitRangeUnits,
    );
    if (!selection) return null;
    return {
      goal: "pursue",
      priority: BOT_PRIORITY.pursue,
      intent: selection.plan.intent,
      targetId: selection.target.id,
      reason: `mob ${Math.round(selection.plan.cost * 100) / 100}s away`,
    };
  },
});

/**
 * When there is nothing to do, walk.
 *
 * The floor of the roster, and the only behaviour that never declines. Its job is partly to find
 * mobs that have not spawned into range yet and partly to be visibly alive: a character standing
 * perfectly still reads as a hung frame, and someone watching a demo cannot tell the difference.
 * Direction is flipped by the map edge in the kernel's bookkeeping, not decided here.
 */
export const patrolBehavior = Object.freeze({
  id: "patrol",
  consider(context: BotContext): BotProposal {
    const sign = context.memory.patrolSign;
    return {
      goal: "patrol",
      priority: BOT_PRIORITY.patrol,
      intent: unstick(playerIntent({ left: sign < 0, right: sign > 0 }), context),
      targetId: null,
      reason: sign > 0 ? "sweeping right" : "sweeping left",
    };
  },
  // `satisfies` rather than an annotation, so the never-declines return type survives: this is the
  // floor of the roster, and a caller that had to null-check it would be checking for a case the
  // design guarantees cannot happen.
}) satisfies BotBehavior;

/** Declaration order is the tiebreak between equal bids, so it is part of the design. */
export const HUNTER_BOT_ROSTER = Object.freeze([
  standDownBehavior,
  healBehavior,
  engageBehavior,
  collectBehavior,
  pursueBehavior,
  patrolBehavior,
]);

export const HUNTER_BOT_PROFILE: BotProfile = Object.freeze({
  id: "hunter_v1",
  tuning: HUNTER_BOT_TUNING,
  roster: HUNTER_BOT_ROSTER,
  capabilities: DEFAULT_MOVEMENT_CAPABILITIES,
});

/**
 * A profile with some behaviours switched off.
 *
 * This is the whole of per-behaviour toggling: the roster is a list, and a bot that should not loot
 * is a bot whose roster has no `collect` in it. No behaviour gains an `enabled` flag, and none of
 * them learns that it can be disabled.
 */
export function botProfileWithout(
  profile: BotProfile,
  disabledIds: readonly string[],
): BotProfile {
  return Object.freeze({
    ...profile,
    id: disabledIds.length === 0 ? profile.id : `${profile.id}-${[...disabledIds].sort().join("-")}`,
    roster: Object.freeze(profile.roster.filter((behavior) => !disabledIds.includes(behavior.id))),
  });
}

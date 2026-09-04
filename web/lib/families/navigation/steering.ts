// What to press this frame, given the move being executed.
//
// The second half of navigation and deliberately the smaller one: the graph
// decides *which* traversal to attempt and this decides how to perform it. A
// behaviour never appears in either.
//
// The buttons come back through an `intentOf` builder rather than as this
// family's own record, because the intent record is the `intent` family's and
// its keys are the genre's — the platformer's ten and the runner's four are
// both legitimate. Steering therefore names the six buttons a navigator can
// ask for and hands them to whoever owns the record.

import type { MovementCapabilities, NavLink } from "./graph";

export type NavAgentState = Readonly<{
  x: number;
  footY: number;
  vx: number;
  vy: number;
  airborne: boolean;
  support: "terrain" | "platform" | "climbable" | "air";
  airJumpsUsed: number;
}>;

/** The buttons a navigator can ask for, whatever record a genre keeps them in. */
export type NavSteerButtons = Readonly<{
  left?: boolean;
  right?: boolean;
  up?: boolean;
  down?: boolean;
  jump?: boolean;
  run?: boolean;
}>;

export type NavSteerTuning = Readonly<{
  /** Within this distance of a destination the navigator stops asking to move. */
  arriveRadiusUnits: number;
  /** Beyond this distance it runs rather than walks. */
  runBeyondUnits: number;
  /** How close to a launch point the jump is committed. */
  launchWindowUnits: number;
  /** How closely a climb must be lined up before the grab is attempted. */
  climbAlignUnits: number;
}>;

export const DEFAULT_NAV_STEER_TUNING: NavSteerTuning = Object.freeze({
  arriveRadiusUnits: 14,
  runBeyondUnits: 190,
  launchWindowUnits: 40,
  climbAlignUnits: 12,
});

function walkToward<I>(
  self: NavAgentState,
  targetX: number,
  tuning: NavSteerTuning,
  extra: NavSteerButtons = {},
  intentOf: (buttons: NavSteerButtons) => I,
): I {
  const delta = targetX - self.x;
  if (Math.abs(delta) <= tuning.arriveRadiusUnits) return intentOf(extra);
  return intentOf({
    ...extra,
    left: delta < 0,
    right: delta > 0,
    run: Math.abs(delta) > tuning.runBeyondUnits,
  });
}

/**
 * The buttons this frame, given the move being executed.
 *
 * A `null` link means the destination is on the shelf already occupied, so the whole of navigation
 * collapses to walking toward it — which is the common case and should read like one.
 *
 * The air jump is spent on the first frame the arc stops rising. That is not a heuristic: it is the
 * same moment `simulatePlatformJump` spends it when proving the link reachable, so the arc actually
 * flown is the arc that was proved. Any other moment would make the graph a promise the steering
 * quietly breaks.
 */
export function steerNav<I>(input: Readonly<{
  self: NavAgentState;
  link: NavLink | null;
  targetX: number;
  capabilities: MovementCapabilities;
  tuning?: NavSteerTuning;
  intentOf: (buttons: NavSteerButtons) => I;
}>): I {
  const tuning = input.tuning ?? DEFAULT_NAV_STEER_TUNING;
  const self = input.self;
  const link = input.link;
  const intentOf = input.intentOf;
  if (!link) return walkToward(self, input.targetX, tuning, {}, intentOf);
  switch (link.move) {
    case "walk":
    case "step_down":
      return walkToward(self, link.toX, tuning, {}, intentOf);
    case "jump":
    case "double_jump": {
      if (self.airborne) {
        const spendAirJump =
          link.move === "double_jump" &&
          self.vy >= 0 &&
          self.airJumpsUsed === 0 &&
          input.capabilities.airJumpVelocity !== null;
        return walkToward(
          self,
          link.toX,
          { ...tuning, arriveRadiusUnits: 0 },
          { jump: spendAirJump },
          intentOf,
        );
      }
      const atLaunch = Math.abs(self.x - link.fromX) <= tuning.launchWindowUnits;
      return walkToward(
        self,
        atLaunch ? link.toX : link.fromX,
        { ...tuning, arriveRadiusUnits: 0 },
        { jump: atLaunch },
        intentOf,
      );
    }
    case "climb": {
      const aligned = Math.abs(self.x - link.fromX) <= tuning.climbAlignUnits;
      const upward = link.rise > 0;
      if (self.support === "climbable") {
        return intentOf({ up: upward, down: !upward });
      }
      if (!aligned) {
        return walkToward(self, link.fromX, { ...tuning, arriveRadiusUnits: 0 }, {}, intentOf);
      }
      return intentOf({ up: upward, down: !upward });
    }
    case "drop_through": {
      const aligned = Math.abs(self.x - link.fromX) <= tuning.arriveRadiusUnits;
      if (!aligned) return walkToward(self, link.fromX, tuning, {}, intentOf);
      return intentOf({ down: true, jump: true });
    }
  }
}

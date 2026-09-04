import { motionNeedsRestart } from "@/lib/families/sideview/motion";
import { Awareness } from "@/lib/families/actor-ai";
import {
  type AggressionProfile,
  attackFootLevelsOverlap,
  mobIntent,
  type MobIntent,
} from "./combat";

export type MobHorizontalDirection = -1 | 1;

export type MobBehaviorVariationConfig = Readonly<{
  movementSpeedVarianceRatio: number;
  pursuitSweepVarianceRatio: number;
}>;

/**
 * Stable per-instance movement noise.
 *
 * Values are sampled once from a deterministic seed, never once per frame. Per-frame randomness
 * makes sprites jitter and makes replays diverge; per-instance variation gives each creature its
 * own tempo and patrol width while preserving deterministic automation.
 */
export class MobBehaviorVariation {
  readonly movementSpeedScale: number;
  readonly pursuitSweepScale: number;
  readonly initialDirection: MobHorizontalDirection;

  constructor(seed: number, config: MobBehaviorVariationConfig) {
    if (!Number.isSafeInteger(seed)) {
      throw new Error("mob behavior variation seed must be a safe integer");
    }
    validateVariance(config.movementSpeedVarianceRatio, "movement speed");
    validateVariance(config.pursuitSweepVarianceRatio, "pursuit sweep");
    this.movementSpeedScale = symmetricScale(
      deterministicUnitNoise(seed, 0x243f6a88),
      config.movementSpeedVarianceRatio,
    );
    this.pursuitSweepScale = symmetricScale(
      deterministicUnitNoise(seed, 0x85a308d3),
      config.pursuitSweepVarianceRatio,
    );
    this.initialDirection =
      deterministicUnitNoise(seed, 0x13198a2e) < 0.5 ? -1 : 1;
    Object.freeze(this);
  }
}

export type MobActionTimingInput = Readonly<{
  windupMs: number;
  cooldownMs: number;
}>;

export type MobActionTiming = Readonly<{
  windupMs: number;
  cooldownMs: number;
}>;

/** Samples bounded action timing once per committed action. */
export class MobActionTimingNode
  implements MobBehaviorNode<MobActionTimingInput, MobActionTiming>
{
  private sequence = 0;

  constructor(
    private readonly seed: number,
    private readonly varianceRatio: number,
  ) {
    if (!Number.isSafeInteger(seed)) {
      throw new Error("mob action timing seed must be a safe integer");
    }
    validateVariance(varianceRatio, "action timing");
  }

  step(input: MobActionTimingInput): MobActionTiming {
    validateActionDelay(input.windupMs, "wind-up");
    validateActionDelay(input.cooldownMs, "cooldown");
    const action = this.sequence++;
    return Object.freeze({
      windupMs: sampleActionDelay(
        input.windupMs,
        this.seed,
        action,
        0xa4093822,
        this.varianceRatio,
      ),
      cooldownMs: sampleActionDelay(
        input.cooldownMs,
        this.seed,
        action,
        0x299f31d0,
        this.varianceRatio,
      ),
    });
  }

  reset(): void {
    this.sequence = 0;
  }
}

function validateActionDelay(value: number, label: string): void {
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`mob action ${label} must be finite and non-negative`);
  }
}

function sampleActionDelay(
  baseMs: number,
  seed: number,
  sequence: number,
  channel: number,
  variance: number,
): number {
  const sequenceSeed = seed ^ Math.imul(sequence + 1, 0x9e3779b1);
  return Math.round(
    baseMs * symmetricScale(deterministicUnitNoise(sequenceSeed, channel), variance),
  );
}

function validateVariance(value: number, label: string): void {
  if (!Number.isFinite(value) || value < 0 || value >= 1) {
    throw new Error(`mob ${label} variance must be finite and in [0, 1)`);
  }
}

function symmetricScale(unit: number, variance: number): number {
  return 1 + (unit * 2 - 1) * variance;
}

function deterministicUnitNoise(seed: number, channel: number): number {
  let value = (seed ^ channel) >>> 0;
  value = Math.imul(value ^ (value >>> 16), 0x7feb352d);
  value = Math.imul(value ^ (value >>> 15), 0x846ca68b);
  value = (value ^ (value >>> 16)) >>> 0;
  return value / 0x1_0000_0000;
}

/**
 * Small composable behaviour unit owned by an actor class.
 *
 * Runtime actors remain responsible for Phaser objects and applying movement. Nodes own one
 * decision and any memory needed to keep that decision stable across frames. That boundary keeps
 * gameplay rules independently testable without turning the scene into another state machine.
 */
export interface MobBehaviorNode<Input, Output> {
  step(input: Input): Output;
  reset(): void;
}

export type MobFacingConfig = Readonly<{
  /** Target movement inside this band cannot reverse a stationary actor's presentation. */
  targetDeadzonePx: number;
  /** Ignore floating-point residue when deriving presentation from applied movement. */
  movementEpsilonPx: number;
}>;

/**
 * Sole authority for a mob's visual facing.
 *
 * Movement nodes request destinations, but facing follows displacement that the terrain resolver
 * actually allowed. Combat may explicitly face a target, with a dead zone that prevents tiny
 * target-X crossings from reversing the sprite every frame. Keeping this memory in one node makes
 * blocked movement, combat recovery, and target jitter share one stable presentation policy.
 */
export class MobFacingNode {
  private direction: MobHorizontalDirection;

  constructor(
    initialDirection: MobHorizontalDirection,
    private readonly config: MobFacingConfig,
  ) {
    validateDirection(initialDirection);
    if (!Number.isFinite(config.targetDeadzonePx) || config.targetDeadzonePx < 0) {
      throw new Error("mob facing target dead zone must be finite and non-negative");
    }
    if (
      !Number.isFinite(config.movementEpsilonPx) ||
      config.movementEpsilonPx < 0
    ) {
      throw new Error("mob facing movement epsilon must be finite and non-negative");
    }
    this.direction = initialDirection;
  }

  get currentDirection(): MobHorizontalDirection {
    return this.direction;
  }

  /** Commit a deliberate pose change, such as an attack or hit reaction. */
  faceTarget(fromX: number, targetX: number): MobHorizontalDirection {
    if (!Number.isFinite(fromX) || !Number.isFinite(targetX)) {
      throw new Error("mob facing target coordinates must be finite");
    }
    const delta = targetX - fromX;
    if (Math.abs(delta) > this.config.targetDeadzonePx) {
      this.direction = delta > 0 ? 1 : -1;
    }
    return this.direction;
  }

  /** Follow only movement that survived navigation and was applied to the sprite. */
  followMovement(previousX: number, currentX: number): MobHorizontalDirection {
    if (!Number.isFinite(previousX) || !Number.isFinite(currentX)) {
      throw new Error("mob facing movement coordinates must be finite");
    }
    const delta = currentX - previousX;
    if (Math.abs(delta) > this.config.movementEpsilonPx) {
      this.direction = delta > 0 ? 1 : -1;
    }
    return this.direction;
  }

  /** Force a semantic reaction whose direction does not come from a target coordinate. */
  commit(direction: MobHorizontalDirection): MobHorizontalDirection {
    validateDirection(direction);
    this.direction = direction;
    return this.direction;
  }

  reset(direction: MobHorizontalDirection): void {
    validateDirection(direction);
    this.direction = direction;
  }
}

function validateDirection(direction: number): asserts direction is MobHorizontalDirection {
  if (direction !== -1 && direction !== 1) {
    throw new Error("mob facing direction must be -1 or 1");
  }
}

export type MobAwarenessInput = Readonly<{
  playerObserved: boolean;
  playerDefeated: boolean;
  playerWithinPursuitTerritory: boolean;
  atHome: boolean;
  homeReturnRequired: boolean;
  distancePx: number;
  nowMs: number;
  attackReadyAtMs: number;
}>;

export type MobDirective = MobIntent | "return_home";

/**
 * Stateful perception node with acquisition/retention hysteresis.
 *
 * Aggro radius answers whether a mob notices or retains the player, while pursuit territory
 * answers where it is allowed to hunt. Losing either condition enters an explicit return-home
 * mode until the actor reaches its home point; it never falls through to an arbitrary patrol
 * step at the pursuit boundary.
 */
export class MobAwarenessNode
  implements MobBehaviorNode<MobAwarenessInput, MobDirective>
{
  private readonly awareness = new Awareness();

  constructor(private readonly profile: AggressionProfile) {}

  step(input: MobAwarenessInput): MobDirective {
    if (
      input.playerObserved &&
      (!Number.isFinite(input.distancePx) || input.distancePx < 0)
    ) {
      throw new Error("mob awareness distance must be finite and non-negative");
    }
    // Every condition for engaging is the *profile's*, evaluated here; the
    // hysteresis around it is the `actor-ai` family's, and has no numbers in it
    // at all. Aggro radius answers whether a creature notices or retains you;
    // pursuit territory answers where it is allowed to hunt.
    const directive = this.awareness.step({
      canEngage:
        input.playerObserved &&
        !input.playerDefeated &&
        input.playerWithinPursuitTerritory &&
        input.distancePx <= this.profile.aggroRadiusPx,
      homeReturnRequired: input.homeReturnRequired,
      atHome: input.atHome,
    });
    if (directive === "engage") {
      return mobIntent({
        profile: this.profile,
        distancePx: input.distancePx,
        nowMs: input.nowMs,
        attackReadyAtMs: input.attackReadyAtMs,
        playerDefeated: false,
      });
    }
    return directive === "return" ? "return_home" : "hold";
  }

  reset(): void {
    this.awareness.reset();
  }
}

export type MobReturnHomeInput = Readonly<{
  mobX: number;
  deltaSeconds: number;
  speedScale: number;
}>;

export type MobReturnHomeDecision = Readonly<{
  targetX: number;
  direction: MobHorizontalDirection;
  arrived: boolean;
}>;

/** Converts the returning state into one stable destination: the actor's spawn home. */
export class MobReturnHomeNode
  implements MobBehaviorNode<MobReturnHomeInput, MobReturnHomeDecision>
{
  constructor(
    private readonly homeX: number,
    private readonly arrivalRadiusPx: number,
    private readonly speedPx: number,
  ) {
    if (!Number.isFinite(homeX)) {
      throw new Error("mob return home requires a finite home coordinate");
    }
    if (!Number.isFinite(arrivalRadiusPx) || arrivalRadiusPx < 0) {
      throw new Error("mob return home arrival radius must be finite and non-negative");
    }
    if (!Number.isFinite(speedPx) || speedPx <= 0) {
      throw new Error("mob return home speed must be positive and finite");
    }
  }

  step(input: MobReturnHomeInput): MobReturnHomeDecision {
    if (
      !Number.isFinite(input.mobX) ||
      !Number.isFinite(input.deltaSeconds) ||
      input.deltaSeconds < 0 ||
      !Number.isFinite(input.speedScale) ||
      input.speedScale <= 0
    ) {
      throw new Error("mob return home step requires valid finite movement inputs");
    }
    const delta = this.homeX - input.mobX;
    const direction: MobHorizontalDirection = delta >= 0 ? 1 : -1;
    if (Math.abs(delta) <= this.arrivalRadiusPx) {
      return Object.freeze({ targetX: this.homeX, direction, arrived: true });
    }
    const distance = Math.min(
      Math.abs(delta),
      this.speedPx * input.speedScale * input.deltaSeconds,
    );
    return Object.freeze({
      targetX: input.mobX + direction * distance,
      direction,
      arrived: distance === Math.abs(delta),
    });
  }

  reset(): void {}
}

export type MobPursuitTargetConfig = Readonly<{
  /** Half-width of the patrol corridor used when the player is on another terrain level. */
  inaccessibleSweepHalfWidthPx: number;
  /** Distance from a corridor endpoint that counts as arrival before selecting the other side. */
  arrivalRadiusPx: number;
}>;

export type MobPursuitTargetInput = Readonly<{
  mobX: number;
  playerX: number;
  attackLevelReachable: boolean;
  currentDirection: MobHorizontalDirection;
}>;

export type MobPursuitTargetDecision = Readonly<{
  targetX: number;
  direction: MobHorizontalDirection;
  sweeping: boolean;
}>;

/**
 * Chooses a stable horizontal pursuit target.
 *
 * A mob that cannot attack a player on another terrain level must not seek the player's exact X.
 * Doing so crosses that one coordinate on every step and reverses facing every frame. Instead the
 * node remembers one side of a corridor around the player, walks through the player's X toward
 * that endpoint, then selects the other side. Different mobs inherit their deterministic current
 * direction when entering the corridor, so a group does not collapse onto one target side.
 */
export class MobPursuitTargetNode
  implements MobBehaviorNode<MobPursuitTargetInput, MobPursuitTargetDecision>
{
  private sweepSide: MobHorizontalDirection | null = null;
  private readonly blockedSweepSides = new Set<MobHorizontalDirection>();

  constructor(private readonly config: MobPursuitTargetConfig) {
    if (
      !Number.isFinite(config.inaccessibleSweepHalfWidthPx) ||
      config.inaccessibleSweepHalfWidthPx <= 0
    ) {
      throw new Error("mob pursuit sweep half-width must be positive and finite");
    }
    if (
      !Number.isFinite(config.arrivalRadiusPx) ||
      config.arrivalRadiusPx < 0 ||
      config.arrivalRadiusPx >= config.inaccessibleSweepHalfWidthPx
    ) {
      throw new Error(
        "mob pursuit arrival radius must be finite, non-negative, and smaller than its sweep half-width",
      );
    }
  }

  step(input: MobPursuitTargetInput): MobPursuitTargetDecision {
    if (!Number.isFinite(input.mobX) || !Number.isFinite(input.playerX)) {
      throw new Error("mob pursuit requires finite actor coordinates");
    }

    if (input.attackLevelReachable) {
      this.reset();
      return Object.freeze({
        targetX: input.playerX,
        direction: directionToward(input.mobX, input.playerX, input.currentDirection),
        sweeping: false,
      });
    }

    this.sweepSide ??= input.currentDirection;
    let targetX = this.sweepTarget(input.playerX);
    if (this.reachedOrPassed(input.mobX, targetX, this.sweepSide)) {
      this.sweepSide = oppositeDirection(this.sweepSide);
      targetX = this.sweepTarget(input.playerX);
    }
    return Object.freeze({
      targetX,
      direction: directionToward(input.mobX, targetX, input.currentDirection),
      sweeping: true,
    });
  }

  /** A terrain face invalidates that endpoint; try the alternate once, then hold if both fail. */
  reportBlocked(): void {
    if (this.sweepSide === null) return;
    this.blockedSweepSides.add(this.sweepSide);
    const alternate = oppositeDirection(this.sweepSide);
    if (!this.blockedSweepSides.has(alternate)) this.sweepSide = alternate;
  }

  /** Successful travel proves the current side is viable again. */
  reportProgress(): void {
    if (this.sweepSide !== null) this.blockedSweepSides.delete(this.sweepSide);
  }

  reset(): void {
    this.sweepSide = null;
    this.blockedSweepSides.clear();
  }

  private sweepTarget(playerX: number): number {
    return playerX + this.sweepSide! * this.config.inaccessibleSweepHalfWidthPx;
  }

  private reachedOrPassed(
    mobX: number,
    targetX: number,
    side: MobHorizontalDirection,
  ): boolean {
    return side === 1
      ? mobX >= targetX - this.config.arrivalRadiusPx
      : mobX <= targetX + this.config.arrivalRadiusPx;
  }
}

function oppositeDirection(direction: MobHorizontalDirection): MobHorizontalDirection {
  return direction === 1 ? -1 : 1;
}

function directionToward(
  fromX: number,
  targetX: number,
  fallback: MobHorizontalDirection,
): MobHorizontalDirection {
  if (targetX === fromX) return fallback;
  return targetX > fromX ? 1 : -1;
}

export function mobAttackLevelReachable(input: Readonly<{
  mobFootY: number;
  playerFootY: number | null;
  tilePixels: number;
}>): boolean {
  return (
    input.playerFootY !== null &&
    attackFootLevelsOverlap(
      input.mobFootY,
      input.playerFootY,
      input.tilePixels,
    )
  );
}

export function constrainMobStrikeToAttackLevel(input: Readonly<{
  requestedIntent: MobIntent;
  mobFootY: number;
  playerFootY: number | null;
  tilePixels: number;
}>): MobIntent {
  if (input.requestedIntent !== "strike") return input.requestedIntent;
  if (mobAttackLevelReachable(input)) {
    return "strike";
  }
  return "chase";
}

/**
 * Recover locomotion after a finite attack/hurt strip has stopped on its last frame.
 *
 * Which of this genre's mob states are sustained is this genre's fact; the rule
 * that a sustained state whose animation is not running has to be restarted is
 * the `sideview/motion` family's, and it is the same rule any actor with
 * looping states needs.
 */
/** The mob states that are conditions rather than events, and so loop. */
const MOB_SUSTAINED_STATES = new Set(["wander", "chase", "return_home", "attack_recovery"]);

export function mobLocomotionAnimationNeedsRestart(input: Readonly<{
  state:
    | "wander"
    | "chase"
    | "return_home"
    | "attack_recovery"
    | "windup"
    | "hurt"
    | "dead";
  currentAnimationKey: string | null;
  idleAnimationKey: string;
  isPlaying: boolean;
}>): boolean {
  return motionNeedsRestart({
    sustained: MOB_SUSTAINED_STATES.has(input.state),
    currentAnimationKey: input.currentAnimationKey,
    sustainedAnimationKey: input.idleAnimationKey,
    isPlaying: input.isPlaying,
  });
}

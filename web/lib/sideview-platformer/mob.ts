// Mob controller (Phase 7).
//
// Owns:
//   - HP scaling: hp = ladderIndex + 1 by default          (TC-084)
//   - Wander state machine (idle/wander/hurt/dead)         (TC-083, TC-085)
//   - Hit reception → turn to the swing, hurt anim, drop   (TC-085, TC-086)
//   - Its own floating health bar, the player's widget at mob size
//   - Terrain faces and drops bound autonomous movement; knockback may cross drops
//
// Each mob is built around an existing Phaser sprite spawned by the scene
// from the pre-loaded mob_<i>_idle / mob_<i>_hurt frame strips.

import Phaser from "phaser";
import {
  MOB_DEATH_FADE_MS,
  MOB_KNOCKBACK_MS,
  sampleFixedMobHit,
  sampleMobSpawnFade,
  type FixedMobHitMotion,
} from "./fixed-motion";
import {
  DEATH_STRIP_FRAME_COUNT,
  DEATH_STRIP_FRAME_RATE,
  mobDeathPresentationPlan,
} from "./death-presentation";
import {
  FloatingHealthBar,
  MOB_HEALTH_BAR_STYLE,
  healthBarRevealedByDamage,
} from "./health-bar";
import { SCENE_CONTENT_DEPTH } from "./depths";
import {
  mobFullAlphaBounds,
  mobHitFacing,
  mobWorldLane,
  type MobRenderEnvelope,
} from "./mob-geometry";
import {
  type DamageResolution,
  type AggressionProfile,
  type MobAggression,
  aggressionProfile,
  resolveDamage,
} from "./combat";
import { anchorRepackedMotionFeet } from "@/lib/sideview/motion-playback";
import {
  constrainMobStrikeToAttackLevel,
  mobAttackLevelReachable,
  MobActionTimingNode,
  MobAwarenessNode,
  MobBehaviorVariation,
  MobFacingNode,
  mobLocomotionAnimationNeedsRestart,
  MobPursuitTargetNode,
  MobReturnHomeNode,
} from "./mob-behavior";
import {
  MobDeckLaneNode,
  MobNavigationPolicy,
  MobTerrainLaneNode,
  type MobLaneNode,
} from "./mob-navigation";
import type { TerrainWalkResolution } from "./vertical";

export type MobAiState =
  | "wander"
  | "chase"
  | "return_home"
  | "attack_recovery"
  | "windup"
  | "hurt"
  | "dead";

/**
 * Authoritative damage outcome plus the scene's existing transition aliases.
 *
 * `died` means this hit caused the death; `defeated` means the target is defeated after the
 * attempt. The distinction keeps a repeated call on a corpse from firing death lifecycle work a
 * second time while allowing new combat-text consumers to use the shared resolution contract.
 */
export type MobHitResult = DamageResolution &
  Readonly<{
    died: boolean;
    hpLeft: number;
  }>;

function mobHitResult(resolution: DamageResolution): MobHitResult {
  return Object.freeze({
    ...resolution,
    died: resolution.connected && resolution.defeated,
    hpLeft: resolution.hpAfter,
  });
}

/**
 * The floating deck a creature was placed on.
 *
 * Geometry only: where the slab starts, where it ends, and how high its top is. A body given one
 * of these walks it end to end and turns at both edges; a body given none walks the floor.
 */
export type MobDeckFooting = Readonly<{
  id: string;
  leftX: number;
  rightX: number;
  surfaceY: number;
}>;

export interface MobOpts {
  scene: Phaser.Scene;
  ladderIndex: number;
  /** Optional authored max health; omitted preserves the established ladder-index rule. */
  startingHealth?: number;
  spawnCol: number;
  tilePx: number;
  worldWidthPx: number;
  baselineY: number;
  heightFn: (col: number) => number;
  /** Deck to stand on; absent stands the creature on the terrain lane under `spawnCol`. */
  deck?: MobDeckFooting;
  speedPx?: number;
  spriteHeightPx: number;
  idleAnimKey: string;
  hurtTextureKey: string;
  renderEnvelope: MobRenderEnvelope;
  hurtFrames?: number;
  /** Optional current aggression archetype; null selects the baseline profile. */
  aggression?: MobAggression | null;
  /** Texture key of this mob's attack strip, when the run drew one. */
  attackTextureKey?: string;
  /** Texture key of this mob's terminal strip, when the run drew one. */
  deathTextureKey?: string;
  /** Use explicit simulation time instead of Phaser's wall-clock tween state. */
  fixedStepMotion?: boolean;
  /** Stable per-instance seed for bounded movement variation. */
  behaviorSeed?: number;
  /** When the creature was placed, for the fade-in; absent places it at full opacity. */
  spawnedAtMs?: number;
}

const DEFAULT_SPEED = 36;
const HURT_DURATION_MS = 600;
const KNOCKBACK_PX = 80;
const FACING_TARGET_DEADZONE_TILES = 0.125;
const FACING_MOVEMENT_EPSILON_PX = 0.01;

export class Mob {
  readonly sprite: Phaser.GameObjects.Sprite;
  readonly ladderIndex: number;
  hp: number;
  state: MobAiState = "wander";
  /** Set on the frame a wind-up completes, for the scene to resolve into player damage. */
  pendingStrike: { damage: number; dirSign: 1 | -1 } | null = null;
  private readonly profile: AggressionProfile;
  private readonly pursuitTarget: MobPursuitTargetNode;
  private readonly awareness: MobAwarenessNode;
  private readonly navigation: MobLaneNode;
  private readonly navigationPolicy: MobNavigationPolicy;
  private returnHome: MobReturnHomeNode;
  private readonly actionTiming: MobActionTimingNode;
  private readonly movementSpeedScale: number;
  private readonly initialDirSign: 1 | -1;
  private readonly facing: MobFacingNode;
  private readonly maxHp: number;
  private attackReadyAtMs = 0;
  private strikeLandsAtMs = 0;
  private playerX: number | null = null;
  private playerY: number | null = null;
  private playerDefeated = false;
  private readonly attackAnim: string | null;
  private readonly deathAnim: string | null;
  private opts: MobOpts;
  private spawnX: number;
  private spawnY: number;
  private readonly spawnColumn: number;
  private homeX: number;
  private patrolDirection: 1 | -1;
  private hurtUntil = 0;
  private spawnFadeFrom: number | null;
  private idleAnim: string;
  private hurtAnim: string;
  private fixedHitMotion?: FixedMobHitMotion;
  private renderEnvelope: MobRenderEnvelope;
  private readonly healthBar: FloatingHealthBar;

  constructor(opts: MobOpts) {
    this.opts = opts;
    this.ladderIndex = opts.ladderIndex;
    const maxHp = opts.startingHealth ?? opts.ladderIndex + 1;
    if (!Number.isSafeInteger(maxHp) || maxHp <= 0) {
      throw new Error("mob startingHealth must be a positive integer");
    }
    this.maxHp = maxHp;
    this.hp = maxHp;
    this.profile = aggressionProfile(opts.aggression);
    this.spawnFadeFrom = opts.spawnedAtMs ?? null;
    this.awareness = new MobAwarenessNode(this.profile);
    const behaviorSeed =
      opts.behaviorSeed ??
      Math.imul(opts.spawnCol + 1, 0x45d9f3b) ^
        Math.imul(opts.ladderIndex + 1, 0x119de1f3);
    const variation = new MobBehaviorVariation(behaviorSeed, {
      movementSpeedVarianceRatio: this.profile.movementSpeedVarianceRatio,
      pursuitSweepVarianceRatio: this.profile.pursuitSweepVarianceRatio,
    });
    this.movementSpeedScale = variation.movementSpeedScale;
    this.initialDirSign = variation.initialDirection;
    this.patrolDirection = this.initialDirSign;
    this.facing = new MobFacingNode(this.initialDirSign, {
      targetDeadzonePx: opts.tilePx * FACING_TARGET_DEADZONE_TILES,
      movementEpsilonPx: FACING_MOVEMENT_EPSILON_PX,
    });
    this.actionTiming = new MobActionTimingNode(
      behaviorSeed,
      this.profile.actionTimingVarianceRatio,
    );
    this.pursuitTarget = new MobPursuitTargetNode({
      inaccessibleSweepHalfWidthPx:
        this.profile.inaccessibleSweepHalfWidthPx * variation.pursuitSweepScale,
      arrivalRadiusPx: this.profile.pursuitArrivalRadiusPx,
    });
    // Null when the run drew no attack strip. The swing still happens - the wind-up, the damage
    // and the cooldown are behaviour, not artwork - it simply plays without a dedicated pose.
    this.attackAnim = opts.attackTextureKey ? `${opts.attackTextureKey}_anim` : null;
    this.deathAnim = opts.deathTextureKey
      ? `${opts.deathTextureKey}_anim`
      : null;

    const navigationPolicy = new MobNavigationPolicy(opts.tilePx);
    this.navigationPolicy = navigationPolicy;
    this.renderEnvelope = opts.renderEnvelope;
    const lane = mobWorldLane({
      candidateSpawnX: opts.spawnCol * opts.tilePx + opts.tilePx / 2,
      wanderExtent: navigationPolicy.patrolHomeRadiusPx,
      worldWidth: opts.worldWidthPx,
      renderedHalfWidth: this.renderEnvelope.halfWidth,
    });
    // The lane comes before the body, because the lane is what decides where the body may stand:
    // the world's edges bound a spawn on the floor, a deck's own edges bound one on a ledge, and
    // in both cases the placed home is the answer rather than the requested column.
    this.navigation = opts.deck
      ? new MobDeckLaneNode({
          deckId: opts.deck.id,
          spawnX: lane.spawnX,
          deckLeftX: opts.deck.leftX,
          deckRightX: opts.deck.rightX,
          deckSurfaceY: opts.deck.surfaceY,
          renderedHalfWidth: this.renderEnvelope.halfWidth,
          policy: navigationPolicy,
        })
      : new MobTerrainLaneNode({
          spawnColumn: Math.floor(lane.spawnX / opts.tilePx),
          spawnX: lane.spawnX,
          tilePixels: opts.tilePx,
          worldWidthPx: opts.worldWidthPx,
          baselineY: opts.baselineY,
          renderedHalfWidth: this.renderEnvelope.halfWidth,
          heightAtColumn: opts.heightFn,
          policy: navigationPolicy,
        });
    const spawnX = this.navigation.homeX;
    this.spawnX = spawnX;
    this.spawnColumn = Math.floor(spawnX / opts.tilePx);
    this.homeX = spawnX;
    this.returnHome = new MobReturnHomeNode(
      spawnX,
      navigationPolicy.returnHomeArrivalRadiusPx,
      navigationPolicy.returnHomeSpeedPx,
    );
    const surfaceY = this.navigation.surfaceYAt(spawnX);
    this.spawnY = surfaceY;

    // Build the idle anim if it doesn't exist (scene may have made it; harmless).
    this.idleAnim = opts.idleAnimKey;
    this.hurtAnim = `${opts.hurtTextureKey}_anim`;
    const scene = opts.scene;
    if (
      !scene.anims.exists(this.hurtAnim) &&
      scene.textures.exists(opts.hurtTextureKey)
    ) {
      const fcount = opts.hurtFrames ?? 4;
      scene.anims.create({
        key: this.hurtAnim,
        frames: Array.from({ length: fcount }, (_, f) => ({
          key: opts.hurtTextureKey,
          frame: f,
        })),
        frameRate: Math.ceil((fcount * 1000) / HURT_DURATION_MS),
        repeat: 0,
      });
    }
    if (
      this.deathAnim &&
      opts.deathTextureKey &&
      !scene.anims.exists(this.deathAnim) &&
      scene.textures.exists(opts.deathTextureKey)
    ) {
      scene.anims.create({
        key: this.deathAnim,
        frames: Array.from({ length: DEATH_STRIP_FRAME_COUNT }, (_, frame) => ({
          key: opts.deathTextureKey!,
          frame,
        })),
        frameRate: DEATH_STRIP_FRAME_RATE,
        repeat: 0,
      });
    }

    const sprite = scene.add.sprite(spawnX, surfaceY, opts.idleAnimKey, 0);
    sprite.setOrigin(0.5, 1.0);
    const tex = scene.textures.get(opts.idleAnimKey);
    const f0 = tex.get(0);
    const aspect = (f0?.width ?? 1) / Math.max(1, f0?.height ?? 1);
    sprite.setDisplaySize(opts.spriteHeightPx * aspect, opts.spriteHeightPx);
    sprite.setDepth(SCENE_CONTENT_DEPTH.mob);
    if (scene.anims.exists(opts.idleAnimKey)) sprite.play(opts.idleAnimKey);
    anchorRepackedMotionFeet(sprite);
    this.sprite = sprite;

    this.renderFacing();

    // The player's own widget at mob size, so a fight is read the same way from both sides. It
    // is the mob's to own rather than the scene's: a mob is created and destroyed per stage and
    // fades out on death, and a bar tracked in a parallel list beside it is a bar that
    // eventually outlives its body.
    this.healthBar = new FloatingHealthBar(scene, this.hp, MOB_HEALTH_BAR_STYLE);
    this.syncHealthBar();
  }

  /**
   * Put the bar under this mob's current feet.
   *
   * Called after every step rather than inside it, because the step moves the sprite through
   * several branches - wander, chase, knockback replay - and anchoring within any one of them
   * would leave the others a frame behind the body.
   */
  private syncHealthBar(): void {
    this.healthBar.update({
      hp: this.hp,
      maxHp: this.maxHp,
      invulnerable: false,
      actorX: this.sprite.x,
      actorFootY: this.sprite.y,
    });
    this.healthBar.setVisible(this.healthBarShouldShow(this.sprite.visible));
  }

  /**
   * Whether this mob's bar is drawn at all.
   *
   * Three conditions, in the order they stop mattering: a hidden body has no readout, a dead one
   * has nothing left to report, and an untouched one has nothing to report yet. The last is why
   * a bar appears at the first hit rather than at spawn - the player learns a creature's health
   * by attacking it, and a route lined with full capsules reads as HUD scattered through the
   * level instead of as feedback from the fight they are actually in.
   */
  private healthBarShouldShow(spriteVisible: boolean): boolean {
    return (
      spriteVisible &&
      this.isAlive() &&
      healthBarRevealedByDamage({ hp: this.hp, maxHp: this.maxHp })
    );
  }

  update(dtMs: number, nowMs: number) {
    this.step(dtMs, nowMs);
    this.syncHealthBar();
  }

  private step(dtMs: number, nowMs: number) {
    if (this.spawnFadeFrom !== null) {
      const fade = sampleMobSpawnFade(this.spawnFadeFrom, nowMs);
      this.sprite.alpha = fade.alpha;
      if (fade.complete) this.spawnFadeFrom = null;
    }
    if (this.fixedHitMotion) {
      const sample = sampleFixedMobHit(this.fixedHitMotion, nowMs);
      this.sprite.x = sample.x;
      this.sprite.alpha = sample.alpha;
      this.sprite.setVisible(!sample.hidden);
      if (sample.complete) this.fixedHitMotion = undefined;
    }
    if (this.state === "dead") return;
    const dt = dtMs / 1000;

    if (this.state === "hurt") {
      if (nowMs >= this.hurtUntil) {
        this.adoptForcedLandingTerritory();
        this.state = "wander";
        this.ensureLocomotionAnimation();
      } else {
        return; // frozen during hurt
      }
    }

    // A wind-up already in flight resolves before anything else is decided: the blow was
    // committed when it started, so backing out of range dodges the *damage* (the scene re-checks
    // distance) but never cancels the animation. A creature that snaps out of its own swing
    // mid-frame reads as a glitch rather than as a miss.
    if (this.state === "windup") {
      if (nowMs >= this.strikeLandsAtMs) {
        this.pendingStrike = {
          damage: this.profile.damage,
          dirSign: this.facing.currentDirection,
        };
        this.state =
          this.playerX === null ? "wander" : "attack_recovery";
      } else {
        this.snapFeet();
        return;
      }
    }

    const directive = this.awareness.step({
      playerObserved: this.playerX !== null,
      playerDefeated: this.playerDefeated,
      playerWithinPursuitTerritory:
        this.playerX !== null && this.navigation.containsPursuitX(this.playerX),
      atHome:
        Math.abs(this.sprite.x - this.homeX) <=
        this.navigationPolicy.returnHomeArrivalRadiusPx,
      homeReturnRequired: !this.navigation.containsPatrolX(this.sprite.x),
      distancePx:
        this.playerX === null ? 0 : Math.abs(this.playerX - this.sprite.x),
      nowMs,
      attackReadyAtMs: this.attackReadyAtMs,
    });
    if (directive === "return_home") {
      this.pursuitTarget.reset();
      this.state = "return_home";
      this.ensureLocomotionAnimation();
      const returning = this.returnHome.step({
        mobX: this.sprite.x,
        deltaSeconds: dt,
        speedScale: this.movementSpeedScale,
      });
      this.walkTo(returning.targetX, "pursuit");
      this.snapFeet();
      return;
    }
    const intent = constrainMobStrikeToAttackLevel({
      requestedIntent: directive,
      mobFootY: this.sprite.y,
      playerFootY: this.playerY,
      tilePixels: this.opts.tilePx,
    });

    if (intent === "strike" && this.playerX !== null) {
      const actionTiming = this.actionTiming.step({
        windupMs: this.profile.windupMs,
        cooldownMs: this.profile.cooldownMs,
      });
      this.facing.faceTarget(this.sprite.x, this.playerX);
      this.renderFacing();
      this.state = "windup";
      this.strikeLandsAtMs = nowMs + actionTiming.windupMs;
      this.attackReadyAtMs = nowMs + actionTiming.cooldownMs;
      if (this.attackAnim && this.opts.scene.anims.exists(this.attackAnim)) {
        this.sprite.play(this.attackAnim, true);
        anchorRepackedMotionFeet(this.sprite);
      }
      this.snapFeet();
      return;
    }

    if (intent === "attack_recovery") {
      this.pursuitTarget.reset();
      this.state = "attack_recovery";
      this.ensureLocomotionAnimation();
      this.snapFeet();
      return;
    }

    if (intent === "chase" && this.playerX !== null) {
      const pursuit = this.pursuitTarget.step({
        mobX: this.sprite.x,
        playerX: this.playerX,
        attackLevelReachable: mobAttackLevelReachable({
          mobFootY: this.sprite.y,
          playerFootY: this.playerY,
          tilePixels: this.opts.tilePx,
        }),
        currentDirection: this.facing.currentDirection,
      });
      const speed = this.profile.chaseSpeedPx * this.movementSpeedScale;
      const next = this.sprite.x + pursuit.direction * speed * dt;
      const blocked = this.walkTo(next, "pursuit");
      if (blocked && pursuit.sweeping) {
        this.pursuitTarget.reportBlocked();
      } else if (pursuit.sweeping) {
        this.pursuitTarget.reportProgress();
      }
      if (this.state !== "chase") this.state = "chase";
      this.ensureLocomotionAnimation();
      this.snapFeet();
      return;
    }

    if (intent === "flee" && this.playerX !== null) {
      this.pursuitTarget.reset();
      const toward = this.playerX >= this.sprite.x ? 1 : -1;
      const fleeDirection = (toward === 1 ? -1 : 1) as 1 | -1;
      const next =
        this.sprite.x +
        fleeDirection *
          this.profile.chaseSpeedPx *
          this.movementSpeedScale *
          dt;
      this.walkTo(next, "pursuit");
      if (this.state !== "chase") this.state = "chase";
      this.ensureLocomotionAnimation();
      this.snapFeet();
      return;
    }

    // Nothing nearby: use the current deterministic patrol default.
    this.pursuitTarget.reset();
    this.returnHome.reset();
    if (this.state !== "wander") this.state = "wander";
    this.ensureLocomotionAnimation();
    const speed = (this.opts.speedPx ?? DEFAULT_SPEED) * this.movementSpeedScale;
    // A face turns a patrol the same way the end of its lane does. Reversing rather than
    // standing still matters because a lane that runs into a rise would otherwise leave the
    // creature pressed against it for the rest of the run, which reads as a stuck mob rather
    // than as one that cannot climb.
    const blocked = this.walkTo(
      this.sprite.x + this.patrolDirection * speed * dt,
      "patrol",
    );
    if (blocked) {
      this.patrolDirection =
        this.patrolDirection === 1 ? -1 : 1;
    }

    this.snapFeet();
  }

  /**
   * Walk toward `nextX`, stopped by any terrain face standing above the feet.
   *
   * The same `resolveTerrainWalk` the player is bound by, and for the same reason: the
   * heightfield steps in whole tiles, so a rise is a wall and the way up is a jump. A mob has no
   * jump, which is exactly the point - it patrols and hunts on the shelf it was spawned on, and
   * turns at the edges of it.
   *
   * Before this, horizontal motion wrote `sprite.x` directly and `snapFeet` lifted the creature
   * onto whatever column it had landed in. Downhill that reads as walking off a ledge; uphill it
   * reads as a mob levitating up a cliff face, and only ever when chasing, because a wander lane
   * is short enough to rarely cross a rise. The physics were never ignored during a chase - they
   * were never applied at all, and the chase was simply the one behaviour that walked far enough
   * to show it.
   */
  private walkTo(
    nextX: number,
    boundary: "patrol" | "pursuit" = "pursuit",
  ): boolean {
    const previousX = this.sprite.x;
    const walk = this.resolveWalk(nextX, boundary, false);
    this.sprite.x = walk.x;
    this.facing.followMovement(previousX, this.sprite.x);
    this.renderFacing();
    return walk.blocked;
  }

  /** Apply the facing node's stable decision; no behavior branch writes sprite mirroring. */
  private renderFacing(): void {
    this.sprite.setFlipX(this.facing.currentDirection === -1);
  }

  /** The same resolution without applying it, for a move that is not the mob's own step. */
  private resolveWalk(
    nextX: number,
    boundary: "patrol" | "pursuit" | "world" = "world",
    allowDescents = true,
  ): TerrainWalkResolution {
    return this.navigation.walk(
      this.sprite.x,
      nextX,
      boundary,
      allowDescents,
    );
  }

  private ensureLocomotionAnimation(): void {
    if (!this.opts.scene.anims.exists(this.idleAnim)) return;
    if (
      !mobLocomotionAnimationNeedsRestart({
        state: this.state,
        currentAnimationKey: this.sprite.anims.currentAnim?.key ?? null,
        idleAnimationKey: this.idleAnim,
        isPlaying: this.sprite.anims.isPlaying,
      })
    ) {
      return;
    }
    this.sprite.play(this.idleAnim, true);
    anchorRepackedMotionFeet(this.sprite);
  }

  /** Keep the mob standing on the terrain column it currently occupies. */
  private snapFeet(): void {
    this.sprite.y = this.navigation.surfaceYAt(this.sprite.x);
  }

  /**
   * Rebase local navigation after player knockback carries the mob over a drop.
   *
   * Autonomous movement cannot cross that drop in reverse, so retaining the original upper
   * shelf as home creates an impossible goal. The terrain node changes home only when the landing
   * coordinate is disconnected; ordinary knockback on the same shelf leaves territory unchanged.
   */
  private adoptForcedLandingTerritory(): void {
    if (!this.navigation.rehomeAfterForcedDisplacement(this.sprite.x)) return;
    this.homeX = this.navigation.homeX;
    this.returnHome = new MobReturnHomeNode(
      this.homeX,
      this.navigationPolicy.returnHomeArrivalRadiusPx,
      this.navigationPolicy.returnHomeSpeedPx,
    );
    this.awareness.reset();
    this.pursuitTarget.reset();
    this.snapFeet();
  }

  /** Tell the mob where the player is. Null means "no player to react to". */
  observePlayer(
    x: number | null,
    footY: number | null,
    defeated: boolean,
  ): void {
    if ((x === null) !== (footY === null)) {
      throw new Error("mob player observation requires both coordinates or neither");
    }
    this.playerX = x;
    this.playerY = footY;
    this.playerDefeated = defeated;
  }

  /** Take the strike this mob committed to, if any, clearing it. */
  consumeStrike(): { damage: number; dirSign: 1 | -1 } | null {
    const strike = this.pendingStrike;
    this.pendingStrike = null;
    return strike;
  }

  /**
   * Apply one blow and report the complete before/after resolution.
   *
   * The amount is the caller's, because whether a swing rolled critical is decided by the combat
   * policy the scene holds, not by the creature absorbing it. It defaults to the single point every
   * player swing was worth before criticals existed.
   */
  takeHit(
    nowMs: number,
    knockbackDir: 1 | -1 = 1,
    amount = 1,
    critical = false,
    knockbackScale = 1,
  ): MobHitResult {
    if (this.state === "dead") {
      return mobHitResult(resolveDamage(this.hp, amount, true, critical));
    }
    const resolution = resolveDamage(this.hp, amount, false, critical);
    this.hp = resolution.hpAfter;
    const hitResult = mobHitResult(resolution);
    // Knockback is the one movement allowed to cross a descending shelf edge. It remains clamped
    // to the patrol lane and cannot push a creature up a raised face; when pushed into a pit the
    // hurt interval carries the horizontal reaction before normal terrain snapping resumes.
    // The scale is the caller's: the later blows of a multi-hit pass zero, so a combo shoves
    // once rather than three times and the creature stays inside the band that is hitting it.
    const targetX = this.resolveWalk(
      this.sprite.x + knockbackDir * KNOCKBACK_PX * knockbackScale,
      "world",
      true,
    ).x;
    // Turn to look at whoever swung. A mob that keeps facing its patrol
    // direction while being knocked backwards reads as scenery taking damage.
    // Wander resumes along the same heading, so the turn is a reaction rather
    // than a one-frame flicker the next update undoes.
    this.facing.commit(mobHitFacing(knockbackDir));
    this.renderFacing();
    const died = hitResult.died;
    if (this.opts.fixedStepMotion) {
      this.fixedHitMotion = {
        startedMs: nowMs,
        startX: this.sprite.x,
        targetX,
        died,
      };
    } else {
      this.opts.scene.tweens.add({
        targets: this.sprite,
        x: targetX,
        duration: MOB_KNOCKBACK_MS,
        ease: "Cubic.easeOut",
      });
    }
    if (died) {
      this.state = "dead";
      // The bar goes at the killing blow rather than fading with the body. An empty capsule
      // riding a corpse out says nothing the corpse does not already say, and a readout that
      // lingers over a mob the player has stopped caring about is the clutter that makes
      // per-mob bars a bad idea in the first place.
      this.healthBar.setVisible(false);
      this.startDeathPresentation();
      return hitResult;
    }
    // Non-fatal: play hurt anim once.
    this.state = "hurt";
    this.hurtUntil = nowMs + HURT_DURATION_MS;
    if (this.opts.scene.anims.exists(this.hurtAnim)) {
      this.sprite.play(this.hurtAnim, true);
      anchorRepackedMotionFeet(this.sprite);
    }
    // Redrawn here, not left to the next step: the blow and the bar dropping have to be the
    // same event on screen, and the mob is frozen for the hurt window that follows.
    this.syncHealthBar();
    return hitResult;
  }

  /** Play an optional terminal strip before preserving the established fade and disposal. */
  private startDeathPresentation(): void {
    const plan = mobDeathPresentationPlan({
      deathAnimationAvailable:
        this.deathAnim !== null && this.opts.scene.anims.exists(this.deathAnim),
      fixedStepMotion: this.opts.fixedStepMotion === true,
    });
    if (plan.playAnimation && this.deathAnim) {
      this.sprite.play(this.deathAnim, true);
      anchorRepackedMotionFeet(this.sprite);
    }
    if (this.opts.fixedStepMotion) return;
    if (plan.fadeDelayMs > 0) {
      this.opts.scene.time.delayedCall(plan.fadeDelayMs, () => this.startDeathFade());
      return;
    }
    this.startDeathFade();
  }

  private startDeathFade(): void {
    if (!this.sprite.active) return;
    this.opts.scene.tweens.add({
      targets: this.sprite,
      alpha: 0,
      duration: MOB_DEATH_FADE_MS,
      onComplete: () => this.destroy(),
    });
  }

  isAlive(): boolean {
    return this.state !== "dead";
  }

  /**
   * Fill the body white, or restore it.
   *
   * The impact presentation decides *when* from simulation time; this only knows *how*, which in
   * Phaser 4 is a colour plus a separate tint mode. Clearing the tint resets the mode as well, so
   * the off branch needs no second call. A retired sprite is left alone rather than touched.
   */
  setFlash(on: boolean): void {
    if (!this.sprite.active) return;
    if (on) this.sprite.setTint(0xffffff).setTintMode(Phaser.TintModes.FILL);
    else this.sprite.clearTint();
  }

  /** Show or hide the whole actor - body and readout - as one thing. */
  setVisible(visible: boolean): void {
    this.sprite.setVisible(visible);
    this.healthBar.setVisible(this.healthBarShouldShow(visible));
  }

  /**
   * Retire the mob.
   *
   * Two objects now, so callers may not reach past this into `sprite.destroy()`: a stage torn
   * down that way would leave one floating bar per mob hanging in the world the player
   * travelled to.
   */
  destroy(): void {
    this.sprite.destroy();
    this.healthBar.destroy();
  }

  /** Restore the exact frame-zero state before deterministic automation starts. */
  resetAutomationState(): void {
    this.hp = this.maxHp;
    this.state = "wander";
    this.patrolDirection = this.initialDirSign;
    this.facing.reset(this.initialDirSign);
    this.hurtUntil = 0;
    this.attackReadyAtMs = 0;
    this.strikeLandsAtMs = 0;
    this.pendingStrike = null;
    this.playerX = null;
    this.playerY = null;
    this.playerDefeated = false;
    this.awareness.reset();
    this.actionTiming.reset();
    this.pursuitTarget.reset();
    this.navigation.restoreHome(this.spawnColumn, this.spawnX);
    this.homeX = this.spawnX;
    this.returnHome = new MobReturnHomeNode(
      this.homeX,
      this.navigationPolicy.returnHomeArrivalRadiusPx,
      this.navigationPolicy.returnHomeSpeedPx,
    );
    this.fixedHitMotion = undefined;
    this.sprite.setPosition(this.spawnX, this.spawnY);
    this.renderFacing();
    this.sprite.setAlpha(1);
    this.sprite.setVisible(true);
    this.sprite.anims.stop();
    this.sprite.setTexture(this.opts.idleAnimKey, 0);
    if (this.opts.scene.anims.exists(this.idleAnim)) {
      this.sprite.play(this.idleAnim, true);
    }
    const f0 = this.opts.scene.textures.get(this.opts.idleAnimKey).get(0);
    const aspect = (f0?.width ?? 1) / Math.max(1, f0?.height ?? 1);
    this.sprite.setDisplaySize(
      this.opts.spriteHeightPx * aspect,
      this.opts.spriteHeightPx,
    );
    anchorRepackedMotionFeet(this.sprite);
    this.healthBar.reset(this.hp, this.maxHp);
    this.syncHealthBar();
  }

  snapshot() {
    return {
      ladderIndex: this.ladderIndex,
      hp: this.hp,
      maxHp: this.maxHp,
      state: this.state,
      aggression: this.opts.aggression ?? null,
      x: this.sprite.x,
      y: this.sprite.y,
      alive: this.isAlive(),
      visible: this.sprite.visible && this.sprite.alpha > 0,
      renderBounds: mobFullAlphaBounds(
        this.sprite.x,
        this.sprite.y,
        this.renderEnvelope,
      ),
      liveSprite: {
        y: this.sprite.y,
        originY: this.sprite.originY,
        scaleY: this.sprite.scaleY,
        displayHeight: this.sprite.displayHeight,
        frameHeight: this.sprite.frame?.height ?? 0,
        frameName: String(this.sprite.frame?.name ?? ""),
        drawnBottom: this.sprite.y + this.sprite.displayHeight * (1 - this.sprite.originY),
        drawnTop:
          this.sprite.y - this.sprite.displayHeight * this.sprite.originY,
      },
    };
  }
}

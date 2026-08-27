// Mob controller (Phase 7).
//
// Owns:
//   - HP scaling: hp = ladderIndex + 1 by default          (TC-084)
//   - Wander state machine (idle/wander/hurt/dead)         (TC-083, TC-085)
//   - Hit reception → turn to the swing, hurt anim, drop   (TC-085, TC-086)
//   - Its own floating health bar, the player's widget at mob size
//   - Terrain faces as walls: a mob walks off a ledge but never up one
//
// Each mob is built around an existing Phaser sprite spawned by the scene
// from the pre-loaded mob_<i>_idle / mob_<i>_hurt frame strips.

import Phaser from "phaser";
import {
  MOB_DEATH_FADE_MS,
  MOB_KNOCKBACK_MS,
  sampleFixedMobHit,
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
} from "./health-bar";
import { SCENE_CONTENT_DEPTH } from "./layers";
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
  mobIntent,
  resolveDamage,
} from "./combat";
import { terrainSurfaceY } from "./terrain";
import {
  resolveTerrainWalk,
  type TerrainWalkResolution,
} from "./vertical";

export type MobAiState = "wander" | "chase" | "windup" | "hurt" | "dead";

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
  /** Wander extent in pixels around spawnCol*tilePx. */
  wanderExtentPx?: number;
  /** Maximum chase displacement in pixels from the spawn/home point. */
  pursuitLeashPx?: number;
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
}

const DEFAULT_WANDER_PX = 100;
const DEFAULT_SPEED = 36;
const HURT_DURATION_MS = 600;
const KNOCKBACK_PX = 80;

/**
 * How far a roused mob may stray from its patrol lane while chasing, in pixels.
 *
 * Without a leash a `relentless` creature follows the player across the whole stage and the
 * hunting ground becomes one accumulating train of mobs. The lane is also what `mobWorldLane`
 * clamped so the full alpha envelope stays inside the world, so wandering outside it would put
 * artwork through the world edge.
 */
const CHASE_LEASH_PX = 384;

export class Mob {
  readonly sprite: Phaser.GameObjects.Sprite;
  readonly ladderIndex: number;
  hp: number;
  state: MobAiState = "wander";
  /** Set on the frame a wind-up completes, for the scene to resolve into player damage. */
  pendingStrike: { damage: number; dirSign: 1 | -1 } | null = null;
  private readonly profile: AggressionProfile;
  private readonly maxHp: number;
  private attackReadyAtMs = 0;
  private strikeLandsAtMs = 0;
  private playerX: number | null = null;
  private playerDefeated = false;
  private readonly attackAnim: string | null;
  private readonly deathAnim: string | null;
  private opts: MobOpts;
  private spawnX: number;
  private spawnY: number;
  private wanderMin: number;
  private wanderMax: number;
  private pursuitMin: number;
  private pursuitMax: number;
  private dirSign: 1 | -1 = 1;
  private hurtUntil = 0;
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
    // Null when the run drew no attack strip. The swing still happens - the wind-up, the damage
    // and the cooldown are behaviour, not artwork - it simply plays without a dedicated pose.
    this.attackAnim = opts.attackTextureKey ? `${opts.attackTextureKey}_anim` : null;
    this.deathAnim = opts.deathTextureKey
      ? `${opts.deathTextureKey}_anim`
      : null;

    const ext = opts.wanderExtentPx ?? DEFAULT_WANDER_PX;
    this.renderEnvelope = opts.renderEnvelope;
    const lane = mobWorldLane({
      candidateSpawnX: opts.spawnCol * opts.tilePx + opts.tilePx / 2,
      wanderExtent: ext,
      worldWidth: opts.worldWidthPx,
      renderedHalfWidth: this.renderEnvelope.halfWidth,
    });
    const spawnX = lane.spawnX;
    this.spawnX = spawnX;
    this.wanderMin = lane.wanderMin;
    this.wanderMax = lane.wanderMax;
    // Authored pursuit leashes are industry-standard home radii, not an extension beyond the
    // patrol lane. An omitted optional value uses the current deterministic patrol-edge default.
    // Both forms are clamped to the render-safe world envelope so visible alpha stays on-map.
    const pursuitMin =
      opts.pursuitLeashPx === undefined
        ? lane.wanderMin - CHASE_LEASH_PX
        : spawnX - opts.pursuitLeashPx;
    const pursuitMax =
      opts.pursuitLeashPx === undefined
        ? lane.wanderMax + CHASE_LEASH_PX
        : spawnX + opts.pursuitLeashPx;
    this.pursuitMin = Math.max(this.renderEnvelope.halfWidth, pursuitMin);
    this.pursuitMax = Math.min(
      opts.worldWidthPx - this.renderEnvelope.halfWidth,
      pursuitMax,
    );

    const colH = opts.heightFn(opts.spawnCol);
    const surfaceY = terrainSurfaceY(colH, opts.tilePx, opts.baselineY);
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
    this.sprite = sprite;

    // Random initial direction based on ladder index for determinism.
    this.dirSign = opts.ladderIndex % 2 === 0 ? 1 : -1;

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
    this.healthBar.setVisible(this.sprite.visible && this.state !== "dead");
  }

  update(dtMs: number, nowMs: number) {
    this.step(dtMs, nowMs);
    this.syncHealthBar();
  }

  private step(dtMs: number, nowMs: number) {
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
        this.state = "wander";
        if (this.opts.scene.anims.exists(this.idleAnim)) {
          this.sprite.play(this.idleAnim, true);
        }
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
        this.pendingStrike = { damage: this.profile.damage, dirSign: this.dirSign };
        this.state = this.playerX === null ? "wander" : "chase";
      } else {
        this.snapFeet();
        return;
      }
    }

    const intent =
      this.playerX === null
        ? "hold"
        : mobIntent({
            profile: this.profile,
            distancePx: Math.abs(this.playerX - this.sprite.x),
            nowMs,
            attackReadyAtMs: this.attackReadyAtMs,
            playerDefeated: this.playerDefeated,
          });

    if (intent === "strike" && this.playerX !== null) {
      this.dirSign = this.playerX >= this.sprite.x ? 1 : -1;
      this.sprite.setFlipX(this.dirSign === -1);
      this.state = "windup";
      this.strikeLandsAtMs = nowMs + this.profile.windupMs;
      this.attackReadyAtMs = nowMs + this.profile.cooldownMs;
      if (this.attackAnim && this.opts.scene.anims.exists(this.attackAnim)) {
        this.sprite.play(this.attackAnim, true);
      }
      this.snapFeet();
      return;
    }

    if ((intent === "chase" || intent === "flee") && this.playerX !== null) {
      // Fleeing is chasing with the sign inverted, which is why one branch covers both: a
      // skittish creature is not a different behaviour, it is the same pursuit pointed away.
      const toward = this.playerX >= this.sprite.x ? 1 : -1;
      this.dirSign = (intent === "flee" ? -toward : toward) as 1 | -1;
      const speed = this.profile.chaseSpeedPx;
      const next = this.sprite.x + this.dirSign * speed * dt;
      // Leashed to the patrol lane so a roused mob cannot be walked across the whole stage, and
      // so its alpha envelope stays inside the world bounds `mobWorldLane` clamped it to.
      //
      // The leash is applied before the terrain, not after: clamping a blocked position back
      // into the lane would push the creature into the face it was just stopped by.
      this.walkTo(
        Math.min(
          this.pursuitMax,
          Math.max(this.pursuitMin, next),
        ),
      );
      // Facing still follows the intent even when the ground refuses the step, so a mob held at
      // the foot of a rise keeps looking at the player standing on top of it rather than turning
      // away from a fight it simply cannot reach.
      this.sprite.setFlipX(this.dirSign === -1);
      if (this.state !== "chase") this.state = "chase";
      this.snapFeet();
      return;
    }

    // Nothing nearby: use the current deterministic patrol default.
    if (this.state !== "wander") this.state = "wander";
    const speed = this.opts.speedPx ?? DEFAULT_SPEED;
    // A face turns a patrol the same way the end of its lane does. Reversing rather than
    // standing still matters because a lane that runs into a rise would otherwise leave the
    // creature pressed against it for the rest of the run, which reads as a stuck mob rather
    // than as one that cannot climb.
    const blocked = this.walkTo(this.sprite.x + this.dirSign * speed * dt);
    if (blocked) {
      this.dirSign = (this.dirSign === 1 ? -1 : 1) as 1 | -1;
    } else if (this.sprite.x <= this.wanderMin) {
      this.sprite.x = this.wanderMin;
      this.dirSign = 1;
    } else if (this.sprite.x >= this.wanderMax) {
      this.sprite.x = this.wanderMax;
      this.dirSign = -1;
    }
    this.sprite.setFlipX(this.dirSign === -1);

    this.snapFeet();
  }

  /**
   * Walk toward `nextX`, stopped by any terrain face standing above the feet.
   *
   * The same `resolveTerrainWalk` the player is bound by, and for the same reason: the
   * heightfield steps in whole tiles, so a rise is a wall and the way up is a jump. A mob has no
   * jump, which is exactly the point - it patrols and hunts on the shelf it was spawned on, and
   * falls off the edges of it.
   *
   * Before this, horizontal motion wrote `sprite.x` directly and `snapFeet` lifted the creature
   * onto whatever column it had landed in. Downhill that reads as walking off a ledge; uphill it
   * reads as a mob levitating up a cliff face, and only ever when chasing, because a wander lane
   * is short enough to rarely cross a rise. The physics were never ignored during a chase - they
   * were never applied at all, and the chase was simply the one behaviour that walked far enough
   * to show it.
   */
  private walkTo(nextX: number): boolean {
    const walk = this.resolveWalk(nextX);
    this.sprite.x = walk.x;
    return walk.blocked;
  }

  /** The same resolution without applying it, for a move that is not the mob's own step. */
  private resolveWalk(nextX: number): TerrainWalkResolution {
    return resolveTerrainWalk({
      previousX: this.sprite.x,
      nextX,
      footY: this.sprite.y,
      tilePixels: this.opts.tilePx,
      surfaceAt: (column) =>
        terrainSurfaceY(
          this.opts.heightFn(column),
          this.opts.tilePx,
          this.opts.baselineY,
        ),
    });
  }

  /** Keep the mob standing on the terrain column it currently occupies. */
  private snapFeet(): void {
    const col = Math.floor(this.sprite.x / this.opts.tilePx);
    const colH = this.opts.heightFn(col);
    this.sprite.y = terrainSurfaceY(
      colH,
      this.opts.tilePx,
      this.opts.baselineY,
    );
  }

  /** Tell the mob where the player is. Null means "no player to react to". */
  observePlayer(x: number | null, defeated: boolean): void {
    this.playerX = x;
    this.playerDefeated = defeated;
  }

  /** Take the strike this mob committed to, if any, clearing it. */
  consumeStrike(): { damage: number; dirSign: 1 | -1 } | null {
    const strike = this.pendingStrike;
    this.pendingStrike = null;
    return strike;
  }

  /** Apply one point of damage and report the complete before/after resolution. */
  takeHit(
    nowMs: number,
    knockbackDir: 1 | -1 = 1,
  ): MobHitResult {
    if (this.state === "dead") {
      return mobHitResult(resolveDamage(this.hp, 1, true));
    }
    const resolution = resolveDamage(this.hp, 1);
    this.hp = resolution.hpAfter;
    const hitResult = mobHitResult(resolution);
    // Knockback tween — clamped to wander bounds so the mob doesn't escape its lane, then
    // resolved against the terrain so a blow cannot shove a creature up a face it is not allowed
    // to walk up. A mob struck with its back to a cliff stops at the cliff.
    const targetX = this.resolveWalk(
      Phaser.Math.Clamp(
        this.sprite.x + knockbackDir * KNOCKBACK_PX,
        this.wanderMin,
        this.wanderMax,
      ),
    ).x;
    // Turn to look at whoever swung. A mob that keeps facing its patrol
    // direction while being knocked backwards reads as scenery taking damage.
    // Wander resumes along the same heading, so the turn is a reaction rather
    // than a one-frame flicker the next update undoes.
    this.dirSign = mobHitFacing(knockbackDir);
    this.sprite.setFlipX(this.dirSign === -1);
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

  /** Show or hide the whole actor - body and readout - as one thing. */
  setVisible(visible: boolean): void {
    this.sprite.setVisible(visible);
    this.healthBar.setVisible(visible && this.isAlive());
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
    this.dirSign = this.ladderIndex % 2 === 0 ? 1 : -1;
    this.hurtUntil = 0;
    this.attackReadyAtMs = 0;
    this.strikeLandsAtMs = 0;
    this.pendingStrike = null;
    this.playerX = null;
    this.playerDefeated = false;
    this.fixedHitMotion = undefined;
    this.sprite.setPosition(this.spawnX, this.spawnY);
    this.sprite.setFlipX(this.dirSign === -1);
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

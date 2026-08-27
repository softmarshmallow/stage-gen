// Player controller (Phase 7).
//
// Owns:
//   - WASD + arrow input → horizontal velocity                     (TC-080)
//   - State machine: idle / walk / run / jump / crouch / attack / hurt / climb
//   - Feet locked to heightmap surface during X movement           (TC-082)
//   - Attack hit-window query for the mob system                   (TC-084/085)
//
// The Phaser scene constructs one Player, calls update(dtSec) every frame,
// and reads .sprite / .state / .attacking for collision + camera follow.

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./layers";
import {
  headMatchedScale,
  masterSheetScale,
  playerSheetScaleForState,
  type ScaleReference,
} from "./sprite-scale";
import {
  type PlayerDamageResolution,
  type PlayerHealthState,
  PLAYER_KNOCKBACK_VX,
  PLAYER_KNOCKBACK_VY,
  applyPlayerDamage,
  initialPlayerHealth,
  isPlayerInvulnerable,
  playerInvulnerabilityBlinkAlpha,
} from "./combat";
import {
  DEATH_STRIP_FRAME_RATE,
  playerDamagePresentationState,
} from "./death-presentation";
import { terrainSurfaceY } from "./terrain";
import {
  anchorRepackedMotionFeet,
  applyMotionPlayback,
  installMotionPlayback,
  type RuntimeMotionPlayback,
} from "./motion-playback";
import {
  PLATFORMER_COYOTE_MS,
  PLATFORMER_GRAVITY,
  PLATFORMER_RUN_SPEED,
  PLATFORMER_WALK_SPEED,
  PLATFORM_DROP_THROUGH_MS,
  PLATFORM_DROP_SETTLE_FRAMES,
  UPPER_PLATFORM_THICKNESS,
  advanceLadderMotion,
  ladderEntryAt,
  ladderJumpOffVelocity,
  platformDropThroughActive,
  resolveCrouchHorizontalVelocity,
  resolveJumpRequest,
  resolveTerrainStep,
  resolveTerrainWalk,
  resolveVerticalLanding,
  type LadderZone,
  type CrouchMovementMode,
  type PlayerSupport,
  type UpperPlatform,
} from "./vertical";

export type PlayerState =
  | "idle"
  | "walk"
  | "run"
  | "jump"
  | "crouch"
  | "attack"
  | "hurt"
  | "death"
  | "climb";

export type PlatformDropTraversalPhase =
  | "drop-commanded"
  | "underside-cleared"
  | "lower-support-landed"
  | "lower-support-settled"
  | "recovery-airborne"
  | "recovered";

export type PlayerTransitionKind =
  | "ladder-enter"
  | "ladder-exit"
  | "platform-land"
  | "platform-drop"
  | "platform-underside-clear"
  | "platform-lower-land"
  | "platform-lower-settle"
  | "platform-recovery-launch"
  | "platform-recovery-land"
  | "air-jump"
  | "terrain-step-off"
  | "terrain-step-block";

export type PlayerStateSnapshot = {
  state: PlayerState;
  facing: "left" | "right";
  x: number;
  y: number;
  column: number;
  vx: number;
  vy: number;
  airborne: boolean;
  /** Mid-air jumps spent since the last support. Reset by landing or a ladder. */
  airJumpsUsed: number;
  attackActive: boolean;
  hp: number;
  maxHp: number;
  invulnerable: boolean;
  defeated: boolean;
  support: PlayerSupport;
  supportId: string | null;
  ladderId: string | null;
  platformId: string | null;
  dropThroughPlatformId: string | null;
  dropTraversalPhase: PlatformDropTraversalPhase | null;
  dropTraversalPlatformId: string | null;
  dropTraversalPlatformBottomY: number | null;
  dropTraversalLowerSupport: "terrain" | "platform" | null;
  dropTraversalLowerSupportId: string | null;
  dropTraversalLowerSupportY: number | null;
  dropTraversalStableFrames: number;
  renderBounds: Readonly<{
    left: number;
    top: number;
    right: number;
    bottom: number;
  }>;
  climbAnimationKey: "player_climb" | null;
  climbTextureKey: "character_climb" | null;
  climbFrame: number | null;
  climbAnimationPaused: boolean | null;
  rearFacing: boolean;
};

export interface PlayerOpts {
  scene: Phaser.Scene;
  startX: number;
  startY: number;
  tilePx: number;
  worldWidthPx: number;
  baselineY: number; // GROUND_BASELINE_Y
  heightFn: (col: number) => number; // returns column height in tiles
  targetSpriteHeight: number; // px
  platforms?: readonly UpperPlatform[];
  ladders?: readonly LadderZone[];
  maximumAirJumps: number;
  combatEnabled: boolean;
  /** Authored starting/max health for this run. */
  startingHealth?: number;
  onTransition?: (
    kind: PlayerTransitionKind,
    data: Record<string, string | number | boolean>,
  ) => void;
  /** Resolved presentation per state; omitted entries use standalone-runtime defaults. */
  motionPlayback?: Partial<Record<PlayerState, RuntimeMotionPlayback>>;
  /**
   * Published anatomical scale reference per texture key.
   */
  scaleReferences: ReadonlyMap<string, ScaleReference>;
  /** States whose authored pose height is meaningful and must retain atlas scale. */
  preserveSourceScaleStates?: readonly PlayerState[];
  /** Prepared crouch is stationary; mature standalone callers retain slow movement. */
  crouchMovementMode?: CrouchMovementMode;
}

/** Every player state, in one place so animations and scale resolution cannot diverge. */
const PLAYER_STATES: readonly PlayerState[] = [
  "idle",
  "walk",
  "run",
  "jump",
  "crouch",
  "attack",
  "hurt",
  "death",
  "climb",
];

/** Current player roles measured by the producer; hurt remains an optional current role. */
const MEASURED_PLAYER_STATES: readonly PlayerState[] = [
  "idle",
  "walk",
  "run",
  "jump",
  "crouch",
  "attack",
  "climb",
];

const DEFAULT_FRAME_RATES: Record<PlayerState, number> = {
  idle: 4,
  walk: 8,
  run: 14,
  jump: 8,
  crouch: 6,
  attack: 12,
  hurt: 7,
  death: DEATH_STRIP_FRAME_RATE,
  climb: 9,
};

function defaultMotionPlayback(state: PlayerState): RuntimeMotionPlayback {
  if (state === "climb") {
    return Object.freeze({
      mode: "gameplay_driven",
      canonical_frame_indices: Object.freeze([0, 1, 2, 3]),
    });
  }
  return Object.freeze({
    mode:
      state === "attack" ||
      state === "jump" ||
      state === "hurt" ||
      state === "death"
        ? "once"
        : "loop",
    canonical_frame_indices: Object.freeze([0, 1, 2, 3]),
    frames_per_second: DEFAULT_FRAME_RATES[state],
  });
}

const ATTACK_DURATION_MS = 333; // 4 frames at 12 fps
const ATTACK_HIT_WINDOW_MS_FROM = 80; // hit window starts ~frame 1
const ATTACK_HIT_WINDOW_MS_TO = 250; // …ends after frame 3
const HURT_DURATION_MS = 600;

export class Player {
  readonly sprite: Phaser.GameObjects.Sprite;
  state: PlayerState = "idle";
  facing: "left" | "right" = "right";
  vx = 0;
  vy = 0;
  airborne = false;
  support: PlayerSupport = "terrain";
  supportId: string | null = null;
  ladderId: string | null = null;
  /** Mid-air jumps spent since the last grounded or ladder support. */
  airJumpsUsed = 0;
  /** Deadline until which a lost support still buys a full grounded jump. */
  private coyoteExpiresAtMs: number | null = null;
  /** Column face currently stopping horizontal motion, for edge-triggered logs. */
  private blockedColumn: number | null = null;
  private opts: PlayerOpts;
  private readonly motionPlayback: Readonly<Record<PlayerState, RuntimeMotionPlayback>>;
  private cursors?: Phaser.Types.Input.Keyboard.CursorKeys;
  private wasdKeys?: {
    up: Phaser.Input.Keyboard.Key;
    down: Phaser.Input.Keyboard.Key;
    left: Phaser.Input.Keyboard.Key;
    right: Phaser.Input.Keyboard.Key;
    jump: Phaser.Input.Keyboard.Key;
    attack1: Phaser.Input.Keyboard.Key;
    attack2: Phaser.Input.Keyboard.Key;
    attack3: Phaser.Input.Keyboard.Key;
    shift: Phaser.Input.Keyboard.Key;
    inventory: Phaser.Input.Keyboard.Key;
  };
  private attackUntil = 0;
  private attackStarted = 0;
  private attackHitConsumed = false;
  /** Deadline for the authored hurt presentation; it does not lock player control. */
  private hurtUntil = 0;
  private activeLadder?: LadderZone;
  private climbFrame: number | null = null;
  /** Sprite scale for textures sliced from the character's master sheet. */
  private masterSheetScale = 1;
  /** Sprite scale by texture key, for sheets that do not share the master's geometry. */
  private readonly sheetScale = new Map<string, number>();
  private dropThroughPlatformId: string | null = null;
  private dropThroughUntil = 0;
  private dropTraversal?: {
    platformId: string;
    platformLeft: number;
    platformRight: number;
    platformDeckY: number;
    platformBottomY: number;
    phase: PlatformDropTraversalPhase;
    lowerSupport: "terrain" | "platform" | null;
    lowerSupportId: string | null;
    lowerSupportY: number | null;
    stableFrames: number;
  };
  /** Hit points, invulnerability window and defeat, owned here because they are gameplay. */
  private health: PlayerHealthState = initialPlayerHealth();

  /** Set while the attack swing is in its hit window. */
  attackActive = false;
  /** Toggled by I key to open inventory; consumed externally. */
  inventoryToggleRequested = false;
  private inventoryKeyHandler?: () => void;

  constructor(opts: PlayerOpts) {
    if (!Number.isSafeInteger(opts.maximumAirJumps) || opts.maximumAirJumps < 0) {
      throw new Error("maximumAirJumps must be a nonnegative integer");
    }
    this.opts = opts;
    this.health = initialPlayerHealth(opts.startingHealth);
    this.motionPlayback = Object.freeze(
      Object.fromEntries(
        PLAYER_STATES.map((state) => [
          state,
          opts.motionPlayback?.[state] ?? defaultMotionPlayback(state),
        ]),
      ) as Record<PlayerState, RuntimeMotionPlayback>,
    );

    const scene = opts.scene;
    // Build animations for each state once.
    for (const st of PLAYER_STATES) {
      const animKey = `player_${st}`;
      const texKey = stateTextureKey(st);
      if (!scene.anims.exists(animKey) && scene.textures.exists(texKey)) {
        installMotionPlayback(scene, animKey, texKey, this.motionPlayback[st]);
      }
    }

    const initialKey = stateTextureKey("idle");
    this.sprite = scene.add.sprite(opts.startX, opts.startY, initialKey, 0);
    this.sprite.setOrigin(0.5, 1.0);
    this.resolveSheetScales();
    this.applySheetScale(initialKey);
    this.sprite.setDepth(SCENE_CONTENT_DEPTH.player);
    applyMotionPlayback(
      this.sprite,
      "player_idle",
      initialKey,
      this.motionPlayback.idle,
    );
    anchorRepackedMotionFeet(this.sprite);

    this.bindInput();
  }

  /**
   * Work out the sprite scale each state's source sheet needs.
   *
   * Each required sheet carries its own producer-published anatomical measurement. Matching each
   * extent to idle is what preserves apparent character size across unrelated source canvases and
   * poses. Optional reaction and terminal strips retain the anchored master-sheet scale because
   * their producer roles do not yet publish measurements.
   */
  private resolveSheetScales(): void {
    const scene = this.opts.scene;
    const idleKey = stateTextureKey("idle");
    this.masterSheetScale = masterSheetScale(
      this.opts.targetSpriteHeight,
      sheetFrameHeight(scene, idleKey, 0),
    );

    // Idle sets the size the character reads at; every other measured sheet is matched to it.
    const references = this.opts.scaleReferences;
    const idleReference = references.get(idleKey);
    if (!idleReference) {
      throw new Error("current player requires character_idle scale reference");
    }
    const reference = {
      extentPixels: idleReference.extentPixels,
      scale: this.masterSheetScale,
    };
    for (const state of MEASURED_PLAYER_STATES) {
      const key = stateTextureKey(state);
      const sheetReference = references.get(key);
      if (!sheetReference) {
        throw new Error(`current player requires ${key} scale reference`);
      }
      this.sheetScale.set(
        key,
        playerSheetScaleForState({
          state,
          masterSheetScale: this.masterSheetScale,
          measuredSheetScale: headMatchedScale(reference, sheetReference),
          preserveSourceScaleStates:
            this.opts.preserveSourceScaleStates ?? Object.freeze([]),
        }),
      );
    }
  }

  /** Apply the scale belonging to `textureKey`'s source sheet. */
  private applySheetScale(textureKey: string): void {
    const measured = this.sheetScale.get(textureKey);
    if (measured !== undefined) {
      this.sprite.setScale(measured);
      return;
    }
    // Reaction and terminal strips are optional producer roles without published measurements.
    // Their explicit current behavior is to retain the anchored master-sheet scale.
    if (
      textureKey === "character_hurt" ||
      textureKey === "character_death"
    ) {
      this.sprite.setScale(this.masterSheetScale);
      return;
    }
    throw new Error(`current player texture ${textureKey} has no resolved scale`);
  }

  private bindInput() {
    const kb = this.opts.scene.input.keyboard;
    if (!kb) return;
    this.cursors = kb.createCursorKeys();
    this.wasdKeys = {
      up: kb.addKey(Phaser.Input.Keyboard.KeyCodes.W),
      down: kb.addKey(Phaser.Input.Keyboard.KeyCodes.S),
      left: kb.addKey(Phaser.Input.Keyboard.KeyCodes.A),
      right: kb.addKey(Phaser.Input.Keyboard.KeyCodes.D),
      jump: kb.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE),
      attack1: kb.addKey(Phaser.Input.Keyboard.KeyCodes.J),
      attack2: kb.addKey(Phaser.Input.Keyboard.KeyCodes.X),
      attack3: kb.addKey(Phaser.Input.Keyboard.KeyCodes.Z),
      shift: kb.addKey(Phaser.Input.Keyboard.KeyCodes.SHIFT),
      inventory: kb.addKey(Phaser.Input.Keyboard.KeyCodes.I),
    };
    // Inventory toggle on JustDown.
    this.inventoryKeyHandler = () => {
      this.inventoryToggleRequested = true;
    };
    kb.on("keydown-I", this.inventoryKeyHandler);
  }

  /**
   * Release this controller's scene bindings.
   *
   * A stage rebuild constructs a fresh Player, so the retired one has to hand
   * back its keyboard listener; otherwise every stage travelled adds another
   * inventory toggle to the same key press.
   */
  destroy(): void {
    if (this.inventoryKeyHandler) {
      this.opts.scene.input.keyboard?.off("keydown-I", this.inventoryKeyHandler);
      this.inventoryKeyHandler = undefined;
    }
    this.sprite.destroy();
  }

  /** Called every frame from the scene. */
  update(dtMs: number, nowMs: number) {
    const dt = dtMs / 1000;
    const k = this.wasdKeys;
    const c = this.cursors;
    const left = !!(k?.left.isDown || c?.left?.isDown);
    const right = !!(k?.right.isDown || c?.right?.isDown);
    const down = !!(k?.down.isDown || c?.down?.isDown);
    const up = !!(k?.up.isDown || c?.up?.isDown);
    const shift = !!k?.shift.isDown;
    const wantsJump = !!(
      k?.jump && Phaser.Input.Keyboard.JustDown(k.jump)
    );
    const wantsAttack =
      this.opts.combatEnabled &&
      (k &&
        (Phaser.Input.Keyboard.JustDown(k.attack1) ||
          Phaser.Input.Keyboard.JustDown(k.attack2) ||
          Phaser.Input.Keyboard.JustDown(k.attack3))) ||
      false;

    // Damage is resolved by the scene after this controller has already stepped for the frame,
    // so `takeDamage` enters its presentation synchronously and this branch owns every later
    // reaction frame. Hurt is feedback, not a stun: ordinary movement and traversal remain live
    // while invulnerability blinks the sprite. Only terminal defeat locks input.
    const hurtPresentationAvailable = this.hasHurtPresentation();
    const deathPresentationAvailable = this.hasDeathPresentation();
    const hurtReaction = hurtPresentationAvailable && this.state === "hurt";
    const hurtMotionActive = hurtReaction && nowMs < this.hurtUntil;
    const controlsLocked = this.health.defeated;
    if (controlsLocked) this.vx = 0;
    this.sprite.setAlpha(playerInvulnerabilityBlinkAlpha(this.health, nowMs));

    // Active ladder traversal has priority over every movement/combat action.
    if (!controlsLocked && this.support === "ladder" && this.activeLadder) {
      this.continueLadder({ dt, up, down, left, right, wantsJump });
      this.sprite.setFlipX(
        this.support === "ladder" ? false : this.facing === "left",
      );
      return;
    }

    // Entering a ladder has priority over platform drop-through.
    const entry = controlsLocked
      ? null
      : ladderEntryAt({
          ladders: this.opts.ladders ?? [],
          support: this.support,
          supportId: this.supportId,
          x: this.sprite.x,
          footY: this.sprite.y,
          up,
          down,
        });
    if (entry) {
      this.activeLadder = entry.ladder;
      this.ladderId = entry.ladder.id;
      this.support = "ladder";
      this.supportId = entry.ladder.id;
      this.airborne = false;
      this.vx = 0;
      this.vy = 0;
      this.sprite.x = entry.ladder.centerX;
      this.clearAttack();
      this.opts.onTransition?.("ladder-enter", {
        ladderId: entry.ladder.id,
        from: entry.direction === "up" ? "terrain" : "platform",
        direction: entry.direction,
      });
      this.continueLadder({ dt, up, down, left, right, wantsJump: false });
      this.sprite.setFlipX(
        this.support === "ladder" ? false : this.facing === "left",
      );
      return;
    }

    this.advanceDropTraversalSettle();

    // Determine target horizontal velocity.
    let targetVx = this.vx;
    if (!controlsLocked) {
      targetVx = 0;
      if (left && !right) {
        targetVx = -(shift ? PLATFORMER_RUN_SPEED : PLATFORMER_WALK_SPEED);
        this.facing = "left";
      } else if (right && !left) {
        targetVx = shift ? PLATFORMER_RUN_SPEED : PLATFORMER_WALK_SPEED;
        this.facing = "right";
      }
    }

    // Crouch reduces speed and locks state on the ground.
    const crouching = !controlsLocked && down && this.support !== "air";
    if (crouching) {
      targetVx = resolveCrouchHorizontalVelocity({
        velocity: targetVx,
        mode: this.opts.crouchMovementMode ?? "slow",
      });
    }

    if (!controlsLocked) this.vx = targetVx;

    // Down+Space drops through the current one-way platform. A valid ladder
    // entry was already consumed above, so it cannot be shadowed by this.
    const dropping =
      !controlsLocked &&
      wantsJump &&
      down &&
      this.support === "platform" &&
      this.supportId !== null;
    if (dropping) {
      const platformId = this.supportId!;
      const platform = (this.opts.platforms ?? []).find(
        (candidate) => candidate.id === platformId,
      );
      if (!platform) {
        throw new Error("drop-through support must name an active platform");
      }
      this.dropThroughPlatformId = platformId;
      this.dropThroughUntil = nowMs + PLATFORM_DROP_THROUGH_MS;
      this.dropTraversal = {
        platformId,
        platformLeft: platform.left,
        platformRight: platform.right,
        platformDeckY: platform.deckY,
        platformBottomY: platform.deckY + UPPER_PLATFORM_THICKNESS,
        phase: "drop-commanded",
        lowerSupport: null,
        lowerSupportId: null,
        lowerSupportY: null,
        stableFrames: 0,
      };
      this.setSupport("air", null);
      this.vy = 0;
      this.opts.onTransition?.("platform-drop", {
        platformId,
        footY: this.sprite.y,
        platformLeft: this.dropTraversal.platformLeft,
        platformRight: this.dropTraversal.platformRight,
        platformBottomY: this.dropTraversal.platformBottomY,
      });
    } else if (!controlsLocked && wantsJump) {
      const jump = resolveJumpRequest({
        support: this.support,
        airJumpsUsed: this.airJumpsUsed,
        nowMs,
        coyoteExpiresAtMs: this.coyoteExpiresAtMs,
        crouching,
        maximumAirJumps: this.opts.maximumAirJumps,
      });
      if (jump.kind !== "none") {
        this.beginDropRecoveryIfReady();
        this.vy = jump.vy;
        this.airJumpsUsed = jump.airJumpsUsed;
        this.coyoteExpiresAtMs = null;
        if (jump.kind === "air") {
          this.opts.onTransition?.("air-jump", {
            airJumpsUsed: jump.airJumpsUsed,
            footY: this.sprite.y,
            vy: jump.vy,
          });
        }
        if (this.support !== "air") this.setSupport("air", null);
      }
    }

    // Horizontal motion, stopped by any column face standing above the feet.
    // A one-tile rise is a wall now, not a step, so the way up is a jump.
    const previousX = this.sprite.x;
    const walk = resolveTerrainWalk({
      previousX,
      nextX: Phaser.Math.Clamp(
        previousX + this.vx * dt,
        this.opts.tilePx / 2,
        this.opts.worldWidthPx - this.opts.tilePx / 2,
      ),
      footY: this.sprite.y,
      tilePixels: this.opts.tilePx,
      surfaceAt: (column) =>
        terrainSurfaceY(
          this.opts.heightFn(column),
          this.opts.tilePx,
          this.opts.baselineY,
        ),
    });
    this.sprite.x = walk.x;
    if (walk.blocked) {
      this.vx = 0;
      // Edge-triggered: held against a face this would otherwise log every
      // frame, and the interesting fact is arriving at the wall, not leaning
      // on it.
      if (this.blockedColumn !== walk.blockedColumn) {
        this.blockedColumn = walk.blockedColumn;
        this.opts.onTransition?.("terrain-step-block", {
          column: walk.blockedColumn!,
          footY: this.sprite.y,
          x: walk.x,
        });
      }
    } else {
      this.blockedColumn = null;
    }

    // Attack overrides locomotion anim state (still moves but plays attack).
    if (
      wantsAttack &&
      !controlsLocked &&
      !this.attackActive &&
      nowMs >= this.attackUntil &&
      this.support !== "ladder"
    ) {
      this.attackUntil = nowMs + ATTACK_DURATION_MS;
      this.attackStarted = nowMs;
      this.attackHitConsumed = false;
    }
    const attacking = nowMs < this.attackUntil;
    const attackElapsed = nowMs - this.attackStarted;
    this.attackActive =
      attacking &&
      attackElapsed >= ATTACK_HIT_WINDOW_MS_FROM &&
      attackElapsed <= ATTACK_HIT_WINDOW_MS_TO;

    // Vertical motion + one-way platform/terrain resolution.
    const col = Math.floor(this.sprite.x / this.opts.tilePx);
    const colH = this.opts.heightFn(col);
    const surfaceY = terrainSurfaceY(
      colH,
      this.opts.tilePx,
      this.opts.baselineY,
    );

    if (this.support === "platform") {
      const platform = (this.opts.platforms ?? []).find(
        (candidate) => candidate.id === this.supportId,
      );
      if (!platform || this.sprite.x < platform.left || this.sprite.x > platform.right) {
        this.openCoyoteWindow(nowMs);
        this.setSupport("air", null);
        this.vy = 0;
      } else {
        this.sprite.y = platform.deckY;
      }
    } else if (this.support === "terrain") {
      // Uphill columns are still absorbed, which keeps this heightfield's
      // column-locked climb. A descending column is a real ledge: the foot
      // holds its height and the airborne branch below drops it under gravity
      // instead of teleporting it onto the new surface.
      const step = resolveTerrainStep({
        footY: this.sprite.y,
        surfaceY,
      });
      this.sprite.y = step.footY;
      if (step.support === "air") {
        this.openCoyoteWindow(nowMs);
        this.setSupport("air", null);
        this.vy = 0;
        this.opts.onTransition?.("terrain-step-off", {
          footY: step.footY,
          surfaceY,
          column: col,
        });
      }
    }

    if (this.support === "air") {
      this.vy += PLATFORMER_GRAVITY * dt;
      const nextFootY = this.sprite.y + this.vy * dt;
      const ignoredPlatformId = this.activeDropThroughPlatform(nowMs);
      const landing = resolveVerticalLanding({
        x: this.sprite.x,
        previousFootY: this.sprite.y,
        nextFootY,
        vy: this.vy,
        terrainY: surfaceY,
        platforms: this.opts.platforms ?? [],
        ignoredPlatformId,
      });
      this.sprite.y = landing.footY;
      this.vy = landing.vy;
      this.setSupport(landing.support, landing.supportId);
      this.advanceDropTraversalAfterAirborne(landing);
      if (landing.support === "platform" && landing.supportId) {
        this.opts.onTransition?.("platform-land", {
          platformId: landing.supportId,
        });
      }
      if (
        landing.support !== "air" &&
        landing.supportId !== this.dropThroughPlatformId
      ) {
        this.clearDropThrough();
      }
    }

    // Compute new state.
    let next: PlayerState;
    const damagePresentation = playerDamagePresentationState({
      defeated: this.health.defeated,
      deathAvailable: deathPresentationAvailable,
      hurtAvailable: hurtPresentationAvailable,
      hurtMotionActive,
      airborne: this.support === "air",
    });
    if (damagePresentation !== null) next = damagePresentation;
    else if (attacking) next = "attack";
    else if (this.support === "air") next = "jump";
    else if (crouching) next = "crouch";
    else if (this.vx !== 0 && shift) next = "run";
    else if (this.vx !== 0) next = "walk";
    else next = "idle";

    if (next !== this.state) {
      this.setState(next);
    }

    // Flip sprite by facing.
    this.sprite.setFlipX(this.facing === "left");
  }

  private continueLadder(input: Readonly<{
    dt: number;
    up: boolean;
    down: boolean;
    left: boolean;
    right: boolean;
    wantsJump: boolean;
  }>): void {
    const ladder = this.activeLadder;
    if (!ladder) throw new Error("ladder support requires an active ladder");
    this.sprite.x = ladder.centerX;
    this.vx = 0;
    if (input.wantsJump) {
      const jump = ladderJumpOffVelocity({
        left: input.left,
        right: input.right,
        facing: this.facing,
      });
      this.vx = jump.vx;
      this.vy = jump.vy;
      this.sprite.x += this.vx * input.dt;
      this.sprite.y += this.vy * input.dt;
      const ladderId = ladder.id;
      this.activeLadder = undefined;
      this.ladderId = null;
      this.setSupport("air", null);
      this.opts.onTransition?.("ladder-exit", {
        ladderId,
        to: "air",
      });
      this.setState("jump");
      return;
    }
    const motion = advanceLadderMotion({
      ladder,
      footY: this.sprite.y,
      deltaSeconds: input.dt,
      up: input.up,
      down: input.down,
    });
    this.sprite.y = motion.footY;
    this.vy = motion.vy;
    if (motion.exit === "platform") {
      const ladderId = ladder.id;
      this.activeLadder = undefined;
      this.ladderId = null;
      this.setSupport("platform", ladder.platformId);
      this.opts.onTransition?.("ladder-exit", {
        ladderId,
        to: "platform",
      });
      this.setState("idle");
      return;
    }
    if (motion.exit === "terrain") {
      const ladderId = ladder.id;
      this.activeLadder = undefined;
      this.ladderId = null;
      this.setSupport("terrain", null);
      this.opts.onTransition?.("ladder-exit", {
        ladderId,
        to: "terrain",
      });
      this.setState("idle");
      return;
    }
    if (this.state !== "climb") this.setState("climb");
    this.setClimbFrame(this.vy !== 0);
  }

  private setSupport(support: PlayerSupport, supportId: string | null): void {
    this.support = support;
    this.supportId = supportId;
    this.airborne = support === "air";
    if (support !== "air") {
      this.airJumpsUsed = 0;
      this.coyoteExpiresAtMs = null;
    }
  }

  /**
   * Open the grace window for a support lost by falling.
   *
   * Only fall sites call this. A jump clears the deadline instead, so the
   * window can never turn one press into two grounded launches.
   */
  private openCoyoteWindow(nowMs: number): void {
    if (this.support === "air") return;
    this.coyoteExpiresAtMs = nowMs + PLATFORMER_COYOTE_MS;
  }

  private activeDropThroughPlatform(nowMs: number): string | null {
    if (!this.dropThroughPlatformId) return null;
    const platform = (this.opts.platforms ?? []).find(
      (candidate) => candidate.id === this.dropThroughPlatformId,
    );
    if (
      !platform ||
      !platformDropThroughActive({
        nowMs,
        expiresAtMs: this.dropThroughUntil,
        footY: this.sprite.y,
        deckY: platform.deckY,
      })
    ) {
      this.clearDropThrough();
      return null;
    }
    return this.dropThroughPlatformId;
  }

  private clearDropThrough(): void {
    this.dropThroughPlatformId = null;
    this.dropThroughUntil = 0;
  }

  private advanceDropTraversalSettle(): void {
    const traversal = this.dropTraversal;
    if (!traversal || traversal.phase !== "lower-support-landed") return;
    if (
      this.support !== traversal.lowerSupport ||
      this.supportId !== traversal.lowerSupportId ||
      this.sprite.y !== traversal.lowerSupportY
    ) {
      return;
    }
    traversal.stableFrames += 1;
    if (traversal.stableFrames !== PLATFORM_DROP_SETTLE_FRAMES) return;
    traversal.phase = "lower-support-settled";
    this.opts.onTransition?.("platform-lower-settle", {
      platformId: traversal.platformId,
      support: traversal.lowerSupport!,
      footY: traversal.lowerSupportY!,
      stableFrames: traversal.stableFrames,
    });
  }

  private beginDropRecoveryIfReady(): void {
    const traversal = this.dropTraversal;
    if (!traversal || traversal.phase !== "lower-support-settled") return;
    if (this.support === "air" || this.support === "ladder") return;
    traversal.phase = "recovery-airborne";
    this.opts.onTransition?.("platform-recovery-launch", {
      platformId: traversal.platformId,
      support: this.support,
      footY: this.sprite.y,
      settledFootY: traversal.lowerSupportY!,
      stableFrames: traversal.stableFrames,
    });
  }

  private advanceDropTraversalAfterAirborne(
    landing: Readonly<{
      footY: number;
      support: "air" | "terrain" | "platform";
      supportId: string | null;
    }>,
  ): void {
    const traversal = this.dropTraversal;
    if (!traversal) return;
    const renderBounds = this.playerRenderBounds();
    const fullyClear =
      renderBounds.right < traversal.platformLeft ||
      renderBounds.left > traversal.platformRight ||
      renderBounds.bottom < traversal.platformDeckY ||
      renderBounds.top > traversal.platformBottomY;
    if (
      traversal.phase === "drop-commanded" &&
      fullyClear
    ) {
      traversal.phase = "underside-cleared";
      this.opts.onTransition?.("platform-underside-clear", {
        platformId: traversal.platformId,
        footY: landing.footY,
        playerLeft: renderBounds.left,
        playerTop: renderBounds.top,
        playerRight: renderBounds.right,
        playerBottom: renderBounds.bottom,
        platformLeft: traversal.platformLeft,
        platformRight: traversal.platformRight,
        platformDeckY: traversal.platformDeckY,
        platformBottomY: traversal.platformBottomY,
        separationAxis:
          renderBounds.left > traversal.platformRight ||
          renderBounds.right < traversal.platformLeft
            ? "horizontal"
            : "vertical",
      });
    }
    if (
      (traversal.phase === "drop-commanded" ||
        traversal.phase === "underside-cleared") &&
      landing.support !== "air" &&
      !(
        landing.support === "platform" &&
        landing.supportId === traversal.platformId
      )
    ) {
      traversal.phase = "lower-support-landed";
      traversal.lowerSupport = landing.support;
      traversal.lowerSupportId = landing.supportId;
      traversal.lowerSupportY = landing.footY;
      traversal.stableFrames = 1;
      this.opts.onTransition?.("platform-lower-land", {
        platformId: traversal.platformId,
        support: landing.support,
        footY: landing.footY,
      });
      return;
    }
    if (
      traversal.phase === "recovery-airborne" &&
      landing.support === "platform" &&
      landing.supportId === traversal.platformId
    ) {
      traversal.phase = "recovered";
      this.opts.onTransition?.("platform-recovery-land", {
        platformId: traversal.platformId,
        support: "platform",
        footY: landing.footY,
      });
    }
  }

  private clearAttack(): void {
    this.attackUntil = 0;
    this.attackStarted = 0;
    this.attackHitConsumed = false;
    this.attackActive = false;
  }

  private playerRenderBounds(): Readonly<{
    left: number;
    top: number;
    right: number;
    bottom: number;
  }> {
    const bounds = this.sprite.getBounds();
    return {
      left: bounds.left,
      top: bounds.top,
      right: bounds.right,
      bottom: bounds.bottom,
    };
  }

  private setClimbFrame(moving: boolean): void {
    const textureKey = "character_climb";
    if (!this.opts.scene.textures.exists(textureKey)) {
      throw new Error("current climb texture is missing");
    }
    if (!this.opts.scene.anims.exists("player_climb")) {
      throw new Error("current climb animation is missing");
    }
    const ladder = this.activeLadder;
    const climbFrameCount = this.motionPlayback.climb.canonical_frame_indices.length;
    const nextFrame =
      moving && ladder
        ? Math.floor(Math.abs(ladder.lowerSurfaceY - this.sprite.y) / 12) %
          climbFrameCount
        : (this.climbFrame ?? 0);
    if (
      this.sprite.anims.currentAnim?.key !== "player_climb" ||
      !this.sprite.anims.isPlaying
    ) {
      this.sprite.play("player_climb", true);
    }
    const animationFrame = this.sprite.anims.currentAnim?.frames[nextFrame];
    if (!animationFrame) {
      throw new Error(`current climb animation frame ${nextFrame} is missing`);
    }
    this.sprite.anims.setCurrentFrame(animationFrame);
    if (moving) this.sprite.anims.resume();
    else this.sprite.anims.pause();
    this.sprite.setFlipX(false);
    this.applySheetScale(textureKey);
    anchorRepackedMotionFeet(this.sprite);
    this.climbFrame = nextFrame;
  }

  /** Force the animation matching `next`. */
  private setState(next: PlayerState) {
    this.state = next;
    if (next === "climb") {
      this.setClimbFrame(false);
      return;
    }
    this.climbFrame = null;
    const animKey = `player_${next}`;
    const texKey = stateTextureKey(next);
    applyMotionPlayback(this.sprite, animKey, texKey, this.motionPlayback[next]);
    this.applySheetScale(texKey);
    anchorRepackedMotionFeet(this.sprite);
  }

  /** A public hurt state exists only when the matching four-frame sheet was actually loaded. */
  private hasHurtPresentation(): boolean {
    return (
      this.opts.scene.textures.exists("character_hurt") &&
      this.opts.scene.anims.exists("player_hurt")
    );
  }

  /** A terminal state exists only when the matching four-frame sheet was actually loaded. */
  private hasDeathPresentation(): boolean {
    return (
      this.opts.scene.textures.exists("character_death") &&
      this.opts.scene.anims.exists("player_death")
    );
  }

  /** Current health, for the HUD and the probe. */
  get healthState(): PlayerHealthState {
    return this.health;
  }

  /**
   * Take a blow from a mob and return the authoritative before/after resolution.
   *
   * Knockback is applied only on a connect, and away from the striker, so a blow reads as a blow
   * rather than as the player snagging on geometry. The invulnerability window that follows is
   * what makes standing beside a mob survivable - without it, contact is continuous and the bar
   * empties in a single cooldown cycle.
   */
  takeDamage(
    amount: number,
    nowMs: number,
    fromDirSign: 1 | -1,
  ): PlayerDamageResolution {
    const result = applyPlayerDamage(this.health, amount, nowMs);
    this.health = result.health;
    if (!result.connected) return result;
    this.sprite.setAlpha(playerInvulnerabilityBlinkAlpha(this.health, nowMs));
    this.vx = fromDirSign * PLAYER_KNOCKBACK_VX;
    this.vy = PLAYER_KNOCKBACK_VY;
    // Look back toward the striker while the body travels away from it. The source strip faces
    // right, so a shove to the right means the attacker was on the left and the sheet is flipped.
    this.facing = fromDirSign === 1 ? "left" : "right";
    // Through the support machine, not by setting `airborne` behind its back. A blow launches
    // the player - that is what `PLAYER_KNOCKBACK_VY` is - so the support they had is gone, and
    // writing the flag alone left the two disagreeing: the state machine kept resolving them
    // against the terrain it still believed they stood on, which pinned them to the surface and
    // swallowed the launch whole, while every reader of `airborne` was told they were in the
    // air. A mob striking a standing player is the ordinary way into that state, so it is the
    // frame-12 invariant failure in the deterministic transcript.
    this.setSupport("air", null);
    this.activeLadder = undefined;
    this.ladderId = null;
    this.clearAttack();
    if (result.health.defeated && this.hasDeathPresentation()) {
      this.hurtUntil = 0;
      this.setState("death");
      this.sprite.setFlipX(this.facing === "left");
    } else if (this.hasHurtPresentation()) {
      this.hurtUntil = nowMs + HURT_DURATION_MS;
      // The scene resolves strikes after `update`, so waiting for the next state-selection pass
      // leaves the hit frame in the old pose. Enter now; the update loop holds the final frame
      // when this is also the best available terminal fallback.
      this.setState("hurt");
      this.sprite.setFlipX(this.facing === "left");
    }
    return result;
  }

  /** Whether the attack hit window is open AND has not consumed a hit. */
  consumeAttackHit(): boolean {
    if (this.attackActive && !this.attackHitConsumed) {
      this.attackHitConsumed = true;
      return true;
    }
    return false;
  }

  snapshot(nowMs?: number): PlayerStateSnapshot {
    const renderBounds = this.playerRenderBounds();
    return {
      state: this.state,
      facing: this.facing,
      x: this.sprite.x,
      y: this.sprite.y,
      column: Math.floor(this.sprite.x / this.opts.tilePx),
      vx: this.vx,
      vy: this.vy,
      airborne: this.airborne,
      airJumpsUsed: this.airJumpsUsed,
      attackActive: this.attackActive,
      hp: this.health.hp,
      maxHp: this.health.maxHp,
      invulnerable: isPlayerInvulnerable(this.health, nowMs ?? 0),
      defeated: this.health.defeated,
      support: this.support,
      supportId: this.supportId,
      ladderId: this.ladderId,
      platformId: this.support === "platform" ? this.supportId : null,
      dropThroughPlatformId: this.dropThroughPlatformId,
      dropTraversalPhase: this.dropTraversal?.phase ?? null,
      dropTraversalPlatformId: this.dropTraversal?.platformId ?? null,
      dropTraversalPlatformBottomY:
        this.dropTraversal?.platformBottomY ?? null,
      dropTraversalLowerSupport: this.dropTraversal?.lowerSupport ?? null,
      dropTraversalLowerSupportId:
        this.dropTraversal?.lowerSupportId ?? null,
      dropTraversalLowerSupportY: this.dropTraversal?.lowerSupportY ?? null,
      dropTraversalStableFrames: this.dropTraversal?.stableFrames ?? 0,
      renderBounds,
      climbAnimationKey:
        this.support === "ladder" && this.climbFrame !== null
          ? "player_climb"
          : null,
      climbTextureKey:
        this.support === "ladder" && this.climbFrame !== null
          ? "character_climb"
          : null,
      climbFrame: this.support === "ladder" ? this.climbFrame : null,
      climbAnimationPaused:
        this.support === "ladder" && this.climbFrame !== null
          ? this.sprite.anims.isPaused
          : null,
      rearFacing: this.support === "ladder" && !this.sprite.flipX,
    };
  }

  /** Test/QA helper to drive position directly. */
  setX(x: number) {
    this.sprite.x = x;
  }

  /** Restore the exact frame-zero state before deterministic automation starts. */
  resetAutomationState(): void {
    this.state = "idle";
    this.facing = "right";
    this.vx = 0;
    this.vy = 0;
    this.airJumpsUsed = 0;
    this.coyoteExpiresAtMs = null;
    this.blockedColumn = null;
    this.setSupport("terrain", null);
    this.activeLadder = undefined;
    this.ladderId = null;
    this.climbFrame = null;
    this.clearDropThrough();
    this.dropTraversal = undefined;
    this.clearAttack();
    this.hurtUntil = 0;
    this.health = initialPlayerHealth(this.opts.startingHealth);
    this.inventoryToggleRequested = false;
    this.sprite.setPosition(this.opts.startX, this.opts.startY);
    this.sprite.setFlipX(false);
    this.sprite.setAlpha(1);
    this.sprite.setVisible(true);
    this.sprite.anims.stop();
    const initialKey = stateTextureKey("idle");
    applyMotionPlayback(
      this.sprite,
      "player_idle",
      initialKey,
      this.motionPlayback.idle,
    );
    this.applySheetScale(initialKey);
    anchorRepackedMotionFeet(this.sprite);
  }
}

/** Height in source pixels of one required loaded strip frame. */
function sheetFrameHeight(
  scene: Phaser.Scene,
  key: string,
  index: number,
): number {
  if (!scene.textures.exists(key)) {
    throw new Error(`current player texture ${key} is missing`);
  }
  const height = scene.textures.get(key).get(index)?.height;
  if (typeof height !== "number" || !Number.isFinite(height) || height <= 0) {
    throw new Error(`current player texture ${key} frame ${index} has invalid height`);
  }
  return height;
}

function stateTextureKey(state: PlayerState): string {
  // Pre-loaded by the scene as character_<state> for master slices and sibling strips.
  if (state === "attack") return "character_attack";
  // Historical mature-runtime key; prepared contracts call this state `crouch`.
  if (state === "crouch") return "character_crawl";
  if (state === "climb") return "character_climb";
  return `character_${state}`;
}

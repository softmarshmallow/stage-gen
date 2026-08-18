// Player controller (Phase 7).
//
// Owns:
//   - WASD + arrow input → horizontal velocity                     (TC-080)
//   - State machine: idle / walk / run / jump / crouch / attack    (TC-081)
//   - Feet locked to heightmap surface during X movement           (TC-082)
//   - Attack hit-window query for the mob system                   (TC-084/085)
//
// The Phaser scene constructs one Player, calls update(dtSec) every frame,
// and reads .sprite / .state / .attacking for collision + camera follow.

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./layers";
import { terrainSurfaceY } from "./terrain";
import {
  PLATFORMER_GRAVITY,
  PLATFORMER_JUMP_VELOCITY,
  PLATFORMER_RUN_SPEED,
  PLATFORMER_WALK_SPEED,
  PLATFORM_DROP_THROUGH_MS,
  PLATFORM_DROP_SETTLE_FRAMES,
  UPPER_PLATFORM_THICKNESS,
  advanceLadderMotion,
  ladderEntryAt,
  ladderJumpOffVelocity,
  platformDropThroughActive,
  resolveVerticalLanding,
  type LadderZone,
  type PlayerSupport,
  type UpperPlatform,
} from "./vertical";

export type PlayerState =
  "idle" | "walk" | "run" | "jump" | "crouch" | "attack" | "climb";

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
  | "platform-recovery-land";

export type PlayerStateSnapshot = {
  state: PlayerState;
  facing: "left" | "right";
  x: number;
  y: number;
  column: number;
  vx: number;
  vy: number;
  airborne: boolean;
  attackActive: boolean;
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
  onTransition?: (
    kind: PlayerTransitionKind,
    data: Record<string, string | number | boolean>,
  ) => void;
  /** Frame rates per state (fps). */
  frameRates?: Partial<Record<PlayerState, number>>;
}

const DEFAULT_FRAME_RATES: Record<PlayerState, number> = {
  idle: 4,
  walk: 8,
  run: 14,
  jump: 8,
  crouch: 6,
  attack: 12,
  climb: 9,
};

const ATTACK_DURATION_MS = 333; // 4 frames at 12 fps
const ATTACK_HIT_WINDOW_MS_FROM = 80; // hit window starts ~frame 1
const ATTACK_HIT_WINDOW_MS_TO = 250; // …ends after frame 3

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
  private opts: PlayerOpts;
  private frameRates: Record<PlayerState, number>;
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
  private activeLadder?: LadderZone;
  private climbFrame: number | null = null;
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
  /** Set while the attack swing is in its hit window. */
  attackActive = false;
  /** Toggled by I key to open inventory; consumed externally. */
  inventoryToggleRequested = false;

  constructor(opts: PlayerOpts) {
    this.opts = opts;
    this.frameRates = { ...DEFAULT_FRAME_RATES, ...(opts.frameRates ?? {}) };

    const scene = opts.scene;
    // Build animations for each state once.
    for (const st of [
      "idle",
      "walk",
      "run",
      "jump",
      "crouch",
      "attack",
      "climb",
    ] as PlayerState[]) {
      const animKey = `player_${st}`;
      const texKey = stateTextureKey(st);
      if (!scene.anims.exists(animKey) && scene.textures.exists(texKey)) {
        scene.anims.create({
          key: animKey,
          frames: [0, 1, 2, 3].map((f) => ({ key: texKey, frame: f })),
          frameRate: this.frameRates[st],
          // attack/jump/crouch/idle can loop or play-once depending on state machine
          repeat: st === "attack" || st === "jump" ? 0 : -1,
        });
      }
    }

    const initialKey = stateTextureKey("idle");
    this.sprite = scene.add.sprite(opts.startX, opts.startY, initialKey, 0);
    this.sprite.setOrigin(0.5, 1.0);
    const tex = scene.textures.get(initialKey);
    const f0 = tex.get(0);
    const aspect = (f0?.width ?? 1) / Math.max(1, f0?.height ?? 1);
    this.sprite.setDisplaySize(
      opts.targetSpriteHeight * aspect,
      opts.targetSpriteHeight,
    );
    this.sprite.setDepth(SCENE_CONTENT_DEPTH.player);
    if (scene.anims.exists("player_idle")) this.sprite.play("player_idle");

    this.bindInput();
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
    kb.on("keydown-I", () => {
      this.inventoryToggleRequested = true;
    });
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
      (k &&
        (Phaser.Input.Keyboard.JustDown(k.attack1) ||
          Phaser.Input.Keyboard.JustDown(k.attack2) ||
          Phaser.Input.Keyboard.JustDown(k.attack3))) ||
      false;

    // Active ladder traversal has priority over every movement/combat action.
    if (this.support === "ladder" && this.activeLadder) {
      this.continueLadder({ dt, up, down, left, right, wantsJump });
      this.sprite.setFlipX(
        this.support === "ladder" ? false : this.facing === "left",
      );
      return;
    }

    // Entering a ladder has priority over platform drop-through.
    const entry = ladderEntryAt({
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
    let targetVx = 0;
    if (left && !right) {
      targetVx = -(shift ? PLATFORMER_RUN_SPEED : PLATFORMER_WALK_SPEED);
      this.facing = "left";
    } else if (right && !left) {
      targetVx = shift ? PLATFORMER_RUN_SPEED : PLATFORMER_WALK_SPEED;
      this.facing = "right";
    }

    // Crouch reduces speed and locks state on the ground.
    const crouching = down && this.support !== "air";
    if (crouching) targetVx *= 0.4;

    this.vx = targetVx;

    // Down+Space drops through the current one-way platform. A valid ladder
    // entry was already consumed above, so it cannot be shadowed by this.
    const dropping =
      wantsJump && down && this.support === "platform" && this.supportId !== null;
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
    } else if (wantsJump && this.support !== "air" && !crouching) {
      this.beginDropRecoveryIfReady();
      this.vy = -PLATFORMER_JUMP_VELOCITY;
      this.setSupport("air", null);
    }

    // Horizontal motion.
    this.sprite.x += this.vx * dt;
    this.sprite.x = Phaser.Math.Clamp(
      this.sprite.x,
      this.opts.tilePx / 2,
      this.opts.worldWidthPx - this.opts.tilePx / 2,
    );

    // Attack overrides locomotion anim state (still moves but plays attack).
    if (
      wantsAttack &&
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
        this.setSupport("air", null);
        this.vy = 0;
      } else {
        this.sprite.y = platform.deckY;
      }
    } else if (this.support === "terrain") {
      // Preserve this preview heightfield's established column-locked terrain
      // traversal. Only an upper-platform edge is a one-way step-off.
      this.sprite.y = surfaceY;
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
    if (attacking) next = "attack";
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
    if (
      this.opts.scene.textures.exists(textureKey) &&
      this.opts.scene.anims.exists("player_climb")
    ) {
      const ladder = this.activeLadder;
      const nextFrame =
        moving && ladder
          ? Math.floor(
              Math.abs(ladder.lowerSurfaceY - this.sprite.y) / 12,
            ) % 4
          : (this.climbFrame ?? 0);
      if (
        this.sprite.anims.currentAnim?.key !== "player_climb" ||
        !this.sprite.anims.isPlaying
      ) {
        this.sprite.play("player_climb", true);
      }
      const animationFrame = this.sprite.anims.currentAnim?.frames[nextFrame];
      if (animationFrame) this.sprite.anims.setCurrentFrame(animationFrame);
      if (moving) this.sprite.anims.resume();
      else this.sprite.anims.pause();
      this.sprite.setFlipX(false);
      this.climbFrame = nextFrame;
      return;
    }
    this.climbFrame = null;
    this.sprite.anims.stop();
    const fallback = "character_jump";
    if (!this.opts.scene.textures.exists(fallback)) return;
    const ladder = this.activeLadder;
    const frame =
      moving && ladder
        ? Math.floor((ladder.lowerSurfaceY - this.sprite.y) / 20) & 1
        : 0;
    this.sprite.setTexture(fallback, frame);
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
    if (this.opts.scene.anims.exists(animKey)) {
      this.sprite.play(animKey, true);
    } else {
      // Fallback to texture swap only.
      const texKey = stateTextureKey(next);
      if (this.opts.scene.textures.exists(texKey)) {
        this.sprite.setTexture(texKey, 0);
      }
    }
  }

  /** Whether the attack hit window is open AND has not consumed a hit. */
  consumeAttackHit(): boolean {
    if (this.attackActive && !this.attackHitConsumed) {
      this.attackHitConsumed = true;
      return true;
    }
    return false;
  }

  snapshot(): PlayerStateSnapshot {
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
      attackActive: this.attackActive,
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
    this.setSupport("terrain", null);
    this.activeLadder = undefined;
    this.ladderId = null;
    this.climbFrame = null;
    this.clearDropThrough();
    this.dropTraversal = undefined;
    this.clearAttack();
    this.inventoryToggleRequested = false;
    this.sprite.setPosition(this.opts.startX, this.opts.startY);
    this.sprite.setFlipX(false);
    this.sprite.setAlpha(1);
    this.sprite.setVisible(true);
    this.sprite.anims.stop();
    const initialKey = stateTextureKey("idle");
    this.sprite.setTexture(initialKey, 0);
    if (this.opts.scene.anims.exists("player_idle")) {
      this.sprite.play("player_idle", true);
    }
    const f0 = this.opts.scene.textures.get(initialKey).get(0);
    const aspect = (f0?.width ?? 1) / Math.max(1, f0?.height ?? 1);
    this.sprite.setDisplaySize(
      this.opts.targetSpriteHeight * aspect,
      this.opts.targetSpriteHeight,
    );
  }
}

function stateTextureKey(state: PlayerState): string {
  // Pre-loaded by the scene as character_<state> for the sliced strips, plus
  // character_attack for the attack strip.
  if (state === "attack") return "character_attack";
  if (state === "crouch") return "character_crawl"; // crawl strip used for crouch
  if (state === "climb") return "character_climb";
  return `character_${state}`;
}

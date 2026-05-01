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

export type PlayerState = "idle" | "walk" | "run" | "jump" | "crouch" | "attack";

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
};

export interface PlayerOpts {
  scene: Phaser.Scene;
  startX: number;
  startY: number;
  tilePx: number;
  baselineY: number; // GROUND_BASELINE_Y
  heightFn: (col: number) => number; // returns column height in tiles
  targetSpriteHeight: number; // px
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
};

const WALK_SPEED = 200; // px/s   (TC-080: "reasonable")
const RUN_SPEED = 360;
const JUMP_VEL = 520; // upward initial velocity
const GRAVITY = 1500; // px/s^2
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
    shift: Phaser.Input.Keyboard.Key;
    inventory: Phaser.Input.Keyboard.Key;
  };
  private attackUntil = 0;
  private attackStarted = 0;
  private attackHitConsumed = false;
  /** Set while the attack swing is in its hit window. */
  attackActive = false;
  /** Toggled by I key to open inventory; consumed externally. */
  inventoryToggleRequested = false;

  constructor(opts: PlayerOpts) {
    this.opts = opts;
    this.frameRates = { ...DEFAULT_FRAME_RATES, ...(opts.frameRates ?? {}) };

    const scene = opts.scene;
    // Build animations for each state once.
    for (const st of ["idle", "walk", "run", "jump", "crouch", "attack"] as PlayerState[]) {
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
    this.sprite.setDisplaySize(opts.targetSpriteHeight * aspect, opts.targetSpriteHeight);
    this.sprite.setDepth(900);
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
    const wantsJump =
      Phaser.Input.Keyboard.JustDown(k!.jump!) ||
      (c?.up && Phaser.Input.Keyboard.JustDown(c.up)) ||
      (k && Phaser.Input.Keyboard.JustDown(k.up)) ||
      false;
    const wantsAttack =
      (k && (Phaser.Input.Keyboard.JustDown(k.attack1) || Phaser.Input.Keyboard.JustDown(k.attack2))) || false;

    // Determine target horizontal velocity.
    let targetVx = 0;
    if (left && !right) {
      targetVx = -(shift ? RUN_SPEED : WALK_SPEED);
      this.facing = "left";
    } else if (right && !left) {
      targetVx = shift ? RUN_SPEED : WALK_SPEED;
      this.facing = "right";
    }

    // Crouch reduces speed and locks state on the ground.
    const crouching = down && !this.airborne;
    if (crouching) targetVx *= 0.4;

    this.vx = targetVx;

    // Jump.
    if (wantsJump && !this.airborne && !crouching) {
      this.vy = -JUMP_VEL;
      this.airborne = true;
    }

    // Apply gravity & vertical integration.
    if (this.airborne) {
      this.vy += GRAVITY * dt;
    }

    // Horizontal motion.
    this.sprite.x += this.vx * dt;
    if (this.sprite.x < this.opts.tilePx / 2) this.sprite.x = this.opts.tilePx / 2;

    // Attack overrides locomotion anim state (still moves but plays attack).
    if (wantsAttack && !this.attackActive && nowMs >= this.attackUntil) {
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

    // Vertical motion + ground snap (TC-082).
    const col = Math.floor(this.sprite.x / this.opts.tilePx);
    const colH = this.opts.heightFn(col);
    const surfaceY = this.opts.baselineY - colH * this.opts.tilePx;

    if (this.airborne) {
      this.sprite.y += this.vy * dt;
      if (this.sprite.y >= surfaceY) {
        this.sprite.y = surfaceY;
        this.vy = 0;
        this.airborne = false;
      }
    } else {
      // Always snap to surface so walking up/down a step looks locked.
      this.sprite.y = surfaceY;
    }

    // Compute new state.
    let next: PlayerState;
    if (attacking) next = "attack";
    else if (this.airborne) next = "jump";
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

  /** Force the animation matching `next`. */
  private setState(next: PlayerState) {
    this.state = next;
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
    };
  }

  /** Test/QA helper to drive position directly. */
  setX(x: number) {
    this.sprite.x = x;
  }
}

function stateTextureKey(state: PlayerState): string {
  // Pre-loaded by the scene as character_<state> for the sliced strips, plus
  // character_attack for the attack strip.
  if (state === "attack") return "character_attack";
  if (state === "crouch") return "character_crawl"; // crawl strip used for crouch
  return `character_${state}`;
}

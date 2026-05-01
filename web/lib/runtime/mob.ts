// Mob controller (Phase 7).
//
// Owns:
//   - HP scaling: hp = ladderIndex + 1                     (TC-084)
//   - Wander state machine (idle/wander/hurt/dead)         (TC-083, TC-085)
//   - Hit reception → swap to hurt anim → death drop hook  (TC-085, TC-086)
//
// Each mob is built around an existing Phaser sprite spawned by the scene
// from the pre-loaded mob_<i>_idle / mob_<i>_hurt frame strips.

import Phaser from "phaser";

export type MobAiState = "wander" | "hurt" | "dead";

export interface MobOpts {
  scene: Phaser.Scene;
  ladderIndex: number;
  spawnCol: number;
  tilePx: number;
  baselineY: number;
  heightFn: (col: number) => number;
  /** Wander extent in pixels around spawnCol*tilePx. */
  wanderExtentPx?: number;
  speedPx?: number;
  spriteHeightPx: number;
  idleAnimKey: string;
  hurtTextureKey: string;
  hurtFrames?: number;
}

const DEFAULT_WANDER_PX = 100;
const DEFAULT_SPEED = 36;
const HURT_DURATION_MS = 600;
const KNOCKBACK_PX = 80;
const KNOCKBACK_MS = 220;

export class Mob {
  readonly sprite: Phaser.GameObjects.Sprite;
  readonly ladderIndex: number;
  hp: number;
  state: MobAiState = "wander";
  private opts: MobOpts;
  private spawnX: number;
  private wanderMin: number;
  private wanderMax: number;
  private dirSign: 1 | -1 = 1;
  private hurtUntil = 0;
  private idleAnim: string;
  private hurtAnim: string;

  constructor(opts: MobOpts) {
    this.opts = opts;
    this.ladderIndex = opts.ladderIndex;
    this.hp = opts.ladderIndex + 1; // TC-084: i+1 hits

    const spawnX = opts.spawnCol * opts.tilePx + opts.tilePx / 2;
    this.spawnX = spawnX;
    const ext = opts.wanderExtentPx ?? DEFAULT_WANDER_PX;
    this.wanderMin = spawnX - ext;
    this.wanderMax = spawnX + ext;

    const colH = opts.heightFn(opts.spawnCol);
    const surfaceY = opts.baselineY - colH * opts.tilePx;

    // Build the idle anim if it doesn't exist (scene may have made it; harmless).
    this.idleAnim = opts.idleAnimKey;
    this.hurtAnim = `${opts.hurtTextureKey}_anim`;
    const scene = opts.scene;
    if (!scene.anims.exists(this.hurtAnim) && scene.textures.exists(opts.hurtTextureKey)) {
      const fcount = opts.hurtFrames ?? 4;
      scene.anims.create({
        key: this.hurtAnim,
        frames: Array.from({ length: fcount }, (_, f) => ({ key: opts.hurtTextureKey, frame: f })),
        frameRate: Math.ceil((fcount * 1000) / HURT_DURATION_MS),
        repeat: 0,
      });
    }

    const sprite = scene.add.sprite(spawnX, surfaceY, opts.idleAnimKey, 0);
    sprite.setOrigin(0.5, 1.0);
    const tex = scene.textures.get(opts.idleAnimKey);
    const f0 = tex.get(0);
    const aspect = (f0?.width ?? 1) / Math.max(1, f0?.height ?? 1);
    sprite.setDisplaySize(opts.spriteHeightPx * aspect, opts.spriteHeightPx);
    sprite.setDepth(800);
    if (scene.anims.exists(opts.idleAnimKey)) sprite.play(opts.idleAnimKey);
    this.sprite = sprite;

    // Random initial direction based on ladder index for determinism.
    this.dirSign = opts.ladderIndex % 2 === 0 ? 1 : -1;
  }

  update(dtMs: number, nowMs: number) {
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

    // Wander.
    const speed = this.opts.speedPx ?? DEFAULT_SPEED;
    this.sprite.x += this.dirSign * speed * dt;
    if (this.sprite.x <= this.wanderMin) {
      this.sprite.x = this.wanderMin;
      this.dirSign = 1;
    } else if (this.sprite.x >= this.wanderMax) {
      this.sprite.x = this.wanderMax;
      this.dirSign = -1;
    }
    this.sprite.setFlipX(this.dirSign === -1);

    // Snap feet (in case heights differ across wander span).
    const col = Math.floor(this.sprite.x / this.opts.tilePx);
    const colH = this.opts.heightFn(col);
    this.sprite.y = this.opts.baselineY - colH * this.opts.tilePx;
  }

  /**
   * Apply one point of damage. Returns true if the mob died from this hit.
   */
  takeHit(nowMs: number, knockbackDir: 1 | -1 = 1): { died: boolean; hpLeft: number } {
    if (this.state === "dead") return { died: false, hpLeft: 0 };
    this.hp -= 1;
    // Knockback tween — clamped to wander bounds so the mob doesn't escape its lane.
    const targetX = Phaser.Math.Clamp(
      this.sprite.x + knockbackDir * KNOCKBACK_PX,
      this.wanderMin,
      this.wanderMax,
    );
    this.opts.scene.tweens.add({
      targets: this.sprite,
      x: targetX,
      duration: KNOCKBACK_MS,
      ease: "Cubic.easeOut",
    });
    if (this.hp <= 0) {
      this.state = "dead";
      // Fade out then destroy.
      this.opts.scene.tweens.add({
        targets: this.sprite,
        alpha: 0,
        duration: 280,
        onComplete: () => this.sprite.destroy(),
      });
      return { died: true, hpLeft: 0 };
    }
    // Non-fatal: play hurt anim once.
    this.state = "hurt";
    this.hurtUntil = nowMs + HURT_DURATION_MS;
    if (this.opts.scene.anims.exists(this.hurtAnim)) {
      this.sprite.play(this.hurtAnim, true);
    }
    return { died: false, hpLeft: this.hp };
  }

  isAlive(): boolean {
    return this.state !== "dead";
  }

  snapshot() {
    return {
      ladderIndex: this.ladderIndex,
      hp: this.hp,
      state: this.state,
      x: this.sprite.x,
      y: this.sprite.y,
      alive: this.isAlive(),
    };
  }
}

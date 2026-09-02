// The boss and its shots on screen: sprites, and nothing that can be wrong.
//
// Everything here is a projection of the director's state onto Phaser objects.
// It decides no outcome and reads no clock of its own: the bob rides the
// simulation's own clock so a replayed run draws identical frames, and the hit
// flash is a comparison against a timestamp the director stamped.
//
// The boss sits one rung behind the avatar and its shots one rung in front, so
// a salvo crossing the avatar reads as passing between the two rather than
// disappearing behind either.

import type { RunnerBoss, RunnerProjectile } from "./contract";
import {
  BOSS_HIT_FLASH_MS,
  type BossState,
  bossBobRows,
  offsetScreenX,
  type EncounterConfig,
  type EncounterShot,
} from "./encounter-arithmetic";
import type { ParallaxStageView } from "./parallax";
import { RUNNER_DEPTHS } from "./parallax";
import { rowToScreenY, type RunnerWorld } from "./world";

export interface BossViewOptions {
  readonly bossTextureKey: (bossId: string, state: string) => string;
  readonly bossAnimationKey: (bossId: string, state: string) => string;
  readonly projectileTextureKey: (projectileId: string) => string;
  /** The published boss, for its per-state rebase multipliers and anchors. */
  readonly boss: RunnerBoss;
  readonly projectiles: readonly RunnerProjectile[];
}

/** Phaser's `TintModes.FILL`. */
const TINT_MODE_FILL = 1;

interface ShotView {
  readonly image: Phaser.GameObjects.Image;
}

export function buildBossView(
  scene: Phaser.Scene,
  world: RunnerWorld,
  options: BossViewOptions,
): ParallaxStageView {
  const config = world.config;
  const encounter = config.encounter;
  const bossSprite = scene.add
    .sprite(0, 0, options.bossTextureKey(encounter?.bossId ?? "", "hover"), 0)
    .setDepth(RUNNER_DEPTHS.boss)
    .setOrigin(0.5, 1)
    .setVisible(false);
  // One scale for the whole actor, from the measured cell: the per-state
  // rebase multiplier rides on top, exactly as the avatar's does.
  const baseScale =
    (config.playerHeightTiles * config.tilePx) / options.boss.calibration.sourcePxPerUnit;
  const shotContainer = scene.add.container(0, 0).setDepth(RUNNER_DEPTHS.shot);
  const shotViews = new Map<number, ShotView>();
  const projectileById = new Map(
    options.projectiles.map((entry) => [entry.projectileId, entry] as const),
  );
  const motionByState = new Map(options.boss.motions.map((entry) => [entry.state, entry]));
  let wornState: string | null = null;
  let wornImpulses = -1;

  function syncBoss(boss: BossState, config: EncounterConfig, clockMs: number): void {
    bossSprite.setVisible(true);
    // The strip replays on the attack IMPULSE, not only on the state change:
    // a second salvo inside the same `attack` state must restart the swing or
    // it reads as the boss firing without moving.
    const replay = boss.motion === "attack" && boss.attackImpulses !== wornImpulses;
    if (boss.motion !== wornState || replay) {
      wornState = boss.motion;
      wornImpulses = boss.attackImpulses;
      const motion = motionByState.get(boss.motion);
      if (motion !== undefined) {
        bossSprite.setScale(baseScale * motion.rebaseMultiplier);
        bossSprite.setOrigin(0.5, motion.anchor === "bottom" ? 1 : 0);
        bossSprite.play(options.bossAnimationKey(config.bossId, boss.motion));
      }
    }
    // The hover bobs; a dying machine does not, because it is falling.
    const bob = boss.motion === "death" ? 0 : bossBobRows(clockMs);
    bossSprite.setPosition(
      offsetScreenX(boss.offsetColumns, world.config.avatarScreenX, world.config.tilePx),
      rowToScreenY(boss.y + bob, world.config),
    );
    if (boss.lastHitAtMs !== null && clockMs - boss.lastHitAtMs < BOSS_HIT_FLASH_MS) {
      // Tint mode FILL by its numeric value: this module is deliberately free
      // of a Phaser *value* import, because pulling the browser bundle in
      // makes every test that touches it need a DOM.
      bossSprite.setTint(0xffffff).setTintMode(TINT_MODE_FILL);
    } else {
      bossSprite.clearTint();
    }
  }

  function syncShot(shot: EncounterShot, config: EncounterConfig): void {
    let view = shotViews.get(shot.id);
    if (view === undefined) {
      const projectileId =
        shot.owner === "boss" ? config.bossProjectileId : config.playerProjectileId;
      const image = scene.add.image(0, 0, options.projectileTextureKey(projectileId));
      const drawn = projectileById.get(projectileId);
      // The declared length is along the travel axis, which is the drawn
      // width; the height follows from the trimmed raster's own aspect, so a
      // thick knot and a slim pin of the same declared length stay in
      // proportion rather than both being squared off.
      const lengthPx =
        (drawn?.lengthUnits ?? config.projectileHeightRows) *
        world.config.playerHeightTiles *
        world.config.tilePx;
      const aspect = image.width > 0 ? image.height / image.width : 1;
      image.setDisplaySize(lengthPx, lengthPx * aspect);
      // Every projectile is drawn pointing right, so only a leftward shot is
      // mirrored; a directionless silhouette reads the same either way and is
      // left alone.
      image.setFlipX(shot.vx < 0 && drawn?.silhouette !== "radial_v1");
      shotContainer.add(image);
      view = { image };
      shotViews.set(shot.id, view);
    }
    view.image.setPosition(
      offsetScreenX(shot.x, world.config.avatarScreenX, world.config.tilePx),
      rowToScreenY(shot.row, world.config),
    );
  }

  return {
    sync() {
      const state = world.encounter;
      const config = world.config.encounter;
      if (state === null || config === null) return;
      const clockMs = world.vitals.clockMs;
      if (state.boss === null) {
        bossSprite.setVisible(false);
        wornState = null;
      } else {
        syncBoss(state.boss, config, clockMs);
      }
      const live = new Set<number>();
      for (const shot of state.shots) {
        syncShot(shot, config);
        live.add(shot.id);
      }
      for (const [id, view] of shotViews) {
        if (live.has(id)) continue;
        view.image.destroy();
        shotViews.delete(id);
      }
    },
  };
}

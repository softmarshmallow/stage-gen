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

import type { RunnerProjectile } from "./contract";
import {
  BOSS_HIT_FLASH_MS,
  type BossState,
  type EncounterConfig,
  type EncounterShot,
} from "./encounter-arithmetic";
import type { ParallaxStageView } from "./parallax";
import { RUNNER_DEPTHS } from "./parallax";
import { rowToScreenY, type RunnerWorld } from "./world";

/** How far the hovering boss rides up and down, in rows. */
export const BOSS_BOB_ROWS = 0.18;
/** Seconds for one full bob. */
export const BOSS_BOB_PERIOD_SECONDS = 2.4;

export interface BossViewOptions {
  readonly bossTextureKey: (bossId: string, state: string) => string;
  readonly projectileTextureKey: (projectileId: string) => string;
  /** Drawn source pixels per player height, per boss motion state. */
  readonly bossSourcePxPerUnit: number;
  readonly projectiles: readonly RunnerProjectile[];
}

/** The bob offset in rows at one moment of the simulation's own clock. */
export function bossBobRows(clockMs: number): number {
  return Math.sin((clockMs / 1000) * ((2 * Math.PI) / BOSS_BOB_PERIOD_SECONDS)) * BOSS_BOB_ROWS;
}

/** Screen x of a point measured in columns ahead of the avatar. */
export function offsetScreenX(offsetColumns: number, world: RunnerWorld): number {
  return world.config.avatarScreenX + offsetColumns * world.config.tilePx;
}

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
    .setVisible(false);
  const shotContainer = scene.add.container(0, 0).setDepth(RUNNER_DEPTHS.shot);
  const shotViews = new Map<number, ShotView>();
  const projectileById = new Map(
    options.projectiles.map((entry) => [entry.projectileId, entry] as const),
  );
  let wornState: string | null = null;
  let wornImpulses = 0;

  function syncBoss(boss: BossState, config: EncounterConfig, clockMs: number): void {
    bossSprite.setVisible(true);
    const scale =
      (config.bossHeightRows * world.config.tilePx) / options.bossSourcePxPerUnit;
    const key = options.bossTextureKey(config.bossId, boss.motion);
    const replay = boss.motion === "attack" && boss.attackImpulses !== wornImpulses;
    if (boss.motion !== wornState || replay) {
      bossSprite.setTexture(key, 0);
      wornState = boss.motion;
      wornImpulses = boss.attackImpulses;
    }
    // The hover bobs; a dying machine does not, because it is falling.
    const bob = boss.motion === "death" ? 0 : bossBobRows(clockMs);
    bossSprite
      .setPosition(
        offsetScreenX(boss.offsetColumns, world),
        rowToScreenY(boss.y + bob, world.config),
      )
      .setScale(scale)
      .setOrigin(0.5, 1);
    if (boss.lastHitAtMs !== null && clockMs - boss.lastHitAtMs < BOSS_HIT_FLASH_MS) {
      bossSprite.setTint(0xffffff).setTintMode(Phaser.TintModes.FILL);
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
      offsetScreenX(shot.x, world),
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

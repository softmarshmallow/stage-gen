// The pool that gives a thrown object a sprite.
//
// Everything that decides an outcome lives in `projectile-flight.ts`; this file owns a Phaser
// image, a depth and a texture key, and nothing else. The division is the same one `Mob` and
// `combat.ts` already draw, and it is what lets the reach, the range budget and the collision band
// be tested without a browser.
//
// The system holds no reference back to the scene and no reference to a `Mob`. `update` is handed
// the target boxes for this frame and *returns* what it hit, the way `PortalSystem.update` returns
// an activation. A pool that could reach into the scene to apply damage would be a second place
// combat resolves, and the first one is already 40 lines long.

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./depths";
import {
  advanceShot,
  firstOverlappingTarget,
  launchShot,
  shotExpiry,
  type ShotExpiry,
  type ShotState,
  type ShotTarget,
  type WorldLimits,
} from "./projectile-flight";
import type { ProjectileProfile } from "./projectile-class";

/** How many shots may be in the air at once. */
export const PROJECTILE_POOL_CAP = 16;

export type ProjectileSystemOpts = Readonly<{
  scene: Phaser.Scene;
  tilePx: number;
  /** Texture the shot is drawn with. The projectile catalog's key, resolved by the scene. */
  textureKey: string;
  /**
   * How long the subject draws, in screen pixels, along its own travel axis.
   *
   * A length rather than a height because that is the axis the producer measured, and the texture
   * is loaded trimmed so the number describes the artwork rather than the canvas it arrived on.
   */
  drawnLengthPx: number;
  /** Everything about how this object moves, is oriented, and resolves on arrival. */
  projectile: ProjectileProfile;
  world: WorldLimits;
}>;

type Shot = {
  state: ShotState;
  sprite: Phaser.GameObjects.Image;
  /** Accumulated free spin, in degrees. Stepped from the frame delta like everything else. */
  spinDegrees: number;
  /** Targets this shot has already resolved against, so a piercing shot cannot hit one twice. */
  struck: Set<number>;
};

/** One resolved impact, handed back to the scene to turn into damage. */
export type ProjectileHit = Readonly<{
  /** Index into the target array the caller passed to `update`. */
  targetIndex: number;
  /** Where the throw started. The scene seeds its critical roll from this, not from the impact. */
  spawnX: number;
  /** Which way it was travelling, for knockback. */
  dirSign: 1 | -1;
  impactX: number;
  impactY: number;
}>;

export class ProjectileSystem {
  private readonly shots: Shot[] = [];
  private nextShotId = 1;

  constructor(private readonly opts: ProjectileSystemOpts) {}

  /** How many shots are currently in the air. */
  get liveCount(): number {
    return this.shots.length;
  }

  /** What this pool throws, for callers that must reason about the flight before one exists. */
  get profile(): ProjectileProfile {
    return this.opts.projectile;
  }

  /**
   * Put one shot in the air, or return null when the pool is full or the texture is missing.
   *
   * Returning null rather than throwing is deliberate and it is what the ammunition rule reads:
   * the caller only spends a round if a shot actually left the hand.
   */
  fire(input: {
    originX: number;
    footY: number;
    bodyHeightPx: number;
    dirSign: 1 | -1;
  }): ShotState | null {
    if (this.shots.length >= PROJECTILE_POOL_CAP) return null;
    if (!this.opts.scene.textures.exists(this.opts.textureKey)) return null;

    const flight = this.opts.projectile.flight;
    const state = launchShot({
      id: `shot_${this.nextShotId++}`,
      originX: input.originX,
      footY: input.footY,
      bodyHeightPx: input.bodyHeightPx,
      dirSign: input.dirSign,
      tilePixels: this.opts.tilePx,
      speedTilesPerSecond: flight.speedTilesPerSecond,
      maxRangeTiles: flight.maxRangeTiles,
      releaseForwardTiles: flight.releaseForwardTiles,
      releaseHeightFraction: flight.releaseHeightFraction,
      halfWidthTiles: flight.halfWidthTiles,
      halfHeightTiles: flight.halfHeightTiles,
    });

    const sprite = this.opts.scene.add.image(state.x, state.y, this.opts.textureKey);
    sprite.setOrigin(0.5, 0.5);
    // The texture is loaded trimmed, so the frame IS the subject: its aspect is the artwork's, the
    // origin is the subject's own centre, and a rotation therefore pivots inside the object rather
    // than around whatever empty canvas it was generated on.
    const frame = this.opts.scene.textures.get(this.opts.textureKey).get();
    const aspect = (frame?.width ?? 1) / Math.max(1, frame?.height ?? 1);
    const length = this.opts.drawnLengthPx;
    sprite.setDisplaySize(length, length / Math.max(aspect, 0.0001));
    sprite.setDepth(SCENE_CONTENT_DEPTH.effect);
    const orientation = this.opts.projectile.orientation;
    // A subject drawn pointing right is mirrored to travel left. One drawn with no leading end is
    // not, because there is nothing for the mirror to preserve.
    sprite.setFlipX(orientation.mirrorWhenReversed && input.dirSign < 0);
    this.applyOrientation(sprite, state, 0);
    this.shots.push({ state, sprite, spinDegrees: 0, struck: new Set() });
    return state;
  }

  /**
   * Point or spin one sprite for the frame it is now on.
   *
   * Aim reads the velocity rather than the launch direction, so an arcing object noses over as it
   * falls; a flat flight leaves the angle at zero and the call costs nothing. Spin accumulates from
   * the frame delta rather than from a clock, for the same reason the position does.
   */
  private applyOrientation(
    sprite: Phaser.GameObjects.Image,
    state: ShotState,
    spinDegrees: number,
  ): void {
    const orientation = this.opts.projectile.orientation;
    if (orientation.spinDegreesPerSecond !== 0) {
      sprite.setAngle(spinDegrees);
      return;
    }
    if (!orientation.aimAlongFlight) return;
    // Measured from the direction of travel, and mirrored back out when the sprite is flipped so a
    // left-travelling object noses down rather than up.
    const angle = (Math.atan2(state.vyPx, Math.abs(state.vxPx)) * 180) / Math.PI;
    // `|| 0` normalises the negative zero a mirrored level flight produces, so a flat shot reports
    // an angle of exactly zero whichever way it is travelling.
    sprite.setAngle((state.dirSign < 0 ? -angle : angle) || 0);
  }

  /**
   * Step every shot, resolve collisions, and return the impacts.
   *
   * `targets` is the caller's list for this frame; indices in the returned hits point into it.
   * Iterating backwards is what lets a shot be removed in the same pass that resolved it.
   */
  update(deltaMs: number, targets: readonly ShotTarget[]): readonly ProjectileHit[] {
    const { flight, impact, orientation } = this.opts.projectile;
    const hits: ProjectileHit[] = [];
    for (let index = this.shots.length - 1; index >= 0; index -= 1) {
      const shot = this.shots[index];
      const next = advanceShot(shot.state, deltaMs, flight.gravityPxPerSecond2);
      shot.state = next;
      shot.spinDegrees =
        (shot.spinDegrees + (orientation.spinDegreesPerSecond * deltaMs) / 1000) % 360;
      shot.sprite.setPosition(next.x, next.y);
      this.applyOrientation(shot.sprite, next, shot.spinDegrees);

      let expiry: ShotExpiry = shotExpiry(next, this.opts.world);
      if (expiry === null) {
        // Every target the box touches this frame, not just the first. A bursting shot resolves
        // against a whole crowd on the frame it arrives; a piercing one takes what it passes
        // through and keeps a record, so a target it has already crossed cannot be struck twice.
        let connected = false;
        while (shot.struck.size < impact.maxTargets) {
          const targetIndex = firstOverlappingTarget(next, targets, shot.struck);
          if (targetIndex < 0) break;
          shot.struck.add(targetIndex);
          connected = true;
          hits.push(
            Object.freeze({
              targetIndex,
              spawnX: next.spawnX,
              dirSign: next.dirSign,
              impactX: next.x,
              impactY: next.y,
            }),
          );
        }
        // Decided after the whole frame is resolved, not inside the loop: a shot that stops on
        // contact still resolves against everything it arrived among.
        if ((connected && !impact.continuesAfterHit) || shot.struck.size >= impact.maxTargets) {
          expiry = "hit";
        }
      }
      if (expiry !== null) {
        shot.sprite.destroy();
        this.shots.splice(index, 1);
      }
    }
    // Backwards iteration produced these in reverse scene order; the caller applies damage in the
    // order shots were fired, so a replay resolves two simultaneous impacts the same way twice.
    return Object.freeze(hits.reverse());
  }

  clearAll(): void {
    for (const shot of this.shots) shot.sprite.destroy();
    this.shots.length = 0;
  }
}

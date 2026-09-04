// Ground dust: what running, sliding, taking off and landing kick up.
//
// The avatar is pinned on screen and the world scrolls under it, so a puff born at the feet
// belongs to the ground, not to the character: it drifts away at the scroll speed and thins as
// it swells. Everything here is a pure sample over the fixed-step clock, the way the platformer's
// impact presentation is: a puff is a record of where and when it was born, and a frame asks what
// every live record looks like at one instant. Nothing owns an emitter, a timer or a random draw,
// so a fixed-step replay of a run draws the same dust on the same frame as the run that was
// played.
//
// No asset is drawn for any of this. At foot scale a puff is a silhouette with an ink rim, which
// is the register the package already paints in, and a painted sprite would show nothing an
// ellipse cannot. World-space effect sprites land under `2d/fx/sprite.*` when a game wants more
// than a silhouette; this module is the caller they would replace.

import type Phaser from "phaser";
import {
  easeOutCubic,
  ParticleRing,
  particleUnitNoise,
  parseParticlesBlock,
  type ParticlesBlockView,
} from "@/lib/families/particles";
import type { BlockTable } from "@/lib/manifest/blocks";
import { RUNNER_BLOCKS } from "./contract";
import type { GameSystem } from "@/lib/kernel/systems";
import { stepClockMs } from "./vitals";
import type { RunnerWorld } from "./world";
import { rowToScreenY } from "./world";

/** How long one puff lives, from a flat speck at the heel to nothing. */
export const DUST_PUFF_LIFE_MS = 380;
/** A stride puff every so often while running; the cadence is not the strip's footfall. */
export const DUST_STRIDE_INTERVAL_MS = 230;
/** A slide lays dust far denser than a run: it is one long contact, not a footfall. */
export const DUST_SLIDE_INTERVAL_MS = 90;
export const DUST_TAKEOFF_PUFFS = 3;
export const DUST_LAND_PUFFS = 4;
export const DUST_DEFAULT_ACTIVE_CAP = 64;
/** Cream paper over graphite ink: the flat fill and the rim the package's style keywords name. */
export const DUST_FILL_COLOR = 0xf3ead9;
export const DUST_RIM_COLOR = 0x2a2f3a;
export const DUST_RIM_WIDTH_PX = 2;

const MAX_ACTIVE_CAP = 256;
/**
 * Puff radius as a fraction of a tile, by kind; the stride grows with the speed ramp. A tile
 * is about a third of the avatar, and dust that reads at runner speed is a third to a half of
 * the character it trails - a speck vanishes under the strip's own motion.
 */
const RADIUS_TILE_FRACTION = Object.freeze({
  stride: 0.18,
  slide: 0.28,
  takeoff: 0.24,
  land: 0.3,
});
const STRIDE_INTENSITY_RADIUS_TILE_FRACTION = 0.12;
/**
 * A puff is solid for most of its life and fades only at the end. Flat cel dust pops out
 * rather than dissolving, and an opaque cloud is also what lets its lobes overlap without a
 * seam: two half-transparent ellipses show their union as a darker lens where they cross.
 */
const SOLID_LIFE_FRACTION = 0.6;
/** How far up its own half-height the newborn puff sits, so it rests on the line, not across it. */
const SEAT_FRACTION = 0.7;

export type DustKind = "stride" | "slide" | "takeoff" | "land";

/** One puff as the presentation reads it: where and when the ground was struck. */
export type DustRecord = Readonly<{
  kind: DustKind;
  /** Which puff of a burst this is; a trail puff is always 0. */
  index: number;
  /** The run's seed folded with the birth frame, so shapes replay with the run. */
  seed: number;
  bornAtMs: number;
  /** Screen x of the feet at birth; the avatar is pinned, so this is the same for a run. */
  feetX: number;
  /** Screen y of the ground under the feet at birth. */
  feetY: number;
  /** Camera scroll at birth: the puff is locked to the ground that has since moved on. */
  scrollXAtBirth: number;
  tilePx: number;
  /** 0..1 along the speed ramp; only the stride reads it. */
  intensity: number;
}>;

export type DustPuff = Readonly<{
  x: number;
  y: number;
  radiusX: number;
  radiusY: number;
  alpha: number;
  /** Which contact threw this puff, so a renderer can choose art per event. */
  kind: DustKind;
  /** 0..1 through its life, so a renderer with stages can choose one. */
  progress: number;
}>;

/**
 * Deterministic unit noise in [0, 1) for one seed and channel; no state, no
 * wall clock. The `particles` family's, under this genre's name: the platformer
 * had written the same eight lines out as `impactUnitNoise`.
 */
export const dustUnitNoise = particleUnitNoise;

/**
 * Where a puff is kicked, in tiles, relative to the feet: `x` positive is forward (the way the
 * avatar faces), `y` positive is up. A stride and a slide throw dust back along the ground; a
 * takeoff throws it back and up off the push; a landing splays it both ways.
 */
function kick(record: DustRecord): Readonly<{ x: number; y: number }> {
  const channel = record.index * 16;
  const noise = (offset: number) => dustUnitNoise(record.seed, channel + offset);
  switch (record.kind) {
    case "stride":
      return { x: -(0.25 + 0.2 * noise(1)), y: 0.16 + 0.1 * noise(2) };
    case "slide":
      return { x: -(0.45 + 0.3 * noise(1)), y: 0.2 + 0.14 * noise(2) };
    case "takeoff": {
      const fan = (record.index / Math.max(1, DUST_TAKEOFF_PUFFS - 1)) * 0.5;
      return { x: -(0.35 + 0.45 * fan + 0.15 * noise(1)), y: 0.12 + 0.4 * (1 - fan) + 0.1 * noise(2) };
    }
    case "land": {
      // The ground is already sliding back under the feet, so the forward half of the splay
      // must be thrown harder than the back half or it lands under the avatar and is never seen.
      const side = record.index % 2 === 0 ? -1 : 1;
      const reach = (0.3 + 0.35 * Math.floor(record.index / 2)) * (side === 1 ? 1.8 : 1);
      return { x: side * (reach + 0.15 * noise(1)), y: 0.14 + 0.12 * noise(2) };
    }
  }
}

/**
 * One puff at one instant, or null once it is spent (or not yet born).
 *
 * The puff starts wide and flat at the heel, swells into a rounder cloud as it lifts, and thins
 * along a curve that keeps it solid for its first third. Its x follows the ground: however far
 * the camera has scrolled since birth is how far the puff has slid back along the screen.
 */
export function sampleDustPuff(record: DustRecord, nowMs: number, scrollXNow: number): DustPuff | null {
  const safeNowMs = Number.isFinite(nowMs) ? nowMs : record.bornAtMs;
  const age = safeNowMs - record.bornAtMs;
  if (age < 0 || age >= DUST_PUFF_LIFE_MS) return null;
  const progress = age / DUST_PUFF_LIFE_MS;
  const swell = easeOutCubic(progress);
  const groundDrift = scrollXNow - record.scrollXAtBirth;
  const thrown = kick(record);
  const tile = record.tilePx;
  const radius =
    tile *
    (RADIUS_TILE_FRACTION[record.kind] +
      (record.kind === "stride" ? STRIDE_INTENSITY_RADIUS_TILE_FRACTION * record.intensity : 0)) *
    (0.6 + 0.9 * dustUnitNoise(record.seed, record.index * 16 + 3));
  const grown = radius * (0.45 + 0.85 * swell);
  const radiusY = grown * (0.7 + 0.3 * swell);
  const fade = Math.max(0, (progress - SOLID_LIFE_FRACTION) / (1 - SOLID_LIFE_FRACTION));
  return Object.freeze({
    x: record.feetX - groundDrift + thrown.x * tile * swell,
    y: record.feetY - radiusY * SEAT_FRACTION - thrown.y * tile * swell,
    radiusX: grown * (1 + 0.35 * (1 - swell)),
    radiusY,
    alpha: 1 - fade * fade,
    kind: record.kind,
    progress,
  });
}

export type DustLobe = Readonly<{ x: number; y: number; radiusX: number; radiusY: number }>;

/**
 * The cloud a puff is drawn as: its own ellipse and two smaller lobes riding its upper
 * shoulders, so the union reads as cartoon dust rather than a bubble. Pure geometry from the
 * puff, so a canvas and a headless render draw the same silhouette.
 */
export function dustCloudLobes(puff: DustPuff): readonly DustLobe[] {
  const { x, y, radiusX, radiusY } = puff;
  return Object.freeze([
    Object.freeze({ x, y, radiusX, radiusY }),
    Object.freeze({ x: x - radiusX * 0.55, y: y - radiusY * 0.35, radiusX: radiusX * 0.6, radiusY: radiusY * 0.62 }),
    Object.freeze({ x: x + radiusX * 0.5, y: y - radiusY * 0.45, radiusX: radiusX * 0.5, radiusY: radiusY * 0.55 }),
  ]);
}

/** True once nothing of the record can still be drawn. */
export function dustRecordSpent(record: DustRecord, nowMs: number): boolean {
  return nowMs - record.bornAtMs >= DUST_PUFF_LIFE_MS;
}

/**
 * The ellipse box is the puff's core, not its outline: a drawn cloud carries lobes past it, so a
 * sprite fitted exactly inside the box reads smaller than the shape it replaces. This is how much
 * bigger the art is drawn, measured against the procedural draw at true game size.
 */
export const DUST_SPRITE_OVERSCAN = 1.35;

export type DustSpriteRect = Readonly<{ x: number; y: number; width: number; height: number }>;

/**
 * Where one puff's art goes: `x`/`y` is the sprite's centre, sized to fit the puff's box with the
 * frame's own aspect preserved and its base seated where the ellipse's base sits. Preserving the
 * frame aspect is what keeps a wide cloud wide - stretching art to the box would undo the
 * silhouette the art was chosen for.
 */
export function dustSpriteRect(puff: DustPuff, frameWidth: number, frameHeight: number): DustSpriteRect {
  if (!(frameWidth > 0) || !(frameHeight > 0)) {
    throw new Error("dust sprite geometry requires a positive frame size");
  }
  const scale =
    Math.min((puff.radiusX * 2) / frameWidth, (puff.radiusY * 2) / frameHeight) * DUST_SPRITE_OVERSCAN;
  const width = frameWidth * scale;
  const height = frameHeight * scale;
  return Object.freeze({ x: puff.x, y: puff.y + puff.radiusY - height / 2, width, height });
}

/** What the scene must offer: a surface cleared each frame, then one call per live puff. */
export interface DustCanvas {
  begin(): void;
  puff(puff: DustPuff): void;
}

export const SILENT_DUST_CANVAS: DustCanvas = Object.freeze({
  begin: () => undefined,
  puff: () => undefined,
});

export interface DustSystemOptions {
  readonly reducedMotion?: boolean;
  readonly maxActive?: number;
}

export interface DustSystemSnapshot {
  readonly reducedMotion: boolean;
  readonly activeCount: number;
  readonly records: readonly DustRecord[];
}

export interface DustSystem extends GameSystem<RunnerWorld> {
  snapshot(): DustSystemSnapshot;
}

/**
 * The block this genre's dust art is authored in.
 *
 * `fx`'s `[sprite.dust]` is the atlas the puffs are cut from, and it is
 * optional in every package: without one the run draws the procedural
 * silhouette, which is an answer. A package that publishes an `fx` block this
 * build cannot read is refused, by name, from the particles.
 */
export const RUNNER_PARTICLES_BLOCK = Object.freeze({
  block: "fx",
  version: RUNNER_BLOCKS.fx,
  optional: true,
});

/** Gate the runner's particles block. Refuses by naming `fx`. */
export function parseRunnerParticlesBlock(blocks: BlockTable): ParticlesBlockView {
  return parseParticlesBlock(blocks, RUNNER_PARTICLES_BLOCK);
}

/**
 * The dust system: presentation, so it writes no world key.
 *
 * What lays a puff is now what the world said happened. A takeoff, a landing
 * and the first frame of a slide are the avatar's own occurrences — the same
 * three the cue system hears — and the two trails are cadences over levels the
 * avatar publishes, which is a read and not a copy. It used to keep four
 * private copies of that slice (`prevJumpImpulses`, `prevGrounded`,
 * `prevSliding`, `prevDistance`) and diff them frame to frame, and the fourth
 * existed only to notice a restart, which the composition's own reset now says.
 *
 * The ring, the cap and the noise are the `particles` family's; what a puff
 * looks like is this genre's, and stays here. Pinned behind the cue system so
 * the sealed order stays unique whatever the registration order; it reads
 * nothing the cue system writes.
 */
export function createDustSystem(
  canvas: DustCanvas,
  options: DustSystemOptions = {},
): DustSystem {
  const reducedMotion = options.reducedMotion ?? false;
  const ring = new ParticleRing<DustRecord>({
    max: options.maxActive ?? DUST_DEFAULT_ACTIVE_CAP,
    ceiling: MAX_ACTIVE_CAP,
  });
  let strideTick = -1;
  let slideTick = -1;
  /** The first frame of a new run lays nothing; see `reset`. */
  let resumed = false;

  return {
    id: "runner/dust",
    contractVersion: "dust-system-v2",
    reads: ["avatar", "run", "camera", "difficulty"],
    writes: [],
    consumes: ["jumped", "landed", "slid"],
    after: ["runner/parallax", "runner/audio"],
    update(world, step) {
      const nowMs = stepClockMs(step.now);
      const avatar = world.avatar;
      const running = world.run.phase === "running";
      const scrollX = world.camera.scrollX;
      const config = world.config;
      const ramp = Math.max(1e-9, config.arithmetic.maxSpeedMultiplier - 1);
      const intensity = Math.max(0, Math.min(1, (world.difficulty.speedMultiplier - 1) / ramp));
      const born = (kind: DustKind, count: number) => {
        const feetY = rowToScreenY(avatar.y, config);
        for (let index = 0; index < count; index += 1) {
          ring.remember(
            Object.freeze({
              kind,
              index,
              seed: (world.run.seed ^ Math.imul(step.frame + 1, 0x27d4eb2f)) >>> 0,
              bornAtMs: nowMs,
              feetX: config.avatarScreenX,
              feetY,
              scrollXAtBirth: scrollX,
              tilePx: config.tilePx,
              intensity,
            }),
          );
        }
      };

      const quiet = resumed;
      resumed = false;
      if (running && !reducedMotion && !quiet) {
        // A ground takeoff kicks dust; an air jump has no ground to kick, and
        // the occurrence says which it was rather than the reader guessing from
        // a copy of last frame's `grounded`.
        for (const jump of world.events.ofType("jumped")) {
          if (!jump.airJump) born("takeoff", DUST_TAKEOFF_PUFFS);
        }
        for (const _landing of world.events.ofType("landed")) born("land", DUST_LAND_PUFFS);
        if (avatar.grounded && avatar.sliding) {
          const tick = Math.floor(nowMs / DUST_SLIDE_INTERVAL_MS);
          // The first frame of a slide lays its own puff rather than waiting
          // for the cadence, and that first frame is an occurrence.
          if (world.events.ofType("slid").length > 0 || tick !== slideTick) {
            slideTick = tick;
            born("slide", 1);
          }
        } else {
          slideTick = -1;
        }
        if (avatar.grounded && !avatar.sliding) {
          const tick = Math.floor(nowMs / DUST_STRIDE_INTERVAL_MS);
          if (tick !== strideTick) {
            strideTick = tick;
            born("stride", 1);
          }
        } else {
          strideTick = -1;
        }
      }

      ring.prune((record) => dustRecordSpent(record, nowMs));
      canvas.begin();
      for (const record of ring.records) {
        const puff = sampleDustPuff(record, nowMs, scrollX);
        if (puff !== null) canvas.puff(puff);
      }
    },
    /**
     * A new run lays no dust from the old one.
     *
     * This is the fourth shadow copy gone: the system used to notice a restart
     * by watching the avatar's distance go backwards, which is a read of
     * another slice's history. The composition knows, and says so.
     */
    reset() {
      ring.clear();
      strideTick = -1;
      slideTick = -1;
      // And the first frame of the new run lays nothing, which is what the
      // distance-watching version did: it spent that frame resynchronising its
      // four copies and laid no puff. Kept exactly, because this commit is a
      // refactor of where the decision lives and not of what it decides — the
      // dust recording is byte-identical across all six hundred frames, and a
      // run's first frame laying a stride puff is a change somebody should make
      // deliberately, with its own evidence.
      resumed = true;
    },
    snapshot: () =>
      Object.freeze({
        reducedMotion,
        activeCount: ring.count,
        records: Object.freeze([...ring.records]),
      }),
  };
}

/**
 * One published atlas cell per dust kind: the sub-frame name already registered on the texture,
 * and the size that frame occupies. The pipeline measures the cells and publishes them; the
 * consumer never re-derives them from the image, the way it never re-derives a motion strip.
 */
export type DustAtlasCell = Readonly<{ frame: string | number; width: number; height: number }>;
export type DustAtlasCells = Readonly<Record<DustKind, DustAtlasCell>>;

/**
 * The generated-art dust surface: one pooled image per live puff, drawn from an atlas.
 *
 * A pool rather than create-and-destroy, because a run lays thousands of puffs and each would
 * otherwise be a game object allocated and freed inside a frame. Every image is hidden when the
 * frame opens and only the ones this frame drew are shown again, so the pool settles at the
 * busiest frame the run ever had and nothing from a past frame is left on screen.
 */
export function createAtlasDustCanvas(
  scene: Phaser.Scene,
  depth: number,
  textureKey: string,
  cells: DustAtlasCells,
): DustCanvas & { destroy(): void } {
  const pool: Phaser.GameObjects.Image[] = [];
  let live = 0;
  return {
    begin: () => {
      for (const image of pool) image.setVisible(false);
      live = 0;
    },
    puff: (puff) => {
      const cell = cells[puff.kind];
      const rect = dustSpriteRect(puff, cell.width, cell.height);
      let image = pool[live];
      if (image === undefined) {
        image = scene.add.image(rect.x, rect.y, textureKey, cell.frame).setDepth(depth);
        pool.push(image);
      }
      image
        .setTexture(textureKey, cell.frame)
        .setPosition(rect.x, rect.y)
        .setDisplaySize(rect.width, rect.height)
        .setAlpha(puff.alpha)
        .setVisible(true);
      live += 1;
    },
    destroy: () => {
      for (const image of pool.splice(0)) image.destroy();
    },
  };
}

/** The scene's dust surface: one graphics object redrawn per frame at the given depth. */
export function createGraphicsDustCanvas(
  scene: Phaser.Scene,
  depth: number,
): DustCanvas & { destroy(): void } {
  const graphics = scene.add.graphics().setDepth(depth);
  return {
    begin: () => {
      graphics.clear();
    },
    puff: (puff) => {
      // The rim is an underlay: every lobe first in ink a rim wider, then every lobe in paper
      // on top, so the union carries one outline and no lobe's edge crosses another's fill.
      const lobes = dustCloudLobes(puff);
      graphics.fillStyle(DUST_RIM_COLOR, puff.alpha);
      for (const lobe of lobes) {
        graphics.fillEllipse(
          lobe.x,
          lobe.y,
          (lobe.radiusX + DUST_RIM_WIDTH_PX) * 2,
          (lobe.radiusY + DUST_RIM_WIDTH_PX) * 2,
        );
      }
      graphics.fillStyle(DUST_FILL_COLOR, puff.alpha);
      for (const lobe of lobes) {
        graphics.fillEllipse(lobe.x, lobe.y, lobe.radiusX * 2, lobe.radiusY * 2);
      }
    },
    destroy: () => {
      graphics.destroy();
    },
  };
}

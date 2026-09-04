// The runner's Phaser boot: one thin adapter between the browser and the
// sealed systems.
//
// Everything that decides the run — physics, streaming, scoring, the ramp —
// lives in the systems and ticks at a fixed 60Hz from the accumulator, fed by
// whatever frame deltas Phaser reports. This module only loads the manifest's
// assets into textures, builds the world once, registers the systems as data,
// seals them, and mirrors world state onto game objects inside the two
// presentation views. Nothing here mutates gameplay state directly.

import Phaser from "phaser";
import { preparedAssetUrl } from "@/lib/shell/asset-url";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import { applyDeviceZoom, currentDevicePixelScale, deviceGameSize } from "@/lib/device-pixels/device-camera";
import {
  loadFrameStrip,
  loadParallaxLayer,
  loadTerrainAtlas,
  loadTrimmedSprite,
  loadTransparentSprite,
  registerCanvas,
} from "@/lib/sideview/assets";
import { parseScreenFxBlock } from "@/lib/families/screen-fx/manifest";
import { HIDDEN_FX_VIEW } from "@/lib/families/screen-fx/view";
import { installMotionPlayback } from "@/lib/sideview/motion-playback";
import { presentPreparedLayerCanvas } from "@/lib/sideview/prepared-layer-presentation";
import {
  createAudioSystem,
  createWebAudioSink,
  SILENT_MUSIC_SINK,
  type RunnerAudioSink,
  type RunnerMusicSink,
} from "./audio";
import { createAvatarSystem } from "./avatar";
import { createRunnerClockSystem, parseRunnerClockBlock } from "./clock";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { RunnerMotionState, RunnerRuntimeManifest } from "./contract";
import { createDifficultySystem } from "./difficulty";
import {
  createAtlasDustCanvas,
  createDustSystem,
  createGraphicsDustCanvas,
  SILENT_DUST_CANVAS,
  type DustAtlasCells,
  type DustCanvas,
} from "./dust";
import { buildBossView } from "./boss-view";
import { createEncounterSystem } from "./encounter";
import type { RunnerEncounterBinding } from "./world";
import { createFixedStepAccumulator } from "@/lib/kernel/fixed-step";
import { buildHud, createHudSystem, type HudView } from "./hud";
import {
  attachKeyboardIntentSource,
  attachPointerIntentSource,
  createIntentLatch,
  parseRunnerIntentBlock,
  createIntentSystem,
  type RunnerIntentLatch,
} from "./intent";
import { createObstaclesSystem, pickupKey } from "./obstacles";
import {
  buildParallaxStage,
  createParallaxSystem,
  runnerLayerFrameHeight,
  RUNNER_DEPTHS,
  structuralGroundSourceSize,
  type ParallaxStageView,
  type RunnerGroundTextures,
} from "./parallax";
import { createScoreSystem } from "./score";
import { createSessionSystemForRunner, parseRunnerSessionBlock } from "./session";
import { avatarBlinkAlpha, createVitalsSystem, parseRunnerVitalsBlock } from "./vitals";
import {
  collectiblePresentation,
  hazardCueAlpha,
  hazardVisualScale,
  presentationPhase,
} from "./presentation";
import {
  createRunnerSoundtrackPlayback,
  type RunnerSoundtrackPlayback,
} from "./soundtrack";
import {
  streamedHazards,
  streamedPickups,
  surfaceRowAt,
  createSegmentsSystem,
} from "./segments";
import {
  sealSystems,
  type GameSystem,
  type SealOptions,
  type SealedSystems,
} from "@/lib/kernel/systems";
import {
  buildCutInView,
  type CutInMomentBinding,
} from "@/lib/families/screen-fx/cut-in-view";
import { createFxSystem, type FxView } from "@/lib/families/screen-fx/moment-system";
import {
  createCameraSystem,
  createRunnerWorld,
  groundLineY,
  resetRunnerWorld,
  rowToScreenY,
  RUNNER_VIEW_HEIGHT,
  RUNNER_VIEW_WIDTH,
  type RunnerWorld,
} from "./world";

const TRANSPARENCY_POLICY: PreviewTransparencyPolicy = "canonical-alpha";
const GROUND_TEXTURE_KEY = "runner:ground";

/**
 * The full system roster, in registration order. The sealed order does not
 * depend on this order — the declarations pin a unique topology — but keeping
 * the list readable in frame order documents the intent.
 */
/**
 * Every family gate this genre's roster depends on, run once at boot.
 *
 * Each family declares the block it cannot go on without and gates it by name
 * through the per-block table. Calling them together here is not the genre
 * parser doing it for them — the dependency and the refusal belong to the
 * family, and a family dropped from the roster takes its line out of this
 * function with it.
 */
export function gateRunnerFamilyBlocks(blocks: BlockTable): void {
  parseRunnerClockBlock(blocks);
  parseRunnerSessionBlock(blocks);
  parseRunnerIntentBlock(blocks);
  parseRunnerVitalsBlock(blocks);
  parseScreenFxBlock(blocks);
}

export function assembleRunnerSystems(
  latch: RunnerIntentLatch,
  stage: ParallaxStageView,
  hud: HudView,
  audio: RunnerAudioSink,
  music: RunnerMusicSink = SILENT_MUSIC_SINK,
  fx: FxView = HIDDEN_FX_VIEW,
  dust: DustCanvas = SILENT_DUST_CANVAS,
  dustOptions: { readonly reducedMotion?: boolean } = {},
): readonly GameSystem<RunnerWorld>[] {
  return [
    // The clock first: everything that integrates is handed its delta, and
    // everything that stamps a deadline is handed its integral.
    createRunnerClockSystem(),
    createIntentSystem(latch),
    // Always sealed, even with nothing to play: two consumers read its
    // release, and one topology is easier to reason about than two.
    //
    // Pinned behind the avatar rather than behind vitals. The encounter
    // director both consumes `fx-released` and emits `shot-contact`, which
    // vitals consumes, so pinning fx behind vitals would close the loop
    // encounter -> vitals -> fx -> encounter and the sealer would refuse it.
    // Behind the avatar the order is unambiguous and nothing cycles.
    createFxSystem<RunnerWorld>(fx, { after: ["runner/avatar"] }),
    createDifficultySystem(),
    createAvatarSystem(),
    createEncounterSystem(),
    createSegmentsSystem(),
    createObstaclesSystem(),
    createVitalsSystem(),
    // The scorer, then the lifecycle: this frame's collections are scored
    // under the phase they were collected in.
    createScoreSystem(),
    createSessionSystemForRunner(),
    createCameraSystem(),
    createParallaxSystem(stage),
    createHudSystem(hud),
    createAudioSystem(audio, music),
    // Ground dust is drawn from the frame every other system has settled; it
    // pins itself last and never writes a key, so it is free to be omitted
    // from a headless boot with the silent canvas.
    createDustSystem(dust, dustOptions),
  ];
}

/**
 * What every host must pass to seal that roster.
 *
 * A composition is its declarations *and* its boundaries: the queue that is
 * cleared each frame, and the occurrence that ends a run. A host that sealed
 * the roster without `resetOn` would run a game in which death is permanent
 * and the restart press does nothing, so it is not left to each host to
 * remember — the boot, the replay harness and the order tests all seal the
 * same way.
 */
export function runnerSealOptions(
  options: {
    readonly clock?: () => { reset(): void };
    readonly devTrap?: boolean;
  } = {},
): SealOptions<RunnerWorld> {
  return {
    events: (world) => world.events,
    resetOn: ["run-restarted"],
    // The clock is for a session reset only: a restart must not rewind the
    // clock a moment in flight is timed against.
    ...(options.clock ? { clock: options.clock } : {}),
    ...(options.devTrap ? { devTrap: true } : {}),
  };
}

/** The viewer's motion preference; a headless or pre-window boot reads as no preference. */
function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function avatarTextureKey(state: RunnerMotionState): string {
  return `runner:avatar:${state}`;
}

export function bossTextureKey(bossId: string, state: string): string {
  return `runner:boss:${bossId}:${state}`;
}

export function bossAnimationKey(bossId: string, state: string): string {
  return `runner:boss:${bossId}:${state}:play`;
}

export function projectileTextureKey(projectileId: string): string {
  return `runner:projectile:${projectileId}`;
}

function avatarAnimationKey(state: RunnerMotionState): string {
  return `runner:anim:${state}`;
}

function structuralGroundTextureKey(segmentId: string): string {
  return `runner:ground:segment:${segmentId}`;
}

interface RasterSize {
  readonly width: number;
  readonly height: number;
}

interface HazardView {
  readonly sprite: Phaser.GameObjects.Image;
  readonly shadow: Phaser.GameObjects.Ellipse;
  readonly cue: Phaser.GameObjects.Ellipse;
}

interface PickupView {
  readonly sprite: Phaser.GameObjects.Image;
  readonly halo: Phaser.GameObjects.Ellipse;
  readonly baseY: number;
  readonly baseScale: number;
  readonly phase: number;
}

class RunnerScene extends Phaser.Scene {
  private world?: RunnerWorld;
  private sealed?: SealedSystems<RunnerWorld>;
  private readonly accumulator = createFixedStepAccumulator();
  private readonly latch = createIntentLatch();
  private readonly disposers: (() => void)[] = [];
  private soundtrack?: RunnerSoundtrackPlayback;
  private audioSink?: RunnerAudioSink;

  constructor(
    private readonly tag: string,
    private readonly manifest: RunnerRuntimeManifest,
  ) {
    super("sideview-runner");
  }

  private url(file: string): string {
    return preparedAssetUrl(this.tag, file);
  }

  create(): void {
    // The canvas is device-pixel sized; zoom the camera back to the design space it is written in.
    applyDeviceZoom(this.cameras.main, { width: RUNNER_VIEW_WIDTH, height: RUNNER_VIEW_HEIGHT });
    this.add
      .text(RUNNER_VIEW_WIDTH / 2, RUNNER_VIEW_HEIGHT / 2, "loading track…", {
        fontFamily: "system-ui, sans-serif",
        fontSize: "22px",
        color: "#98a0ab",
      })
      .setOrigin(0.5)
      .setName("loading-label");
    void this.buildStage().catch((error: unknown) => {
      this.children.getByName("loading-label")?.destroy();
      this.add
        .text(
          RUNNER_VIEW_WIDTH / 2,
          RUNNER_VIEW_HEIGHT / 2,
          `Unable to load runner track\n${error instanceof Error ? error.message : String(error)}`,
          {
            align: "center",
            color: "#ffffff",
            fontFamily: "system-ui, sans-serif",
            fontSize: "20px",
            backgroundColor: "#5b1720dd",
            padding: { x: 22, y: 16 },
            wordWrap: { width: 900 },
          },
        )
        .setOrigin(0.5)
        .setDepth(1200);
    });
  }

  private async buildStage(): Promise<void> {
    const manifest = this.manifest;
    let groundTextures: RunnerGroundTextures;
    if (manifest.ground.mode === "terrain-atlas-3x3-minimal-v1") {
      await loadTerrainAtlas(
        this.url(manifest.ground.atlas),
        GROUND_TEXTURE_KEY,
        this.textures,
        TRANSPARENCY_POLICY,
      );
      groundTextures = Object.freeze({
        mode: "terrain-atlas-3x3-minimal-v1",
        key: GROUND_TEXTURE_KEY,
      });
    } else {
      const keys = new Map<string, string>();
      for (const chunk of manifest.ground.chunks) {
        const key = structuralGroundTextureKey(chunk.segmentId);
        const canvas = await loadTransparentSprite(
          this.url(chunk.image),
          key,
          this.textures,
          TRANSPARENCY_POLICY,
        );
        const expected = structuralGroundSourceSize(
          chunk.columns,
          chunk.rows,
          manifest.ground.cellPx,
        );
        if (canvas.width !== expected.width || canvas.height !== expected.height) {
          throw new Error(
            `structural ground ${chunk.segmentId} must be exactly ${expected.width}x${expected.height}`,
          );
        }
        keys.set(chunk.segmentId, key);
      }
      groundTextures = Object.freeze({
        mode: "runner-structural-ground-v1",
        keys,
      });
    }
    for (const layer of manifest.layers) {
      const key = `runner:layer:${layer.layerId}`;
      // Loop-admitted layers repeat seamlessly, so no edge fade: fading would
      // paint a visible seam at every repeat boundary.
      const loaded = await loadParallaxLayer(
        this.url(layer.image),
        key,
        layer.alphaMode === "opaque",
        0,
        this.textures,
        TRANSPARENCY_POLICY,
      );
      presentPreparedLayerCanvas(
        loaded.canvas,
        layer.presentation,
        runnerLayerFrameHeight(layer, manifest.layers) / RUNNER_VIEW_HEIGHT,
      );
      registerCanvas(this.textures, key, loaded.canvas);
    }
    for (const motion of manifest.avatar.motions) {
      await loadFrameStrip(
        this.url(motion.atlas),
        avatarTextureKey(motion.state),
        motion.columns,
        this.textures,
        TRANSPARENCY_POLICY,
      );
      installMotionPlayback(this, avatarAnimationKey(motion.state), avatarTextureKey(motion.state), {
        mode: motion.playbackMode,
        canonical_frame_indices: motion.canonicalFrameIndices,
        frames_per_second: motion.framesPerSecond,
      });
    }
    const propRasterSizes = new Map<string, RasterSize>();
    for (const prop of manifest.props) {
      const loaded = await loadTrimmedSprite(
        this.url(prop.image),
        `runner:prop:${prop.id}`,
        this.textures,
        TRANSPARENCY_POLICY,
      );
      propRasterSizes.set(prop.id, {
        width: loaded.canvas.width,
        height: loaded.canvas.height,
      });
    }
    const itemRasterSizes = new Map<string, RasterSize>();
    for (const item of manifest.items) {
      const loaded = await loadTrimmedSprite(
        this.url(item.image),
        `runner:item:${item.id}`,
        this.textures,
        TRANSPARENCY_POLICY,
      );
      itemRasterSizes.set(item.id, {
        width: loaded.canvas.width,
        height: loaded.canvas.height,
      });
    }

    const fxView = await this.buildFxView(manifest);
    const encounter = await this.buildEncounterBinding(manifest);
    const world = createRunnerWorld(manifest, (Math.random() * 0x100000000) >>> 0, {
      intro: fxView !== null,
      encounter,
    });
    const groundLine = groundLineY(world.config);
    const bands = buildParallaxStage(
      this,
      manifest.layers.map((layer) => ({ layer, key: `runner:layer:${layer.layerId}` })),
      groundTextures,
      world.config.tilePx,
      groundLine,
    );
    const encounterBoss =
      encounter === null
        ? null
        : (manifest.bosses.find((entry) => entry.bossId === encounter.encounter.bossId) ?? null);
    const actors = this.buildActorsView(world, propRasterSizes, itemRasterSizes);
    const bossView =
      encounter === null || encounterBoss === null
        ? null
        : buildBossView(this, world, {
            bossTextureKey,
            bossAnimationKey,
            projectileTextureKey,
            boss: encounterBoss,
            projectiles: manifest.projectiles,
          });
    const stage: ParallaxStageView = {
      sync: (current) => {
        bands.sync(current);
        actors.sync(current);
        bossView?.sync(current);
      },
    };
    const hud = buildHud(
      this,
      world.config.tilePx,
      world.config.maxVitalPoints,
      encounterBoss === null || encounter === null
        ? null
        : {
            displayName: encounterBoss.displayName,
            hitsToDefeat: encounter.encounter.hitsToDefeat,
          },
    );

    this.disposers.push(attachKeyboardIntentSource(this.latch, window));
    this.disposers.push(attachPointerIntentSource(this.latch, this.game.canvas));
    // One gesture unlocks both: the soundtrack, and the announcement the
    // audio sink is holding for a context the browser would not start cold.
    const unlock = () => {
      this.soundtrack?.unlock();
      this.audioSink?.unlock?.();
    };
    window.addEventListener("keydown", unlock);
    this.game.canvas.addEventListener("pointerdown", unlock);
    this.disposers.push(() => {
      window.removeEventListener("keydown", unlock);
      this.game.canvas.removeEventListener("pointerdown", unlock);
    });
    if (manifest.soundtrack) {
      this.soundtrack = createRunnerSoundtrackPlayback(
        manifest.soundtrack,
        (path) => this.url(path),
        { music: manifest.audio.music },
      );
      this.disposers.push(() => {
        this.soundtrack?.dispose();
        this.soundtrack = undefined;
      });
    }

    // A published atlas replaces the procedural draw outright; a package without one
    // keeps the ellipses, so dust never depends on a provider having been paid.
    const dustCanvas =
      (await this.buildDustCanvas(manifest)) ?? createGraphicsDustCanvas(this, RUNNER_DEPTHS.dust);
    this.disposers.push(() => dustCanvas.destroy());
    this.audioSink = createWebAudioSink(manifest.audio, (path) => this.url(path));
    gateRunnerFamilyBlocks(manifest.blocks);
    this.sealed = sealSystems(
      assembleRunnerSystems(
        this.latch,
        stage,
        hud,
        this.audioSink,
        this.soundtrack ?? SILENT_MUSIC_SINK,
        fxView ?? HIDDEN_FX_VIEW,
        dustCanvas,
        { reducedMotion: prefersReducedMotion() },
      ),
      runnerSealOptions({ clock: () => this.accumulator }),
    );
    this.world = world;
    this.children.getByName("loading-label")?.destroy();
  }

  /** Avatar, hazard, pickup, and contact-shadow drawing, mirrored from world state. */
  private buildActorsView(
    world: RunnerWorld,
    propRasterSizes: ReadonlyMap<string, RasterSize>,
    itemRasterSizes: ReadonlyMap<string, RasterSize>,
  ): ParallaxStageView {
    const manifest = this.manifest;
    const config = world.config;
    const spriteScale = (calibrationPxPerUnit: number): number =>
      (config.playerHeightTiles * config.tilePx) / calibrationPxPerUnit;

    const avatarBaseScale = spriteScale(manifest.avatar.calibration.sourcePxPerUnit);
    const motionByState = new Map(manifest.avatar.motions.map((entry) => [entry.state, entry]));
    const avatar = this.add
      .sprite(config.avatarScreenX, rowToScreenY(world.avatar.y, config), avatarTextureKey("run"), 0)
      .setDepth(RUNNER_DEPTHS.avatar);
    let wornState: RunnerMotionState | null = null;
    let wornImpulses = 0;

    const shadow = this.add.graphics().setDepth(RUNNER_DEPTHS.shadow);
    const shadows = manifest.presentation.contactShadows;

    const hazardContainer = this.add.container(0, 0).setDepth(RUNNER_DEPTHS.hazard);
    const pickupContainer = this.add.container(0, 0).setDepth(RUNNER_DEPTHS.pickup);
    const hazardViews = new Map<string, HazardView>();
    const pickupViews = new Map<string, PickupView>();
    const collisionWidthPixels =
      config.tilePx * (1 - config.arithmetic.hazardColumnInset * 2);
    const propScale = new Map(
      manifest.props.map((prop) => {
        const calibrated = spriteScale(prop.calibration.sourcePxPerUnit);
        const raster = propRasterSizes.get(prop.id);
        return [
          prop.id,
          hazardVisualScale(
            calibrated,
            raster?.width ?? collisionWidthPixels / calibrated,
            collisionWidthPixels,
          ),
        ] as const;
      }),
    );
    const itemScale = new Map(
      manifest.items.map((item) => {
        const calibrated = spriteScale(item.calibration.sourcePxPerUnit);
        const raster = itemRasterSizes.get(item.id);
        const readableCell = config.tilePx * 0.72;
        const fitted = raster
          ? Math.min(calibrated, readableCell / raster.width, readableCell / raster.height)
          : calibrated;
        return [item.id, fitted] as const;
      }),
    );

    let wornSeed = world.run.seed;
    return {
      sync: (current) => {
        // A restart replays the same world columns with different chunks;
        // sprites cached by (worldColumn, id) would alias stale geometry
        // across it, so the whole mirror resets with the seed.
        if (current.run.seed !== wornSeed) {
          wornSeed = current.run.seed;
          for (const view of hazardViews.values()) {
            view.sprite.destroy();
            view.shadow.destroy();
            view.cue.destroy();
          }
          hazardViews.clear();
          for (const view of pickupViews.values()) {
            view.sprite.destroy();
            view.halo.destroy();
          }
          pickupViews.clear();
        }
        // Avatar: state decides texture, animation, scale, and anchor. The
        // animation replays on the jump IMPULSE, not only the state change:
        // an air jump inside the same `jump` state must restart the strip or
        // the second hop reads as having no animation at all.
        const state = current.avatar.motion;
        const impulses = current.avatar.jumpImpulses;
        if (state !== wornState || impulses !== wornImpulses) {
          wornState = state;
          wornImpulses = impulses;
          const motion = motionByState.get(state);
          if (motion) {
            avatar.setScale(avatarBaseScale * motion.rebaseMultiplier);
            avatar.setOrigin(0.5, motion.anchor === "bottom" ? 1 : 0);
            avatar.play(avatarAnimationKey(state));
          }
        }
        avatar.setY(rowToScreenY(current.avatar.y, config));
        // The contracted nonvisual hurt representation: while the gauge is
        // refusing input the avatar blinks, and the phase is arithmetic on the
        // frame's clock rather than a tween, so a fixed-step replay of this
        // run draws the same alpha on the same frame. Re-applied every frame
        // because it is a function of time, not an event.
        avatar.setAlpha(avatarBlinkAlpha(current));

        // Contact shadow on the support under the avatar, thinning with air.
        shadow.clear();
        if (shadows.enabled && current.run.phase === "running") {
          const support = surfaceRowAt(
            current.segments,
            Math.floor(current.avatar.distanceColumns),
          );
          if (support !== null) {
            const airRows = Math.max(0, support - current.avatar.y);
            const spread = Math.max(0.45, 1 - airRows / 6);
            shadow.fillStyle(0x000000, shadows.opacity * spread);
            shadow.fillEllipse(
              config.avatarScreenX,
              rowToScreenY(support, config),
              config.tilePx * 0.95 * spread,
              config.tilePx * 0.28 * spread,
            );
          }
        }

        // Hazards and pickups: mirror the streamed window, keyed by instance.
        const wantedHazards = new Set<string>();
        for (const hazard of streamedHazards(current.segments)) {
          const key = `${hazard.worldColumn}:${hazard.propId}`;
          wantedHazards.add(key);
          let view = hazardViews.get(key);
          if (!view) {
            const support = surfaceRowAt(current.segments, hazard.worldColumn);
            if (support === null) continue;
            // An overhead hazard hangs with its underside at the clearance
            // line; a surface one stands on its ground.
            const baseRow =
              hazard.anchor === "overhead"
                ? support - (hazard.clearanceRows ?? 0)
                : support;
            const centerX = (hazard.worldColumn + 0.5) * config.tilePx;
            const baseY = rowToScreenY(baseRow, config);
            const heightRows =
              (config.propHeightUnits.get(hazard.propId) ?? 1) * config.playerHeightTiles;
            const visualScale = propScale.get(hazard.propId) ?? { scaleX: 1, scaleY: 1 };
            // The quiet grounding shadow and approach rim make the visual
            // footprint agree with the already-published collision box. They
            // never alter that box or the authored placement.
            const hazardShadow = this.add
              .ellipse(
                centerX,
                baseY,
                collisionWidthPixels,
                config.tilePx * 0.16,
                0x000000,
                hazard.anchor === "surface" ? 0.24 : 0,
              )
              .setOrigin(0.5, 0.5);
            const cue = this.add
              .ellipse(
                centerX,
                baseY - (heightRows * config.tilePx) / 2,
                collisionWidthPixels * 1.08,
                heightRows * config.tilePx * 1.04,
                0xffd166,
                0,
              )
              .setStrokeStyle(2, 0xffd166, 1)
              .setAlpha(0);
            const sprite = this.add
              .image(
                centerX,
                baseY,
                `runner:prop:${hazard.propId}`,
              )
              .setOrigin(0.5, 1)
              .setScale(visualScale.scaleX, visualScale.scaleY);
            hazardContainer.add([hazardShadow, cue, sprite]);
            view = { sprite, shadow: hazardShadow, cue };
            hazardViews.set(key, view);
          }
          if (!view) continue;
          view.cue.setAlpha(
            hazardCueAlpha(
              hazard.worldColumn - current.avatar.distanceColumns,
              this.time.now,
            ),
          );
        }
        for (const [key, view] of hazardViews) {
          if (!wantedHazards.has(key)) {
            view.sprite.destroy();
            view.shadow.destroy();
            view.cue.destroy();
            hazardViews.delete(key);
          }
        }
        const wantedPickups = new Set<string>();
        for (const pickup of streamedPickups(current.segments)) {
          const key = pickupKey(pickup);
          wantedPickups.add(key);
          let view = pickupViews.get(key);
          if (!view) {
            const baseY =
              (pickup.row + 0.5) * config.tilePx + rowToScreenY(0, config);
            const baseScale = itemScale.get(pickup.itemId) ?? 1;
            const centerX = (pickup.worldColumn + 0.5) * config.tilePx;
            const halo = this.add
              .ellipse(
                centerX,
                baseY,
                config.tilePx * 0.72,
                config.tilePx * 0.72,
                0xffe69a,
                0.06,
              )
              .setStrokeStyle(2, 0xfff0ad, 0.8);
            const sprite = this.add
              .image(
                centerX,
                baseY,
                `runner:item:${pickup.itemId}`,
              )
              .setOrigin(0.5, 0.5);
            pickupContainer.add([halo, sprite]);
            view = {
              sprite,
              halo,
              baseY,
              baseScale,
              phase: presentationPhase(key),
            };
            pickupViews.set(key, view);
          }
          if (!view) continue;
          const motion = collectiblePresentation(this.time.now, view.phase);
          view.sprite
            .setY(view.baseY + motion.bobRows * config.tilePx)
            .setScale(
              view.baseScale * motion.scaleXMultiplier,
              view.baseScale * motion.scaleYMultiplier,
            );
          view.halo
            .setY(view.baseY + motion.bobRows * config.tilePx)
            .setScale(motion.haloScale)
            .setAlpha(motion.haloAlpha);
          const visible = !current.obstacles.collected.has(key);
          view.sprite.setVisible(visible);
          view.halo.setVisible(visible);
        }
        for (const [key, view] of pickupViews) {
          if (!wantedPickups.has(key)) {
            view.sprite.destroy();
            view.halo.destroy();
            pickupViews.delete(key);
          }
        }

        hazardContainer.x = -current.camera.scrollX;
        pickupContainer.x = -current.camera.scrollX;
      },
    };
  }

  /**
   * The stage-start cut-in, when the package binds one: both plates loaded
   * under the canonical alpha policy, the view built over the HUD. A package
   * with no binding gets null, and the world is born running.
   */
  /**
   * Resolve the published encounter into what the world needs, loading its art.
   *
   * The manifest publishes the fight as names and numbers; the world wants the
   * arithmetic, the arena chunk and the moment. Resolving once at boot keeps
   * every system downstream testable from a hand-built config with no manifest
   * at all.
   */
  private async buildEncounterBinding(
    manifest: RunnerRuntimeManifest,
  ): Promise<RunnerEncounterBinding | null> {
    const published = manifest.gameplay.encounter;
    if (published === null) return null;
    const arena = manifest.segments.chunks.find(
      (chunk) => chunk.segmentId === published.arenaSegmentId,
    );
    const boss = manifest.bosses.find((entry) => entry.bossId === published.bossId);
    // Both resolve by contract; the parser refused the document otherwise.
    if (arena === undefined || boss === undefined) return null;
    // A motion atlas is a strip, not a picture: loaded as one image every cell
    // is drawn at once, which is four bosses in a row. Split it the way the
    // avatar's strips are split, and install the same playback.
    //
    // The hover is the baseline every other strip was rebased against, so its
    // cell is the one the hit box is measured from.
    let hoverCellAspect = 0;
    for (const motion of boss.motions) {
      const key = bossTextureKey(boss.bossId, motion.state);
      const loaded = await loadFrameStrip(
        this.url(motion.atlas),
        key,
        motion.columns,
        this.textures,
        TRANSPARENCY_POLICY,
      );
      installMotionPlayback(this, bossAnimationKey(boss.bossId, motion.state), key, {
        mode: motion.playbackMode,
        canonical_frame_indices: motion.canonicalFrameIndices,
        frames_per_second: motion.framesPerSecond,
      });
      if (motion.state === "hover") {
        const cell = loaded.cells[0];
        if (cell !== undefined && cell.h > 1) hoverCellAspect = cell.w / cell.h;
      }
    }
    for (const shot of manifest.projectiles) {
      await loadTrimmedSprite(
        this.url(shot.image),
        projectileTextureKey(shot.projectileId),
        this.textures,
        TRANSPARENCY_POLICY,
      );
    }
    return {
      encounter: {
        profile: published.profile,
        locomotion: published.locomotion,
        intervalColumns: published.intervalColumns,
        arenaSegmentId: published.arenaSegmentId,
        bossId: published.bossId,
        bossProjectileId: published.bossProjectileId,
        playerProjectileId: published.playerProjectileId,
        thrust: {
          maxClimbRowsPerSecond: published.maxClimbRowsPerSecond,
          maxFallRowsPerSecond: published.maxFallRowsPerSecond,
          climbAccelerationRowsPerSecondSquared:
            published.climbAccelerationRowsPerSecondSquared,
        },
        firingDistanceColumns: published.firingDistanceColumns,
        projectileSpeedColumnsPerSecond: published.projectileSpeedColumnsPerSecond,
        projectileHeightRows: published.projectileHeightRows,
        salvoShots: published.salvoShots,
        salvoPeriodSeconds: published.salvoPeriodSeconds,
        salvoBudget: published.salvoBudget,
        laneMarginRows: published.laneMarginRows,
        hitsToDefeat: published.hitsToDefeat,
        playerFirePeriodSeconds: published.playerFirePeriodSeconds,
        playerShotSpeedColumnsPerSecond: published.playerShotSpeedColumnsPerSecond,
        bossHeightRows: boss.calibration.heightUnits * manifest.scale.playerHeightTiles,
        bossHalfWidthColumns:
          (boss.calibration.heightUnits * manifest.scale.playerHeightTiles * hoverCellAspect) / 2,
      },
      arenaChunk: arena,
      moment:
        manifest.fx?.moments.find((entry) => entry.moment === "encounter_start") ?? null,
    };
  }

  /**
   * The published dust atlas, as a texture with one registered sub-frame per kind, or
   * null when the package authored none. Registering the cells the producer measured is
   * the whole of the consumer's job here: it never looks at the pixels to find them.
   */
  private async buildDustCanvas(
    manifest: RunnerRuntimeManifest,
  ): Promise<(DustCanvas & { destroy(): void }) | null> {
    const dust = manifest.fx?.sprite?.dust;
    if (!dust) return null;
    const textureKey = "runner:fx:sprite:dust";
    await loadTransparentSprite(this.url(dust.asset), textureKey, this.textures, TRANSPARENCY_POLICY);
    const texture = this.textures.get(textureKey);
    const cells = Object.fromEntries(
      dust.cells.map((cell) => {
        texture.add(cell.kind, 0, cell.x, cell.y, cell.width, cell.height);
        return [cell.kind, { frame: cell.kind, width: cell.width, height: cell.height }];
      }),
    ) as DustAtlasCells;
    return createAtlasDustCanvas(this, RUNNER_DEPTHS.dust, textureKey, cells);
  }

  private async buildFxView(manifest: RunnerRuntimeManifest): Promise<FxView | null> {
    const cutIn = manifest.fx?.cutIn;
    const moments = manifest.fx?.moments ?? [];
    if (!cutIn || moments.length === 0) return null;
    const frameKey = "runner:fx:cut_in:frame";
    await loadTransparentSprite(
      this.url(cutIn.frame.asset),
      frameKey,
      this.textures,
      TRANSPARENCY_POLICY,
    );
    // Every published moment is bound up front, so the director can begin one
    // mid-run without loading anything: a texture fetch during a fight would
    // stall the frame the boss arrives on.
    const bindings = new Map<string, CutInMomentBinding>();
    for (const moment of moments) {
      const portrait = cutIn.portraits.find((entry) => entry.portraitId === moment.portraitId);
      if (!portrait) continue;
      const portraitKey = `runner:fx:cut_in:portrait:${portrait.portraitId}`;
      await loadTransparentSprite(
        this.url(portrait.asset),
        portraitKey,
        this.textures,
        TRANSPARENCY_POLICY,
      );
      bindings.set(moment.moment, {
        portrait,
        portraitTextureKey: portraitKey,
        title: moment.title,
        subtitle: moment.subtitle,
      });
    }
    if (bindings.size === 0) return null;
    const view = buildCutInView(this, {
      viewWidth: RUNNER_VIEW_WIDTH,
      viewHeight: RUNNER_VIEW_HEIGHT,
      depth: RUNNER_DEPTHS.fx,
      frame: cutIn.frame,
      frameTextureKey: frameKey,
      bindings,
    });
    view.hide();
    this.disposers.push(() => view.destroy());
    return view;
  }

  override update(_time: number, delta: number): void {
    const world = this.world;
    const sealed = this.sealed;
    if (!world || !sealed) return;
    for (const step of this.accumulator.advance(delta)) {
      sealed.tick(world, step);
    }
  }

  sealedOrder(): readonly string[] {
    return this.sealed?.order ?? [];
  }

  restartRun(seed?: number): void {
    if (!this.world) return;
    resetRunnerWorld(this.world, seed ?? this.world.run.seed);
  }

  dispose(): void {
    for (const disposer of this.disposers.splice(0)) disposer();
  }
}

export interface RunnerGameHandle {
  destroy(removeCanvas: boolean): void;
  /** Reset the run in place: same seed replays the same track, a new one varies it. */
  restart(seed?: number): void;
  /** The sealed system order, for inspection; empty until assets finish loading. */
  sealedOrder(): readonly string[];
}

/**
 * Boot one runner track into `parent`, scaled to fit whatever that element
 * is. The design space is fixed at 1280×720; the engine letterboxes. The canvas itself is
 * sized in device pixels and the scene's camera zooms it back, so nothing in the scene is
 * measured in CSS pixels and nothing is drawn at less than screen resolution.
 */
export function bootRunnerGame(
  parent: HTMLElement,
  tag: string,
  manifest: RunnerRuntimeManifest,
): RunnerGameHandle {
  const scene = new RunnerScene(tag, manifest);
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    ...deviceGameSize(
      { width: RUNNER_VIEW_WIDTH, height: RUNNER_VIEW_HEIGHT },
      currentDevicePixelScale(),
    ),
    parent,
    backgroundColor: "#000000",
    scene: [scene],
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
  });
  return {
    destroy: (removeCanvas: boolean) => {
      scene.dispose();
      game.destroy(removeCanvas);
    },
    restart: (seed?: number) => scene.restartRun(seed),
    sealedOrder: () => scene.sealedOrder(),
  };
}

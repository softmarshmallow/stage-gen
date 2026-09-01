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
import {
  loadFrameStrip,
  loadParallaxLayer,
  loadTerrainAtlas,
  loadTrimmedSprite,
  registerCanvas,
} from "@/lib/sideview/assets";
import { installMotionPlayback } from "@/lib/sideview/motion-playback";
import { presentPreparedLayerCanvas } from "@/lib/sideview/prepared-layer-presentation";
import { createAvatarSystem } from "./avatar";
import type { RunnerMotionState, RunnerRuntimeManifest } from "./contract";
import { createDifficultySystem } from "./difficulty";
import { createFixedStepAccumulator } from "./fixed-step";
import { buildHud, createHudSystem, type HudView } from "./hud";
import {
  attachKeyboardIntentSource,
  attachPointerIntentSource,
  createIntentLatch,
  createIntentSystem,
  type RunnerIntentLatch,
} from "./intent";
import { createObstaclesSystem, pickupKey } from "./obstacles";
import {
  buildParallaxStage,
  createParallaxSystem,
  RUNNER_DEPTHS,
  type ParallaxStageView,
} from "./parallax";
import { createRunLoopSystem } from "./run-loop";
import {
  streamedHazards,
  streamedPickups,
  surfaceRowAt,
  createSegmentsSystem,
} from "./segments";
import { sealSystems, type GameSystem, type SealedSystems } from "./systems";
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
const SOUNDTRACK_VOLUME = 0.34;

/**
 * The full system roster, in registration order. The sealed order does not
 * depend on this order — the declarations pin a unique topology — but keeping
 * the list readable in frame order documents the intent.
 */
export function assembleRunnerSystems(
  latch: RunnerIntentLatch,
  stage: ParallaxStageView,
  hud: HudView,
): readonly GameSystem<RunnerWorld>[] {
  return [
    createIntentSystem(latch),
    createDifficultySystem(),
    createAvatarSystem(),
    createSegmentsSystem(),
    createObstaclesSystem(),
    createRunLoopSystem(),
    createCameraSystem(),
    createParallaxSystem(stage),
    createHudSystem(hud),
  ];
}

function avatarTextureKey(state: RunnerMotionState): string {
  return `runner:avatar:${state}`;
}

function avatarAnimationKey(state: RunnerMotionState): string {
  return `runner:anim:${state}`;
}

class RunnerScene extends Phaser.Scene {
  private world?: RunnerWorld;
  private sealed?: SealedSystems<RunnerWorld>;
  private readonly accumulator = createFixedStepAccumulator();
  private readonly latch = createIntentLatch();
  private readonly disposers: (() => void)[] = [];
  private audio?: HTMLAudioElement;
  private audioUnlocked = false;

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
    await loadTerrainAtlas(
      this.url(manifest.ground.atlas),
      GROUND_TEXTURE_KEY,
      this.textures,
      TRANSPARENCY_POLICY,
    );
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
        layer.height / RUNNER_VIEW_HEIGHT,
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
    for (const prop of manifest.props) {
      await loadTrimmedSprite(
        this.url(prop.image),
        `runner:prop:${prop.id}`,
        this.textures,
        TRANSPARENCY_POLICY,
      );
    }
    for (const item of manifest.items) {
      await loadTrimmedSprite(
        this.url(item.image),
        `runner:item:${item.id}`,
        this.textures,
        TRANSPARENCY_POLICY,
      );
    }

    const world = createRunnerWorld(manifest, (Math.random() * 0x100000000) >>> 0);
    const groundLine = groundLineY(world.config);
    const bands = buildParallaxStage(
      this,
      manifest.layers.map((layer) => ({ layer, key: `runner:layer:${layer.layerId}` })),
      GROUND_TEXTURE_KEY,
      world.config.tilePx,
      groundLine,
    );
    const actors = this.buildActorsView(world);
    const stage: ParallaxStageView = {
      sync: (current) => {
        bands.sync(current);
        actors.sync(current);
      },
    };
    const hud = buildHud(this, world.config.tilePx);

    this.disposers.push(attachKeyboardIntentSource(this.latch, window));
    this.disposers.push(attachPointerIntentSource(this.latch, this.game.canvas));
    const unlock = () => this.unlockAudio();
    window.addEventListener("keydown", unlock);
    this.game.canvas.addEventListener("pointerdown", unlock);
    this.disposers.push(() => {
      window.removeEventListener("keydown", unlock);
      this.game.canvas.removeEventListener("pointerdown", unlock);
    });
    this.startSoundtrack();

    this.sealed = sealSystems(assembleRunnerSystems(this.latch, stage, hud));
    this.world = world;
    this.children.getByName("loading-label")?.destroy();
  }

  /** Avatar, hazard, pickup, and contact-shadow drawing, mirrored from world state. */
  private buildActorsView(world: RunnerWorld): ParallaxStageView {
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

    const shadow = this.add.graphics().setDepth(RUNNER_DEPTHS.shadow);
    const shadows = manifest.presentation.contactShadows;

    const hazardContainer = this.add.container(0, 0).setDepth(RUNNER_DEPTHS.hazard);
    const pickupContainer = this.add.container(0, 0).setDepth(RUNNER_DEPTHS.pickup);
    const hazardSprites = new Map<string, Phaser.GameObjects.Image>();
    const pickupSprites = new Map<string, Phaser.GameObjects.Image>();
    const propScale = new Map(
      manifest.props.map((prop) => [prop.id, spriteScale(prop.calibration.sourcePxPerUnit)]),
    );
    const itemScale = new Map(
      manifest.items.map((item) => [item.id, spriteScale(item.calibration.sourcePxPerUnit)]),
    );

    return {
      sync: (current) => {
        // Avatar: state decides texture, animation, scale, and anchor.
        const state = current.avatar.motion;
        if (state !== wornState) {
          wornState = state;
          const motion = motionByState.get(state);
          if (motion) {
            avatar.setScale(avatarBaseScale * motion.rebaseMultiplier);
            avatar.setOrigin(0.5, motion.anchor === "bottom" ? 1 : 0);
            avatar.play(avatarAnimationKey(state), true);
          }
        }
        avatar.setY(rowToScreenY(current.avatar.y, config));

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
          if (!hazardSprites.has(key)) {
            const support = surfaceRowAt(current.segments, hazard.worldColumn);
            if (support === null) continue;
            const sprite = this.add
              .image(
                (hazard.worldColumn + 0.5) * config.tilePx,
                rowToScreenY(support, config),
                `runner:prop:${hazard.propId}`,
              )
              .setOrigin(0.5, 1)
              .setScale(propScale.get(hazard.propId) ?? 1);
            hazardContainer.add(sprite);
            hazardSprites.set(key, sprite);
          }
        }
        for (const [key, sprite] of hazardSprites) {
          if (!wantedHazards.has(key)) {
            sprite.destroy();
            hazardSprites.delete(key);
          }
        }
        const wantedPickups = new Set<string>();
        for (const pickup of streamedPickups(current.segments)) {
          const key = pickupKey(pickup);
          wantedPickups.add(key);
          let sprite = pickupSprites.get(key);
          if (!sprite) {
            sprite = this.add
              .image(
                (pickup.worldColumn + 0.5) * config.tilePx,
                (pickup.row + 0.5) * config.tilePx + rowToScreenY(0, config),
                `runner:item:${pickup.itemId}`,
              )
              .setOrigin(0.5, 0.5)
              .setScale(itemScale.get(pickup.itemId) ?? 1);
            pickupContainer.add(sprite);
            pickupSprites.set(key, sprite);
          }
          sprite.setVisible(!current.obstacles.collected.has(key));
        }
        for (const [key, sprite] of pickupSprites) {
          if (!wantedPickups.has(key)) {
            sprite.destroy();
            pickupSprites.delete(key);
          }
        }

        hazardContainer.x = -current.camera.scrollX;
        pickupContainer.x = -current.camera.scrollX;
      },
    };
  }

  private unlockAudio(): void {
    if (this.audioUnlocked) return;
    this.audioUnlocked = true;
    void this.audio?.play().catch(() => undefined);
  }

  /** Shuffle through the declared tracks; playback starts on the first gesture. */
  private startSoundtrack(): void {
    const soundtrack = this.manifest.soundtrack;
    if (!soundtrack) return;
    const queue = [...soundtrack.tracks].sort(() => Math.random() - 0.5);
    let index = 0;
    const playNext = () => {
      const track = queue[index % queue.length];
      index += 1;
      const audio = new Audio(this.url(track.audio));
      audio.volume = SOUNDTRACK_VOLUME;
      audio.addEventListener("ended", playNext);
      this.audio = audio;
      if (this.audioUnlocked) void audio.play().catch(() => undefined);
    };
    playNext();
    this.disposers.push(() => {
      this.audio?.pause();
      this.audio = undefined;
    });
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
 * is. The design space is fixed at 1280×720; the engine letterboxes.
 */
export function bootRunnerGame(
  parent: HTMLElement,
  tag: string,
  manifest: RunnerRuntimeManifest,
): RunnerGameHandle {
  const scene = new RunnerScene(tag, manifest);
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    width: RUNNER_VIEW_WIDTH,
    height: RUNNER_VIEW_HEIGHT,
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

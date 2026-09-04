// One scene base: the loading/failure/ready state machine, the device zoom, and
// the publish seam every host scene needs and each of the four wrote by hand.
//
// The audit's list, in order:
//
//   - "three loading implementations and a fourth in React" — the runner and the
//     platformer each open with a loading label, await an async build and catch
//     into a failure card; the room and the dialogue scene use Phaser's
//     declarative `preload` and have no notion of either. The shape is one state
//     machine here (`loading -> ready | failed`), with one label and one card, and
//     the two strategies stay what they are: a scene that only needs images
//     declares them in `preload`, a scene that decodes terrain and sheets awaits
//     `hostLoad`. What is shared is the *state*, which is what a host and a view
//     ask about.
//   - "the failure card copied twice and absent twice" — one card, and every
//     scene has it. A room published without an interface sheet used to degrade
//     silently; a room whose backdrop cannot be decoded now says so.
//   - "device-pixel zoom as the first act of every scene (already true)" — kept
//     true, and done once, by the base, before the subclass draws anything.
//   - "three dispose orders" — `hostDispose` runs the scene's own teardown before
//     `game.destroy`, from the one boot.
//
// The publish seam is the other half of `GameHandle.subscribe`: a scene calls
// `publish(world, frame)` at the end of each frame and the host's listeners hear
// it there. It is deliberately a push and not a getter — the preview console read
// its handle on a 200 ms interval precisely because there was nothing to hear.

// A factory over the engine's own `Scene` rather than a class extending it, and
// that is not a style choice. A base class here would bind ONE `Phaser.Scene` —
// the first one this module saw — and the headless replay harnesses each install
// their own stand-in for the engine per genre. A shared base would hand the
// platformer's golden whichever stub happened to load first. Taking the class as
// an argument means every genre's scene is built on the engine binding its own
// module has, which is the one its harness replaced.

import type Phaser from "phaser";

import { applyDeviceZoom } from "@/lib/device-pixels/device-camera";
import type { GameEvent } from "@/lib/kernel/events";
import type { ResetScope } from "@/lib/kernel/systems";
import type { HostListener, HostMode, HostSceneContract, HostSize } from "./host";

export type HostLoadState = "loading" | "ready" | "failed";

export interface HostSceneOptions {
  readonly key: string;
  readonly designSpace: HostSize;
  readonly background: string;
  readonly mode?: HostMode;
}

const LOADING_NAME = "host-loading-label";
const FAILURE_NAME = "host-failure-card";

/** The engine's scene class, as this module is willing to name it. */
export type PhaserSceneClass = new (
  config: string | Phaser.Types.Scenes.SettingsConfig,
) => Phaser.Scene;

/**
 * The one scene base, over the engine class the calling module holds.
 *
 * `class RunnerScene extends hostScene<RunnerWorld>(Phaser.Scene) { ... }`
 */
export function hostScene<W>(base: PhaserSceneClass) {
  class HostScene extends base implements HostSceneContract<W> {
    readonly designSpace: HostSize;
    readonly background: string;
    readonly hostMode: HostMode;

    private loadState: HostLoadState = "loading";
    private loadFailure: string | null = null;
    private readonly listeners = new Set<HostListener<W>>();

    constructor(options: HostSceneOptions) {
      super({ key: options.key });
      this.designSpace = options.designSpace;
      this.background = options.background;
      this.hostMode = options.mode ?? "interactive";
    }

    // ---------------------------------------------------------------- lifecycle

    /** Whether this scene has finished loading, and how it went. */
    get hostLoadState(): HostLoadState {
      return this.loadState;
    }

    /** Why the scene could not be loaded, or null. */
    get hostLoadFailure(): string | null {
      return this.loadFailure;
    }

    /**
     * The first act of every scene, before it draws anything.
     *
     * The canvas is sized in device pixels at boot and the camera zooms by the same
     * factor about a top-left origin, so everything below keeps addressing the
     * design space. A capture boots a design-space canvas, for which this is the
     * identity.
     */
    protected zoomToDesignSpace(): void {
      applyDeviceZoom(this.cameras.main, this.designSpace);
    }

    /** Say what is being waited for, in the one place a scene says it. */
    protected showLoading(label: string): void {
      this.loadState = "loading";
      this.loadFailure = null;
      this.children.getByName(LOADING_NAME)?.destroy();
      this.add
        .text(this.designSpace.width / 2, this.designSpace.height / 2, label, {
          color: "#ffffff",
          fontFamily: "system-ui, sans-serif",
          fontSize: "22px",
          backgroundColor: "#15334faa",
          padding: { x: 18, y: 12 },
        })
        .setOrigin(0.5)
        .setScrollFactor(0)
        .setDepth(1000)
        .setName(LOADING_NAME);
    }

    /** Everything this scene needed has arrived. */
    protected finishLoading(): void {
      if (this.loadState === "failed") return;
      this.loadState = "ready";
      this.children.getByName(LOADING_NAME)?.destroy();
    }

    /**
     * One failure card, and every scene has it.
     *
     * Two of the four drew this by hand and two drew nothing at all, which is how a
     * missing sheet became a silent degrade in the room and in the dialogue scene.
     */
    protected failLoading(headline: string, error: unknown): void {
      const message = error instanceof Error ? error.message : String(error);
      this.loadState = "failed";
      this.loadFailure = message;
      this.children.getByName(LOADING_NAME)?.destroy();
      this.children.getByName(FAILURE_NAME)?.destroy();
      this.add
        .text(
          this.designSpace.width / 2,
          this.designSpace.height / 2,
          `${headline}\n${message}`,
          {
            align: "center",
            color: "#ffffff",
            fontFamily: "system-ui, sans-serif",
            fontSize: "20px",
            backgroundColor: "#5b1720dd",
            padding: { x: 22, y: 16 },
            wordWrap: { width: Math.max(240, this.designSpace.width - 380) },
          },
        )
        .setOrigin(0.5)
        .setScrollFactor(0)
        .setDepth(1200)
        .setName(FAILURE_NAME);
    }

    // ------------------------------------------------------------ subscriptions

    hostSubscribe(listener: HostListener<W>): () => void {
      this.listeners.add(listener);
      return () => {
        this.listeners.delete(listener);
      };
    }

    /**
     * Hand this frame to whoever is listening.
     *
     * Called at the end of a frame, after the sealed order has run, so a listener
     * sees a settled world rather than one mid-tick. A listener that throws is not
     * allowed to take the frame down with it: a console with a bug is a console
     * with a bug, not a game that stops.
     */
    protected publish(world: W, frame: readonly GameEvent[] = []): void {
      if (this.listeners.size === 0) return;
      for (const listener of this.listeners) {
        try {
          listener(world, frame);
        } catch (error) {
          console.error("[host] a frame listener threw:", error);
        }
      }
    }

    // ----------------------------------------------------------------- contract

    /** The sealed order this scene is running; empty until it has one. */
    hostSealedOrder(): readonly string[] {
      return [];
    }

    /** Start over. A scene with no notion of a reset says nothing and stays put. */
    hostReset(_seed: number, _scope: ResetScope): void {}

    /** Everything this scene owns that Phaser does not. */
    hostDispose(): void {
      this.listeners.clear();
    }
  }
  return HostScene;
}

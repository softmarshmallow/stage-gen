// The one boot. Every `Phaser.Game` this repository constructs is constructed here.
//
// The host audit found the same block four times — runner, room, dialogue scene,
// prepared platformer — with only the design space, the background colour and the
// teardown extras varying, and with the capture mode threaded through a route, a
// React component and a boot as a parameter that three of the four had to ignore.
// The block is one function now, and the three things that actually differ are
// declared by the scene rather than passed alongside it:
//
//   - `designSpace`   the logical pixels the scene is written in.
//   - `background`    the colour behind it.
//   - `hostMode`      interactive, or a capture.
//
// `hostMode` is what makes capture a *mode of the host* rather than a parameter:
// a capture keeps the design-space canvas so a frame hash is the same on every
// screen, and takes Phaser's canvas renderer with scaling off; a person gets a
// canvas sized in device pixels which the scene's own camera zooms back. Neither
// the route nor the React component decides any of that any more — they say which
// mode, and the two lines that depend on it live here.
//
// What the handle adds over the four ad-hoc ones it replaced is the subscription.
// A view that wants to mirror what the game is doing used to have exactly one
// option — read the handle on a timer, which the preview console did at 200 ms —
// because the handle had no event seam at all. It has one now: the scene publishes
// its world and the frame's occurrences at the end of every frame, and a listener
// hears them at the frame boundary rather than a fifth of a second later.

import Phaser from "phaser";

import { currentDevicePixelScale, deviceGameSize } from "@/lib/device-pixels/device-camera";
import type { GameEvent } from "@/lib/kernel/events";
import type { ResetScope } from "@/lib/kernel/systems";

/**
 * How this boot is being watched.
 *
 * `capture` is a recording of one published run: the canvas stays in design
 * space, nothing is zoomed by the device, and the scenes that have a bot or a
 * developer override refuse both, because a transcript digest carries no record
 * of either.
 */
export type HostMode = "interactive" | "capture";

export type HostListener<W> = (world: W, frame: readonly GameEvent[]) => void;

export interface HostSize {
  readonly width: number;
  readonly height: number;
}

/**
 * What `bootGame` needs of a scene, and the whole of it.
 *
 * Structural rather than nominal so the four scenes can reach it by extending
 * `HostScene` without the boot ever naming a genre. Every method has a base
 * implementation there; a scene overrides the ones it can actually answer.
 */
export interface HostSceneContract<W> {
  readonly designSpace: HostSize;
  readonly background: string;
  readonly hostMode: HostMode;
  hostSubscribe(listener: HostListener<W>): () => void;
  hostSealedOrder(): readonly string[];
  hostReset(seed: number, scope: ResetScope): void;
  hostDispose(): void;
}

export interface GameHandle<W> {
  /** Every scene teardown, then the game. Nothing of ours outlives the canvas. */
  destroy(removeCanvas?: boolean): void;
  reset(seed: number, scope: ResetScope): void;
  /** Hear the world and this frame's occurrences, at the frame boundary. */
  subscribe(listener: HostListener<W>): () => void;
  /** The sealed order this boot is running; empty until the scene has one. */
  readonly sealedOrder: readonly string[];
}

/**
 * Boot one scene into `parent`.
 *
 * The scene is constructed by its genre — it is the only thing here that knows
 * what it needs — and hands the host the three facts the engine configuration
 * depends on. The design space is what the scene is written in; the engine
 * letterboxes it into whatever `parent` turns out to be, so a game laid out at
 * 1280x720 plays identically on a phone and in a page column.
 */
export function bootGame<W>(
  parent: HTMLElement,
  scene: Phaser.Scene & HostSceneContract<W>,
): GameHandle<W> {
  const capture = scene.hostMode === "capture";
  // A capture keeps the design-space canvas so its frame hashes are the same on
  // every screen; a person gets one sized in device pixels, which the scene's
  // camera zooms back to design space.
  const size = capture
    ? scene.designSpace
    : deviceGameSize(scene.designSpace, currentDevicePixelScale());
  const game = new Phaser.Game({
    type: capture ? Phaser.CANVAS : Phaser.AUTO,
    width: size.width,
    height: size.height,
    parent,
    backgroundColor: scene.background,
    scene: [scene],
    scale: {
      mode: capture ? Phaser.Scale.NONE : Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
  });
  return Object.freeze({
    destroy(removeCanvas = true): void {
      // Before the game, not after: `game.destroy` drops every reference to the
      // scene, and the audio element a soundtrack is playing on is not one of
      // the things it knows how to stop. Three dispose orders, one of which got
      // this wrong, are one order now.
      scene.hostDispose();
      game.destroy(removeCanvas);
    },
    reset(seed: number, scope: ResetScope): void {
      scene.hostReset(seed, scope);
    },
    subscribe(listener: HostListener<W>): () => void {
      return scene.hostSubscribe(listener);
    },
    get sealedOrder(): readonly string[] {
      return scene.hostSealedOrder();
    },
  });
}

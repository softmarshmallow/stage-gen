// The in-canvas HUD: distance, score, and the death card.
//
// Distance is reported in meters on an honest conversion — 100 screen pixels
// of world at scale 1 is one meter, so meters = columns * tile_px / 100. The
// number the player watches is exactly the number the physics advanced, in a
// unit that stays meaningful across manifests with different tile sizes.
//
// Layout is pure and unit-tested; drawing takes a live scene. Phaser enters
// as types alone.

import type Phaser from "phaser";
import type { Rect } from "@/lib/shell/hud-geometry";
import { RUNNER_DEPTHS } from "./parallax";
import { GaugeBar } from "@/lib/sideview/gauge-bar";
import type { GameSystem } from "@/lib/game-systems/systems";
import { avatarIsImmune } from "./vitals";
import { RUNNER_VIEW_HEIGHT, RUNNER_VIEW_WIDTH, type RunnerWorld } from "./world";

/** Screen pixels of world (at scale 1) that count as one reported meter. */
export const SCREEN_PIXELS_PER_METER = 100;

export function runDistanceMeters(distanceColumns: number, tilePx: number): number {
  return Math.max(0, Math.floor((distanceColumns * tilePx) / SCREEN_PIXELS_PER_METER));
}

export function formatRunDistance(distanceColumns: number, tilePx: number): string {
  return `${runDistanceMeters(distanceColumns, tilePx)} m`;
}

export function formatScore(score: number): string {
  return `✦ ${Math.max(0, Math.floor(score))}`;
}

/** The chain readout: silent until a chain exists, loud about the multiplier. */
export function formatCombo(chain: number, multiplier: number): string {
  if (chain <= 0) return "";
  return multiplier > 1 ? `×${multiplier} · ${chain} chain` : `${chain} chain`;
}

/** The readout band across the top-left of the canvas. */
export function hudReadoutRect(viewWidth: number = RUNNER_VIEW_WIDTH): Rect {
  return { x: 24, y: 18, width: Math.min(420, viewWidth - 48), height: 44 };
}

/**
 * The vitals bar, pinned above the readout band.
 *
 * Screen furniture, not a floating bar: the runner's avatar is pinned to a
 * fixed screen anchor and never leaves it, so a bar tracking the body would
 * hold still anyway while stealing the glance downward that a runner cannot
 * afford. The top-left corner is where the run's other promises already are —
 * distance, score, chain — and how many mistakes are left is the same kind of
 * fact about the run rather than a fact about a body.
 */
export function vitalsBarRect(viewWidth: number = RUNNER_VIEW_WIDTH): Rect {
  const readout = hudReadoutRect(viewWidth);
  return { x: readout.x, y: readout.y - 12, width: Math.min(180, readout.width), height: 10 };
}

/** The death card, centered with a fixed aspect so it reads the same everywhere. */
export function deathPanelRect(
  viewWidth: number = RUNNER_VIEW_WIDTH,
  viewHeight: number = RUNNER_VIEW_HEIGHT,
): Rect {
  const width = Math.min(560, viewWidth * 0.6);
  const height = Math.min(230, viewHeight * 0.4);
  return {
    x: (viewWidth - width) / 2,
    y: (viewHeight - height) / 2,
    width,
    height,
  };
}

export interface HudView {
  sync(world: RunnerWorld): void;
}

/** The HUD paints over everything, so it seals after the world presentation. */
export function createHudSystem(view: HudView): GameSystem<RunnerWorld> {
  return {
    id: "runner/hud",
    contractVersion: "hud-system-v3",
    reads: ["run", "avatar", "camera", "vitals"],
    writes: [],
    after: ["runner/parallax"],
    update(world) {
      view.sync(world);
    },
  };
}

const READOUT_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "system-ui, sans-serif",
  fontSize: "26px",
  color: "#f2f3f5",
};

const HINT_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "system-ui, sans-serif",
  fontSize: "22px",
  color: "#98a0ab",
};

/** Build the HUD objects on a live scene and return the view the system drives. */
export function buildHud(scene: Phaser.Scene, tilePx: number, maxPoints: number | null): HudView {
  const readout = hudReadoutRect();
  // A one-hit-kill package has nothing to draw: a bar that can only ever read
  // full is a promise about mistakes the player does not have.
  const vitalsRect = vitalsBarRect();
  const vitalsBar =
    maxPoints === null
      ? null
      : new GaugeBar(scene, {
          style: { width: vitalsRect.width, height: vitalsRect.height },
          max: maxPoints,
          // Zero: the bar belongs to the run, not to the world under it.
          scrollFactor: 0,
          depth: RUNNER_DEPTHS.hud,
        });
  const distanceText = scene.add
    .text(readout.x, readout.y, "0 m", READOUT_STYLE)
    .setDepth(RUNNER_DEPTHS.hud)
    .setScrollFactor(0);
  const scoreText = scene.add
    .text(readout.x, readout.y + 30, formatScore(0), {
      ...READOUT_STYLE,
      fontSize: "20px",
      color: "#ffdf8a",
    })
    .setDepth(RUNNER_DEPTHS.hud)
    .setScrollFactor(0);
  const comboText = scene.add
    .text(readout.x, readout.y + 56, "", {
      ...READOUT_STYLE,
      fontSize: "18px",
      color: "#9fe3a8",
    })
    .setDepth(RUNNER_DEPTHS.hud)
    .setScrollFactor(0);

  const panel = deathPanelRect();
  const dim = scene.add.graphics().setDepth(RUNNER_DEPTHS.hud + 1);
  dim.fillStyle(0x05070a, 0.66);
  dim.fillRect(0, 0, RUNNER_VIEW_WIDTH, RUNNER_VIEW_HEIGHT);
  const card = scene.add.graphics().setDepth(RUNNER_DEPTHS.hud + 2);
  card.fillStyle(0x0d1014, 0.95);
  card.fillRoundedRect(panel.x, panel.y, panel.width, panel.height, 10);
  card.lineStyle(2, 0xffdf8a, 0.9);
  card.strokeRoundedRect(panel.x, panel.y, panel.width, panel.height, 10);
  const title = scene.add
    .text(panel.x + panel.width / 2, panel.y + 42, "Run over", {
      ...READOUT_STYLE,
      fontSize: "30px",
      color: "#ffdf8a",
    })
    .setOrigin(0.5, 0)
    .setDepth(RUNNER_DEPTHS.hud + 3);
  const summary = scene.add
    .text(panel.x + panel.width / 2, panel.y + 96, "", READOUT_STYLE)
    .setOrigin(0.5, 0)
    .setDepth(RUNNER_DEPTHS.hud + 3);
  const hint = scene.add
    .text(
      panel.x + panel.width / 2,
      panel.y + 150,
      "press R or tap the upper screen to run again",
      HINT_STYLE,
    )
    .setOrigin(0.5, 0)
    .setDepth(RUNNER_DEPTHS.hud + 3);
  const deathLayer = [dim, card, title, summary, hint];
  for (const object of deathLayer) object.setVisible(false);

  return {
    sync(world: RunnerWorld): void {
      const gauge = world.vitals.gauge;
      if (vitalsBar && gauge) {
        vitalsBar.update({
          value: gauge.value,
          max: gauge.max,
          x: vitalsRect.x + vitalsRect.width / 2,
          y: vitalsRect.y + vitalsRect.height / 2,
          // The bar flashes with the immunity window, so the readout itself
          // says a blow connected rather than only the avatar saying it.
          dimmed: avatarIsImmune(world),
        });
      }
      distanceText.setText(formatRunDistance(world.avatar.distanceColumns, tilePx));
      scoreText.setText(formatScore(world.run.score));
      comboText.setText(formatCombo(world.run.chain, world.run.multiplier));
      const dead = world.run.phase === "dead";
      if (dead) {
        summary.setText(
          `${formatRunDistance(world.avatar.distanceColumns, tilePx)} · ${formatScore(world.run.score)}`,
        );
      }
      for (const object of deathLayer) object.setVisible(dead);
    },
  };
}

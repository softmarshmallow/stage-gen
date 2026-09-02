import { describe, expect, mock, test } from "bun:test";

// The boot module subclasses Phaser.Scene at import time; a class stub is all
// the assembly needs — no canvas, no game loop.
mock.module("phaser", () => ({
  default: {
    Scene: class {},
    AUTO: 0,
    Scale: { FIT: 1, CENTER_BOTH: 2 },
    Textures: { FilterMode: { NEAREST: 0 } },
  },
}));

const { assembleRunnerSystems } = await import("./game");
const { sealSystems } = await import("@/lib/game-systems/systems");
const { createIntentLatch } = await import("./intent");
const { SILENT_AUDIO_SINK } = await import("./audio");

const DOCUMENTED_ORDER = [
  "runner/intent",
  "runner/difficulty",
  "runner/avatar",
  // The screen-FX moment seals before the encounter director that consumes
  // its release; the director seals before the stream it asks for an arena,
  // before the vitals that answer for the shots it fires, and before the
  // run-loop that pays for the boss it defeats.
  "fx/moment",
  "runner/encounter",
  "runner/segments",
  "runner/obstacles",
  "runner/vitals",
  "runner/run-loop",
  "runner/camera",
  "runner/parallax",
  "runner/hud",
  "runner/audio",
];

const noopView = { sync: () => undefined };

// The runner declares events, so sealing needs the accessor that clears the
// frame queue each tick — the same one `RunnerScene` passes.
const EVENTS = { events: (world: { events: unknown }) => world.events as { beginFrame(): void } };

describe("assembleRunnerSystems", () => {
  test("seals into the documented frame order", () => {
    const sealed = sealSystems(
      assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK),
      EVENTS,
    );
    expect(sealed.order).toEqual(DOCUMENTED_ORDER);
  });

  test("the order derives from declarations, not registration order", () => {
    const reversed = [
      ...assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK),
    ].reverse();
    expect(sealSystems(reversed, EVENTS).order).toEqual(DOCUMENTED_ORDER);
  });

  test("every system declares a contract version", () => {
    for (const system of assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK)) {
      expect(system.contractVersion).toMatch(/-v\d+$/);
    }
  });
});

describe("the encounter in the sealed order", () => {
  test("seals identically whether or not a package fights anything", () => {
    // The topology is declaration-driven: the director is always assembled,
    // and a package with nothing to fight simply carries a null slice.
    const sealed = sealSystems(
      assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK),
      EVENTS,
    );
    expect(sealed.order).toEqual(DOCUMENTED_ORDER);
  });

  test("the director sits between the moment it consumes and the systems that answer it", () => {
    const order = sealSystems(
      assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK),
      EVENTS,
    ).order;
    const at = (id: string) => order.indexOf(id);

    // It consumes fx-released ...
    expect(at("fx/moment")).toBeLessThan(at("runner/encounter"));
    // ... asks the stream for an arena ...
    expect(at("runner/encounter")).toBeLessThan(at("runner/segments"));
    // ... and emits shot-contact and boss-defeated, which these answer.
    expect(at("runner/encounter")).toBeLessThan(at("runner/vitals"));
    expect(at("runner/encounter")).toBeLessThan(at("runner/run-loop"));
  });
});

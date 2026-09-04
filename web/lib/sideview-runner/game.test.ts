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

const { assembleRunnerSystems, runnerSealOptions } = await import("./game");
const {
  sealSystems,
  OwnershipConflictError,
  SystemCycleError,
  UndeclaredWriteError,
  UnemittedEventError,
  UnknownSystemError,
} = await import("@/lib/kernel/systems");
const { createIntentLatch } = await import("./intent");
const { SILENT_AUDIO_SINK } = await import("./audio");
const { createRunnerWorld } = await import("./world");
const { parseRunnerRuntimeManifest } = await import("./contract");
const { runnerManifestFixture } = await import("./fixture");
type RunnerWorld = import("./world").RunnerWorld;
type RunnerSystem = import("@/lib/kernel/systems").GameSystem<RunnerWorld>;

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
  "runner/dust",
];

const noopView = { sync: () => undefined, hide: () => undefined };

// The runner declares events and a run boundary, so sealing needs the options
// the boot passes: the accessor that clears the queue, and the occurrence that
// ends a run.
const EVENTS = runnerSealOptions();

/** The real roster, with one system's declaration replaced. */
function rosterWith(id: string, replace: (system: RunnerSystem) => RunnerSystem): RunnerSystem[] {
  return assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK).map(
    (system) => (system.id === id ? replace(system) : system),
  );
}

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

  test("the camera keeps its place on an after edge instead of a read it never made", () => {
    // It used to declare `reads: ["run"]` and never touch the slice, purely to
    // land behind the run-loop. The edge is the same edge; only the honesty
    // changed, which is why the documented order is untouched.
    const camera = assembleRunnerSystems(
      createIntentLatch(),
      noopView,
      noopView,
      SILENT_AUDIO_SINK,
    ).find((system) => system.id === "runner/camera");
    expect(camera?.reads).toEqual(["avatar"]);
    expect(camera?.after).toEqual(["runner/run-loop"]);
    const order = sealSystems(
      assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK),
      EVENTS,
    ).order;
    expect(order.indexOf("runner/run-loop")).toBeLessThan(order.indexOf("runner/camera"));
  });
});

// --- The refusals, with the runner's own pre-fix declarations as fixtures ------------------

describe("the sealer refuses the declarations this step corrected", () => {
  test("two owners of one slice: fx, as the director used to write it", () => {
    // Before this step the encounter director wrote `fx` as well as the fx
    // system. Restore the claim and the seal names both systems and the slice.
    const seal = () =>
      sealSystems(
        rosterWith("runner/encounter", (system) => ({ ...system, owns: [...(system.owns ?? []), "fx"] })),
        EVENTS,
      );
    expect(seal).toThrow(OwnershipConflictError);
    expect(seal).toThrow('refused two owners of "fx"');
    expect(seal).toThrow('"fx/moment" and "runner/encounter"');
  });

  test("a shared write into an owned slice is refused the same way", () => {
    const seal = () =>
      sealSystems(
        rosterWith("runner/encounter", (system) => ({ ...system, writes: [...system.writes, "fx"] })),
        EVENTS,
      );
    expect(seal).toThrow(OwnershipConflictError);
    expect(seal).toThrow('it writes "fx", which "fx/moment" owns');
  });

  test("an undeclared write: the death pose the run-loop used to apply", () => {
    const sealed = sealSystems(
      rosterWith("runner/run-loop", (system) => ({
        ...system,
        update(world, step) {
          system.update(world, step);
          // The line this step deleted.
          world.avatar.motion = "death";
        },
      })),
      runnerSealOptions({ devTrap: true }),
    );
    const world = createRunnerWorld(parseRunnerRuntimeManifest(runnerManifestFixture()), 1);
    const tick = () => sealed.tick(world, { dt: 1 / 60, now: 1 / 60, frame: 1 });
    expect(tick).toThrow(UndeclaredWriteError);
    expect(tick).toThrow('"runner/run-loop" wrote "avatar.motion"');
  });

  test("declaring that write instead would have closed a cycle", () => {
    // Ownership refuses it first, so this fixture also gives up the avatar's
    // ownership — which is the second half of the reason the pose became the
    // avatar's own to write. `avatar` is read by nearly everything sealed
    // before the run-loop, so a run-loop that writes it would have to run both
    // before and after them, and no order exists.
    const shared = rosterWith("runner/avatar", (system) => ({
      ...system,
      owns: [],
      writes: ["avatar"],
    })).map((system) =>
      system.id === "runner/run-loop" ? { ...system, writes: ["avatar" as const] } : system,
    );
    const seal = () => sealSystems(shared, EVENTS);
    expect(seal).toThrow(SystemCycleError);
    expect(seal).toThrow("runner/run-loop");
  });

  test("a consumed type with no emitter: the verdict with nobody to give it", () => {
    // Drop vitals, the only system that emits `run-ended`, and the run-loop's
    // consume has no other end.
    const withoutVitals = assembleRunnerSystems(
      createIntentLatch(),
      noopView,
      noopView,
      SILENT_AUDIO_SINK,
    ).filter((system) => system.id !== "runner/vitals");
    const seal = () => sealSystems(withoutVitals, EVENTS);
    expect(seal).toThrow(UnemittedEventError);
    expect(seal).toThrow('it consumes "run-ended", which no system emits');
  });

  test("an unknown name in an after edge", () => {
    const seal = () =>
      sealSystems(
        rosterWith("runner/camera", (system) => ({ ...system, after: ["runner/run-lop"] })),
        EVENTS,
      );
    expect(seal).toThrow(UnknownSystemError);
    expect(seal).toThrow('names unregistered "runner/run-lop"');
  });
});

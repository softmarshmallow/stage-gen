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
const { parseRunnerClockBlock, momentHolds } = await import("./clock");
const { parseRunnerSessionBlock } = await import("./session");
const { gateRunnerFamilyBlocks } = await import("./game");
const { RUNNER_INTENT_SHAPE, parseRunnerIntentBlock } = await import("./intent");
const { parseRunnerVitalsBlock, RUNNER_REFRACTORY_MS, RUNNER_BLINK_ALPHA } = await import("./vitals");
const { CONTACT_HURT_PROFILE } = await import("@/lib/families/vitals");
const { RUNNER_BLOCKS } = await import("./contract");
const { SILENT_AUDIO_SINK } = await import("./audio");
const { createRunnerWorld } = await import("./world");
const { parseRunnerRuntimeManifest } = await import("./contract");
const { runnerManifestFixture } = await import("./fixture");
type RunnerWorld = import("./world").RunnerWorld;
type RunnerSystem = import("@/lib/kernel/systems").GameSystem<RunnerWorld>;

const DOCUMENTED_ORDER = [
  // The `clock` family, first: it decides how much simulation time this frame
  // carries, and the intent that is drained under a hold, the avatar that
  // integrates it and the vitals that stamp against it all read the answer.
  "clock/step",
  "runner/intent",
  "runner/difficulty",
  "runner/avatar",
  // The screen-FX moment seals before the encounter director that consumes
  // its release; the director seals before the stream it asks for an arena,
  // before the vitals that answer for the shots it fires, and before the
  // scorer that pays for the boss it defeats.
  "fx/moment",
  "runner/encounter",
  "runner/segments",
  "runner/obstacles",
  "runner/vitals",
  // The scorer, then the lifecycle. They were one system, and the split is the
  // one the `session` family rules: "what ended the run" and "what a token was
  // worth" are two questions. The scorer runs first and feedback-reads the
  // phase, which is how the single system behaved — it scored the frame and
  // only then asked whether the frame had ended the run.
  "score/run",
  "session/run",
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
    // One tie does not survive the reversal, and it is named rather than
    // papered over: `score/run` and `runner/vitals` are unordered by anything
    // either declares — neither reads what the other writes, and the scorer's
    // read of the phase is a feedback read by construction — so the
    // registration order is the only thing separating them. Every other pair
    // is bought by a declaration.
    const swapped = [...DOCUMENTED_ORDER];
    const at = swapped.indexOf("score/run");
    swapped[at - 1] = "score/run";
    swapped[at] = "runner/vitals";
    expect(sealSystems(reversed, EVENTS).order).toEqual(swapped);
  });

  test("and every load-bearing pair survives the reversal", () => {
    const reversed = [
      ...assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK),
    ].reverse();
    const order = sealSystems(reversed, EVENTS).order;
    const before = (a: string, b: string) =>
      expect(order.indexOf(a)).toBeLessThan(order.indexOf(b));
    before("clock/step", "runner/intent");
    before("clock/step", "runner/avatar");
    before("runner/intent", "runner/avatar");
    before("runner/obstacles", "score/run");
    before("score/run", "session/run");
    before("runner/vitals", "session/run");
    before("session/run", "runner/camera");
    before("session/run", "runner/audio");
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
    expect(at("runner/encounter")).toBeLessThan(at("session/run"));
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
    expect(camera?.after).toEqual(["session/run"]);
    const order = sealSystems(
      assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK),
      EVENTS,
    ).order;
    expect(order.indexOf("session/run")).toBeLessThan(order.indexOf("runner/camera"));
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

  test("an undeclared write: the death pose the run loop used to apply", () => {
    const sealed = sealSystems(
      rosterWith("session/run", (system) => ({
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
    expect(tick).toThrow('"session/run" wrote "avatar.motion"');
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
      system.id === "session/run" ? { ...system, writes: ["avatar" as const] } : system,
    );
    const seal = () => sealSystems(shared, EVENTS);
    expect(seal).toThrow(SystemCycleError);
    expect(seal).toThrow("session/run");
  });

  test("a consumed type with no emitter: the verdict with nobody to give it", () => {
    // Drop vitals, the only system that emits `run-ended`, and the session's
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

// --- The `clock` family, sealed into this genre ---------------------------------------------

describe("the clock family in the runner", () => {
  const roster = () =>
    assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK);

  test("E7 subtraction: with the clock taken out, the rest seals to the identical order", () => {
    // The family is one entry, and removing it moves nothing else: every
    // system that reads the clock reads it as an input, not as a position.
    const quiet = roster().filter((system) => system.id !== "clock/step");
    expect(sealSystems(quiet, EVENTS).order).toEqual(
      DOCUMENTED_ORDER.filter((id) => id !== "clock/step"),
    );
  });

  test("the moment is this genre's one holder, and the dead phase is not", () => {
    const world = createRunnerWorld(parseRunnerRuntimeManifest(runnerManifestFixture()), 1);
    expect(momentHolds(world)).toBe(false);
    world.fx = { moment: "boss_arrival", choreography: "tear_reveal_v1", startedAt: null, released: false };
    expect(momentHolds(world)).toBe(true);
    // Released is released: the simulation resumes while the overlay tears away.
    world.fx.released = true;
    expect(momentHolds(world)).toBe(false);
    world.fx = null;
    world.run.phase = "dead";
    expect(momentHolds(world)).toBe(false);
  });

  test("under a hold the avatar integrates nothing and the jump edge is spent, not queued", () => {
    const latch = createIntentLatch();
    const sealed = sealSystems(
      assembleRunnerSystems(latch, noopView, noopView, SILENT_AUDIO_SINK),
      runnerSealOptions({ devTrap: true }),
    );
    const world = createRunnerWorld(parseRunnerRuntimeManifest(runnerManifestFixture()), 1);
    // A moment already in flight, the way a boss cut-in reaches a running run.
    world.fx = { moment: "boss_arrival", choreography: "tear_reveal_v1", startedAt: null, released: false };
    const before = { ...world.avatar };
    latch.requestJump();
    sealed.tick(world, { dt: 1 / 60, now: 1 / 60, frame: 1 });
    expect(world.clock.held).toBe(true);
    expect(world.clock.simulationDt).toBe(0);
    expect(world.clock.simulationNow).toBe(0);
    // The edge was drained by the sample and reported neutral, so nothing
    // launched — and nothing is queued to launch when the overlay lets go.
    expect(world.intent.jump).toBe(false);
    expect(world.avatar.jumpImpulses).toBe(before.jumpImpulses);
    expect(world.avatar.distanceColumns).toBe(before.distanceColumns);
    expect(world.avatar.grounded).toBe(true);
  });

  test("the family gates its own block, and the refusal names it", () => {
    const blocks = { ...RUNNER_BLOCKS };
    expect(parseRunnerClockBlock(blocks).published).toBe(true);
    const { fx: _fx, ...withoutFx } = blocks;
    // No fx block is no moment, which is no holder — not a refusal.
    expect(parseRunnerClockBlock(withoutFx).published).toBe(false);
    expect(() => parseRunnerClockBlock({ ...blocks, fx: "fx-block-v2" })).toThrow(
      'manifest block "fx" is published as fx-block-v2; this build reads fx-block-v1',
    );
  });
});

// --- The `session` family, sealed into this genre ---------------------------------------------

describe("the session family in the runner", () => {
  const roster = () =>
    assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK);

  test("E7 subtraction: a genre that keeps the session and refuses the score still seals", () => {
    // The plan's cinematic platformer wants the lifecycle and not the token
    // line. Take the scorer out, drop the one edge that names it, and the rest
    // of the frame is the same frame — which is the whole claim of splitting
    // them: the lifecycle never needed the score to decide anything.
    const quiet = roster()
      .filter((system) => system.id !== "score/run")
      .map((system) =>
        system.id === "session/run"
          ? { ...system, after: (system.after ?? []).filter((id) => id !== "score/run") }
          : system,
      );
    expect(sealSystems(quiet, EVENTS).order).toEqual(
      DOCUMENTED_ORDER.filter((id) => id !== "score/run"),
    );
  });

  test("the two questions have two authors, and the sealer says so", () => {
    const systems = roster();
    const session = systems.find((system) => system.id === "session/run");
    const score = systems.find((system) => system.id === "score/run");
    expect(session?.owns).toEqual(["run"]);
    expect(score?.owns).toEqual(["score"]);
    // The scorer's read of the phase is a feedback read by construction: it is
    // not declared, and the session's own `after` edge is what keeps the frame
    // scored under the phase it was collected in.
    expect(score?.reads).toEqual(["obstacles"]);
    expect(session?.after).toEqual(["score/run"]);
  });

  test("the family gates its own block, and the refusal names it", () => {
    expect(parseRunnerSessionBlock(RUNNER_BLOCKS).published).toBe(true);
    expect(() =>
      parseRunnerSessionBlock({ ...RUNNER_BLOCKS, gameplay: "runner-gameplay-block-v2" }),
    ).toThrow('manifest block "gameplay" is published as runner-gameplay-block-v2');
  });
});

// --- The `intent` family, sealed into this genre -----------------------------------------------

describe("the intent family in the runner", () => {
  const roster = () =>
    assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK);

  test("E7 subtraction: with the intent taken out, the rest seals to the identical order", () => {
    // One system names it in an `after` edge — the difficulty ramp, which is
    // pinned behind the frame's one input read — so the subtraction drops that
    // edge with it. That is the honest form of "the family is quiet": a genre
    // that has no intent has no ramp pinned behind one either.
    const quiet = roster()
      .filter((system) => system.id !== "runner/intent")
      .map((system) => ({
        ...system,
        after: (system.after ?? []).filter((id) => id !== "runner/intent"),
      }));
    expect(sealSystems(quiet, EVENTS).order).toEqual(
      DOCUMENTED_ORDER.filter((id) => id !== "runner/intent"),
    );
  });

  test("the edge-vs-level split is data this genre declares, not a comment", () => {
    expect([...RUNNER_INTENT_SHAPE.edges].sort()).toEqual(["action", "jump"]);
    expect([...RUNNER_INTENT_SHAPE.levels].sort()).toEqual(["duck", "thrust"]);
  });

  test("the family gates its own block, and the boot runs every family's gate", () => {
    expect(parseRunnerIntentBlock(RUNNER_BLOCKS).published).toBe(true);
    expect(() => gateRunnerFamilyBlocks(RUNNER_BLOCKS)).not.toThrow();
    expect(() =>
      gateRunnerFamilyBlocks({ ...RUNNER_BLOCKS, gameplay: "runner-gameplay-block-v2" }),
    ).toThrow('manifest block "gameplay" is published as runner-gameplay-block-v2');
  });
});

// --- The `vitals` family, sealed into this genre -----------------------------------------------

describe("the vitals family in the runner", () => {
  const roster = () =>
    assembleRunnerSystems(createIntentLatch(), noopView, noopView, SILENT_AUDIO_SINK);

  test("E7 subtraction: a genre with no vitals seals to the identical order", () => {
    // The one thing that has to come out with it is the session's consume of
    // `run-ended`: vitals is the only emitter, and a channel with no other end
    // is a refusal the kernel already makes (fixtured above). A genre with no
    // vitals has no verdict to hear, which is the point of taking it out.
    const quiet = roster()
      .filter((system) => system.id !== "runner/vitals")
      .map((system) =>
        system.id === "session/run"
          ? { ...system, consumes: (system.consumes ?? []).filter((type) => type !== "run-ended") }
          : system,
      );
    expect(sealSystems(quiet, EVENTS).order).toEqual(
      DOCUMENTED_ORDER.filter((id) => id !== "runner/vitals"),
    );
  });

  test("the window and the blink are the family's profile, not a second copy", () => {
    expect(RUNNER_REFRACTORY_MS).toBe(CONTACT_HURT_PROFILE.refractoryMs);
    expect(RUNNER_BLINK_ALPHA).toBe(CONTACT_HURT_PROFILE.blinkAlpha);
  });

  test("the family gates its own block, and the refusal names it", () => {
    expect(parseRunnerVitalsBlock(RUNNER_BLOCKS).published).toBe(true);
    expect(() =>
      parseRunnerVitalsBlock({ ...RUNNER_BLOCKS, gameplay: "runner-gameplay-block-v2" }),
    ).toThrow('manifest block "gameplay" is published as runner-gameplay-block-v2');
  });
});

import { describe, expect, test } from "bun:test";
import { createSessionSystemForRunner, nextRunSeed, parseRunnerSessionBlock } from "./session";
import { parseRunnerRuntimeManifest, RUNNER_BLOCKS } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { runnerIntent } from "./intent";
import { stepAvatar } from "./avatar";
import { mulberry32 } from "@/lib/kernel/rng";
import { createRunnerWorld } from "./world";

const STEP = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;
const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());
const system = createSessionSystemForRunner();

describe("the session in the runner", () => {
  test("a run-ended verdict ends the run and carries its source", () => {
    const world = createRunnerWorld(manifest, 1);
    world.events.emit({ type: "run-ended", source: "crush" });
    system.update(world, STEP);
    expect(world.run.phase).toBe("dead");
    expect(world.run.endedBy).toBe("crush");
    // The death pose is not written here. `avatar` has one author, and it
    // wears the pose on its own next tick, from the phase this system just
    // set — the one frame its own comment has always claimed.
    expect(world.avatar.motion).not.toBe("death");
    stepAvatar(world, STEP.dt);
    expect(world.avatar.motion).toBe("death");
  });

  test("hazard contact alone does not end the run: the consequence decides", () => {
    const world = createRunnerWorld(manifest, 1);
    world.obstacles.hazardContact = true;
    world.events.emit({ type: "hazard-contact", key: "6:filter_stack" });
    system.update(world, STEP);
    // No verdict was emitted, so nothing here ends anything. Under this
    // fixture a hazard drains instead, which is runner/vitals' answer to give.
    expect(world.run.phase).toBe("running");
  });

  test("a drained point that did not empty the gauge leaves the run alive", () => {
    const world = createRunnerWorld(manifest, 1);
    world.events.emit({ type: "drained", source: "hazard", remaining: 2 });
    system.update(world, STEP);
    expect(world.run.phase).toBe("running");
    expect(world.run.endedBy).toBe(null);
  });

  test("a jump or action request asks for a restart rather than performing one", () => {
    const session = createSessionSystemForRunner();
    const world = createRunnerWorld(manifest, 1);
    const firstSeed = world.run.seed;
    world.run.phase = "dead";
    world.avatar.distanceColumns = 300;
    world.intent = runnerIntent({ jump: true });
    session.update(world, STEP);
    // The world is untouched: the ask is an occurrence, and the composition
    // performs the reset at the end of the frame that carried it.
    expect(world.run.phase).toBe("dead");
    const asked = world.events.ofType("run-restarted");
    expect(asked).toHaveLength(1);
    expect(asked[0]?.seed).not.toBe(firstSeed);

    session.reset?.(world, "run");
    // Widened read: TS control-flow narrowing cannot see the in-place reset.
    expect(world.run.phase as string).toBe("running");
    expect(world.run.seed).toBe(asked[0]?.seed);
    expect(world.avatar.distanceColumns).toBe(2);
    expect(world.segments.chunks.length).toBeGreaterThan(0);
  });

  test("the lineage is counted: a run inside a session, a session from zero", () => {
    const session = createSessionSystemForRunner();
    const world = createRunnerWorld(manifest, 1);
    expect(world.run.runIndex).toBe(0);
    world.run.phase = "dead";
    world.intent = runnerIntent({ action: true });
    session.update(world, STEP);
    session.reset?.(world, "run");
    expect(world.run.runIndex).toBe(1);
    session.reset?.(world, "run");
    expect(world.run.runIndex).toBe(2);
    session.reset?.(world, "session");
    expect(world.run.runIndex).toBe(0);
  });

  test("the fresh seed is deterministic from the dying run's RNG", () => {
    const seeds = [5, 5].map((seed) => {
      const session = createSessionSystemForRunner();
      const world = createRunnerWorld(manifest, seed);
      world.run.phase = "dead";
      world.intent = runnerIntent({ action: true });
      session.update(world, STEP);
      session.reset?.(world, "run");
      return world.run.seed;
    });
    expect(seeds[0]).toBe(seeds[1]);
  });

  test("the family gates its own block, and the refusal names it", () => {
    expect(parseRunnerSessionBlock(RUNNER_BLOCKS).published).toBe(true);
    expect(() =>
      parseRunnerSessionBlock({ ...RUNNER_BLOCKS, gameplay: "runner-gameplay-block-v2" }),
    ).toThrow(
      'manifest block "gameplay" is published as runner-gameplay-block-v2; ' +
        "this build reads runner-gameplay-block-v1",
    );
  });
});

describe("nextRunSeed", () => {
  test("draws a 32-bit seed from the stream", () => {
    const seed = nextRunSeed(mulberry32(9));
    expect(Number.isSafeInteger(seed)).toBe(true);
    expect(seed).toBeGreaterThanOrEqual(0);
    expect(seed).toBeLessThan(0x100000000);
  });
});

describe("the intro phase", () => {
  test("holds the run until the fx moment releases it, then never replays on restart", async () => {
    const { fxBlockFixture } = await import("@/lib/manifest/fx");
    const document = runnerManifestFixture();
    document.fx = fxBlockFixture();
    const world = createRunnerWorld(parseRunnerRuntimeManifest(document), 1);
    expect(world.run.phase).toBe("intro");
    expect(world.fx?.moment).toBe("stage_start");
    system.update(world, STEP);
    expect(world.run.phase).toBe("intro");
    world.events.emit({ type: "fx-released", moment: "stage_start" });
    system.update(world, STEP);
    expect(world.run.phase).toBe("running");

    world.events.beginFrame();
    world.events.emit({ type: "run-ended", source: "pit" });
    system.update(world, STEP);
    expect(world.run.phase).toBe("dead");
    world.events.beginFrame();
    world.intent = runnerIntent({ jump: true });
    const session = createSessionSystemForRunner();
    session.update(world, STEP);
    session.reset?.(world, "run");
    expect(world.run.phase).toBe("running");
    expect(world.fx).toBeNull();
  });

  test("a package with no fx block is born running", () => {
    const world = createRunnerWorld(manifest, 1);
    expect(world.run.phase).toBe("running");
    expect(world.fx).toBeNull();
  });
});

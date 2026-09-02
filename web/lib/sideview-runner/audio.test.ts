import { describe, expect, test } from "bun:test";
import { createAudioSystem, strengthLift, type RunnerAudioCue } from "./audio";
import { parseRunnerRuntimeManifest, type RunnerMusicEvent } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { runnerIntent } from "./intent";
import { createRunnerWorld } from "./world";
import { stepAvatar } from "./avatar";

const STEP = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;
const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());

function recorder(): { cues: RunnerAudioCue[]; play: (cue: RunnerAudioCue) => void } {
  const cues: RunnerAudioCue[] = [];
  return { cues, play: (cue) => cues.push(cue) };
}

describe("createAudioSystem", () => {
  test("a takeoff and the air jump each cue once, on their own edges", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const system = createAudioSystem(sink);
    system.update(world, STEP);
    expect(sink.cues).toEqual([]);

    world.intent = runnerIntent({ jump: true });
    stepAvatar(world, STEP.dt);
    system.update(world, STEP);
    expect(sink.cues).toEqual(["takeoff"]);

    stepAvatar(world, STEP.dt);
    system.update(world, STEP);
    expect(sink.cues).toEqual(["takeoff", "air_jump"]);

    world.intent = runnerIntent();
    stepAvatar(world, STEP.dt);
    system.update(world, STEP);
    expect(sink.cues).toEqual(["takeoff", "air_jump"]);
  });

  test("the slide cues on its leading edge only", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const system = createAudioSystem(sink);
    world.intent = runnerIntent({ duck: true });
    stepAvatar(world, STEP.dt);
    system.update(world, STEP);
    stepAvatar(world, STEP.dt);
    system.update(world, STEP);
    expect(sink.cues).toEqual(["slide"]);
  });

  test("a survivable hit cues on the frame the drain connects, and not once dead", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const system = createAudioSystem(sink);
    system.update(world, STEP);
    world.vitals.hurtThisFrame = true;
    system.update(world, STEP);
    world.vitals.hurtThisFrame = false;
    system.update(world, STEP);
    expect(sink.cues).toEqual(["hurt"]);

    world.vitals.hurtThisFrame = true;
    world.run.phase = "dead";
    system.update(world, STEP);
    expect(sink.cues).toEqual(["hurt", "death"]);
  });

  test("death cues once and a restart resets the edges quietly", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const system = createAudioSystem(sink);
    system.update(world, STEP);
    world.run.phase = "dead";
    system.update(world, STEP);
    system.update(world, STEP);
    expect(sink.cues).toEqual(["death"]);
    // A restart rewinds distance; the system resigns the frame silently.
    world.run.phase = "running";
    world.avatar.distanceColumns = 0.5;
    system.update(world, STEP);
    expect(sink.cues).toEqual(["death"]);
  });
});

describe("createAudioSystem music sink", () => {
  test("death, restart, and hurt reach the music sink beside their cues", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const edges: RunnerMusicEvent[] = [];
    const system = createAudioSystem(sink, { transition: (event) => edges.push(event) });
    system.update(world, STEP);
    world.vitals.hurtThisFrame = true;
    system.update(world, STEP);
    world.vitals.hurtThisFrame = false;
    world.run.phase = "dead";
    system.update(world, STEP);
    system.update(world, STEP);
    expect(edges).toEqual(["hurt", "death"]);

    world.run.phase = "running";
    world.avatar.distanceColumns = 0.5;
    system.update(world, STEP);
    system.update(world, STEP);
    expect(edges).toEqual(["hurt", "death", "restart"]);
    expect(sink.cues).toEqual(["hurt", "death"]);
  });
});

describe("strengthLift", () => {
  test("scales playback rate by the clamped strength and the authored multiplier", () => {
    expect(strengthLift(0, 1)).toBe(1);
    expect(strengthLift(0.5, 1)).toBe(1.5);
    expect(strengthLift(2, 0.25)).toBe(1.25);
    expect(strengthLift(-1, 2)).toBe(1);
    expect(strengthLift(1, 0)).toBe(1);
  });
});

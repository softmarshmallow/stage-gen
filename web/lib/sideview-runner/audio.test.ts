import { describe, expect, test } from "bun:test";
import { createAudioSystem, type RunnerAudioCue } from "./audio";
import { parseRunnerRuntimeManifest } from "./contract";
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

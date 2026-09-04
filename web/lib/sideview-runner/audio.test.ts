import { describe, expect, test } from "bun:test";
import { createAudioSystem, parseRunnerCuesBlock, strengthLift, type RunnerAudioCue } from "./audio";
import { parseRunnerRuntimeManifest, RUNNER_BLOCKS, type RunnerMusicEvent } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { createRunnerWorld, type RunnerWorld } from "./world";
import type { RunnerEvent } from "./vitals";
import type { GameSystem } from "@/lib/kernel/systems";

const STEP = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;
const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());

/** Records every cue but the announcement, which the edge tests are not about. */
function recorder(): { cues: RunnerAudioCue[]; play: (cue: RunnerAudioCue) => void } {
  const cues: RunnerAudioCue[] = [];
  return {
    cues,
    play: (cue) => {
      if (cue !== "stage_start") cues.push(cue);
    },
  };
}

function fullRecorder(): { cues: RunnerAudioCue[]; play: (cue: RunnerAudioCue) => void } {
  const cues: RunnerAudioCue[] = [];
  return { cues, play: (cue) => cues.push(cue) };
}

/**
 * One frame: the occurrences it carried, then the cue system hearing them.
 *
 * This is what "a pure consumer" buys the test. The system used to be driven by
 * mutating another system's slice and letting it notice — a jump was
 * `stepAvatar` and a hope that `jumpImpulses` had moved — so a test could only
 * assert a cue by reproducing the physics that caused it. Now a frame is its
 * occurrences, written down, and a cue is what the table makes of them.
 */
function frame(
  world: RunnerWorld,
  system: GameSystem<RunnerWorld>,
  events: readonly RunnerEvent[] = [],
): void {
  world.events.beginFrame();
  for (const event of events) world.events.emit(event);
  system.update(world, STEP);
}

describe("createAudioSystem", () => {
  test("a takeoff and the air jump are one occurrence with two names", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const system = createAudioSystem(sink);
    frame(world, system);
    expect(sink.cues).toEqual([]);

    frame(world, system, [{ type: "jumped", airJump: false }]);
    expect(sink.cues).toEqual(["takeoff"]);

    frame(world, system, [{ type: "jumped", airJump: true }]);
    expect(sink.cues).toEqual(["takeoff", "air_jump"]);

    // Nothing happened, so nothing is said; there is no level to re-read.
    frame(world, system);
    expect(sink.cues).toEqual(["takeoff", "air_jump"]);
  });

  test("the slide and the landing are the avatar's own verbs", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const system = createAudioSystem(sink);
    frame(world, system, [{ type: "slid" }, { type: "landed" }]);
    frame(world, system);
    // Table order, not emission order: the rules read top to bottom, and a
    // landing that starts a slide says "land" before "slide" however the two
    // occurrences reached the frame.
    expect(sink.cues).toEqual(["land", "slide"]);
  });

  test("a survivable hit cues on the frame the drain connects, and not once dead", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const system = createAudioSystem(sink);
    frame(world, system);
    frame(world, system, [{ type: "drained", source: "hazard", remaining: 2 }]);
    frame(world, system);
    expect(sink.cues).toEqual(["hurt"]);

    // A hit that ends the run is death's to answer, not the drain's: the phase
    // is already `dead` when this system runs, and the guard is a read of the
    // lifecycle rather than a shadow copy of it.
    world.run.phase = "dead";
    frame(world, system, [
      { type: "drained", source: "hazard", remaining: 0 },
      { type: "run-ended", source: "hazard" },
    ]);
    expect(sink.cues).toEqual(["hurt", "death"]);
  });

  test("a collect is graded by this frame's chain, and a dead run collects nothing", () => {
    const world = createRunnerWorld(manifest, 1);
    const cues: RunnerAudioCue[] = [];
    const strengths: number[] = [];
    const system = createAudioSystem({
      play: (cue, strength) => {
        cues.push(cue);
        strengths.push(strength);
      },
    });
    world.score.chain = 15;
    frame(world, system, [
      { type: "collected", key: "a" },
      { type: "collected", key: "b" },
    ]);
    expect(cues).toEqual(["stage_start", "collect", "collect"]);
    expect(strengths).toEqual([1, 0.5, 0.5]);
    world.run.phase = "dead";
    frame(world, system, [{ type: "collected", key: "c" }]);
    expect(cues).toEqual(["stage_start", "collect", "collect"]);
  });

  test("death cues once, because the end of a run happens once", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const system = createAudioSystem(sink);
    frame(world, system);
    world.run.phase = "dead";
    frame(world, system, [{ type: "run-ended", source: "pit" }]);
    frame(world, system);
    expect(sink.cues).toEqual(["death"]);
  });

  test("the family gates its own block, by name", () => {
    expect(parseRunnerCuesBlock(RUNNER_BLOCKS).published).toBe(true);
    expect(() => parseRunnerCuesBlock({ ...RUNNER_BLOCKS, audio: "runner-audio-block-v2" })).toThrow(
      'manifest block "audio" is published as runner-audio-block-v2',
    );
  });
});

describe("createAudioSystem announcement", () => {
  test("the stage start is announced on the first frame of a boot and never again", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = fullRecorder();
    const system = createAudioSystem(sink);
    frame(world, system);
    expect(sink.cues).toEqual(["stage_start"]);
    frame(world, system);
    expect(sink.cues).toEqual(["stage_start"]);

    // A restart is a new run and not a new boot: the composition's reset tells
    // this system, and what it posts is the resume rather than the announcement.
    system.reset?.(world, "run");
    frame(world, system);
    expect(sink.cues.filter((cue) => cue === "stage_start")).toEqual(["stage_start"]);
    // A whole new session is a new boot, and the stage is announced again.
    system.reset?.(world, "session");
    frame(world, system);
    expect(sink.cues.filter((cue) => cue === "stage_start")).toEqual([
      "stage_start",
      "stage_start",
    ]);
  });

  test("a package that binds no announcement still posts the cue, which the sink drops", () => {
    const document = runnerManifestFixture() as {
      audio: { bindings: Record<string, unknown>; effects: Array<{ effect_id: string }> };
    };
    document.audio.bindings.stage_start = null;
    document.audio.effects = document.audio.effects.filter(
      (effect) => effect.effect_id !== "mira_go",
    );
    const silent = parseRunnerRuntimeManifest(document);
    expect(silent.audio.bindings.stage_start).toBeNull();
    const world = createRunnerWorld(silent, 1);
    const sink = fullRecorder();
    createAudioSystem(sink).update(world, STEP);
    expect(sink.cues).toEqual(["stage_start"]);
  });
});

describe("createAudioSystem music sink", () => {
  test("death and hurt reach the music sink beside their cues", () => {
    const world = createRunnerWorld(manifest, 1);
    const sink = recorder();
    const edges: RunnerMusicEvent[] = [];
    const system = createAudioSystem(sink, { transition: (event) => edges.push(event) });
    frame(world, system);
    frame(world, system, [{ type: "drained", source: "hazard", remaining: 1 }]);
    world.run.phase = "dead";
    frame(world, system, [{ type: "run-ended", source: "hazard" }]);
    frame(world, system);
    expect(edges).toEqual(["hurt", "death"]);
    expect(sink.cues).toEqual(["hurt", "death"]);
  });

  test("the restart is the composition's, because the ask does not survive the reset", () => {
    // `run-restarted` is named in `resetOn`, so the queue throws both frames
    // away with the run they described and no consumer — deferred or not — can
    // hear it on the frame after. The reset hook is what says a run began.
    const world = createRunnerWorld(manifest, 1);
    const edges: RunnerMusicEvent[] = [];
    const system = createAudioSystem(recorder(), { transition: (event) => edges.push(event) });
    frame(world, system, [{ type: "run-restarted", seed: 7 }]);
    expect(edges).toEqual([]);
    system.reset?.(world, "run");
    frame(world, system);
    expect(edges).toEqual(["restart"]);
    // Once, on the first frame of the run and not on the second.
    frame(world, system);
    expect(edges).toEqual(["restart"]);
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

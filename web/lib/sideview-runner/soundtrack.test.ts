import { describe, expect, test } from "bun:test";
import type { RunnerMusicTransitions, RunnerSoundtrack } from "./contract";
import { createRunnerSoundtrackPlayback, fadeGain } from "./soundtrack";

const SOUNDTRACK: RunnerSoundtrack = {
  selection: "shuffle",
  tracks: [
    { trackId: "sunpetal_sprint", audio: "soundtrack/sunpetal_sprint.mp3" },
    { trackId: "orchard_rush", audio: "soundtrack/orchard_rush.mp3" },
  ],
};

class FakeAudio {
  volume = 0;
  playCalls = 0;
  pauseCalls = 0;
  allowPlayback: boolean;
  private ended?: () => void;

  constructor(
    readonly source: string,
    allowPlayback: boolean,
  ) {
    this.allowPlayback = allowPlayback;
  }

  play(): Promise<void> {
    this.playCalls += 1;
    return this.allowPlayback ? Promise.resolve() : Promise.reject(new Error("autoplay blocked"));
  }

  pause(): void {
    this.pauseCalls += 1;
  }

  addEventListener(_type: "ended", listener: () => void): void {
    this.ended = listener;
  }

  removeEventListener(_type: "ended", listener: () => void): void {
    if (this.ended === listener) this.ended = undefined;
  }

  finish(): void {
    this.ended?.();
  }
}

async function settlePlayback(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

describe("createRunnerSoundtrackPlayback", () => {
  test("attempts audible playback immediately when the browser permits it", async () => {
    const created: FakeAudio[] = [];
    const playback = createRunnerSoundtrackPlayback(SOUNDTRACK, (path) => `/runs/v5/${path}`, {
      createAudio: (source) => {
        const audio = new FakeAudio(source, true);
        created.push(audio);
        return audio;
      },
      random: () => 0.99,
    });

    expect(created).toHaveLength(1);
    expect(created[0].playCalls).toBe(1);
    expect(created[0].source).toBe("/runs/v5/soundtrack/sunpetal_sprint.mp3");
    expect(created[0].volume).toBe(0.34);
    await settlePlayback();
    playback.unlock();
    expect(created[0].playCalls).toBe(1);
  });

  test("retries a policy-blocked start on the first trusted gesture", async () => {
    const audio = new FakeAudio("soundtrack", false);
    const playback = createRunnerSoundtrackPlayback(SOUNDTRACK, (path) => path, {
      createAudio: () => audio,
      random: () => 0.99,
    });

    expect(audio.playCalls).toBe(1);
    await settlePlayback();
    audio.allowPlayback = true;
    playback.unlock();
    expect(audio.playCalls).toBe(2);
    await settlePlayback();
    playback.unlock();
    expect(audio.playCalls).toBe(2);
  });

  test("continues through the shuffled queue and disposes the active track", async () => {
    const created: FakeAudio[] = [];
    const playback = createRunnerSoundtrackPlayback(SOUNDTRACK, (path) => path, {
      createAudio: (source) => {
        const audio = new FakeAudio(source, true);
        created.push(audio);
        return audio;
      },
      random: () => 0.99,
    });

    await settlePlayback();
    created[0].finish();
    expect(created).toHaveLength(2);
    expect(created[1].source).toBe("soundtrack/orchard_rush.mp3");
    expect(created[1].playCalls).toBe(1);
    playback.dispose();
    expect(created[1].pauseCalls).toBe(1);
  });
});

/** A manual clock and frame queue: fades advance only when the test says so. */
function fakeFrames() {
  let time = 0;
  const pending: Array<() => void> = [];
  return {
    now: () => time,
    schedule: (callback: () => void) => {
      pending.push(callback);
      return () => {
        const at = pending.indexOf(callback);
        if (at >= 0) pending.splice(at, 1);
      };
    },
    /** Advance the clock and run one frame. */
    frame(milliseconds: number) {
      time += milliseconds;
      const due = pending.splice(0);
      for (const callback of due) callback();
    },
    pendingCount: () => pending.length,
  };
}

const STOP_PLAY: RunnerMusicTransitions = {
  death: { action: "stop", fadeSeconds: 1, curve: "linear" },
  restart: { action: "play", fadeSeconds: 0.5, curve: "linear" },
  hurt: { duckGain: 0.5, fadeSeconds: 0.1, holdSeconds: 0.2, recoverySeconds: 0.4, curve: "linear" },
};

const PAUSE_RESUME: RunnerMusicTransitions = {
  death: { action: "pause", fadeSeconds: 1, curve: "exponential" },
  restart: { action: "resume", fadeSeconds: 0, curve: "linear" },
  hurt: null,
};

function playbackWith(music: RunnerMusicTransitions) {
  const created: FakeAudio[] = [];
  const frames = fakeFrames();
  const playback = createRunnerSoundtrackPlayback(SOUNDTRACK, (path) => `/runs/v7/${path}`, {
    createAudio: (source) => {
      const audio = new FakeAudio(source, true);
      created.push(audio);
      return audio;
    },
    random: () => 0,
    volume: 0.4,
    music,
    schedule: frames.schedule,
    now: frames.now,
  });
  return { created, frames, playback };
}

describe("createRunnerSoundtrackPlayback transitions", () => {
  test("death stops the music through a monotonic linear fade and pauses once at silence", async () => {
    const { created, frames, playback } = playbackWith(STOP_PLAY);
    await settlePlayback();
    playback.transition("death");
    const levels = [created[0].volume];
    frames.frame(250);
    levels.push(created[0].volume);
    frames.frame(250);
    levels.push(created[0].volume);
    expect(created[0].pauseCalls).toBe(0);
    frames.frame(600);
    levels.push(created[0].volume);
    expect(levels[0]).toBe(0.4);
    expect(levels[1]).toBeCloseTo(0.3, 10);
    expect(levels[2]).toBeCloseTo(0.2, 10);
    expect(levels[3]).toBe(0);
    expect(created[0].pauseCalls).toBe(1);
    expect(frames.pendingCount()).toBe(0);
  });

  test("an exponential fade ends at exactly zero with the ramp floor stripped", async () => {
    const { created, frames, playback } = playbackWith(PAUSE_RESUME);
    await settlePlayback();
    playback.transition("death");
    frames.frame(500);
    const halfway = created[0].volume;
    expect(halfway).toBeGreaterThan(0);
    expect(halfway).toBeLessThan(0.2);
    expect(halfway).toBeCloseTo(fadeGain(0.4, 0, 0.5, "exponential"), 10);
    frames.frame(500);
    expect(created[0].volume).toBe(0);
    expect(created[0].pauseCalls).toBe(1);
  });

  test("play after stop starts the next track at silence and fades it in", async () => {
    const { created, frames, playback } = playbackWith(STOP_PLAY);
    await settlePlayback();
    playback.transition("death");
    frames.frame(1000);
    playback.transition("restart");
    expect(created).toHaveLength(2);
    expect(created[1].source).not.toBe(created[0].source);
    expect(created[1].volume).toBe(0);
    expect(created[1].playCalls).toBe(1);
    frames.frame(250);
    expect(created[1].volume).toBeCloseTo(0.2, 10);
    frames.frame(250);
    expect(created[1].volume).toBe(0.4);
  });

  test("resume after pause continues the same element and a zero fade applies at once", async () => {
    const { created, frames, playback } = playbackWith(PAUSE_RESUME);
    await settlePlayback();
    playback.transition("death");
    frames.frame(1000);
    expect(created[0].pauseCalls).toBe(1);
    playback.transition("restart");
    expect(created).toHaveLength(1);
    expect(created[0].playCalls).toBe(2);
    expect(created[0].volume).toBe(0.4);
    expect(frames.pendingCount()).toBe(0);
  });

  test("a restart during the death fade cancels it and the old element is silenced", async () => {
    const { created, frames, playback } = playbackWith(STOP_PLAY);
    await settlePlayback();
    playback.transition("death");
    frames.frame(300);
    playback.transition("restart");
    expect(created[0].pauseCalls).toBe(1);
    frames.frame(1000);
    expect(created[0].pauseCalls).toBe(1);
    expect(created[1].volume).toBe(0.4);
  });

  test("a hurt ducks the music, holds, and recovers; a duck while halted is ignored", async () => {
    const { created, frames, playback } = playbackWith(STOP_PLAY);
    await settlePlayback();
    playback.transition("hurt");
    frames.frame(100);
    expect(created[0].volume).toBeCloseTo(0.2, 10);
    frames.frame(100);
    expect(created[0].volume).toBeCloseTo(0.2, 10);
    frames.frame(100);
    expect(created[0].volume).toBeCloseTo(0.2, 10);
    frames.frame(200);
    expect(created[0].volume).toBeCloseTo(0.3, 10);
    frames.frame(200);
    expect(created[0].volume).toBe(0.4);
    expect(frames.pendingCount()).toBe(0);

    playback.transition("death");
    frames.frame(1000);
    playback.transition("hurt");
    expect(created[0].volume).toBe(0);
    expect(frames.pendingCount()).toBe(0);
  });

  test("continue leaves the element alone and unlock stays quiet while halted", async () => {
    const { created, frames, playback } = playbackWith({
      death: { action: "continue", fadeSeconds: 0, curve: "linear" },
      restart: { action: "continue", fadeSeconds: 0, curve: "linear" },
      hurt: null,
    });
    await settlePlayback();
    playback.transition("death");
    playback.transition("restart");
    expect(created[0].volume).toBe(0.4);
    expect(created[0].pauseCalls).toBe(0);
    expect(frames.pendingCount()).toBe(0);

    const halted = playbackWith(STOP_PLAY);
    await settlePlayback();
    halted.playback.transition("death");
    halted.frames.frame(1000);
    halted.playback.unlock();
    expect(halted.created[0].playCalls).toBe(1);
  });

  test("dispose cancels an in-flight fade", async () => {
    const { created, frames, playback } = playbackWith(STOP_PLAY);
    await settlePlayback();
    playback.transition("death");
    frames.frame(100);
    playback.dispose();
    expect(frames.pendingCount()).toBe(0);
    expect(created[0].pauseCalls).toBe(1);
  });
});

describe("fadeGain", () => {
  test("linear interpolates and exponential is geometric above the floor", () => {
    expect(fadeGain(0.4, 0, 0.5, "linear")).toBeCloseTo(0.2, 10);
    expect(fadeGain(0, 0.4, 0.25, "linear")).toBeCloseTo(0.1, 10);
    expect(fadeGain(0.4, 0, 0, "exponential")).toBeCloseTo(0.4, 10);
    expect(fadeGain(0.4, 0, 1, "exponential")).toBeCloseTo(0.0001, 10);
    expect(fadeGain(0.4, 0, 0.5, "exponential")).toBeCloseTo(Math.sqrt(0.4 * 0.0001), 10);
    expect(fadeGain(0.4, 0, 2, "linear")).toBe(0);
  });
});

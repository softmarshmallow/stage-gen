import { describe, expect, test } from "bun:test";
import type { RunnerSoundtrack } from "./contract";
import { createRunnerSoundtrackPlayback } from "./soundtrack";

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

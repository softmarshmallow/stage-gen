import { describe, expect, test } from "bun:test";
import { fadeGain } from "./fade";
import { ShuffleBag, ShuffleQueue } from "./selection";
import { poolKey, resolvePool, soundtrackCatalog } from "./track";
import { SoundtrackPlayer, type FadingTransport, type SoundtrackTrack } from "./player";

const CATALOG = soundtrackCatalog([
  { trackId: "village_theme", source: "audio/village.mp3" },
  { trackId: "road_theme", source: "audio/road.mp3" },
  { trackId: "road_theme_b", source: "audio/road_b.mp3" },
]);

/** A transport with a gain, a pause and a start that may be refused. */
function fakeFadingTransport(): FadingTransport & {
  readonly played: string[];
  readonly pauses: number;
  finish(): void;
  allow(value: boolean): void;
} {
  const played: string[] = [];
  let ended: (() => void) | undefined;
  let gain: number | null = null;
  let pauses = 0;
  let allowed = false;
  let permit = true;
  return {
    played,
    get pauses() {
      return pauses;
    },
    finish: () => ended?.(),
    allow: (value: boolean) => {
      permit = value;
    },
    play(track: SoundtrackTrack, onEnded: () => void, startGain?: number) {
      played.push(track.trackId);
      ended = onEnded;
      gain = startGain ?? 1;
      allowed = permit;
    },
    stop() {
      gain = null;
      ended = undefined;
    },
    pause() {
      pauses += 1;
    },
    resume() {
      allowed = permit;
    },
    gain: () => gain,
    setGain(value: number) {
      gain = value;
    },
    get allowed() {
      return allowed;
    },
  };
}

/** A manual clock and frame queue: fades advance only when the test says so. */
function fakeFrames() {
  let time = 0;
  const pending: Array<() => void> = [];
  return {
    now: () => time,
    schedule: (callback: () => void) => {
      pending.push(callback);
      return () => {
        const index = pending.indexOf(callback);
        if (index >= 0) pending.splice(index, 1);
      };
    },
    advance(ms: number) {
      time += ms;
      const due = pending.splice(0);
      for (const callback of due) callback();
    },
  };
}

describe("the catalog and its pools", () => {
  test("a pool is admitted in catalog order, however the place lists it", () => {
    expect(resolvePool(CATALOG, ["road_theme_b", "road_theme"]).map((t) => t.trackId)).toEqual([
      "road_theme",
      "road_theme_b",
    ]);
    expect(poolKey(resolvePool(CATALOG, ["road_theme", "road_theme_b"]))).toBe(
      poolKey(resolvePool(CATALOG, ["road_theme_b", "road_theme"])),
    );
  });

  test("an unknown, duplicate or empty pool is refused", () => {
    expect(() => resolvePool(CATALOG, ["nowhere"])).toThrow("names an unknown track_id");
    expect(() => resolvePool(CATALOG, ["road_theme", "road_theme"])).toThrow("must be unique");
    expect(() => resolvePool(CATALOG, [])).toThrow("requires at least one track_id");
  });
});

// --- E4: one family file, two genres, one half of it each --------------------------------------

describe("E4: the soundtrack family instantiated twice", () => {
  test("a placed soundtrack: a seeded bag, a gesture gate, and no transitions", () => {
    // Platformer-shaped. The transport has no gain at all — this genre never
    // fades anything — and the catalog is narrowed by where the player is.
    const played: string[] = [];
    let ended: (() => void) | undefined;
    const snapshots: string[] = [];
    const player = new SoundtrackPlayer({
      selector: new ShuffleBag(CATALOG, "package-digest", ["village_theme"]),
      transport: {
        play: (track, onEnded) => {
          played.push(track.trackId);
          ended = onEnded;
        },
        stop: () => played.push("<stop>"),
      },
      start: "gesture",
      onStateChange: (snapshot) => snapshots.push(snapshot.current_track_id ?? "<none>"),
    });
    // Nothing is touched before the gesture, which is the whole of the gate.
    expect(played).toEqual([]);
    expect(player.snapshot()).toEqual({
      started: false,
      current_track_id: null,
      next_track_id: "village_theme",
    });
    expect(player.beginFromPlayerGesture()).toBe(true);
    expect(played).toEqual(["village_theme"]);
    // The place changes and the destination does not admit what is playing, so
    // playback switches at once and the run stays deterministic.
    expect(player.bindPool(["road_theme", "road_theme_b"])).toBe(true);
    expect(played).toEqual(["village_theme", "road_theme_b"]);
    // Rebinding the same place is a no-op rather than a reshuffle.
    expect(player.bindPool(["road_theme_b", "road_theme"])).toBe(false);
    expect(player.next_track_id).toBe("road_theme");
    ended?.();
    expect(played).toEqual(["village_theme", "road_theme_b", "road_theme"]);
    player.stop();
    expect(player.snapshot()).toEqual({
      started: false,
      current_track_id: null,
      next_track_id: null,
    });
    expect(snapshots.at(-1)).toBe("<none>");
  });

  test("an edged soundtrack: a queue, an eager start, and a duck under a hit", () => {
    // Runner-shaped. No place binding exists to ask for — and asking is a
    // refusal rather than a silent no-op — but every run edge fades the music.
    const frames = fakeFrames();
    const transport = fakeFadingTransport();
    const player = new SoundtrackPlayer({
      selector: new ShuffleQueue(CATALOG, () => 0.99),
      transport,
      start: "eager",
      gain: 0.34,
      fades: { schedule: frames.schedule, now: frames.now },
    });
    expect(transport.played).toEqual(["village_theme"]);
    expect(transport.gain()).toBe(0.34);
    expect(() => player.bindPool(["village_theme"])).toThrow("no place binding");

    // A survivable hit ducks the music, holds it, and recovers.
    player.duck({
      duckGain: 0.5,
      fadeSeconds: 0.1,
      holdSeconds: 0.2,
      recoverySeconds: 0.1,
      curve: "linear",
    });
    frames.advance(100);
    expect(transport.gain()).toBeCloseTo(0.17, 6);
    frames.advance(200);
    expect(transport.gain()).toBeCloseTo(0.17, 6);
    frames.advance(100);
    expect(transport.gain()).toBeCloseTo(0.34, 6);

    // Death stops it through a fade and pauses once at silence; a duck while
    // halted is ignored, because there is nothing playing to dip.
    player.transition({ action: "stop", fadeSeconds: 0.5, curve: "linear" });
    frames.advance(500);
    expect(transport.gain()).toBe(0);
    expect(transport.pauses).toBe(1);
    player.duck({
      duckGain: 0.5,
      fadeSeconds: 0.1,
      holdSeconds: 0,
      recoverySeconds: 0.1,
      curve: "linear",
    });
    frames.advance(100);
    expect(transport.gain()).toBe(0);

    // And the restart takes the next track from silence back up.
    player.transition({ action: "play", fadeSeconds: 0.5, curve: "linear" });
    expect(transport.played).toEqual(["village_theme", "road_theme"]);
    expect(transport.gain()).toBe(0);
    frames.advance(500);
    expect(transport.gain()).toBe(0.34);
  });
});

describe("fadeGain", () => {
  test("linear interpolates and exponential is geometric above the floor", () => {
    expect(fadeGain(1, 0, 0.5, "linear")).toBeCloseTo(0.5, 9);
    expect(fadeGain(1, 0, 1, "exponential")).toBeCloseTo(0.0001, 9);
    expect(fadeGain(0.4, 0.1, 0, "exponential")).toBeCloseTo(0.4, 9);
  });
});

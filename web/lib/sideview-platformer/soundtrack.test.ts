import { describe, expect, test } from "bun:test";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import {
  DeterministicSoundtrackPlayer,
  parsePlatformerSoundtrackBlock,
  declaresMapScopedSoundtrack,
  parseSoundtrackForMapPool,
  parseSoundtrackManifest,
  type SoundtrackTrack,
  type SoundtrackTransport,
} from "./soundtrack";

const TRACKS = Object.freeze([
  Object.freeze({ track_id: "lantern_road", path: "music/lantern-road.mp3" }),
  Object.freeze({ track_id: "mossy_steps", path: "music/mossy-steps.mp3" }),
  Object.freeze({ track_id: "village_night", path: "music/village-night.mp3" }),
]);

const MANIFEST_TRACKS = Object.freeze(
  TRACKS.map((track, index) =>
    Object.freeze({
      ...track,
      display_name: track.track_id,
      provenance_path: `${track.path}.meta.json`,
      sha256: String(index + 1).repeat(64),
      bytes: 4096 + index,
      media_type: "audio/mpeg",
      generation_capability: "generate-music",
      rights_status: index === 0 ? "unreviewed" : "redistribution-approved",
      seamless_loop: true,
      target_duration_seconds: 90,
      duration_seconds: 89.5,
    }),
  ),
);

const SOURCE_SHA256 = "a".repeat(64);
const CANONICAL_SHA256 = "b".repeat(64);

const soundtrackManifest = (tracks: readonly unknown[] = MANIFEST_TRACKS) => ({
  schema_version: 7,
  soundtrack: {
    schema_version: 2,
    kind: "game-soundtrack-manifest-v2",
    game_id: "storybook-preview",
    revision: 2,
    source: {
      path: "library/games/storybook-preview/soundtrack.toml",
      provenance_path:
        "library/games/storybook-preview/soundtrack.toml.meta.json",
      source_sha256: SOURCE_SHA256,
      canonical_sha256: CANONICAL_SHA256,
    },
    playback: { selection: "shuffle", no_immediate_repeat: true },
    tracks,
  },
  map_book: {
    schema_version: 2,
    kind: "game-map-book-manifest-v2",
    game_id: "storybook-preview",
  },
});

function recordingTransport() {
  const played: string[] = [];
  let ended: (() => void) | null = null;
  let stopCount = 0;
  const transport: SoundtrackTransport = {
    play(track, onEnded) {
      played.push(track.track_id);
      ended = onEnded;
    },
    stop() {
      stopCount += 1;
      ended = null;
    },
  };
  return {
    transport,
    played,
    endCurrent() {
      const callback = ended;
      ended = null;
      callback?.();
    },
    stopCount: () => stopCount,
  };
}

function playSequence(seed: string, count: number): string[] {
  const recording = recordingTransport();
  const player = new DeterministicSoundtrackPlayer({
    tracks: TRACKS,
    seed,
    transport: recording.transport,
  });
  player.beginFromPlayerGesture();
  while (recording.played.length < count) recording.endCurrent();
  return recording.played;
}

describe("soundtrack manifest", () => {
  test("reads only the current public lower_snake_case map-aware projection", () => {
    const parsed = parseSoundtrackManifest(soundtrackManifest());
    expect(parsed).toEqual({
      playback: { selection: "shuffle", no_immediate_repeat: true },
      tracks: TRACKS,
      map_scoped: true,
    });
    expect(Object.isFrozen(parsed)).toBeTrue();
    expect(Object.isFrozen(parsed?.tracks)).toBeTrue();
  });

  test("distinguishes true absence from a malformed declaration", () => {
    expect(parseSoundtrackManifest({ schema_version: 7 })).toBeNull();
    expect(() => parseSoundtrackManifest({ schema_version: 6 })).toThrow(
      "manifest schema_version must be 7",
    );
    expect(() => parseSoundtrackManifest({})).toThrow(
      "manifest schema_version must be 7",
    );
    expect(
      parseSoundtrackManifest({
        schema_version: 7,
        music: { path: "music/obsolete.mp3" },
      }),
    ).toBeNull();
    expect(declaresMapScopedSoundtrack({ schema_version: 7 })).toBeFalse();
    expect(
      declaresMapScopedSoundtrack({ schema_version: 7, soundtrack: null }),
    ).toBeTrue();
    for (const malformed of [null, undefined, [], "soundtrack"]) {
      expect(() =>
        parseSoundtrackManifest({ schema_version: 7, soundtrack: malformed }),
      ).toThrow("invalid declared soundtrack");
    }
    expect(() => parseSoundtrackManifest(null)).toThrow(
      "manifest must be a JSON object",
    );
  });

  test("requires parent v7, soundtrack v2, and the matching public map-book v2", () => {
    const wrongParent = soundtrackManifest();
    wrongParent.schema_version = 6;
    expect(() => parseSoundtrackManifest(wrongParent)).toThrow(
      "parent manifest schema_version must be 7",
    );

    const wrongSoundtrack = soundtrackManifest();
    wrongSoundtrack.soundtrack.schema_version = 1;
    wrongSoundtrack.soundtrack.kind = "game-soundtrack-manifest-v1";
    expect(() => parseSoundtrackManifest(wrongSoundtrack)).toThrow(
      "identity is invalid",
    );

    const missingMapBook = soundtrackManifest();
    const { map_book: _mapBook, ...withoutMapBook } = missingMapBook;
    expect(() => parseSoundtrackManifest(withoutMapBook)).toThrow(
      "game-map-book-manifest-v2",
    );

    const wrongMapBook = soundtrackManifest();
    wrongMapBook.map_book.schema_version = 1;
    wrongMapBook.map_book.kind = "game-map-book-manifest-v1";
    expect(() => parseSoundtrackManifest(wrongMapBook)).toThrow(
      "game-map-book-manifest-v2",
    );

    const mismatchedGame = soundtrackManifest();
    mismatchedGame.map_book.game_id = "another-game";
    expect(() => parseSoundtrackManifest(mismatchedGame)).toThrow(
      "game-map-book-manifest-v2",
    );
  });

  test("composes map-aware declaration and opening-pool requirements", () => {
    const valid = soundtrackManifest();
    expect(
      parseSoundtrackForMapPool(valid, ["lantern_road", "mossy_steps"]),
    ).toMatchObject({ map_scoped: true });
    expect(() => parseSoundtrackForMapPool(valid)).toThrow("opening map pool");
    expect(() =>
      parseSoundtrackForMapPool({ schema_version: 7 }, ["lantern_road"]),
    ).toThrow("requires a valid map-aware soundtrack");
    expect(parseSoundtrackForMapPool({ schema_version: 7 })).toBeNull();
  });

  test("rejects malformed selection, strict keys, duplicates, and unsafe paths", () => {
    const manifest = (
      tracks: readonly unknown[] = MANIFEST_TRACKS,
      playback: unknown = {
        selection: "shuffle",
        no_immediate_repeat: true,
      },
    ) => {
      const value = soundtrackManifest(tracks);
      return {
        ...value,
        soundtrack: { ...value.soundtrack, playback },
      };
    };

    expect(() =>
      parseSoundtrackManifest(
        manifest(MANIFEST_TRACKS, {
          selection: "ordered",
          no_immediate_repeat: true,
        }),
      ),
    ).toThrow("playback policy is invalid");
    expect(() =>
      parseSoundtrackManifest(
        manifest([
          { ...MANIFEST_TRACKS[0], track_id: "CamelCase" },
          MANIFEST_TRACKS[1],
        ]),
      ),
    ).toThrow("track entry is invalid");
    expect(() =>
      parseSoundtrackManifest(
        manifest([
          { ...MANIFEST_TRACKS[0], track_id: "one" },
          { ...MANIFEST_TRACKS[1], track_id: "one" },
        ]),
      ),
    ).toThrow("track entry is invalid");
    expect(() =>
      parseSoundtrackManifest(
        manifest([
          { ...MANIFEST_TRACKS[0], approved: true },
          MANIFEST_TRACKS[1],
        ]),
      ),
    ).toThrow("track keys are invalid");
    for (const path of [
      "../secret.mp3",
      "/absolute.mp3",
      "a\\b.mp3",
      "a/%2e%2e/b.mp3",
      "C:/music.mp3",
      " https://example.test/music.mp3",
    ]) {
      expect(() =>
        parseSoundtrackManifest(
          manifest([{ ...MANIFEST_TRACKS[0], path }, MANIFEST_TRACKS[1]]),
        ),
      ).toThrow("track entry is invalid");
    }
    for (const [field, value] of [
      ["provenance_path", undefined],
      ["sha256", "abc"],
      ["bytes", 0],
      ["media_type", "audio/wav"],
      ["generation_capability", "download"],
      ["rights_status", "restricted"],
      ["seamless_loop", "yes"],
      ["target_duration_seconds", 14],
      ["duration_seconds", Number.NaN],
    ] as const) {
      expect(() =>
        parseSoundtrackManifest(
          manifest([
            { ...MANIFEST_TRACKS[0], [field]: value },
            MANIFEST_TRACKS[1],
          ]),
        ),
      ).toThrow("track entry is invalid");
    }
  });
});

describe("deterministic soundtrack player", () => {
  test("does not touch playback before the player gesture", () => {
    const recording = recordingTransport();
    const states: unknown[] = [];
    const player = new DeterministicSoundtrackPlayer({
      tracks: TRACKS,
      seed: "run-17",
      transport: recording.transport,
      onStateChange: (state) => states.push(state),
    });

    expect(recording.played).toEqual([]);
    expect(player.current_track_id).toBeNull();
    const plannedTrack = player.next_track_id;
    expect(plannedTrack).not.toBeNull();
    if (plannedTrack === null) throw new Error("player did not plan its first track");
    expect(player.snapshot()).toEqual({
      started: false,
      current_track_id: null,
      next_track_id: player.next_track_id,
    });
    expect(states).toEqual([]);

    expect(player.beginFromPlayerGesture()).toBeTrue();
    expect(recording.played).toEqual([plannedTrack]);
    expect(player.beginFromPlayerGesture()).toBeFalse();
    expect(recording.played).toHaveLength(1);
  });

  test("is deterministic and exhausts each bag without adjacent repeats", () => {
    const first = playSequence("same-run", 12);
    const second = playSequence("same-run", 12);
    expect(second).toEqual(first);
    for (let offset = 0; offset < first.length; offset += TRACKS.length) {
      expect(new Set(first.slice(offset, offset + TRACKS.length))).toEqual(
        new Set(TRACKS.map((track) => track.track_id)),
      );
    }
    for (let index = 1; index < first.length; index += 1) {
      expect(first[index]).not.toBe(first[index - 1]);
    }
  });

  test("exposes current and next identity at every transition", () => {
    const recording = recordingTransport();
    const states: {
      current_track_id: string | null;
      next_track_id: string | null;
    }[] = [];
    const player = new DeterministicSoundtrackPlayer({
      tracks: TRACKS,
      seed: "probe-run",
      transport: recording.transport,
      onStateChange: ({ current_track_id, next_track_id }) =>
        states.push({ current_track_id, next_track_id }),
    });

    const plannedFirst = player.next_track_id;
    player.beginFromPlayerGesture();
    expect(player.current_track_id).toBe(plannedFirst);
    expect(player.next_track_id).not.toBeNull();
    expect(player.next_track_id).not.toBe(player.current_track_id);
    recording.endCurrent();
    expect(states).toHaveLength(2);
    expect(states[1]?.current_track_id).toBe(states[0]?.next_track_id);
  });

  test("narrows the planned first track before the player gesture", () => {
    const recording = recordingTransport();
    const player = new DeterministicSoundtrackPlayer({
      tracks: TRACKS,
      trackIds: ["lantern_road", "mossy_steps"],
      seed: "map-entry",
      transport: recording.transport,
    });

    const initialPlan = player.next_track_id;
    if (initialPlan === null) throw new Error("initial map pool is empty");
    expect(["lantern_road", "mossy_steps"]).toContain(initialPlan);
    expect(
      player.setTrackPool(["mossy_steps", "village_night"]),
    ).toBeTrue();
    expect(recording.played).toEqual([]);
    const destinationPlan = player.next_track_id;
    if (destinationPlan === null) throw new Error("destination map pool is empty");
    expect(["mossy_steps", "village_night"]).toContain(destinationPlan);
    const planned = player.next_track_id;
    if (planned === null) throw new Error("destination track was not planned");
    player.beginFromPlayerGesture();
    expect(recording.played).toEqual([planned]);
  });

  test("keeps an allowed current track and replans within the destination pool", () => {
    const recording = recordingTransport();
    const player = new DeterministicSoundtrackPlayer({
      tracks: TRACKS,
      seed: "allowed-transition",
      transport: recording.transport,
    });
    player.beginFromPlayerGesture();
    const current = player.current_track_id;
    if (current === null) throw new Error("player did not start a track");
    const companion = TRACKS.find((track) => track.track_id !== current);
    if (!companion) throw new Error("test catalog needs another track");

    expect(player.setTrackPool([current, companion.track_id])).toBeTrue();
    expect(recording.played).toEqual([current]);
    expect(player.current_track_id).toBe(current);
    expect(player.next_track_id).toBe(companion.track_id);
    // Pool identity is set-like and an idempotent update does not reshuffle.
    expect(player.setTrackPool([companion.track_id, current])).toBeFalse();
    expect(player.next_track_id).toBe(companion.track_id);
  });

  test("counts a retained track as consumed in the destination's first bag", () => {
    const recording = recordingTransport();
    const player = new DeterministicSoundtrackPlayer({
      tracks: TRACKS,
      trackIds: ["lantern_road"],
      seed: "retained-transition",
      transport: recording.transport,
    });
    player.beginFromPlayerGesture();
    expect(recording.played).toEqual(["lantern_road"]);

    player.setTrackPool(TRACKS.map((track) => track.track_id));
    recording.endCurrent();
    recording.endCurrent();
    expect(new Set(recording.played.slice(0, 3))).toEqual(
      new Set(["lantern_road", "mossy_steps", "village_night"]),
    );
    expect(recording.played.slice(1, 3)).not.toContain("lantern_road");
  });

  test("switches immediately when the destination excludes the current track", () => {
    const callbacks: Array<() => void> = [];
    const played: string[] = [];
    const player = new DeterministicSoundtrackPlayer({
      tracks: TRACKS,
      seed: "excluded-transition",
      transport: {
        play(track, onEnded) {
          played.push(track.track_id);
          callbacks.push(onEnded);
        },
        stop() {},
      },
    });
    player.beginFromPlayerGesture();
    const departed = player.current_track_id;
    if (departed === null) throw new Error("player did not start a track");
    const destination: string[] = TRACKS.filter(
      (track) => track.track_id !== departed,
    ).map((track) => track.track_id);

    expect(player.setTrackPool(destination)).toBeTrue();
    expect(played).toHaveLength(2);
    const current = player.current_track_id;
    const next = player.next_track_id;
    if (current === null || next === null) {
      throw new Error("destination pool did not plan current and next tracks");
    }
    expect(destination).toContain(current);
    expect(current).not.toBe(departed);
    expect(destination).toContain(next);
    // The ended callback from the replaced media cannot advance the new bag.
    callbacks[0]?.();
    expect(played).toHaveLength(2);
  });

  test("rejects empty, duplicate, and unknown map pools", () => {
    const player = new DeterministicSoundtrackPlayer({
      tracks: TRACKS,
      seed: "invalid-pool",
      transport: recordingTransport().transport,
    });
    expect(() => player.setTrackPool([])).toThrow("at least one");
    expect(() =>
      player.setTrackPool(["lantern_road", "lantern_road"]),
    ).toThrow("unique");
    expect(() => player.setTrackPool(["missing_track"])).toThrow("unknown");
  });

  test("plays a one-track catalog once instead of violating no-repeat", () => {
    const recording = recordingTransport();
    const only: readonly SoundtrackTrack[] = [
      { track_id: "only_track", path: "only.mp3" },
    ];
    const player = new DeterministicSoundtrackPlayer({
      tracks: only,
      seed: "single",
      transport: recording.transport,
    });
    player.beginFromPlayerGesture();
    expect(player.snapshot()).toEqual({
      started: true,
      current_track_id: "only_track",
      next_track_id: null,
    });
    recording.endCurrent();
    expect(recording.played).toEqual(["only_track"]);
    expect(player.current_track_id).toBeNull();
    expect(player.next_track_id).toBeNull();
  });

  test("stops the transport and ignores a stale ended callback", () => {
    const callbacks: { ended?: () => void } = {};
    const played: string[] = [];
    const player = new DeterministicSoundtrackPlayer({
      tracks: TRACKS,
      seed: "shutdown",
      transport: {
        play(track, onEnded) {
          played.push(track.track_id);
          callbacks.ended = onEnded;
        },
        stop() {},
      },
    });
    player.beginFromPlayerGesture();
    player.stop();
    callbacks.ended?.();
    expect(played).toHaveLength(1);
    expect(player.snapshot()).toEqual({
      started: false,
      current_track_id: null,
      next_track_id: null,
    });
  });
});

// --- The `soundtrack` family, sealed into this genre -------------------------------------------

describe("the soundtrack family in the platformer", () => {
  test("E7 subtraction: a package that publishes no soundtrack has none, which is an answer", () => {
    // The soundtrack is not a frame step in either genre — it is a host object
    // the scene builds when the package has tracks — so "quiet" is a package
    // with no catalog. That is not a refusal: `parseSoundtrackManifest` answers
    // null, the scene builds no player, and the run is silent.
    const manifest = { schema_version: 7 } as const;
    expect(parseSoundtrackManifest(manifest)).toBeNull();
    expect(parseSoundtrackForMapPool(manifest, undefined)).toBeNull();
    expect(declaresMapScopedSoundtrack(manifest)).toBe(false);
  });

  test("the transitions half is the other genre's, and this one authors none", () => {
    // The family carries both halves; the parameter this genre sets is the
    // transport, which has no gain, so nothing here can fade. A run edge that
    // wanted one would author `[music]` first — which is a contract bump.
    const recording = recordingTransport();
    const player = new DeterministicSoundtrackPlayer({
      tracks: TRACKS,
      seed: "no-transitions",
      transport: recording.transport,
    });
    player.beginFromPlayerGesture();
    expect(Object.hasOwn(recording.transport, "gain")).toBe(false);
    expect(player.current_track_id).not.toBeNull();
  });

  test("the family gates its own block, by name", () => {
    expect(parsePlatformerSoundtrackBlock(PREPARED_RUNTIME_BLOCKS).published).toBe(true);
    expect(() =>
      parsePlatformerSoundtrackBlock({
        ...PREPARED_RUNTIME_BLOCKS,
        soundtrack: "platformer-soundtrack-block-v2",
      }),
    ).toThrow('manifest block "soundtrack" is published as platformer-soundtrack-block-v2');
  });
});

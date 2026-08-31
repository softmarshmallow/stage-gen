import { describe, expect, test } from "bun:test";

import { ScenarioAudio, trackTransition, type SceneAudioTransport } from "./scene-audio";
import type { DialogueSceneFixture } from "./schema";

function recorder(): SceneAudioTransport & { readonly log: string[] } {
  const log: string[] = [];
  return {
    log,
    play(trackId) {
      log.push(`play:${trackId}`);
    },
    stop(trackId) {
      log.push(`stop:${trackId}`);
    },
  };
}

/** Only the tracks matter here; the rest of the fixture is not consulted. */
function fixture(trackIds: readonly string[]): DialogueSceneFixture {
  return {
    tracks: trackIds.map((trackId) => ({
      trackId,
      id: trackId.replace(/_/g, "-"),
      src: `/api/assets/run/assets/track-${trackId.replace(/_/g, "-")}.mp3`,
    })),
  } as unknown as DialogueSceneFixture;
}

describe("the transition between two moments", () => {
  test("a track playing before and after is not restarted", () => {
    // A restart is audible, and the script never asked for one.
    expect(trackTransition(["a", "b"], ["b", "a"])).toEqual({ start: [], stop: [] });
  });

  test("it names what to start and what to stop", () => {
    expect(trackTransition(["summer_room"], ["dusk_signal"])).toEqual({
      start: ["dusk_signal"],
      stop: ["summer_room"],
    });
  });

  test("silence in and out of it", () => {
    expect(trackTransition([], ["x"])).toEqual({ start: ["x"], stop: [] });
    expect(trackTransition(["x"], [])).toEqual({ start: [], stop: ["x"] });
    expect(trackTransition([], [])).toEqual({ start: [], stop: [] });
  });
});

describe("the player", () => {
  test("nothing is heard before a gesture, and the pending track starts on unlock", () => {
    // Browsers refuse audio before a user gesture, so the opening `play` has to
    // survive as an intention until the player's first click.
    const transport = recorder();
    const audio = new ScenarioAudio(fixture(["summer_room"]), transport);
    audio.apply(["summer_room"]);
    expect(transport.log).toEqual([]);
    audio.unlock();
    expect(transport.log).toEqual(["play:summer_room"]);
  });

  test("unlocking twice does not double up", () => {
    const transport = recorder();
    const audio = new ScenarioAudio(fixture(["summer_room"]), transport);
    audio.apply(["summer_room"]);
    audio.unlock();
    audio.unlock();
    expect(transport.log).toEqual(["play:summer_room"]);
  });

  test("a stage change swaps one track for another, stopping before starting", () => {
    const transport = recorder();
    const audio = new ScenarioAudio(fixture(["summer_room", "dusk_signal"]), transport);
    audio.unlock();
    audio.apply(["summer_room"]);
    audio.apply(["dusk_signal"]);
    expect(transport.log).toEqual(["play:summer_room", "stop:summer_room", "play:dusk_signal"]);
  });

  test("re-applying the same moment is silent", () => {
    const transport = recorder();
    const audio = new ScenarioAudio(fixture(["summer_room"]), transport);
    audio.unlock();
    audio.apply(["summer_room"]);
    audio.apply(["summer_room"]);
    expect(transport.log).toEqual(["play:summer_room"]);
  });

  test("a track with no audio is skipped rather than thrown mid-scene", () => {
    // The fixture validator already refuses this package; belt and braces.
    const transport = recorder();
    const audio = new ScenarioAudio(fixture([]), transport);
    audio.unlock();
    audio.apply(["nobody_generated_this"]);
    expect(transport.log).toEqual([]);
  });

  test("leaving the scene stops everything the script left running", () => {
    const transport = recorder();
    const audio = new ScenarioAudio(fixture(["a", "b"]), transport);
    audio.unlock();
    audio.apply(["a", "b"]);
    audio.stopAll();
    expect(transport.log).toEqual(["play:a", "play:b", "stop:a", "stop:b"]);
    // And a later apply does not resurrect them.
    audio.apply([]);
    expect(transport.log).toEqual(["play:a", "play:b", "stop:a", "stop:b"]);
  });
});

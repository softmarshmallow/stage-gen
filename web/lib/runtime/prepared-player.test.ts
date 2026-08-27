import { describe, expect, test } from "bun:test";
import type { MotionBinding } from "./prepared-manifest";
import { playerSheetScaleForState } from "./sprite-scale";
import {
  PREPARED_PLAYER_PRESERVE_SOURCE_SCALE_STATES,
  preparedPlayerMotionPlayback,
  preparedPlayerStateAdapter,
} from "./prepared-player";

const ASSET = Object.freeze({
  path: "content/players/wayfarer/states/crouch.png",
  sha256: "a".repeat(64),
  bytes: 1,
  media_type: "image/png",
});

function crouchBinding(): MotionBinding {
  return Object.freeze({
    source_facing: "right",
    runtime_mirror: true,
    columns: 4,
    rows: 1,
    source_frame_count: 4,
    playback: Object.freeze({
      mode: "loop",
      canonical_frame_indices: Object.freeze([0, 1, 2, 3]),
      frames_per_second: 6,
    }),
    asset: ASSET,
  });
}

describe("prepared player adapter", () => {
  test("keeps crouch as public vocabulary while targeting the mature texture role", () => {
    expect(preparedPlayerStateAdapter("crouch")).toEqual({
      runtime_state: "crouch",
      texture_key: "character_crawl",
    });
  });

  test("projects authored crouch playback without changing its frame policy", () => {
    expect(preparedPlayerMotionPlayback({ crouch: crouchBinding() })).toEqual({
      crouch: {
        mode: "loop",
        canonical_frame_indices: [0, 1, 2, 3],
        frames_per_second: 6,
      },
    });
  });

  test("ignores producer-only states that the mature controller does not consume", () => {
    expect(
      preparedPlayerMotionPlayback({ celebration: crouchBinding() }),
    ).toEqual({});
  });

  test("preserves crouch atlas scale instead of enlarging its compressed pose", () => {
    const shared = {
      masterSheetScale: 0.2,
      measuredSheetScale: 0.32,
      preserveSourceScaleStates:
        PREPARED_PLAYER_PRESERVE_SOURCE_SCALE_STATES,
    } as const;
    expect(playerSheetScaleForState({ ...shared, state: "crouch" })).toBe(0.2);
    expect(playerSheetScaleForState({ ...shared, state: "walk" })).toBe(0.32);
  });
});

import { describe, expect, test } from "bun:test";
import type { MotionBinding } from "@/lib/manifest/prepared-manifest";
import { playerSheetScaleForState } from "@/lib/sideview/sprite-scale";
import {
  PREPARED_PLAYER_PRESERVE_SOURCE_SCALE_STATES,
  preparedPlayerClimbArtwork,
  preparedPlayerMotionPlayback,
  preparedPlayerStateAdapter,
  parsePlatformerMotionBlocks,
  PREPARED_PLAYER_MOTIONS,
  PREPARED_PLAYER_STATE_ADAPTERS,
  resolvePreparedPlayerMotions,
} from "./prepared-player";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";

const ASSET = Object.freeze({
  path: "content/players/wayfarer/states/crouch.png",
  sha256: "a".repeat(64),
  bytes: 1,
  media_type: "image/png",
  role: "asset" as const,
});

function crouchBinding(): MotionBinding {
  return Object.freeze({
    source_facing: "right",
    runtime_mirror: true,
    columns: 4,
    rows: 1,
    source_frame_count: 4,
    anchor: "bottom",
    playback: Object.freeze({
      mode: "loop",
      canonical_frame_indices: Object.freeze([0, 1, 2, 3]),
      frames_per_second: 6,
    }),
    asset: ASSET,
  });
}

function climbBinding(state: string): MotionBinding {
  return Object.freeze({
    source_facing: "back",
    runtime_mirror: false,
    columns: 2,
    rows: 1,
    source_frame_count: 2,
    anchor: "top",
    playback: Object.freeze({
      mode: "gameplay_driven",
      canonical_frame_indices: Object.freeze([0, 1]),
    }),
    asset: Object.freeze({ ...ASSET, path: `content/players/wayfarer/states/${state}.png` }),
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

  test("selects a distinct climb strip per climbable role", () => {
    const states = {
      climb_ladder: climbBinding("climb_ladder"),
      climb_rope: climbBinding("climb_rope"),
    };
    expect(preparedPlayerClimbArtwork(states)).toEqual({
      ladder: {
        textureKey: "character_climb_ladder",
        animKey: "player_climb_ladder",
        playback: { mode: "gameplay_driven", canonical_frame_indices: [0, 1] },
        anchor: "top",
      },
      rope: {
        textureKey: "character_climb_rope",
        animKey: "player_climb_rope",
        playback: { mode: "gameplay_driven", canonical_frame_indices: [0, 1] },
        anchor: "top",
      },
    });
  });

  test("resolves only the climbable roles a package actually publishes", () => {
    expect(
      Object.keys(preparedPlayerClimbArtwork({ climb_ladder: climbBinding("climb_ladder") })),
    ).toEqual(["ladder"]);
  });

  test("keeps both climb states out of the state-keyed playback record", () => {
    // Both adapt to the single controller state `climb`, so a state-keyed record cannot carry
    // them both without one silently overwriting the other.
    expect(
      preparedPlayerMotionPlayback({
        climb_ladder: climbBinding("climb_ladder"),
        climb_rope: climbBinding("climb_rope"),
        crouch: crouchBinding(),
      }),
    ).toEqual({
      crouch: {
        mode: "loop",
        canonical_frame_indices: [0, 1, 2, 3],
        frames_per_second: 6,
      },
    });
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

describe("the platformer's motion vocabulary is the family's, closed", () => {
  test("the adapter table is the vocabulary, and idle is the one owed state", () => {
    expect([...PREPARED_PLAYER_MOTIONS.states]).toEqual(
      Object.keys(PREPARED_PLAYER_STATE_ADAPTERS),
    );
    expect([...PREPARED_PLAYER_MOTIONS.required]).toEqual(["idle"]);
  });

  test("the new refusal: a pose nothing draws, and a missing idle", () => {
    const states = { idle: crouchBinding(), crouch: crouchBinding() };
    expect([...resolvePreparedPlayerMotions(states)]).toEqual(["idle", "crouch"]);
    // Before this family a published pose the controller does not draw was
    // *skipped*, silently, in two places. It is refused by name now.
    expect(() =>
      resolvePreparedPlayerMotions({ ...states, wobble: crouchBinding() }),
    ).toThrow("player.states declares unknown motion state wobble");
    // And the one state the controller draws before any rule has run.
    expect(() => resolvePreparedPlayerMotions({ crouch: crouchBinding() })).toThrow(
      "player.states is missing the idle state",
    );
  });

  test("the motion blocks are gated by the family, by name, and there are two", () => {
    expect(parsePlatformerMotionBlocks(PREPARED_RUNTIME_BLOCKS).map((view) => view.block)).toEqual([
      "player",
      "mobs",
    ]);
    expect(() =>
      parsePlatformerMotionBlocks({
        ...PREPARED_RUNTIME_BLOCKS,
        mobs: "platformer-mobs-block-v2",
      }),
    ).toThrow('manifest block "mobs" is published as platformer-mobs-block-v2');
  });
});

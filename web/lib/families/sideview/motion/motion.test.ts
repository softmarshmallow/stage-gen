import { describe, expect, test } from "bun:test";

import {
  mirrorFor,
  motionNeedsRestart,
  resolveMotionSet,
  sealMotionVocabulary,
  selectMotion,
} from "./index";

// E4 for `sideview/motion`: one vocabulary machine, three closed sets that
// share no member and disagree about how many of them are owed.
//
// The runner's avatar has six states, three owed outright and three owed on
// conditions the genre evaluates. The platformer's player has ten and owes one.
// And the jumper the plan's own table describes — which does not exist yet —
// has three, `{rise, fall, death}`, all owed. If the vocabulary were anything
// but a parameter the third of those could not be written at all, so it is
// written here, with no jumper in the tree, exactly as the intent family's
// held-axis test was.

const RUNNER_AVATAR = sealMotionVocabulary({
  states: ["run", "jump", "slide", "fly", "hurt", "death"],
  required: ["run", "jump", "death"],
  looping: ["run", "fly"],
});

const PLATFORMER_PLAYER = sealMotionVocabulary({
  states: [
    "idle",
    "walk",
    "run",
    "jump",
    "crouch",
    "climb_ladder",
    "climb_rope",
    "basic_attack",
    "skill_cast",
    "hurt",
    "death",
  ],
  required: ["idle"],
});

/** The plan's jumper: a held axis, two arcs and an end. No jumper exists. */
const JUMPER = sealMotionVocabulary({
  states: ["rise", "fall", "death"],
  required: ["rise", "fall", "death"],
  looping: ["rise", "fall"],
});

describe("the vocabulary is a parameter", () => {
  test("three closed sets, and the family knows nothing about any of them", () => {
    expect(RUNNER_AVATAR.states.length).toBe(6);
    expect(PLATFORMER_PLAYER.states.length).toBe(11);
    expect(JUMPER.states.length).toBe(3);
    // The one member all three share is `death`, and even that is only owed by
    // two of them.
    expect(RUNNER_AVATAR.isRequired("death")).toBe(true);
    expect(JUMPER.isRequired("death")).toBe(true);
    expect(PLATFORMER_PLAYER.isRequired("death")).toBe(false);
    expect(RUNNER_AVATAR.isLooping("run")).toBe(true);
    expect(JUMPER.isLooping("rise")).toBe(true);
    expect(PLATFORMER_PLAYER.isLooping("run")).toBe(false);
  });

  test("a vocabulary that contradicts itself is refused before any package is", () => {
    expect(() => sealMotionVocabulary({ states: [], required: [] })).toThrow(
      "at least one state",
    );
    expect(() => sealMotionVocabulary({ states: ["run", "run"], required: [] })).toThrow(
      "must not name a state twice",
    );
    expect(() => sealMotionVocabulary({ states: ["run"], required: ["fly"] })).toThrow(
      "requires fly, which it does not contain",
    );
    expect(() =>
      sealMotionVocabulary({ states: ["run"], required: [], looping: ["fly"] }),
    ).toThrow("loops fly, which it does not contain");
  });
});

describe("the refusal a package gets", () => {
  test("a missing required state is refused at parse, by name", () => {
    expect(() =>
      resolveMotionSet(["run", "jump"], RUNNER_AVATAR, { label: "avatar.motions" }),
    ).toThrow("avatar.motions is missing the death state");
    expect(() =>
      resolveMotionSet(["walk", "run"], PLATFORMER_PLAYER, { label: "player.states" }),
    ).toThrow("player.states is missing the idle state");
  });

  test("a conditional requirement is the genre's to evaluate, not the family's", () => {
    // A duck profile owes a slide; nothing about the family knows what a duck
    // profile is, and it does not have to.
    expect(() =>
      resolveMotionSet(["run", "jump", "death"], RUNNER_AVATAR, {
        label: "avatar.motions",
        extraRequired: ["slide"],
      }),
    ).toThrow("avatar.motions is missing the slide state");
    expect(
      resolveMotionSet(["run", "jump", "death", "slide"], RUNNER_AVATAR, {
        label: "avatar.motions",
        extraRequired: ["slide"],
      }),
    ).toEqual(["run", "jump", "slide", "death"]);
  });

  test("a state outside the vocabulary is refused rather than silently skipped", () => {
    expect(() =>
      resolveMotionSet(["idle", "wobble"], PLATFORMER_PLAYER, { label: "player.states" }),
    ).toThrow("player.states declares unknown motion state wobble");
    expect(() =>
      resolveMotionSet(["idle", "idle"], PLATFORMER_PLAYER, { label: "player.states" }),
    ).toThrow("player.states declares the idle motion twice");
  });

  test("the resolved set comes back in the vocabulary's order, not the package's", () => {
    expect(resolveMotionSet(["death", "run", "jump"], RUNNER_AVATAR, { label: "x" })).toEqual([
      "run",
      "jump",
      "death",
    ]);
  });
});

describe("availability chooses a presentation and never a rule", () => {
  const has = (...states: readonly string[]) => (state: string) => states.includes(state);

  test("a chosen state is drawn when it shipped, and substituted when it did not", () => {
    const chain = { death: ["hurt", "idle"], hurt: [] as readonly string[] };
    expect(
      selectMotion({ state: "death", available: has("death", "hurt", "idle"), fallbacks: chain }),
    ).toEqual({ state: "death", drawn: "death", substituted: false });
    expect(
      selectMotion({ state: "death", available: has("hurt", "idle"), fallbacks: chain }),
    ).toEqual({ state: "death", drawn: "hurt", substituted: true });
    expect(selectMotion({ state: "death", available: has("idle"), fallbacks: chain })).toEqual({
      state: "death",
      drawn: "idle",
      substituted: true,
    });
    // Nothing to draw is an answer: the caller holds the pose it already had.
    expect(selectMotion({ state: "hurt", available: has("idle"), fallbacks: chain })).toEqual({
      state: "hurt",
      drawn: null,
      substituted: false,
    });
  });

  test("the chosen state is the same whatever shipped, which is the whole point", () => {
    // Four different packages, one rule. `state` never moves; only `drawn`
    // does, and a caller that reads `state` is reading a decision no art
    // decision could have changed.
    for (const available of [
      has("death", "hurt", "idle"),
      has("hurt", "idle"),
      has("idle"),
      has(),
    ]) {
      expect(
        selectMotion({ state: "death", available, fallbacks: { death: ["hurt", "idle"] } }).state,
      ).toBe("death");
    }
  });
});

describe("the two rules that were welded into three actors", () => {
  test("a sustained state whose strip has stopped is restarted; an event's is not", () => {
    const base = { currentAnimationKey: "mob_attack", sustainedAnimationKey: "mob_idle" };
    expect(motionNeedsRestart({ ...base, sustained: true, isPlaying: true })).toBe(true);
    expect(
      motionNeedsRestart({
        ...base,
        currentAnimationKey: "mob_idle",
        sustained: true,
        isPlaying: false,
      }),
    ).toBe(true);
    expect(
      motionNeedsRestart({
        ...base,
        currentAnimationKey: "mob_idle",
        sustained: true,
        isPlaying: true,
      }),
    ).toBe(false);
    // A wind-up, a flinch or a death is an event: it holds its last frame and
    // nothing restarts it.
    expect(motionNeedsRestart({ ...base, sustained: false, isPlaying: false })).toBe(false);
  });

  test("mirroring is one line with the painted direction as a parameter", () => {
    expect(mirrorFor("left")).toBe(true);
    expect(mirrorFor("right")).toBe(false);
    // A package whose strips were painted facing left inverts, and no call site
    // has to know it.
    expect(mirrorFor("left", "left")).toBe(false);
    expect(mirrorFor("right", "left")).toBe(true);
  });
});

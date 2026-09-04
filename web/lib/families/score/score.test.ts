import { describe, expect, test } from "bun:test";
import { sealSystems } from "@/lib/kernel/systems";
import {
  applyScore,
  chainMultiplier,
  createScoreState,
  createScoreSystem,
  resetScore,
  type ScoreParams,
  type ScoreState,
} from "./score";
import { parseScoreBlock, scoreIsShown, scoreParamsFromBlock } from "./manifest";
import { PREPARED_RUNTIME_BLOCKS, type ScoreBlock } from "@/lib/manifest/prepared-manifest";

const STEP = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;

// --- E4: one scorer, two worlds that share no field but the total --------------------------------

/**
 * A runner-shaped world: a token line with a chain, a phase that gates scoring,
 * and a flat award for a fight that is not part of the line.
 */
type TrailWorld = {
  score: ScoreState;
  phase: "running" | "dead";
  collected: number;
  missed: number;
  bossesDefeated: number;
};

type TrailKind = "collected" | "boss-defeated";

const TRAIL_PARAMS: ScoreParams<TrailKind> = {
  awards: { collected: 10, "boss-defeated": 500 },
  chain: { steps: [5, 15, 30], extendedBy: ["collected"] },
};

/**
 * A minigame-shaped world: no chain at all, four authored kinds, and a run that
 * is scored on every frame it ticks because nothing about it can be "not yet".
 */
type WaveWorld = {
  points: ScoreState;
  defeated: number;
  cleared: number;
};

type WaveKind = "mob_defeated" | "wave_cleared";

const WAVE_PARAMS: ScoreParams<WaveKind> = {
  awards: { mob_defeated: 25, wave_cleared: 250 },
  chain: null,
};

describe("E4: the same scorer sealed into a chained run and a chainless one", () => {
  test("a runner-shaped world: the line chains, the fight pays flat", () => {
    const world: TrailWorld = {
      score: createScoreState(),
      phase: "running",
      collected: 0,
      missed: 0,
      bossesDefeated: 0,
    };
    const system = createScoreSystem<TrailWorld, TrailKind>({
      slice: "score",
      params: TRAIL_PARAMS,
      scoring: (w) => w.phase === "running",
      chainBroken: (w) => w.missed > 0,
      counts: (w) => ({ collected: w.collected, "boss-defeated": w.bossesDefeated }),
    });
    // Four collected: no rung reached, so the line pays at ×1.
    world.collected = 4;
    system.update(world, STEP);
    expect(world.score).toEqual({ total: 40, chain: 4, multiplier: 1 });
    // The fifth reaches the first rung, and the frame that reaches it is paid at
    // the multiplier it earned rather than the one it arrived with.
    world.collected = 1;
    system.update(world, STEP);
    expect(world.score).toEqual({ total: 40 + 20, chain: 5, multiplier: 2 });
    // A fight, mid-line: flat, and it does not extend the chain.
    world.collected = 0;
    world.bossesDefeated = 1;
    system.update(world, STEP);
    expect(world.score).toEqual({ total: 560, chain: 5, multiplier: 2 });
    // A run that is over scores nothing at all.
    world.phase = "dead";
    world.collected = 3;
    world.bossesDefeated = 0;
    system.update(world, STEP);
    expect(world.score.total).toBe(560);
  });

  test("a minigame-shaped world: no chain, so the awards are the whole rule", () => {
    const world: WaveWorld = { points: createScoreState(), defeated: 0, cleared: 0 };
    const system = createScoreSystem<WaveWorld, WaveKind>({
      slice: "points",
      params: WAVE_PARAMS,
      counts: (w) => ({ mob_defeated: w.defeated, wave_cleared: w.cleared }),
    });
    world.defeated = 3;
    system.update(world, STEP);
    // The multiplier stays exactly 1: a genre with no chain is not a genre whose
    // chain is always one, and the family never touches the field.
    expect(world.points).toEqual({ total: 75, chain: 0, multiplier: 1 });
    world.defeated = 4;
    world.cleared = 1;
    system.update(world, STEP);
    expect(world.points).toEqual({ total: 75 + 100 + 250, chain: 0, multiplier: 1 });
  });

  test("the two worlds share no field but the slice the family owns", () => {
    const trail = new Set(["score", "phase", "collected", "missed", "bossesDefeated"]);
    const wave = new Set(["points", "defeated", "cleared"]);
    expect([...trail].filter((key) => wave.has(key))).toEqual([]);
  });
});

// --- the arithmetic, stated once ----------------------------------------------------------------

describe("the chain ladder is a parameter", () => {
  test("a rung is reached at or past it, and the ladder's length is the cap", () => {
    expect(chainMultiplier(0, [5, 15, 30])).toBe(1);
    expect(chainMultiplier(4, [5, 15, 30])).toBe(1);
    expect(chainMultiplier(5, [5, 15, 30])).toBe(2);
    expect(chainMultiplier(15, [5, 15, 30])).toBe(3);
    expect(chainMultiplier(500, [5, 15, 30])).toBe(4);
    // A different genre, a different ladder, the same function.
    expect(chainMultiplier(3, [3])).toBe(2);
    expect(chainMultiplier(100, [])).toBe(1);
  });

  test("a break is applied before this frame's occurrences extend the chain", () => {
    // Which is what makes a frame carrying both a miss and a collection start
    // the new chain at that collection rather than losing it.
    const state = createScoreState();
    state.chain = 40;
    state.multiplier = 4;
    const award = applyScore(state, TRAIL_PARAMS, { collected: 1 }, true);
    expect(state).toEqual({ total: 10, chain: 1, multiplier: 1 });
    expect(award).toEqual({ delta: 10, broken: true });
  });

  test("a kind with no award pays nothing, and is not an error", () => {
    const state = createScoreState();
    // `boss_defeated` is in the closed vocabulary and this package awards none.
    applyScore(state, { awards: { mob_defeated: 5 }, chain: null }, {
      mob_defeated: 2,
      boss_defeated: 1,
    });
    expect(state.total).toBe(10);
  });

  test("a genre with no chain cannot have one broken", () => {
    const state = createScoreState();
    state.chain = 9;
    const award = applyScore(state, WAVE_PARAMS, { mob_defeated: 1 }, true);
    expect(state.chain).toBe(9);
    expect(award.broken).toBe(false);
  });

  test("the reset is in place, because the views and the seal hold the object", () => {
    const state: ScoreState = { total: 900, chain: 12, multiplier: 3 };
    const held = state;
    resetScore(state);
    expect(held).toEqual({ total: 0, chain: 0, multiplier: 1 });
  });
});

// --- E7: the subtraction ------------------------------------------------------------------------

describe("E7: a roster with the scorer quiet", () => {
  test("the roster with `score/run` removed seals to the identical order minus it", () => {
    type W = { score: ScoreState; tick: number };
    const scorer = createScoreSystem<W, "mob_defeated">({
      slice: "score",
      params: { awards: { mob_defeated: 1 }, chain: null },
      counts: () => ({}),
    });
    const noop = { update: () => {} };
    const before = { id: "clock/step", contractVersion: "v1", reads: [], writes: ["tick"], ...noop } as const;
    const after = { id: "hud/readout", contractVersion: "v1", reads: ["score"], writes: [], ...noop } as const;
    const full = sealSystems<W>([before, scorer, after]);
    // Dropping the family means dropping the read that names its slice with it —
    // the honest form of "quiet", because a readout of a score nobody keeps is
    // not a readout that draws zero.
    const quiet = sealSystems<W>([before, { ...after, reads: [] }]);
    expect(full.order).toEqual(["clock/step", "score/run", "hud/readout"]);
    expect(quiet.order).toEqual(full.order.filter((id) => id !== "score/run"));
  });

  test("a package that authors no score is not a package whose awards are zero", () => {
    // `null` in, `null` out. The genre reads the absence and builds nothing,
    // which is the answer rule 6 asks an optional block for.
    expect(scoreParamsFromBlock(null)).toBeNull();
    expect(scoreIsShown(null)).toBe(false);
  });
});

// --- the block, and the refusal -----------------------------------------------------------------

describe("the family gates its own block", () => {
  const binding = { block: "score", version: PREPARED_RUNTIME_BLOCKS.score, optional: true };

  test("an absent optional block is an answer, not a refusal", () => {
    const view = parseScoreBlock({ gameplay: PREPARED_RUNTIME_BLOCKS.gameplay }, binding);
    expect(view).toEqual({ block: "score", version: null, published: false });
  });

  test("a published block at the version this build reads", () => {
    const view = parseScoreBlock({ score: PREPARED_RUNTIME_BLOCKS.score }, binding);
    expect(view.published).toBe(true);
    expect(view.version).toBe(PREPARED_RUNTIME_BLOCKS.score);
  });

  test("a block at a version this build does not read is refused by name", () => {
    expect(() => parseScoreBlock({ score: "platformer-score-block-v2" }, binding)).toThrow(
      'manifest block "score" is published as platformer-score-block-v2; this build reads platformer-score-block-v1',
    );
  });

  test("the authored table becomes the family's parameters, display included", () => {
    const block: ScoreBlock = {
      awards: { mob_defeated: 25, wave_cleared: 250 },
      display: "hud",
    };
    expect(scoreParamsFromBlock(block)).toEqual({
      awards: { mob_defeated: 25, wave_cleared: 250 },
      chain: null,
    });
    expect(scoreIsShown(block)).toBe(true);
    expect(scoreIsShown({ ...block, display: "hidden" })).toBe(false);
  });
});

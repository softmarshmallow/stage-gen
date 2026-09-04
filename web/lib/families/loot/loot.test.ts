import { describe, expect, test } from "bun:test";
import { dropSpread, resolveLootDrops, type LootRule } from "./rules";
import {
  DROP_BOUNCE_RESTITUTION,
  DROP_GRAVITY,
  dropPopVelocity,
  launchDrop,
  stepDrop,
  type DropBody,
} from "./drop";
import { collectDrops, createLootLedger } from "./collect";
import { parseLootBlock } from "./manifest";

const RULES: readonly LootRule[] = Object.freeze([
  Object.freeze({
    mob_id: "page_eater",
    item_id: "castle_moonkey",
    chance: 1,
    quantity_min: 1,
    quantity_max: 3,
  }),
  Object.freeze({
    mob_id: "page_eater",
    item_id: "welcome_tart",
    chance: 0,
    quantity_min: 1,
    quantity_max: 1,
  }),
  Object.freeze({
    mob_id: "ink_moth",
    item_id: "paper_dart",
    chance: 1,
    quantity_min: 2,
    quantity_max: 2,
  }),
]);

describe("the authored rule", () => {
  test("a certain rule drops and an impossible one does not, for the same death", () => {
    const drops = resolveLootDrops(RULES, "page_eater", 7);
    expect(drops).toEqual([{ itemId: "castle_moonkey", quantity: 1 + (7 % 3) }]);
  });

  test("one seed answers for every rule the creature carries", () => {
    // Deliberate, and the sentence that says so: this is "the death was lucky",
    // not "each drop was rolled separately". Two certain rules both fire.
    const both: readonly LootRule[] = [RULES[0], { ...RULES[2], mob_id: "page_eater" }];
    expect(resolveLootDrops(both, "page_eater", 0).map((drop) => drop.itemId)).toEqual([
      "castle_moonkey",
      "paper_dart",
    ]);
  });

  test("a creature with no rule drops nothing, which is an answer", () => {
    expect(resolveLootDrops(RULES, "baker", 0)).toEqual([]);
  });

  test("a stack straddles the corpse it fell out of", () => {
    expect(dropSpread(1, 28)).toEqual([0]);
    expect(dropSpread(2, 28)).toEqual([-14, 14]);
    expect(dropSpread(4, 28)).toEqual([-42, -14, 14, 42]);
  });
});

// --- the drop's own arc ------------------------------------------------------------------------

describe("a drop on the ground", () => {
  const flat = { surfaceAt: () => 400 };

  test("pops away from the blow, bounces exactly once, and settles into a bob", () => {
    const body = launchDrop(300, 336, 1, 1, 0);
    expect(body.vy).toBeLessThan(0);
    expect(body.vx).toBeGreaterThan(0);
    let bounced = 0;
    let settledAt: number | null = null;
    for (let frame = 1; frame <= 240; frame += 1) {
      const step = stepDrop(body, 1000 / 60, frame * (1000 / 60), flat);
      if (step === "bounced") bounced += 1;
      if (step === "settled") settledAt ??= frame;
    }
    expect(bounced).toBe(1);
    expect(settledAt).not.toBeNull();
    expect(body.vx).toBe(0);
    expect(body.groundY).toBe(400);
    // Resting is a bob about the surface, not a stop on it.
    expect(Math.abs(body.y - 400)).toBeLessThanOrEqual(2);
    expect(body.x).toBeGreaterThan(300);
  });

  test("the bounce keeps the authored restitution", () => {
    const body: DropBody = {
      x: 0,
      y: 400,
      vx: 0,
      vy: 600,
      settled: false,
      bounces: 0,
      groundY: 400,
      bobPhase: 0,
    };
    expect(stepDrop(body, 1000 / 60, 16, flat)).toBe("bounced");
    expect(body.vy).toBeCloseTo(-(600 + DROP_GRAVITY / 60) * DROP_BOUNCE_RESTITUTION, 6);
  });

  test("a crawl settles outright rather than jittering", () => {
    const body: DropBody = {
      x: 0,
      y: 400,
      vx: 0,
      vy: 10,
      settled: false,
      bounces: 0,
      groundY: 400,
      bobPhase: 0,
    };
    expect(stepDrop(body, 1000 / 60, 16, flat)).toBe("settled");
  });

  test("two drops with different phases do not rise and fall as one object", () => {
    const left = { ...launchDrop(0, 400, 1, 1, 0), settled: true, groundY: 400 };
    const right = { ...launchDrop(0, 400, 1, 1, 3), settled: true, groundY: 400 };
    stepDrop(left, 1000 / 60, 500, flat);
    stepDrop(right, 1000 / 60, 500, flat);
    expect(left.y).not.toBeCloseTo(right.y, 6);
  });

  test("the pop replays: the same sequence and direction give the same launch twice", () => {
    expect(dropPopVelocity(4, -1)).toEqual(dropPopVelocity(4, -1));
    // And a caller with no blow to report alternates rather than always going right.
    expect(dropPopVelocity(2, 0).vx).toBeGreaterThan(0);
    expect(dropPopVelocity(3, 0).vx).toBeLessThan(0);
    expect(() => dropPopVelocity(-1, 0)).toThrow("nonnegative sequence");
  });

  test("a world with edges keeps a pop inside them", () => {
    const body = launchDrop(10, 400, 1, -1, 0);
    stepDrop(body, 1000 / 60, 16, { surfaceAt: () => 400, clampX: (x) => Math.max(32, x) });
    expect(body.x).toBe(32);
  });
});

// --- E4: the collect half, in the two shapes that have one -----------------------------------

type Placement = Readonly<{ id: string; column: number }>;
type Drop = Readonly<{ id: string; x: number }>;

describe("E4: the collect half instantiated into two shapes", () => {
  test("a runner-shaped collect: a ledger, and pickups that can be passed for good", () => {
    const ledger = createLootLedger();
    const track: readonly Placement[] = [
      { id: "a", column: 1 },
      { id: "b", column: 5 },
      { id: "c", column: 9 },
    ];
    const at = (distance: number) =>
      collectDrops<Placement>({
        candidates: track,
        key: (pickup) => pickup.id,
        ledger,
        passed: (pickup) => pickup.column + 1 < distance - 0.5,
        reached: (pickup) => Math.abs(pickup.column - distance) < 0.5,
      });
    expect(at(1).taken.map((pickup) => pickup.id)).toEqual(["a"]);
    // Taken once ever: standing on it a second time collects nothing.
    expect(at(1).taken).toEqual([]);
    // And passed once ever, however long the track runs on.
    expect(at(7).missed.map((pickup) => pickup.id)).toEqual(["b"]);
    expect(at(8).missed).toEqual([]);
    // A collected pickup is never also missed, whatever the avatar does after.
    expect(at(20).missed.map((pickup) => pickup.id)).toEqual(["c"]);
    expect([...ledger.collected]).toEqual(["a"]);
    expect([...ledger.missed]).toEqual(["b", "c"]);
  });

  test("a platformer-shaped collect: no ledger, no passing, and order is the caller's", () => {
    // A taken drop is destroyed, so the world is the ledger and remembering it
    // would be a second copy of a fact that is already there.
    const drops: readonly Drop[] = [
      { id: "drop_1", x: 100 },
      { id: "drop_2", x: 104 },
      { id: "drop_3", x: 400 },
    ];
    const back = collectDrops<Drop>({
      candidates: [...drops].reverse(),
      key: (drop) => drop.id,
      reached: (drop) => Math.abs(drop.x - 102) < 10,
    });
    // Back to front, which is what the array-splicing loop it replaced did, and
    // which is what a replay hashes when two drops land on one frame.
    expect(back.taken.map((drop) => drop.id)).toEqual(["drop_2", "drop_1"]);
    expect(back.missed).toEqual([]);
    // The genre with no `passed` rule never reports one, which is an answer.
    const front = collectDrops<Drop>({
      candidates: drops,
      key: (drop) => drop.id,
      reached: (drop) => Math.abs(drop.x - 102) < 10,
    });
    expect(front.taken.map((drop) => drop.id)).toEqual(["drop_1", "drop_2"]);
  });
});

// --- E7 ---------------------------------------------------------------------------------------

describe("E7: the subtraction", () => {
  test("a genre that drops nothing still collects, and one that collects nothing still drops", () => {
    // The runner: no rules at all, and the collect half is unaffected.
    expect(resolveLootDrops([], "anything", 12345)).toEqual([]);
    // And a frame with nothing within reach is an empty verdict rather than a
    // special case anyone has to guard against.
    expect(
      collectDrops<Drop>({ candidates: [], key: (drop) => drop.id, reached: () => true }),
    ).toEqual({ taken: [], missed: [] });
  });
});

// --- the block, and the refusal ---------------------------------------------------------------

describe("the blocks the family gates for itself", () => {
  test("the platformer's drop half refuses by naming its own block", () => {
    expect(() =>
      parseLootBlock(
        { gameplay: "platformer-gameplay-block-v2" },
        { block: "gameplay", version: "platformer-gameplay-block-v1" },
      ),
    ).toThrow('manifest block "gameplay" is published as platformer-gameplay-block-v2');
  });

  test("and the runner's collect half by naming the block its placements live in", () => {
    expect(() =>
      parseLootBlock(
        { segments: "runner-segments-block-v2" },
        { block: "segments", version: "runner-segments-block-v1" },
      ),
    ).toThrow('manifest block "segments" is published as runner-segments-block-v2');
  });
});

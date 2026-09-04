import { describe, expect, test } from "bun:test";
import { mulberry32 } from "@/lib/kernel/rng";
import { sealSystems, type GameSystem } from "@/lib/kernel/systems";
import {
  createSessionSystem,
  nextSessionSeed,
  SESSION_SYSTEM_ID,
  type SessionState,
} from "./session";
import { parseSessionBlock } from "./manifest";

const step = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;

// --- E4: one family file, two worlds with different phase names and different restarts ------

/** A runner-shaped world: a held start, a seeded lineage, a composition reset. */
interface RunWorld {
  run: SessionState<"intro" | "running" | "dead", "pit" | "crush"> & {
    rng: ReturnType<typeof mulberry32>;
  };
  released: boolean;
  verdict: "pit" | "crush" | null;
  press: boolean;
  rebuilds: number;
}

/** A platformer-shaped world: no held start, no lineage, a restart that is a map entry. */
interface StageWorld {
  session: SessionState<"starting" | "running" | "defeated", "defeat">;
  defeated: boolean;
  confirmed: boolean;
  respawns: number;
}

describe("E4: the session family instantiated into two different worlds", () => {
  test("a runner-shaped session: held start, seeded lineage, reset by the composition", () => {
    const world: RunWorld = {
      run: { phase: "intro", seed: 7, runIndex: 0, endedBy: null, rng: mulberry32(7) },
      released: false,
      verdict: null,
      press: false,
      rebuilds: 0,
    };
    const asked: number[] = [];
    const session = createSessionSystem<RunWorld, "intro" | "running" | "dead", "pit" | "crush">({
      slice: "run",
      phases: { starting: "intro", running: "running", ended: "dead" },
      begins: (w) => w.released,
      ended: (w) => w.verdict,
      restarts: (w) => w.press,
      stream: (w) => w.run.rng,
      onRestartAsked: (_w, seed) => asked.push(seed),
      restart: (w, seed) => {
        w.rebuilds += 1;
        w.verdict = null;
        w.press = false;
        w.run = { ...w.run, phase: "running", seed, rng: mulberry32(seed) };
      },
    });
    const sealed = sealSystems<RunWorld>([session]);
    expect(sealed.order).toEqual([SESSION_SYSTEM_ID]);

    sealed.tick(world, step);
    expect(world.run.phase).toBe("intro");
    world.released = true;
    sealed.tick(world, step);
    expect(world.run.phase).toBe("running");

    world.verdict = "pit";
    sealed.tick(world, step);
    expect(world.run.phase).toBe("dead");
    expect(world.run.endedBy).toBe("pit");

    world.press = true;
    sealed.tick(world, step);
    // Asked for, not performed: the world is untouched until the composition resets.
    expect(world.run.phase as string).toBe("dead");
    expect(world.rebuilds).toBe(0);
    expect(asked).toHaveLength(1);

    sealed.reset(world, "run");
    expect(world.run.phase as string).toBe("running");
    expect(world.run.seed).toBe(asked[0]);
    expect(world.run.runIndex).toBe(1);
    expect(world.rebuilds).toBe(1);
  });

  test("a platformer-shaped session: no held start, no lineage, a restart in place", () => {
    const world: StageWorld = {
      session: { phase: "running", seed: 0, runIndex: 0, endedBy: null },
      defeated: false,
      confirmed: false,
      respawns: 0,
    };
    const session = createSessionSystem<
      StageWorld,
      "starting" | "running" | "defeated",
      "defeat"
    >({
      slice: "session",
      phases: { starting: "starting", running: "running", ended: "defeated" },
      begins: () => true,
      ended: (w) => (w.defeated ? "defeat" : null),
      restarts: (w) => w.confirmed,
      // A genre with no seeded run still has a stream to draw from; nothing
      // reads the seed it produces, and the lineage index is what is worth
      // having — "this is your third attempt" is a fact the runtime dropped.
      stream: () => mulberry32(1),
      restartsInPlace: true,
      restart: (w) => {
        w.respawns += 1;
        w.defeated = false;
        w.confirmed = false;
      },
    });
    const sealed = sealSystems<StageWorld>([session]);

    sealed.tick(world, step);
    expect(world.session.phase).toBe("running");

    world.defeated = true;
    sealed.tick(world, step);
    expect(world.session.phase).toBe("defeated");
    expect(world.session.endedBy).toBe("defeat");

    // The panel is answered: the world is rebuilt on this frame, not by a
    // composition reset that this genre does not have.
    world.confirmed = true;
    sealed.tick(world, step);
    expect(world.session.phase as string).toBe("running");
    expect(world.session.runIndex).toBe(1);
    expect(world.session.endedBy).toBe(null);
    expect(world.respawns).toBe(1);
  });
});

describe("the lifecycle's own refusals and arithmetic", () => {
  test("a second author of the session slice is refused at seal", () => {
    const session = createSessionSystem<StageWorld, "starting" | "running" | "defeated", "defeat">({
      slice: "session",
      phases: { starting: "starting", running: "running", ended: "defeated" },
      begins: () => true,
      ended: () => null,
      restarts: () => false,
      stream: () => mulberry32(1),
      restart: () => undefined,
    });
    const panel: GameSystem<StageWorld, never> = {
      id: "ui/defeat-panel",
      contractVersion: "panel-v1",
      reads: [],
      writes: ["session"],
      update: () => undefined,
    };
    expect(() => sealSystems<StageWorld>([session, panel])).toThrow(
      'it writes "session", which "session/run" owns',
    );
  });

  test("the next seed is a 32-bit draw from the dying run's stream", () => {
    const a = nextSessionSeed(mulberry32(9));
    const b = nextSessionSeed(mulberry32(9));
    expect(a).toBe(b);
    expect(Number.isSafeInteger(a)).toBe(true);
    expect(a).toBeGreaterThanOrEqual(0);
    expect(a).toBeLessThan(0x100000000);
  });
});

describe("the block the family gates for itself", () => {
  test("a moved block is refused by name", () => {
    expect(() =>
      parseSessionBlock(
        { gameplay: "runner-gameplay-block-v2" },
        { block: "gameplay", version: "runner-gameplay-block-v1" },
      ),
    ).toThrow(
      'manifest block "gameplay" is published as runner-gameplay-block-v2; ' +
        "this build reads runner-gameplay-block-v1",
    );
  });
});

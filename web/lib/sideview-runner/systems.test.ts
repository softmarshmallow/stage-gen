import { describe, expect, test } from "bun:test";
import { sealSystems, type FixedStep, type GameSystem } from "./systems";

interface World {
  a: number;
  b: number;
  c: number;
}

const STEP: FixedStep = Object.freeze({ dt: 1 / 60, now: 1 / 60, frame: 1 });

function system(
  id: string,
  reads: readonly (keyof World & string)[],
  writes: readonly (keyof World & string)[],
  options: { after?: readonly string[]; onUpdate?: (world: World) => void } = {},
): GameSystem<World> {
  return {
    id,
    contractVersion: `${id}-v1`,
    reads,
    writes,
    after: options.after,
    update(world) {
      options.onUpdate?.(world);
    },
  };
}

describe("sealSystems", () => {
  test("orders every writer of a key before every reader of it", () => {
    const sealed = sealSystems<World>([
      system("reader", ["a", "b"], ["c"]),
      system("writer-b", [], ["b"]),
      system("writer-a", [], ["a"]),
    ]);
    const order = sealed.order;
    expect(order.indexOf("writer-a")).toBeLessThan(order.indexOf("reader"));
    expect(order.indexOf("writer-b")).toBeLessThan(order.indexOf("reader"));
  });

  test("keeps registration order among independent systems, deterministically", () => {
    const systems = [
      system("first", [], ["a"]),
      system("second", [], ["b"]),
      system("third", [], ["c"]),
    ];
    expect(sealSystems<World>(systems).order).toEqual(["first", "second", "third"]);
    // Sealing the same declarations again derives the same order.
    expect(sealSystems<World>(systems).order).toEqual(sealSystems<World>(systems).order);
  });

  test("honors explicit after edges where dataflow is silent", () => {
    const sealed = sealSystems<World>([
      system("late", [], [], { after: ["early"] }),
      system("early", [], []),
    ]);
    expect(sealed.order).toEqual(["early", "late"]);
  });

  test("refuses duplicate ids at seal time", () => {
    expect(() =>
      sealSystems<World>([system("twin", [], ["a"]), system("twin", [], ["b"])]),
    ).toThrow('duplicate system id "twin"');
  });

  test("refuses an after edge naming an unregistered system", () => {
    expect(() =>
      sealSystems<World>([system("orphan", [], [], { after: ["phantom"] })]),
    ).toThrow('after edge names unregistered "phantom"');
  });

  test("refuses a read/write cycle and names it", () => {
    const seal = () =>
      sealSystems<World>([
        system("ping", ["b"], ["a"]),
        system("pong", ["a"], ["b"]),
      ]);
    expect(seal).toThrow("sealSystems refused a dependency cycle");
    expect(seal).toThrow(/ping -> pong -> ping|pong -> ping -> pong/);
  });

  test("refuses a cycle closed by an after edge", () => {
    expect(() =>
      sealSystems<World>([
        system("alpha", [], ["a"], { after: ["beta"] }),
        system("beta", ["a"], []),
      ]),
    ).toThrow("dependency cycle");
  });

  test("tick runs updates in the sealed order", () => {
    const world: World = { a: 0, b: 0, c: 0 };
    const trace: string[] = [];
    const sealed = sealSystems<World>([
      system("consumer", ["a"], ["b"], { onUpdate: () => trace.push("consumer") }),
      system("producer", [], ["a"], { onUpdate: () => trace.push("producer") }),
    ]);
    sealed.tick(world, STEP);
    sealed.tick(world, STEP);
    expect(trace).toEqual(["producer", "consumer", "producer", "consumer"]);
    expect(sealed.order).toEqual(["producer", "consumer"]);
  });

  test("a system reading its own written key needs no self edge", () => {
    const sealed = sealSystems<World>([system("loner", ["a"], ["a"])]);
    expect(sealed.order).toEqual(["loner"]);
  });
});

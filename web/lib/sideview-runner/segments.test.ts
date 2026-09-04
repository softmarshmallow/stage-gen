import { describe, expect, test } from "bun:test";
import { parseRunnerRuntimeManifest, type RunnerChunk } from "./contract";
import { runnerManifestFixture } from "./fixture";
import {
  chunkAt,
  createSegmentStream,
  dropBehind,
  selectChunkIndex,
  streamAhead,
  streamedHazards,
  streamedPickups,
  surfaceRowAt,
  windowOccupancyGrid,
} from "./segments";
import { mulberry32 } from "@/lib/kernel/rng";

function chunkFixture(overrides: Partial<RunnerChunk> = {}): RunnerChunk {
  return {
    segmentId: "flat",
    difficulty: 1,
    occupancy: [
      "00000000",
      "00000000",
      "00000000",
      "00000000",
      "00000000",
      "11111111",
      "11111111",
      "11111111",
    ],
    hazards: [],
    pickups: [],
    ...overrides,
  };
}

const PIT_CHUNK = chunkFixture({
  segmentId: "pit",
  difficulty: 2,
  occupancy: [
    "00000000",
    "00000000",
    "00000000",
    "00000000",
    "00000000",
    "11100111",
    "11100111",
    "11100111",
  ],
});

describe("selectChunkIndex", () => {
  const catalog = [
    chunkFixture({ segmentId: "easy", difficulty: 1 }),
    chunkFixture({ segmentId: "mid", difficulty: 4 }),
    chunkFixture({ segmentId: "hard", difficulty: 9 }),
  ];

  test("picks only chunks at or under the ceiling", () => {
    const rng = mulberry32(7);
    for (let i = 0; i < 50; i += 1) {
      expect(selectChunkIndex(catalog, { ceiling: 1 }, rng)).toBe(0);
    }
    const seen = new Set<number>();
    for (let i = 0; i < 200; i += 1) seen.add(selectChunkIndex(catalog, { ceiling: 5 }, rng));
    expect([...seen].sort()).toEqual([0, 1]);
  });

  test("falls back to the easiest chunks when nothing fits the ceiling", () => {
    const steep = [
      chunkFixture({ segmentId: "five", difficulty: 5 }),
      chunkFixture({ segmentId: "nine", difficulty: 9 }),
    ];
    const rng = mulberry32(3);
    for (let i = 0; i < 20; i += 1) {
      expect(selectChunkIndex(steep, { ceiling: 1 }, rng)).toBe(0);
    }
  });

  test("is reproducible from its seed", () => {
    const picks = (seed: number) => {
      const rng = mulberry32(seed);
      return Array.from({ length: 20 }, () => selectChunkIndex(catalog, { ceiling: 10 }, rng));
    };
    expect(picks(42)).toEqual(picks(42));
    expect(picks(42)).not.toEqual(picks(43));
  });
});

describe("streamAhead / dropBehind", () => {
  test("appends contiguous chunks through the requested column", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [chunkFixture()], { ceiling: 1 }, mulberry32(1), 20);
    expect(stream.chunks).toHaveLength(3);
    expect(stream.chunks.map((chunk) => chunk.startColumn)).toEqual([0, 8, 16]);
    expect(stream.nextColumn).toBe(24);
  });

  test("drops chunks fully behind the keep line and keeps the rest", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [chunkFixture()], { ceiling: 1 }, mulberry32(1), 30);
    dropBehind(stream, 17);
    expect(stream.chunks[0].startColumn).toBe(16);
    expect(chunkAt(stream, 0)).toBeNull();
    expect(chunkAt(stream, 17)?.startColumn).toBe(16);
  });

  test("maps hazards and pickups into world columns", () => {
    const stream = createSegmentStream(8, 5);
    const chunk = chunkFixture({
      hazards: [{ propId: "cart", column: 3, anchor: "surface" as const, clearanceRows: null }],
      pickups: [{ itemId: "token", column: 4, row: 2 }],
    });
    streamAhead(stream, [chunk], { ceiling: 1 }, mulberry32(1), 10);
    expect(streamedHazards(stream).map((entry) => entry.worldColumn)).toEqual([3, 11]);
    expect(streamedHazards(stream)[0].anchor).toBe("surface");
    expect(streamedPickups(stream)[1]).toEqual({ itemId: "token", worldColumn: 12, row: 2 });
  });
});

describe("surfaceRowAt", () => {
  test("answers the walk surface over ground and null over a pit", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [PIT_CHUNK], { ceiling: 10 }, mulberry32(1), 6);
    expect(surfaceRowAt(stream, 0)).toBe(5);
    expect(surfaceRowAt(stream, 3)).toBeNull();
    expect(surfaceRowAt(stream, 4)).toBeNull();
    expect(surfaceRowAt(stream, 6)).toBe(5);
  });

  test("refuses a column outside the streamed window", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [chunkFixture()], { ceiling: 1 }, mulberry32(1), 6);
    expect(() => surfaceRowAt(stream, 99)).toThrow("outside the streamed window");
  });
});

describe("windowOccupancyGrid", () => {
  test("stitches the retained chunks into one row-major grid", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [PIT_CHUNK], { ceiling: 10 }, mulberry32(1), 10);
    dropBehind(stream, 9);
    const { startColumn, grid } = windowOccupancyGrid(stream);
    expect(startColumn).toBe(8);
    expect(grid).toHaveLength(8);
    expect(grid[5].length).toBe(8);
    expect(grid[5][2]).toBe(true);
    expect(grid[5][3]).toBe(false);
  });

  test("an empty window yields an empty grid", () => {
    const stream = createSegmentStream(8, 5);
    expect(windowOccupancyGrid(stream)).toEqual({ startColumn: 0, grid: [] });
  });
});

describe("streaming from the parsed manifest", () => {
  test("the parsed chunk catalog streams directly", () => {
    const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());
    const stream = createSegmentStream(
      manifest.segments.rows,
      manifest.segments.walkSurfaceRow,
    );
    streamAhead(stream, manifest.segments.chunks, { ceiling: 1 }, mulberry32(11), 30);
    expect(surfaceRowAt(stream, 15)).toBe(manifest.segments.walkSurfaceRow);
    expect(streamedHazards(stream).length).toBeGreaterThan(0);
  });
});

describe("the selection grammar", () => {
  const catalog = [
    chunkFixture({ segmentId: "easy", difficulty: 1 }),
    chunkFixture({ segmentId: "mid", difficulty: 4 }),
    chunkFixture({ segmentId: "hard", difficulty: 6 }),
  ];

  test("the floor ages easy chunks out of the band", () => {
    const rng = mulberry32(5);
    const seen = new Set<number>();
    for (let i = 0; i < 200; i += 1) {
      seen.add(selectChunkIndex(catalog, { ceiling: 6, floor: 4 }, rng));
    }
    expect([...seen].sort()).toEqual([1, 2]);
  });

  test("an empty band widens to the ceiling pool rather than refusing", () => {
    const rng = mulberry32(5);
    for (let i = 0; i < 20; i += 1) {
      expect(selectChunkIndex(catalog, { ceiling: 1, floor: 3 }, rng)).toBe(0);
    }
  });

  test("the previous chunk is excluded while anything else is eligible", () => {
    const rng = mulberry32(9);
    for (let i = 0; i < 100; i += 1) {
      const previous = i % catalog.length;
      expect(selectChunkIndex(catalog, { ceiling: 10 }, rng, previous)).not.toBe(previous);
    }
  });

  test("streamAhead never repeats a chunk back to back given alternatives", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, catalog, { ceiling: 10 }, mulberry32(2), 400);
    for (let i = 1; i < stream.chunks.length; i += 1) {
      expect(stream.chunks[i].segmentId).not.toBe(stream.chunks[i - 1].segmentId);
    }
  });

  test("the rest cadence forces a catalog-easiest breather on the beat", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(
      stream,
      catalog,
      { ceiling: 10, floor: 4, restEveryAppends: 3 },
      mulberry32(4),
      400,
    );
    for (let i = 2; i < stream.chunks.length; i += 3) {
      expect(stream.chunks[i].difficulty).toBe(1);
    }
  });

  test("consumption is reproducible from the seed with the grammar on", () => {
    const run = (seed: number) => {
      const stream = createSegmentStream(8, 5);
      streamAhead(
        stream,
        catalog,
        { ceiling: 10, floor: 2, restEveryAppends: 4 },
        mulberry32(seed),
        300,
      );
      return stream.chunks.map((chunk) => chunk.segmentId);
    };
    expect(run(7)).toEqual(run(7));
    expect(run(7)).not.toEqual(run(8));
  });
});

describe("the arena an encounter is fought over", () => {
  const ARENA = chunkFixture({ segmentId: "boss_arena", role: "arena" });
  const CATALOG = [chunkFixture(), PIT_CHUNK];

  test("streams the arena verbatim, back to back, while it is asked for", () => {
    const stream = createSegmentStream(8, 5);

    streamAhead(stream, CATALOG, { ceiling: 2, arena: ARENA }, mulberry32(1), 20);

    expect(stream.chunks.length).toBeGreaterThan(1);
    for (const streamed of stream.chunks) {
      expect(streamed.segmentId).toBe("boss_arena");
      expect(streamed.role).toBe("arena");
    }
    // Contiguous, like any other streamed run of chunks.
    expect(stream.chunks[1].startColumn).toBe(stream.chunks[0].width);
  });

  test("spends no randomness and leaves the pacing counters where they were", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, CATALOG, { ceiling: 2, restEveryAppends: 3 }, mulberry32(4), 8);
    const lastIndex = stream.lastChunkIndex;
    const appends = stream.appendsSinceRest;

    let rngCalls = 0;
    const countingRng = () => {
      rngCalls += 1;
      return 0.5;
    };
    streamAhead(
      stream,
      CATALOG,
      { ceiling: 2, restEveryAppends: 3, arena: ARENA },
      countingRng,
      40,
    );

    expect(rngCalls).toBe(0);
    expect(stream.lastChunkIndex).toBe(lastIndex);
    expect(stream.appendsSinceRest).toBe(appends);
  });

  test("ordinary selection resumes the moment the arena is no longer asked for", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, CATALOG, { ceiling: 2, arena: ARENA }, mulberry32(1), 16);
    const arenaCount = stream.chunks.length;

    streamAhead(stream, CATALOG, { ceiling: 2 }, mulberry32(1), 40);

    expect(stream.chunks.length).toBeGreaterThan(arenaCount);
    expect(stream.chunks.slice(arenaCount).every((c) => c.segmentId !== "boss_arena")).toBe(true);
  });

  test("a streamed chunk carries the role it was authored with", () => {
    const stream = createSegmentStream(8, 5);

    streamAhead(stream, CATALOG, { ceiling: 2 }, mulberry32(1), 8);

    expect(stream.chunks[0].role).toBe("run");
  });
});

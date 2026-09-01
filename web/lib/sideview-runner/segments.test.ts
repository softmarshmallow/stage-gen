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
import { mulberry32 } from "./world";

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
      expect(selectChunkIndex(catalog, 1, rng)).toBe(0);
    }
    const seen = new Set<number>();
    for (let i = 0; i < 200; i += 1) seen.add(selectChunkIndex(catalog, 5, rng));
    expect([...seen].sort()).toEqual([0, 1]);
  });

  test("falls back to the easiest chunks when nothing fits the ceiling", () => {
    const steep = [
      chunkFixture({ segmentId: "five", difficulty: 5 }),
      chunkFixture({ segmentId: "nine", difficulty: 9 }),
    ];
    const rng = mulberry32(3);
    for (let i = 0; i < 20; i += 1) {
      expect(selectChunkIndex(steep, 1, rng)).toBe(0);
    }
  });

  test("is reproducible from its seed", () => {
    const picks = (seed: number) => {
      const rng = mulberry32(seed);
      return Array.from({ length: 20 }, () => selectChunkIndex(catalog, 10, rng));
    };
    expect(picks(42)).toEqual(picks(42));
    expect(picks(42)).not.toEqual(picks(43));
  });
});

describe("streamAhead / dropBehind", () => {
  test("appends contiguous chunks through the requested column", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [chunkFixture()], 1, mulberry32(1), 20);
    expect(stream.chunks).toHaveLength(3);
    expect(stream.chunks.map((chunk) => chunk.startColumn)).toEqual([0, 8, 16]);
    expect(stream.nextColumn).toBe(24);
  });

  test("drops chunks fully behind the keep line and keeps the rest", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [chunkFixture()], 1, mulberry32(1), 30);
    dropBehind(stream, 17);
    expect(stream.chunks[0].startColumn).toBe(16);
    expect(chunkAt(stream, 0)).toBeNull();
    expect(chunkAt(stream, 17)?.startColumn).toBe(16);
  });

  test("maps hazards and pickups into world columns", () => {
    const stream = createSegmentStream(8, 5);
    const chunk = chunkFixture({
      hazards: [{ propId: "cart", column: 3 }],
      pickups: [{ itemId: "token", column: 4, row: 2 }],
    });
    streamAhead(stream, [chunk], 1, mulberry32(1), 10);
    expect(streamedHazards(stream).map((entry) => entry.worldColumn)).toEqual([3, 11]);
    expect(streamedPickups(stream)[1]).toEqual({ itemId: "token", worldColumn: 12, row: 2 });
  });
});

describe("surfaceRowAt", () => {
  test("answers the walk surface over ground and null over a pit", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [PIT_CHUNK], 10, mulberry32(1), 6);
    expect(surfaceRowAt(stream, 0)).toBe(5);
    expect(surfaceRowAt(stream, 3)).toBeNull();
    expect(surfaceRowAt(stream, 4)).toBeNull();
    expect(surfaceRowAt(stream, 6)).toBe(5);
  });

  test("refuses a column outside the streamed window", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [chunkFixture()], 1, mulberry32(1), 6);
    expect(() => surfaceRowAt(stream, 99)).toThrow("outside the streamed window");
  });
});

describe("windowOccupancyGrid", () => {
  test("stitches the retained chunks into one row-major grid", () => {
    const stream = createSegmentStream(8, 5);
    streamAhead(stream, [PIT_CHUNK], 10, mulberry32(1), 10);
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
    streamAhead(stream, manifest.segments.chunks, 1, mulberry32(11), 30);
    expect(surfaceRowAt(stream, 15)).toBe(manifest.segments.walkSurfaceRow);
    expect(streamedHazards(stream).length).toBeGreaterThan(0);
  });
});

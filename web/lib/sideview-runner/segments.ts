// Windowed chunk streaming: the endless track as a finite sliding window.
//
// The manifest carries a catalog of interchangeable chunks; the run is an
// unbounded sequence drawn from it. Nothing here touches Phaser: the stream
// is plain data — appended ahead of the camera, dropped behind it — and the
// physics asks it one question, "what row does this world column stand on".
// Chunk choice goes through the injected RNG, so a seed reproduces a track.

import { bottomContiguousSurfaceRow, type RunnerChunk } from "./contract";
import type { GameSystem } from "./systems";
import type { RunnerWorld } from "./world";

export interface StreamedHazard {
  readonly propId: string;
  readonly worldColumn: number;
}

export interface StreamedPickup {
  readonly itemId: string;
  readonly worldColumn: number;
  readonly row: number;
}

export interface StreamedChunk {
  readonly segmentId: string;
  readonly difficulty: number;
  /** World column of this chunk's local column 0. */
  readonly startColumn: number;
  readonly width: number;
  readonly occupancy: readonly string[];
  readonly hazards: readonly StreamedHazard[];
  readonly pickups: readonly StreamedPickup[];
}

export interface SegmentStream {
  readonly rows: number;
  readonly walkSurfaceRow: number;
  /** The retained window, ordered and contiguous in world columns. */
  chunks: StreamedChunk[];
  /** World column where the next appended chunk will start. */
  nextColumn: number;
}

export function createSegmentStream(rows: number, walkSurfaceRow: number): SegmentStream {
  return { rows, walkSurfaceRow, chunks: [], nextColumn: 0 };
}

/**
 * Pick the next chunk: uniform among those at or under the difficulty
 * ceiling. A catalog whose easiest chunk sits above the ceiling still has to
 * produce track, so the fallback pool is the minimum-difficulty chunks rather
 * than a refusal mid-run.
 */
export function selectChunkIndex(
  chunks: readonly RunnerChunk[],
  ceiling: number,
  rng: () => number,
): number {
  const eligible: number[] = [];
  for (const [index, chunk] of chunks.entries()) {
    if (chunk.difficulty <= ceiling) eligible.push(index);
  }
  let pool = eligible;
  if (pool.length === 0) {
    const easiest = Math.min(...chunks.map((chunk) => chunk.difficulty));
    pool = chunks.flatMap((chunk, index) => (chunk.difficulty === easiest ? [index] : []));
  }
  return pool[Math.min(pool.length - 1, Math.floor(rng() * pool.length))];
}

function streamChunk(chunk: RunnerChunk, startColumn: number): StreamedChunk {
  return Object.freeze({
    segmentId: chunk.segmentId,
    difficulty: chunk.difficulty,
    startColumn,
    width: chunk.occupancy[0].length,
    occupancy: chunk.occupancy,
    hazards: Object.freeze(
      chunk.hazards.map((hazard) =>
        Object.freeze({ propId: hazard.propId, worldColumn: startColumn + hazard.column }),
      ),
    ),
    pickups: Object.freeze(
      chunk.pickups.map((pickup) =>
        Object.freeze({
          itemId: pickup.itemId,
          worldColumn: startColumn + pickup.column,
          row: pickup.row,
        }),
      ),
    ),
  });
}

/** Append chunks until the window covers every column through `throughColumn`. */
export function streamAhead(
  stream: SegmentStream,
  catalog: readonly RunnerChunk[],
  ceiling: number,
  rng: () => number,
  throughColumn: number,
): void {
  while (stream.nextColumn <= throughColumn) {
    const chunk = catalog[selectChunkIndex(catalog, ceiling, rng)];
    stream.chunks.push(streamChunk(chunk, stream.nextColumn));
    stream.nextColumn += chunk.occupancy[0].length;
  }
}

/** Drop chunks that end strictly before `beforeColumn`. */
export function dropBehind(stream: SegmentStream, beforeColumn: number): void {
  while (stream.chunks.length > 0) {
    const first = stream.chunks[0];
    if (first.startColumn + first.width >= beforeColumn) return;
    stream.chunks.shift();
  }
}

export function chunkAt(stream: SegmentStream, worldColumn: number): StreamedChunk | null {
  for (const chunk of stream.chunks) {
    if (worldColumn >= chunk.startColumn && worldColumn < chunk.startColumn + chunk.width) {
      return chunk;
    }
  }
  return null;
}

/**
 * The row `worldColumn` stands on, or null over a pit.
 *
 * Asking about a column outside the retained window is a streaming-contract
 * violation, not a pit, and is refused so the bug surfaces where it happened
 * rather than as an avatar quietly falling through unstreamed ground.
 */
export function surfaceRowAt(stream: SegmentStream, worldColumn: number): number | null {
  const chunk = chunkAt(stream, worldColumn);
  if (chunk === null) {
    throw new Error(`world column ${worldColumn} is outside the streamed window`);
  }
  return bottomContiguousSurfaceRow(chunk.occupancy, worldColumn - chunk.startColumn);
}

/** Every hazard placement currently inside the retained window. */
export function streamedHazards(stream: SegmentStream): readonly StreamedHazard[] {
  return stream.chunks.flatMap((chunk) => chunk.hazards);
}

/** Every pickup placement currently inside the retained window. */
export function streamedPickups(stream: SegmentStream): readonly StreamedPickup[] {
  return stream.chunks.flatMap((chunk) => chunk.pickups);
}

/**
 * The whole retained window as one boolean occupancy grid, for terrain
 * drawing. Row-major like the authored occupancy: grid[row][column], with
 * column 0 at `startColumn`.
 */
/**
 * The streaming system: keep the window covering everything the camera and
 * the physics can reach this frame — well ahead of the avatar, so the one
 * feedback read in the frame (the avatar sampling last frame's window) can
 * never reach unstreamed ground.
 */
export function createSegmentsSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/segments",
    contractVersion: "segments-system-v1",
    reads: ["difficulty", "avatar"],
    writes: ["segments"],
    update(world) {
      const ahead = Math.ceil(world.avatar.distanceColumns) + world.config.streamAheadColumns;
      streamAhead(
        world.segments,
        world.config.chunks,
        world.difficulty.ceiling,
        world.run.rng,
        ahead,
      );
      dropBehind(
        world.segments,
        Math.floor(world.avatar.distanceColumns) - world.config.keepBehindColumns,
      );
    },
  };
}

export function windowOccupancyGrid(stream: SegmentStream): {
  readonly startColumn: number;
  readonly grid: readonly (readonly boolean[])[];
} {
  const first = stream.chunks[0];
  if (!first) return { startColumn: 0, grid: [] };
  const grid: boolean[][] = Array.from({ length: stream.rows }, () => []);
  for (const chunk of stream.chunks) {
    for (let row = 0; row < stream.rows; row += 1) {
      for (let column = 0; column < chunk.width; column += 1) {
        grid[row].push(chunk.occupancy[row][column] === "1");
      }
    }
  }
  return { startColumn: first.startColumn, grid };
}

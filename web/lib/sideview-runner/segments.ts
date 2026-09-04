// Windowed chunk streaming: the endless track as a finite sliding window.
//
// The manifest carries a catalog of interchangeable chunks; the run is an
// unbounded sequence drawn from it. Nothing here touches Phaser: the stream
// is plain data — appended ahead of the camera, dropped behind it — and the
// physics asks it one question, "what row does this world column stand on".
// Chunk choice goes through the injected RNG, so a seed reproduces a track.

import { bottomContiguousSurfaceRow, type RunnerChunk } from "./contract";
import { rampProfile } from "./difficulty";
import type { GameSystem } from "@/lib/kernel/systems";
import { encounterWantsArena } from "./encounter";
import type { RunnerWorld } from "./world";

export interface StreamedHazard {
  readonly propId: string;
  readonly worldColumn: number;
  readonly anchor: "surface" | "overhead";
  readonly clearanceRows: number | null;
}

export interface StreamedPickup {
  readonly itemId: string;
  readonly worldColumn: number;
  readonly row: number;
}

export interface StreamedChunk {
  readonly segmentId: string;
  readonly difficulty: number;
  /** What this chunk is for; the encounter director reads it off the window. */
  readonly role: "run" | "arena";
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
  /** Catalog index of the most recently appended chunk, for anti-repeat. */
  lastChunkIndex: number | null;
  /** Appends since the last forced breather; the rest cadence's counter. */
  appendsSinceRest: number;
}

export function createSegmentStream(rows: number, walkSurfaceRow: number): SegmentStream {
  return {
    rows,
    walkSurfaceRow,
    chunks: [],
    nextColumn: 0,
    lastChunkIndex: null,
    appendsSinceRest: 0,
  };
}

/** How the stream picks: the band, the anti-repeat, and the rest cadence. */
export interface ChunkSelection {
  readonly ceiling: number;
  /** Chunks below this rank have aged out of the pool; defaults to 1. */
  readonly floor?: number;
  /** Every this-many appends, one catalog-easiest breather is forced. */
  readonly restEveryAppends?: number;
  /**
   * When set, every append streams this chunk verbatim.
   *
   * The encounter's floor, back to back for as long as the fight lasts. It
   * spends no randomness and leaves the anti-repeat and the rest cadence
   * exactly where they were, so the ordinary track resumes on the beat it
   * would have reached had the fight not happened - an encounter interrupts
   * the run without rewriting its pacing.
   */
  readonly arena?: RunnerChunk | null;
}

/**
 * Pick the next chunk: uniform among those inside the difficulty band, never
 * the immediately previous one unless nothing else is eligible. A catalog
 * whose whole band is empty still has to produce track, so the fallbacks
 * widen — first to everything under the ceiling, then to the catalog's
 * easiest rank — rather than refusing mid-run.
 */
export function selectChunkIndex(
  chunks: readonly RunnerChunk[],
  selection: ChunkSelection,
  rng: () => number,
  previousIndex: number | null = null,
): number {
  const floor = selection.floor ?? 1;
  const banded: number[] = [];
  const underCeiling: number[] = [];
  for (const [index, chunk] of chunks.entries()) {
    if (chunk.difficulty <= selection.ceiling) {
      underCeiling.push(index);
      if (chunk.difficulty >= floor) banded.push(index);
    }
  }
  let pool = banded.length > 0 ? banded : underCeiling;
  if (pool.length === 0) {
    const easiest = Math.min(...chunks.map((chunk) => chunk.difficulty));
    pool = chunks.flatMap((chunk, index) => (chunk.difficulty === easiest ? [index] : []));
  }
  if (previousIndex !== null && pool.length > 1) {
    const varied = pool.filter((index) => index !== previousIndex);
    if (varied.length > 0) pool = varied;
  }
  return pool[Math.min(pool.length - 1, Math.floor(rng() * pool.length))];
}

/** The forced breather: the catalog's easiest rank, anti-repeat still applied. */
function selectRestIndex(
  chunks: readonly RunnerChunk[],
  rng: () => number,
  previousIndex: number | null,
): number {
  const easiest = Math.min(...chunks.map((chunk) => chunk.difficulty));
  return selectChunkIndex(chunks, { ceiling: easiest, floor: easiest }, rng, previousIndex);
}

function streamChunk(chunk: RunnerChunk, startColumn: number): StreamedChunk {
  return Object.freeze({
    segmentId: chunk.segmentId,
    difficulty: chunk.difficulty,
    role: chunk.role ?? "run",
    startColumn,
    width: chunk.occupancy[0].length,
    occupancy: chunk.occupancy,
    hazards: Object.freeze(
      chunk.hazards.map((hazard) =>
        Object.freeze({
          propId: hazard.propId,
          worldColumn: startColumn + hazard.column,
          anchor: hazard.anchor,
          clearanceRows: hazard.clearanceRows,
        }),
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
  selection: ChunkSelection,
  rng: () => number,
  throughColumn: number,
): void {
  const restEvery = selection.restEveryAppends ?? Number.POSITIVE_INFINITY;
  while (stream.nextColumn <= throughColumn) {
    if (selection.arena) {
      stream.chunks.push(streamChunk(selection.arena, stream.nextColumn));
      stream.nextColumn += selection.arena.occupancy[0].length;
      continue;
    }
    const resting = stream.appendsSinceRest + 1 >= restEvery;
    const index = resting
      ? selectRestIndex(catalog, rng, stream.lastChunkIndex)
      : selectChunkIndex(catalog, selection, rng, stream.lastChunkIndex);
    const chunk = catalog[index];
    stream.chunks.push(streamChunk(chunk, stream.nextColumn));
    stream.nextColumn += chunk.occupancy[0].length;
    stream.lastChunkIndex = index;
    stream.appendsSinceRest = resting ? 0 : stream.appendsSinceRest + 1;
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
    contractVersion: "segments-system-v3",
    reads: ["difficulty", "avatar", "encounter"],
    writes: ["segments"],
    update(world) {
      const profile = rampProfile(world.config.rampProfile);
      const ahead = Math.ceil(world.avatar.distanceColumns) + world.config.streamAheadColumns;
      // While a fight is on the way or under way the stream feeds the arena
      // instead of drawing from the catalog. The director asks; this decides
      // nothing about when.
      const arena = encounterWantsArena(world) ? world.config.arenaChunk : null;
      streamAhead(
        world.segments,
        world.config.chunks,
        {
          ceiling: world.difficulty.ceiling,
          floor: world.difficulty.floor,
          restEveryAppends: profile.restEveryAppends,
          arena,
        },
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

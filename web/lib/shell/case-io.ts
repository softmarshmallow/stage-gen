// Server-side helper: read one case and the leaves its beats name.
//
// A case is published beside the runs it chains, as `out/<tag>/case.json`, and
// each beat names the run that produced its leaf. The shell locates and
// validates; it never generates, and it never invents a beat a document did not
// declare.
//
// Every leaf is loaded up front rather than one at a time. The alternative is an
// endpoint the client calls when it crosses a beat boundary, which buys a smaller
// first payload and pays for it with a loading state in the middle of a scene -
// the one place in a visual novel where a spinner is unforgivable. An episode is
// a handful of beats, so the whole case is small enough to hand over at once.

import { promises as fs } from "node:fs";
import path from "node:path";
import { parseCase, type CaseBeat, type CaseDocument } from "./case";
import { readSceneFixture } from "./dialogue-scene";
import { readRoomManifest } from "./pointclick-room";
import type { DialogueSceneFixture } from "@/lib/dialogue-scene/schema";
import type { RoomManifest } from "@/lib/pointclick/contract";
import { assertSafeOutRoot, isSafeRunTag, OUT_ROOT, runDirFor } from "./runs";

const CASE_NAME = "case.json";

/**
 * One beat with its leaf, or with the reason the leaf could not be read.
 *
 * A case whose fourth beat was generated against a contract this build no longer
 * reads must still play its first three: the shell says which beat is missing and
 * where, rather than refusing the whole episode with one stack trace.
 */
export interface CaseBeatLeaf {
  readonly beat: CaseBeat;
  readonly scene: DialogueSceneFixture | null;
  readonly room: RoomManifest | null;
  readonly error: string | null;
}

export interface PlayableCase {
  readonly tag: string;
  readonly document: CaseDocument;
  readonly leaves: readonly CaseBeatLeaf[];
}

export async function readCaseDocument(tag: string): Promise<CaseDocument | null> {
  if (!isSafeRunTag(tag)) return null;
  let raw: string;
  try {
    raw = await fs.readFile(path.join(runDirFor(tag), CASE_NAME), "utf8");
  } catch {
    return null;
  }
  // A case document that is present and wrong is a contract violation, not a
  // run this build declines to read: it throws rather than reporting "no case".
  return parseCase(JSON.parse(raw) as unknown);
}

export async function readPlayableCase(tag: string): Promise<PlayableCase | null> {
  const document = await readCaseDocument(tag);
  if (document === null) return null;
  const leaves = await Promise.all(document.beats.map(readLeaf));
  return { tag, document, leaves };
}

async function readLeaf(beat: CaseBeat): Promise<CaseBeatLeaf> {
  try {
    if (beat.kind === "scenario") {
      const scene = await readSceneFixture(beat.runTag, beat.scenarioId ?? undefined);
      if (scene === null) {
        return failed(beat, `run ${beat.runTag} carries no scene bundle`);
      }
      return { beat, scene, room: null, error: null };
    }
    const room = await readRoomManifest(beat.runTag);
    if (room === null) {
      return failed(beat, `run ${beat.runTag} carries no room manifest`);
    }
    return { beat, scene: null, room, error: null };
  } catch (error) {
    return failed(beat, error instanceof Error ? error.message : "leaf could not be read");
  }
}

function failed(beat: CaseBeat, reason: string): CaseBeatLeaf {
  return { beat, scene: null, room: null, error: reason };
}


export interface ReadyCase {
  readonly tag: string;
  readonly displayName: string;
  readonly beats: number;
}

/** Every case published under `out/`, for the index. */
export async function listReadyCases(): Promise<ReadyCase[]> {
  if (!(await assertSafeOutRoot())) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const found: ReadyCase[] = [];
  await Promise.all(
    entries.map(async (entry) => {
      if (!entry.isDirectory() || !isSafeRunTag(entry.name)) return;
      try {
        const document = await readCaseDocument(entry.name);
        if (document === null) return;
        found.push({
          tag: entry.name,
          displayName: document.displayName,
          beats: document.beats.length,
        });
      } catch {
        // A case document this build cannot read is not a playable case. The
        // run viewer still lists the run; only the play link is withheld.
      }
    }),
  );
  return found.sort((left, right) => left.tag.localeCompare(right.tag));
}

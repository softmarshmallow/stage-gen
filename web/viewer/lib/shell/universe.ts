// Server-side helper: read one universe gallery run, wherever its root is.
//
// The shell is a consumer. It locates and validates paths, parses each
// document against its own contract, and never generates: a gallery is
// produced by `stage-gen run universe --phase gallery` and only read here.
//
// One gallery page needs three kinds of document — the manifest, the admitted
// universe the manifest names, and one record per entity — so this module owns
// composing them into the single value the route renders from.

import {
  type AdmittedUniverse,
  type EntityRecord,
  GALLERY_MANIFEST_KIND,
  type GalleryManifest,
  parseAdmittedUniverse,
  parseEntityRecord,
  parseGalleryManifest,
} from "@/lib/universe/contract";
import { viewLocation } from "./execution-view";
import { readRunManifestDocument } from "./manifest-io";
import { readRunDocument } from "./run-json";
import type { RunRef } from "./run-ref";

/**
 * A manifest published under any other identity is not a universe gallery
 * here, exactly as an absent one is not. A manifest that claims this identity
 * and then fails validation still throws, because that is a contract violation
 * rather than a run this build does not read.
 */
export async function readUniverseManifest(
  run: RunRef,
): Promise<GalleryManifest | null> {
  const document = await readRunManifestDocument(run);
  if (document === null || document.kind !== GALLERY_MANIFEST_KIND) return null;
  return parseGalleryManifest(document.declared);
}

/** Everything one gallery page renders from, read once on the server. */
export interface UniverseGallery {
  readonly run: RunRef;
  readonly manifest: GalleryManifest;
  readonly universe: AdmittedUniverse;
  /** Records by entity id. A branch that produced none is simply absent. */
  readonly records: Readonly<Record<string, EntityRecord>>;
  /**
   * Entity ids whose record exists but could not be read, with the reason.
   *
   * Counted rather than swallowed: a record this build refuses looks exactly
   * like a branch that never produced one, and the difference is a contract
   * change nobody would otherwise notice.
   */
  readonly unreadableRecords: readonly {
    readonly entityId: string;
    readonly reason: string;
  }[];
  /**
   * Whether this run also carries an execution view, and so has a graph to open.
   *
   * A gallery and a trace are separate documents: a run reconstructed from a
   * package has the first and not the second. The viewer offers the run-view
   * link only when there is something behind it.
   */
  readonly hasExecutionView: boolean;
}

async function readEntityRecord(
  run: RunRef,
  ref: string,
): Promise<EntityRecord | null> {
  const read = await readRunDocument(run, ref, {
    label: "universe entity record",
    noun: "entity record",
  });
  if (read === null) return null;
  return parseEntityRecord(read.document);
}

/**
 * Compose one gallery, or null when the run is not a universe gallery.
 *
 * A missing or unreadable entity record is not fatal: the manifest already
 * carries a terminal status for every entity precisely so a gallery survives
 * the branches that failed, and the viewer says so per card.
 */
export async function readUniverseGallery(
  run: RunRef,
): Promise<UniverseGallery | null> {
  const manifest = await readUniverseManifest(run);
  if (!manifest) return null;

  const read = await readRunDocument(run, manifest.inputs.universePath, {
    label: "admitted universe",
    noun: "admitted universe",
  });
  if (read === null) {
    throw new Error(
      `this run does not carry ${manifest.inputs.universePath}; re-export the gallery`,
    );
  }
  const universe = parseAdmittedUniverse(read.document);

  type Attempt =
    | {
        readonly ok: true;
        readonly entityId: string;
        readonly record: EntityRecord;
      }
    | { readonly ok: false; readonly entityId: string; readonly reason: string }
    | null;

  const attempts: readonly Attempt[] = await Promise.all(
    manifest.entities.map(async (entry): Promise<Attempt> => {
      if (!entry.record) return null;
      try {
        const parsed = await readEntityRecord(run, entry.record);
        return parsed === null
          ? null
          : { ok: true, entityId: entry.entityId, record: parsed };
      } catch (error) {
        return {
          ok: false,
          entityId: entry.entityId,
          reason: error instanceof Error ? error.message : String(error),
        };
      }
    }),
  );

  const records: Record<string, EntityRecord> = {};
  const unreadableRecords: { entityId: string; reason: string }[] = [];
  for (const attempt of attempts) {
    if (attempt === null) continue;
    if (attempt.ok) records[attempt.entityId] = attempt.record;
    else
      unreadableRecords.push({
        entityId: attempt.entityId,
        reason: attempt.reason,
      });
  }

  const view = await viewLocation(run).catch(() => null);

  return {
    run,
    manifest,
    universe,
    records,
    unreadableRecords,
    hasExecutionView: view !== null,
  };
}

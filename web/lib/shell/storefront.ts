// Server-side helper: read and enumerate storefront runs under out/.
//
// The shell is a consumer. It locates and validates paths, parses each document
// against its own contract, and never generates: a storefront is produced by
// `stage-gen storefront generate` and only read here.
//
// A storefront publishes no runtime manifest — nothing plays it — so this
// module locates a run by its package inventory instead of by manifest.json.

import { promises as fs } from "node:fs";
import {
  INVENTORY_KIND,
  parseInventory,
  parseListing,
  parseSurfaceRecord,
  type StoreListing,
  type StorefrontInventory,
  type SurfaceRecord,
} from "@/lib/storefront/contract";
import { EXECUTION_VIEW_FILENAME } from "./execution-view";
import { readRunDocument } from "./run-json";
import { assertSafeOutRoot, isSafeRunTag, OUT_ROOT } from "./runs";

const INVENTORY_REF = "package/inventory.json";

/**
 * A document published under any other identity is not a storefront inventory
 * here, exactly as an absent one is not. One that claims this identity and then
 * fails validation still throws, because that is a contract violation rather
 * than a run this build does not read.
 */
export async function readStorefrontInventory(
  tag: string,
): Promise<StorefrontInventory | null> {
  const read = await readRunDocument(tag, INVENTORY_REF, {
    label: "storefront inventory",
    noun: "inventory",
  });
  if (read === null) return null;
  const document = read.document as Record<string, unknown>;
  if (document?.kind !== INVENTORY_KIND) return null;
  return parseInventory(document);
}

/** One row of the storefront index: enough to choose a run, nothing more. */
export interface StorefrontRunListEntry {
  readonly tag: string;
  readonly storefrontId: string;
  readonly displayName: string;
  readonly surfaceCount: number;
  readonly admitted: number;
  readonly rejected: number;
  /** The icon, when the run drew one: the one image a list row is worth showing. */
  readonly iconRef: string | null;
}

export async function listStorefrontRuns(): Promise<
  readonly StorefrontRunListEntry[]
> {
  if (!(await assertSafeOutRoot())) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const rows: StorefrontRunListEntry[] = [];
  await Promise.all(
    entries.map(async (entry) => {
      if (!entry.isDirectory()) return;
      const tag = entry.name;
      if (!isSafeRunTag(tag)) return;
      try {
        const inventory = await readStorefrontInventory(tag);
        if (!inventory) return;
        const icon = inventory.surfaces.find(
          (surface) => surface.surfaceKind === "app_icon",
        );
        rows.push({
          tag,
          storefrontId: inventory.storefrontId,
          displayName: inventory.displayName,
          surfaceCount: inventory.surfaces.length,
          admitted: inventory.admitted,
          rejected: inventory.rejected,
          iconRef: icon?.artifactRef ?? null,
        });
      } catch {
        // An invalid inventory is not a listable storefront. The detail route
        // still surfaces the refusal for anyone who addresses the tag.
      }
    }),
  );
  rows.sort((a, b) => a.tag.localeCompare(b.tag));
  return rows;
}

/** Everything one storefront page renders from, read once on the server. */
export interface Storefront {
  readonly tag: string;
  readonly inventory: StorefrontInventory;
  readonly listing: StoreListing;
  /** Records by surface id. A branch that produced none is simply absent. */
  readonly records: Readonly<Record<string, SurfaceRecord>>;
  /**
   * Surface ids whose record exists but could not be read, with the reason.
   *
   * Counted rather than swallowed: a record this build refuses looks exactly
   * like a branch that never produced one, and the difference is a contract
   * change nobody would otherwise notice.
   */
  readonly unreadableRecords: readonly {
    readonly surfaceId: string;
    readonly reason: string;
  }[];
  /** Whether this run also carries an execution view, and so appears at /runs. */
  readonly hasExecutionView: boolean;
}

/**
 * Compose one storefront, or null when the tag is not a storefront run.
 *
 * A missing or unreadable surface record is not fatal: the inventory already
 * carries a terminal status for every surface precisely so a storefront
 * survives the branches that failed, and the page says so per surface.
 */
export async function readStorefront(tag: string): Promise<Storefront | null> {
  const inventory = await readStorefrontInventory(tag);
  if (!inventory) return null;

  const listingRead = await readRunDocument(tag, inventory.listingRef, {
    label: "store listing",
    noun: "listing",
  });
  if (listingRead === null) {
    throw new Error(
      `this run does not carry ${inventory.listingRef}; regenerate the storefront`,
    );
  }
  const listing = parseListing(listingRead.document);

  type Attempt =
    | { readonly ok: true; readonly surfaceId: string; readonly record: SurfaceRecord }
    | { readonly ok: false; readonly surfaceId: string; readonly reason: string }
    | null;

  const attempts: readonly Attempt[] = await Promise.all(
    inventory.surfaces.map(async (surface): Promise<Attempt> => {
      const ref = `package/surfaces/${surface.surfaceId}.json`;
      try {
        const read = await readRunDocument(tag, ref, {
          label: "storefront surface record",
          noun: "surface record",
        });
        if (read === null) return null;
        return {
          ok: true,
          surfaceId: surface.surfaceId,
          record: parseSurfaceRecord(read.document),
        };
      } catch (error) {
        return {
          ok: false,
          surfaceId: surface.surfaceId,
          reason: error instanceof Error ? error.message : String(error),
        };
      }
    }),
  );

  const records: Record<string, SurfaceRecord> = {};
  const unreadableRecords: { surfaceId: string; reason: string }[] = [];
  for (const attempt of attempts) {
    if (attempt === null) continue;
    if (attempt.ok) records[attempt.surfaceId] = attempt.record;
    else
      unreadableRecords.push({
        surfaceId: attempt.surfaceId,
        reason: attempt.reason,
      });
  }

  const view = await readRunDocument(tag, EXECUTION_VIEW_FILENAME, {
    label: "execution view",
    noun: "execution view",
  }).catch(() => null);

  return {
    tag,
    inventory,
    listing,
    records,
    unreadableRecords,
    hasExecutionView: view !== null,
  };
}

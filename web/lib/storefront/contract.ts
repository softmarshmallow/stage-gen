/**
 * The storefront contracts the viewer reads: `storefront-inventory-v1`, the
 * listing copy it names (`storefront-listing-v1`), and the per-surface record
 * (`storefront-surface-record-v1`).
 *
 * Strict, hand-written validating parsers in the house style: an unknown kind
 * is refused with a re-generate hint, shapes are checked field by field, and
 * wire `lower_snake_case` is translated to runtime camelCase here — this module
 * is the boundary, so nothing downstream spells a field two ways.
 *
 * The viewer reads three documents and never the graph: a finished storefront
 * is finished work, and the run view at /runs/<tag> already owns how it was
 * produced.
 */

export const INVENTORY_KIND = "storefront-inventory-v1";
export const LISTING_KIND = "storefront-listing-v1";
export const SURFACE_RECORD_KIND = "storefront-surface-record-v1";
export const STOREFRONT_SCHEMA_VERSION = 1;

export const STOREFRONT_REFUSAL =
  "unsupported storefront run; regenerate it with a current stage-gen " +
  "(stage-gen storefront generate)";

/**
 * The surface kinds, in the order a storefront presents them rather than the
 * order a package happens to declare them: the icon is the thing a person sees
 * first, the stills are the body, the banner is the header behind both.
 */
export const SURFACE_KIND_ORDER = [
  "app_icon",
  "store_still_portrait",
  "store_still_landscape",
  "feature_graphic",
] as const;
export type SurfaceKind = (typeof SURFACE_KIND_ORDER)[number];

/** The four named grades one surface review returns, in reading order. */
export const REVIEW_CHECKS = [
  "fitness",
  "direction_fidelity",
  "legibility",
  "free_of_lettering",
] as const;
export type ReviewCheck = (typeof REVIEW_CHECKS)[number];

export type Grade = "pass" | "fail";

function object(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function array(value: unknown, label: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function count(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return value;
}

function grade(value: unknown, label: string): Grade {
  if (value !== "pass" && value !== "fail") {
    throw new Error(`${label} must be pass or fail`);
  }
  return value;
}

function surfaceKind(value: unknown, label: string): SurfaceKind {
  const declared = text(value, label);
  const known = SURFACE_KIND_ORDER.find((kind) => kind === declared);
  if (known === undefined) throw new Error(`${label} names an unknown surface kind`);
  return known;
}

/**
 * A path a document supplies is never joined blindly: the asset route encodes
 * each segment, but a `..` segment would still address another run's bytes.
 */
function artifactRef(value: unknown, label: string): string {
  const ref = text(value, label);
  if (ref.startsWith("/") || ref.split("/").some((part) => part === "" || part === "." || part === "..")) {
    throw new Error(`${label} must be a run-relative path with no traversal`);
  }
  return ref;
}

function identity(document: Record<string, unknown>, kind: string): void {
  if (document.kind !== kind || document.schema_version !== STOREFRONT_SCHEMA_VERSION) {
    throw new Error(STOREFRONT_REFUSAL);
  }
}

export interface InventorySurface {
  readonly surfaceId: string;
  readonly surfaceKind: SurfaceKind;
  readonly artifactRef: string;
  readonly artifactSha256: string;
  readonly shipSize: string;
  readonly status: string;
}

export interface StorefrontInventory {
  readonly storefrontId: string;
  readonly displayName: string;
  readonly appName: string;
  readonly surfaces: readonly InventorySurface[];
  readonly admitted: number;
  readonly rejected: number;
  readonly listingRef: string;
  readonly references: readonly {
    readonly referenceId: string;
    readonly artifactRef: string;
  }[];
  /**
   * Always false on a generated run, and read rather than assumed: a page that
   * showed this work as approved would be making a claim the recipe cannot.
   */
  readonly publicationAuthorized: boolean;
}

export function parseInventory(value: unknown): StorefrontInventory {
  const root = object(value, "storefront inventory");
  identity(root, INVENTORY_KIND);
  return Object.freeze({
    storefrontId: text(root.storefront_id, "storefront_id"),
    displayName: text(root.display_name, "display_name"),
    appName: text(root.app_name, "app_name"),
    surfaces: Object.freeze(
      array(root.surfaces, "surfaces").map((entry, index) => {
        const surface = object(entry, `surfaces[${index}]`);
        return Object.freeze({
          surfaceId: text(surface.surface_id, `surfaces[${index}].surface_id`),
          surfaceKind: surfaceKind(surface.surface_kind, `surfaces[${index}].surface_kind`),
          artifactRef: artifactRef(surface.artifact_ref, `surfaces[${index}].artifact_ref`),
          artifactSha256: text(surface.artifact_sha256, `surfaces[${index}].artifact_sha256`),
          shipSize: text(surface.ship_size, `surfaces[${index}].ship_size`),
          status: text(surface.status, `surfaces[${index}].status`),
        });
      }),
    ),
    admitted: count(root.admitted, "admitted"),
    rejected: count(root.rejected, "rejected"),
    listingRef: artifactRef(root.listing_ref, "listing_ref"),
    references: Object.freeze(
      array(root.references, "references").map((entry, index) => {
        const reference = object(entry, `references[${index}]`);
        return Object.freeze({
          referenceId: text(reference.reference_id, `references[${index}].reference_id`),
          artifactRef: artifactRef(reference.artifact_ref, `references[${index}].artifact_ref`),
        });
      }),
    ),
    publicationAuthorized: root.publication_authorized === true,
  });
}

export interface StoreListing {
  readonly appName: string;
  readonly subtitle: string;
  readonly shortDescription: string;
  readonly longDescription: string;
  readonly keywords: readonly string[];
  readonly promotionalText: string;
}

export function parseListing(value: unknown): StoreListing {
  const root = object(value, "store listing");
  identity(root, LISTING_KIND);
  return Object.freeze({
    appName: text(root.app_name, "app_name"),
    subtitle: text(root.subtitle, "subtitle"),
    shortDescription: text(root.short_description, "short_description"),
    longDescription: text(root.long_description, "long_description"),
    keywords: Object.freeze(
      array(root.keywords, "keywords").map((entry, index) => text(entry, `keywords[${index}]`)),
    ),
    promotionalText: text(root.promotional_text, "promotional_text"),
  });
}

export interface SurfaceReview {
  readonly verdict: Grade;
  readonly checks: Readonly<Record<ReviewCheck, Grade>>;
  readonly notes: readonly string[];
}

export interface SurfaceRecord {
  readonly surfaceId: string;
  readonly surfaceKind: SurfaceKind;
  readonly title: string;
  /** `generated` today; `capture` is declared in the package and refused while planning. */
  readonly source: string;
  readonly brief: string;
  readonly shipSize: string;
  readonly drawSize: string;
  /** Which draw of this surface the run asked for; 0 unless it was rerolled. */
  readonly draw: number;
  readonly artifactRef: string;
  readonly bytes: number;
  readonly review: SurfaceReview;
  readonly status: string;
}

export function parseSurfaceRecord(value: unknown): SurfaceRecord {
  const root = object(value, "surface record");
  identity(root, SURFACE_RECORD_KIND);
  const review = object(root.review, "review");
  const checks = Object.fromEntries(
    REVIEW_CHECKS.map((check) => [check, grade(review[check], `review.${check}`)]),
  ) as Record<ReviewCheck, Grade>;
  return Object.freeze({
    surfaceId: text(root.surface_id, "surface_id"),
    surfaceKind: surfaceKind(root.surface_kind, "surface_kind"),
    title: text(root.title, "title"),
    source: text(root.source, "source"),
    brief: text(root.brief, "brief"),
    shipSize: text(root.ship_size, "ship_size"),
    drawSize: text(root.draw_size, "draw_size"),
    draw: count(root.draw, "draw"),
    artifactRef: artifactRef(root.artifact_ref, "artifact_ref"),
    bytes: count(root.bytes, "bytes"),
    review: Object.freeze({
      verdict: grade(review.verdict, "review.verdict"),
      checks: Object.freeze(checks),
      notes: Object.freeze(
        array(review.notes, "review.notes").map((entry, index) =>
          text(entry, `review.notes[${index}]`),
        ),
      ),
    }),
    status: text(root.status, "status"),
  });
}

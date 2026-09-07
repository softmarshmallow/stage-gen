// The storefront contracts refuse what they do not understand, and translate
// what they do. Fixtures are hand-authored to the shape the producer writes.

import { describe, expect, test } from "bun:test";
import {
  parseInventory,
  parseListing,
  parseSurfaceRecord,
  STOREFRONT_REFUSAL,
} from "./contract";

function inventoryDocument(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: "storefront-inventory-v1",
    storefront_id: "ember_hollow",
    display_name: "Ember Hollow",
    app_name: "Ember Hollow",
    surfaces: [
      {
        surface_id: "icon",
        surface_kind: "app_icon",
        artifact_ref: "package/surfaces/icon.png",
        artifact_sha256: "a".repeat(64),
        ship_size: "1024x1024",
        status: "pass",
      },
    ],
    admitted: 1,
    rejected: 0,
    listing_ref: "package/listing.json",
    references: [
      { reference_id: "style_plate", artifact_ref: "references/plate.png" },
    ],
    publication_authorized: false,
    ...overrides,
  };
}

function recordDocument(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: "storefront-surface-record-v1",
    surface_id: "icon",
    surface_kind: "app_icon",
    title: "App icon",
    source: "generated",
    brief: "One lantern against dusk.",
    ship_size: "1024x1024",
    draw_size: "1024x1024",
    draw: 0,
    artifact_ref: "package/surfaces/icon.png",
    artifact_sha256: "a".repeat(64),
    bytes: 1024,
    review: {
      schema_version: 1,
      kind: "storefront-surface-review-v1",
      surface_id: "icon",
      fitness: "pass",
      direction_fidelity: "pass",
      legibility: "pass",
      free_of_lettering: "pass",
      verdict: "pass",
      notes: ["One silhouette, no lettering."],
    },
    status: "pass",
    publication_authorized: false,
    ...overrides,
  };
}

describe("the inventory", () => {
  test("translates the wire shape into runtime names", () => {
    const inventory = parseInventory(inventoryDocument());
    expect(inventory.storefrontId).toBe("ember_hollow");
    expect(inventory.appName).toBe("Ember Hollow");
    expect(inventory.surfaces[0].surfaceKind).toBe("app_icon");
    expect(inventory.surfaces[0].shipSize).toBe("1024x1024");
    expect(inventory.publicationAuthorized).toBe(false);
  });

  test("refuses another document's kind with a regenerate hint", () => {
    expect(() =>
      parseInventory(inventoryDocument({ kind: "universe-gallery-manifest-v1" })),
    ).toThrow(STOREFRONT_REFUSAL);
  });

  test("refuses a schema version this build does not read", () => {
    expect(() => parseInventory(inventoryDocument({ schema_version: 2 }))).toThrow(
      STOREFRONT_REFUSAL,
    );
  });

  test("refuses a surface kind outside the closed set", () => {
    const document = inventoryDocument();
    (document.surfaces as Record<string, unknown>[])[0].surface_kind = "wallpaper";
    expect(() => parseInventory(document)).toThrow("unknown surface kind");
  });

  test("refuses an artifact path that climbs out of the run", () => {
    // The asset route encodes each segment, so a traversal would not escape the
    // filesystem — but it would still address another run's bytes, and a
    // document is not trusted to name one.
    const document = inventoryDocument();
    (document.surfaces as Record<string, unknown>[])[0].artifact_ref =
      "../other-run/icon.png";
    expect(() => parseInventory(document)).toThrow("no traversal");
  });

  test("refuses an absolute artifact path", () => {
    const document = inventoryDocument();
    (document.surfaces as Record<string, unknown>[])[0].artifact_ref = "/etc/passwd";
    expect(() => parseInventory(document)).toThrow("no traversal");
  });

  test("treats a missing publication flag as unauthorized", () => {
    const document = inventoryDocument();
    delete document.publication_authorized;
    expect(parseInventory(document).publicationAuthorized).toBe(false);
  });
});

describe("the listing", () => {
  test("carries every field the page renders", () => {
    const listing = parseListing({
      schema_version: 1,
      kind: "storefront-listing-v1",
      storefront_id: "ember_hollow",
      app_name: "Ember Hollow",
      subtitle: "Survive one quiet winter",
      short_description: "Forage, craft, and tend a small fire.",
      long_description: "A quiet survival game.",
      keywords: ["survival", "winter"],
      promotional_text: "Autumn gives way to snow.",
    });
    expect(listing.appName).toBe("Ember Hollow");
    expect(listing.keywords).toEqual(["survival", "winter"]);
    expect(listing.promotionalText).toBe("Autumn gives way to snow.");
  });

  test("refuses an empty required field", () => {
    expect(() =>
      parseListing({
        schema_version: 1,
        kind: "storefront-listing-v1",
        app_name: "",
        subtitle: "x",
        short_description: "x",
        long_description: "x",
        keywords: ["x"],
        promotional_text: "x",
      }),
    ).toThrow("app_name");
  });
});

describe("the surface record", () => {
  test("carries both canvases and every named grade", () => {
    const record = parseSurfaceRecord(recordDocument());
    expect(record.drawSize).toBe("1024x1024");
    expect(record.shipSize).toBe("1024x1024");
    expect(record.review.verdict).toBe("pass");
    expect(record.review.checks.free_of_lettering).toBe("pass");
    expect(record.review.notes).toHaveLength(1);
  });

  test("keeps a refusal readable rather than dropping it", () => {
    // A rejection is a result: the page shows the surface and says it failed.
    const document = recordDocument();
    const review = document.review as Record<string, unknown>;
    review.legibility = "fail";
    review.verdict = "fail";
    const record = parseSurfaceRecord(document);
    expect(record.review.verdict).toBe("fail");
    expect(record.review.checks.legibility).toBe("fail");
  });

  test("refuses a grade outside pass and fail", () => {
    const document = recordDocument();
    (document.review as Record<string, unknown>).fitness = "maybe";
    expect(() => parseSurfaceRecord(document)).toThrow("must be pass or fail");
  });

  test("refuses a negative draw index", () => {
    expect(() => parseSurfaceRecord(recordDocument({ draw: -1 }))).toThrow("draw");
  });
});

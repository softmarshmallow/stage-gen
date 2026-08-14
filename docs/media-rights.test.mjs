import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { validatePublishedMediaRecord } from "./media-rights.mjs";

function fixture(name) {
  return JSON.parse(
    readFileSync(join(import.meta.dirname, "check-fixtures", name), "utf8"),
  );
}

describe("generated-media publication validator", () => {
  test("accepts an artifact-specific approval record without decoding media", () => {
    const value = fixture("media-rights-approved.json");
    expect(validatePublishedMediaRecord(value)).toEqual([]);
  });

  test("rejects unreviewed rights, mismatched facts, and temp source refs", () => {
    const value = fixture("media-rights-unreviewed.json");
    const failures = validatePublishedMediaRecord(value);
    expect(failures).toContain("inventory reviewStatus must be repository-approved");
    expect(failures).toContain("sidecar artifact digest does not match media bytes");
    expect(failures).toContain("sidecar artifact byte size does not match media bytes");
    expect(failures).toContain(
      "sidecar.inputs[0].ref must be a stable non-file identifier",
    );
    expect(failures).toContain("sidecar.rights is required for repository publication");
  });

  test("does not infer generated-media rights from BSD or blanket CC0", () => {
    const bsd = fixture("media-rights-approved.json");
    bsd.sidecar.rights.license_id = "BSD-3-Clause";
    expect(validatePublishedMediaRecord(bsd)).toContain(
      "the repository source license cannot be inherited by generated media",
    );

    const cc0 = fixture("media-rights-approved.json");
    cc0.sidecar.rights.license_id = "CC0-1.0";
    cc0.sidecar.rights.basis = ["provider provenance only"];
    expect(validatePublishedMediaRecord(cc0)).toContain(
      "CC0 requires an artifact-specific rights-holder dedication basis",
    );

    const provenanceOnly = fixture("media-rights-approved.json");
    provenanceOnly.sidecar.rights.basis = ["provider provenance only"];
    expect(validatePublishedMediaRecord(provenanceOnly)).toContain(
      "sidecar.rights.basis cannot rely only on provider provenance",
    );
  });

  test("requires a role-based listening attestation without a legal name", () => {
    const value = fixture("media-rights-approved.json");
    delete value.entry.listeningReview.authorityBasis;
    value.entry.listeningReview.result = "approved";
    expect(validatePublishedMediaRecord(value)).toContain(
      "inventory listeningReview.authorityBasis is required",
    );
    expect(validatePublishedMediaRecord(value)).toContain(
      "inventory listeningReview.result must record the protected-material finding",
    );
  });
});

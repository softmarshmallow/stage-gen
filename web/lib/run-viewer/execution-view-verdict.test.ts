import { describe, expect, test } from "bun:test";
import { hasVerdictContent, parseReviewVerdict } from "./execution-view-verdict";

describe("parseReviewVerdict", () => {
  test("reads a review-verdict-v1 payload into a renderable shape", () => {
    const verdict = parseReviewVerdict({
      verdict: "reject",
      confidence: 0.82,
      checks: { identity_fidelity: true, style_coherence: false },
      issues: ["the walk cycle drifts off the ground line"],
      evidence: "frames 2-4",
    });
    expect(verdict.outcome).toBe("reject");
    expect(verdict.confidence).toBe(0.82);
    expect(verdict.checks).toEqual([
      { name: "identity_fidelity", passed: true },
      { name: "style_coherence", passed: false },
    ]);
    expect(verdict.issues).toEqual(["the walk cycle drifts off the ground line"]);
    expect(verdict.evidence).toBe("frames 2-4");
    expect(hasVerdictContent(verdict)).toBe(true);
  });

  test("keeps every declared outcome and rejects anything else", () => {
    expect(parseReviewVerdict({ verdict: "accept" }).outcome).toBe("accept");
    expect(parseReviewVerdict({ verdict: "uncertain" }).outcome).toBe("uncertain");
    expect(parseReviewVerdict({ verdict: "maybe" }).outcome).toBeNull();
  });

  test("degrades instead of throwing: this reads an artifact, it does not gate one", () => {
    for (const payload of [null, 42, "text", [], {}, { checks: "no" }, { issues: 3 }]) {
      const verdict = parseReviewVerdict(payload);
      expect(verdict.outcome).toBeNull();
      expect(verdict.checks).toHaveLength(0);
      expect(verdict.issues).toHaveLength(0);
      expect(hasVerdictContent(verdict)).toBe(false);
    }
  });

  test("drops non-boolean checks and non-string issues rather than rendering them", () => {
    const verdict = parseReviewVerdict({
      checks: { real: true, bogus: "yes" },
      issues: ["kept", 7, null],
    });
    expect(verdict.checks).toEqual([{ name: "real", passed: true }]);
    expect(verdict.issues).toEqual(["kept"]);
  });

  test("a rebase reading has no verdict fields and says so", () => {
    // The other artifact the judge view offers: a measurement, not a review.
    const reading = parseReviewVerdict({
      baseline_state: "idle",
      states: { idle: 1.0, walk: 1.08 },
      plate_sha256: "a".repeat(64),
    });
    expect(hasVerdictContent(reading)).toBe(false);
  });
});

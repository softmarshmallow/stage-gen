// Reader for a judge node's answer artifact (review-verdict-v1 and friends).
//
// Deliberately non-throwing: this is a rendering aid over an artifact the
// pipeline has already validated, so an unrecognised payload degrades to "no
// verdict here, use the raw link" rather than taking the inspector down.

export type ReviewOutcome = "accept" | "reject" | "uncertain";

export interface ReviewCheck {
  readonly name: string;
  readonly passed: boolean;
}

export interface ReviewVerdict {
  readonly outcome: ReviewOutcome | null;
  readonly confidence: number | null;
  readonly checks: readonly ReviewCheck[];
  readonly issues: readonly string[];
  readonly evidence: string | null;
}

const OUTCOMES: readonly string[] = ["accept", "reject", "uncertain"];

/** True when the panel has anything worth drawing. */
export function hasVerdictContent(verdict: ReviewVerdict): boolean {
  return (
    verdict.outcome !== null ||
    verdict.confidence !== null ||
    verdict.checks.length > 0 ||
    verdict.issues.length > 0
  );
}

export function parseReviewVerdict(value: unknown): ReviewVerdict {
  const record =
    typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  const rawChecks = record.checks;
  const checks: ReviewCheck[] =
    typeof rawChecks === "object" && rawChecks !== null && !Array.isArray(rawChecks)
      ? Object.entries(rawChecks as Record<string, unknown>)
          .filter(([, passed]) => typeof passed === "boolean")
          .map(([name, passed]) => ({ name, passed: passed === true }))
      : [];
  return Object.freeze({
    outcome:
      typeof record.verdict === "string" && OUTCOMES.includes(record.verdict)
        ? (record.verdict as ReviewOutcome)
        : null,
    confidence:
      typeof record.confidence === "number" && Number.isFinite(record.confidence)
        ? record.confidence
        : null,
    checks: Object.freeze(checks),
    issues: Object.freeze(
      Array.isArray(record.issues)
        ? record.issues.filter((issue): issue is string => typeof issue === "string")
        : [],
    ),
    evidence: typeof record.evidence === "string" ? record.evidence : null,
  });
}

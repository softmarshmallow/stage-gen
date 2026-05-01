// Blind-retry wrapper for AI SDK calls.
//
// Per AGENTS.md: every AI SDK call must be wrapped in a retry. The SDK fails
// randomly — transient network errors, model hiccups, schema-violating
// outputs. A bare call is a latent bug. Default policy: 5 blind retries with
// exponential backoff before surfacing failure.
//
// The helper is "blind" — it does NOT classify errors as
// retryable/non-retryable. By the project's policy any error from the SDK is
// retried until attempts are exhausted, including silent failures (malformed
// JSON, schema mismatch, empty output) that the caller can detect by
// throwing inside the body.
//
// Phase 1: the orchestrator stubs do not actually call the SDK yet, but
// every Phase 2+ generator imports this helper.

export interface RetryOptions {
  /** Number of retries AFTER the first attempt. Default 5 (so 6 attempts total). */
  retries?: number;
  /** Initial backoff in milliseconds. Default 500. */
  initialDelayMs?: number;
  /** Multiplier applied to delay after each failure. Default 2. */
  backoffFactor?: number;
  /** Cap on the per-attempt delay. Default 16_000 (16s). */
  maxDelayMs?: number;
  /** Optional label included in the surfaced error message for debugging. */
  label?: string;
  /** Optional logger; defaults to a no-op. */
  onAttemptFail?: (attempt: number, err: unknown, nextDelayMs: number) => void;
}

const DEFAULTS: Required<Omit<RetryOptions, "label" | "onAttemptFail">> = {
  retries: 5,
  initialDelayMs: 500,
  backoffFactor: 2,
  maxDelayMs: 16_000,
};

export async function withRetry<T>(
  fn: () => Promise<T>,
  opts: RetryOptions = {},
): Promise<T> {
  const cfg = { ...DEFAULTS, ...opts };
  const totalAttempts = cfg.retries + 1;
  let delay = cfg.initialDelayMs;
  let lastErr: unknown;

  for (let attempt = 1; attempt <= totalAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      if (attempt === totalAttempts) break;
      const nextDelay = Math.min(delay, cfg.maxDelayMs);
      opts.onAttemptFail?.(attempt, err, nextDelay);
      await sleep(nextDelay);
      delay = Math.min(delay * cfg.backoffFactor, cfg.maxDelayMs);
    }
  }

  const labelPart = opts.label ? `[${opts.label}] ` : "";
  const cause = errorMessage(lastErr);
  const wrapped = new Error(
    `${labelPart}exhausted ${totalAttempts} attempts; last error: ${cause}`,
  );
  // Preserve the original error as the cause for stack inspection.
  (wrapped as { cause?: unknown }).cause = lastErr;
  throw wrapped;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}

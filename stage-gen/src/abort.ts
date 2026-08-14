export class StageGenTimeoutError extends Error {
  constructor(label: string, timeoutMs: number) {
    super(`${label} timed out after ${timeoutMs}ms`);
    this.name = "StageGenTimeoutError";
  }
}

export interface AbortScope {
  signal: AbortSignal;
  cleanup(): void;
}

export function createAbortScope(options: {
  parent?: AbortSignal;
  timeoutMs?: number;
  label: string;
}): AbortScope {
  const controller = new AbortController();
  const onParentAbort = () => controller.abort(options.parent?.reason ?? new Error("cancelled"));
  if (options.parent?.aborted) onParentAbort();
  else options.parent?.addEventListener("abort", onParentAbort, { once: true });

  const timeout =
    options.timeoutMs && options.timeoutMs > 0
      ? setTimeout(
          () => controller.abort(new StageGenTimeoutError(options.label, options.timeoutMs!)),
          options.timeoutMs,
        )
      : undefined;

  return {
    signal: controller.signal,
    cleanup() {
      if (timeout) clearTimeout(timeout);
      options.parent?.removeEventListener("abort", onParentAbort);
    },
  };
}

export function throwIfAborted(signal?: AbortSignal): void {
  if (!signal?.aborted) return;
  const reason = signal.reason;
  if (reason instanceof Error) throw reason;
  throw new Error(reason ? String(reason) : "cancelled");
}

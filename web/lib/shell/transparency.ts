// Transparency policy for the preview consumer.
//
// A published runtime package always carries canonical straight alpha: the producer
// resolved every transparency strategy before it wrote the package. The consumer's
// only job is to refuse a run that does not state one.

export type PreviewTransparencyPolicy = "canonical-alpha";

export function previewPolicyForRunMode(prepared: boolean): PreviewTransparencyPolicy {
  if (!prepared) {
    throw new Error("preview requires a published prepared-runtime package");
  }
  return "canonical-alpha";
}

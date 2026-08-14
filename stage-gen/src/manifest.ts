import type { TransparencyMode } from "./config.ts";
import type { ArtifactRef } from "./types.ts";

export type TransparencyDerivationKind = "ai-background-removal" | "chroma-key";

export interface ArtifactTransparencyMetadata {
  mode: TransparencyMode;
  canonicalPath: string;
  retainedRawPath: string;
  canonicalProvenancePath: string;
  rawProvenancePath: string;
  derivation: {
    kind: TransparencyDerivationKind;
    sourceSha256?: string;
    outputSha256?: string;
    tool?: { name: string; version: string };
  };
}

/** Opaque artifacts omit `transparency` entirely. */
export interface ArtifactManifestSource extends ArtifactRef {
  transparency?: ArtifactTransparencyMetadata;
}

export interface CanonicalArtifactManifestEntry {
  path: string;
  provenancePath?: string;
  transparency?: ArtifactTransparencyMetadata;
}

/**
 * Project a source/debug artifact record into a consumer manifest. Raw files
 * remain referenced as provenance but never become top-level consumer paths.
 */
export function toCanonicalManifestEntry(
  artifact: ArtifactManifestSource,
): CanonicalArtifactManifestEntry {
  if (!artifact.transparency) {
    return {
      path: artifact.path,
      ...(artifact.provenancePath ? { provenancePath: artifact.provenancePath } : {}),
    };
  }
  return {
    path: artifact.transparency.canonicalPath,
    provenancePath: artifact.transparency.canonicalProvenancePath,
    transparency: artifact.transparency,
  };
}

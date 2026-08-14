import { createHash, randomUUID } from "node:crypto";
import {
  mkdir,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path";
import {
  isPortableArtifactReference,
  parseArtifactRights,
  writeArtifactWithProvenance,
  type ArtifactRights,
} from "@stage-gen/core";
import {
  toCanonicalManifestEntry,
  type ArtifactTransparencyMetadata,
  type CanonicalArtifactManifestEntry,
} from "../../../src/manifest.ts";
import type { TransparencyMode } from "../../../src/config.ts";

const DEFAULT_MUSIC_FALLBACK = resolve(
  import.meta.dir,
  "../assets/music/preview-loop.mp3",
);

export interface ScrollingPreviewManifest {
  schemaVersion: 2;
  recipe: "scrolling-preview";
  tag: string;
  transparencyMode: TransparencyMode;
  artifacts: string[];
  canonicalArtifacts: ScrollingCanonicalArtifactManifestEntry[];
  music: {
    path: string;
    provenancePath: string;
    source: "per-run" | "generated-fallback";
    generationCapability: "generate-music";
    rightsStatus: MusicRightsStatus;
    rightsNoticePath?: string;
  };
}

export type MusicRightsStatus = ArtifactRights["status"] | "unrecorded";

export type ScrollingTransparencyDerivationKind =
  | ArtifactTransparencyMetadata["derivation"]["kind"]
  | "alpha-composite"
  | "png-slice";

export interface DerivedArtifactTransparencyMetadata {
  mode: TransparencyMode;
  canonicalPath: string;
  canonicalProvenancePath: string;
  derivation: {
    kind: ScrollingTransparencyDerivationKind;
    sourceSha256?: string;
    outputSha256?: string;
    tool?: { name: string; version: string };
  };
  lineage: {
    kind: "derived";
    sourcePaths: string[];
    sourceProvenancePaths: string[];
  };
}

export type GeneratedArtifactTransparencyMetadata = ArtifactTransparencyMetadata & {
  lineage: {
    kind: "generated";
    sourcePaths: [string];
    sourceProvenancePaths: [string];
  };
};

export type ScrollingArtifactTransparencyMetadata =
  | GeneratedArtifactTransparencyMetadata
  | DerivedArtifactTransparencyMetadata;

export interface ScrollingCanonicalArtifactManifestEntry
  extends Omit<CanonicalArtifactManifestEntry, "transparency"> {
  transparency?: ScrollingArtifactTransparencyMetadata;
}

export async function writeScrollingPreviewManifest(options: {
  runDir: string;
  tag: string;
  transparencyMode?: TransparencyMode;
  fallbackMusicPath?: string;
}): Promise<{
  manifestPath: string;
  manifestProvenancePath: string;
  musicPath: string;
  musicProvenancePath: string;
  musicSource: "per-run" | "generated-fallback";
  musicRightsStatus: MusicRightsStatus;
  musicNoticePath?: string;
}> {
  await mkdir(options.runDir, { recursive: true });
  const transparencyMode = options.transparencyMode ?? "ai";
  const musicName = `music_${options.tag}.mp3`;
  const musicPath = join(options.runDir, musicName);
  const musicProvenancePath = `${musicPath}.meta.json`;
  const music = await ensureRunMusicPair(
    musicPath,
    options.fallbackMusicPath ?? DEFAULT_MUSIC_FALLBACK,
  );

  const manifestName = `manifest_${options.tag}.json`;
  const manifestPath = join(options.runDir, manifestName);
  const entries = await readdir(options.runDir);
  const artifacts = entries
    .filter(
      (name) =>
        !name.startsWith(".") &&
        name !== manifestName &&
        !name.includes(".raw.png"),
    )
    .sort();
  const canonicalArtifacts = await collectCanonicalImages(
    options.runDir,
    entries,
    transparencyMode,
  );
  const manifest: ScrollingPreviewManifest = {
    schemaVersion: 2,
    recipe: "scrolling-preview",
    tag: options.tag,
    transparencyMode,
    artifacts,
    canonicalArtifacts,
    music: {
      path: musicName,
      provenancePath: basename(musicProvenancePath),
      source: music.source,
      generationCapability: "generate-music",
      rightsStatus: music.rightsStatus,
      ...(music.noticePath ? { rightsNoticePath: basename(music.noticePath) } : {}),
    },
  };
  const bytes = new TextEncoder().encode(`${JSON.stringify(manifest, null, 2)}\n`);
  const manifestProvenancePath = await writeArtifactWithProvenance(
    manifestPath,
    { bytes, mediaType: "application/json" },
    {
      provider: "local",
      model: "deterministic-manifest",
      prompt: "assemble scrolling-preview run manifest",
      refs: [
        musicName,
        basename(musicProvenancePath),
        ...(music.noticePath ? [basename(music.noticePath)] : []),
      ],
      params: {
        recipe: "scrolling-preview",
        tag: options.tag,
        transparency_mode: transparencyMode,
        music_source: music.source,
        music_rights_status: music.rightsStatus,
        fallback_policy: "copy only when per-run music is absent and publication-approved",
      },
      validation: {
        music_artifact_present: true,
        music_provenance_present: true,
        music_rights_status: music.rightsStatus,
        music_notice_present: music.noticePath ? true : null,
        retained_raw_excluded_from_top_level: artifacts.every(
          (path) => !path.includes(".raw.png"),
        ),
        canonical_transparency_entries: canonicalArtifacts.filter(
          (artifact) => artifact.transparency !== undefined,
        ).length,
      },
      component: { name: "@stage-gen/stage-gen", version: "0.0.0" },
      tool: { name: "scrolling-preview-manifest", version: "1" },
      attempts: 1,
    },
  );
  return {
    manifestPath,
    manifestProvenancePath,
    musicPath,
    musicProvenancePath,
    musicSource: music.source,
    musicRightsStatus: music.rightsStatus,
    ...(music.noticePath ? { musicNoticePath: music.noticePath } : {}),
  };
}

async function collectCanonicalImages(
  runDir: string,
  entries: string[],
  mode: TransparencyMode,
): Promise<ScrollingCanonicalArtifactManifestEntry[]> {
  const entrySet = new Set(entries);
  const canonicalNames = entries
    .filter(
      (name) =>
        name.endsWith(".png") &&
        !name.startsWith(".") &&
        !name.endsWith(".raw.png"),
    )
    .sort();
  const results: ScrollingCanonicalArtifactManifestEntry[] = [];
  for (const canonicalName of canonicalNames) {
    const canonicalProvenanceName = `${canonicalName}.meta.json`;
    if (!entrySet.has(canonicalProvenanceName)) {
      throw new Error(`canonical artifact provenance is missing for ${canonicalName}`);
    }
    const sidecar = await readSidecar(runDir, canonicalProvenanceName, canonicalName);
    const rawName = canonicalName.replace(/\.png$/i, ".raw.png");
    if (entrySet.has(rawName)) {
      const rawProvenanceName = `${rawName}.meta.json`;
      if (!entrySet.has(rawProvenanceName)) {
        throw new Error(`transparent artifact pair is incomplete for ${canonicalName}`);
      }
      const transparency = generatedTransparencyMetadata(
        sidecar,
        mode,
        canonicalName,
        rawName,
        canonicalProvenanceName,
        rawProvenanceName,
      );
      results.push(
        toCanonicalManifestEntry({
          path: rawName,
          provenancePath: rawProvenanceName,
          transparency,
        }) as ScrollingCanonicalArtifactManifestEntry,
      );
      continue;
    }

    const transparency = sidecar.params.transparency;
    if (isRecord(transparency)) {
      results.push({
        path: canonicalName,
        provenancePath: canonicalProvenanceName,
        transparency: await derivedTransparencyMetadata(
          runDir,
          entrySet,
          sidecar,
          transparency,
          mode,
          canonicalName,
          canonicalProvenanceName,
        ),
      });
      continue;
    }

    assertOpaqueArtifact(sidecar, canonicalName);
    results.push({ path: canonicalName, provenancePath: canonicalProvenanceName });
  }
  return results;
}

function generatedTransparencyMetadata(
  sidecar: ParsedArtifactSidecar,
  mode: TransparencyMode,
  canonicalPath: string,
  retainedRawPath: string,
  canonicalProvenancePath: string,
  rawProvenancePath: string,
): GeneratedArtifactTransparencyMetadata {
  const transparency = sidecar.params.transparency;
  if (!isRecord(transparency) || transparency.mode !== mode) {
    throw new Error(`canonical transparency mode mismatch for ${canonicalPath}`);
  }
  const processor = isRecord(transparency.processor)
    ? transparency.processor
    : {};
  const tool = isRecord(sidecar.tool) ? sidecar.tool : undefined;
  return {
    mode,
    canonicalPath,
    retainedRawPath,
    canonicalProvenancePath,
    rawProvenancePath,
    lineage: {
      kind: "generated",
      sourcePaths: [retainedRawPath],
      sourceProvenancePaths: [rawProvenancePath],
    },
    derivation: {
      kind: mode === "ai" ? "ai-background-removal" : "chroma-key",
      ...(typeof transparency.raw_sha256 === "string"
        ? { sourceSha256: transparency.raw_sha256 }
        : {}),
      ...(typeof transparency.output_sha256 === "string"
        ? { outputSha256: transparency.output_sha256 }
        : {}),
      ...(tool && typeof tool.name === "string" && typeof tool.version === "string"
        ? { tool: { name: tool.name, version: tool.version } }
        : typeof processor.kind === "string"
          ? { tool: { name: processor.kind, version: "1" } }
          : {}),
    },
  };
}

async function derivedTransparencyMetadata(
  runDir: string,
  entries: Set<string>,
  sidecar: ParsedArtifactSidecar,
  transparency: Record<string, unknown>,
  mode: TransparencyMode,
  canonicalPath: string,
  canonicalProvenancePath: string,
): Promise<DerivedArtifactTransparencyMetadata> {
  if (transparency.mode !== mode) {
    throw new Error(`canonical transparency mode mismatch for ${canonicalPath}`);
  }
  const sourceValues =
    typeof transparency.source_path === "string"
      ? [transparency.source_path]
      : isRecord(transparency.source_paths)
        ? Object.values(transparency.source_paths).filter(
            (value): value is string => typeof value === "string",
          )
        : [];
  if (sourceValues.length === 0) {
    throw new Error(`derived transparency lineage is missing for ${canonicalPath}`);
  }
  const sourcePaths = sourceValues.map((path) => runRelativePath(runDir, path));
  const sourceProvenancePaths = sourcePaths.map((path) => `${path}.meta.json`);
  for (let index = 0; index < sourcePaths.length; index += 1) {
    const sourcePath = sourcePaths[index];
    const sourceProvenancePath = sourceProvenancePaths[index];
    if (!entries.has(sourcePath) || !entries.has(sourceProvenancePath)) {
      throw new Error(`derived transparency source is missing for ${canonicalPath}`);
    }
    const sourceSidecar = await readSidecar(runDir, sourceProvenancePath, sourcePath);
    const sourceTransparency = sourceSidecar.params.transparency;
    if (!isRecord(sourceTransparency) || sourceTransparency.mode !== mode) {
      throw new Error(`derived transparency source mode mismatch for ${canonicalPath}`);
    }
  }

  const processorName =
    typeof transparency.processor === "string"
      ? transparency.processor
      : isRecord(transparency.processor) && typeof transparency.processor.kind === "string"
        ? transparency.processor.kind
        : "";
  const kind: ScrollingTransparencyDerivationKind = processorName.includes("slice")
    ? "png-slice"
    : processorName.includes("composite")
      ? "alpha-composite"
      : (() => {
          throw new Error(`unknown derived transparency processor for ${canonicalPath}`);
        })();
  const tool = sidecar.tool;
  return {
    mode,
    canonicalPath,
    canonicalProvenancePath,
    derivation: {
      kind,
      ...(typeof transparency.source_sha256 === "string"
        ? { sourceSha256: transparency.source_sha256 }
        : {}),
      ...(typeof transparency.output_sha256 === "string"
        ? { outputSha256: transparency.output_sha256 }
        : {}),
      ...(tool && typeof tool.name === "string" && typeof tool.version === "string"
        ? { tool: { name: tool.name, version: tool.version } }
        : {}),
    },
    lineage: {
      kind: "derived",
      sourcePaths,
      sourceProvenancePaths,
    },
  };
}

interface ParsedArtifactSidecar {
  artifact: Record<string, unknown>;
  params: Record<string, unknown>;
  tool?: Record<string, unknown>;
}

async function readSidecar(
  runDir: string,
  provenanceName: string,
  artifactName: string,
): Promise<ParsedArtifactSidecar> {
  const parsed: unknown = JSON.parse(await Bun.file(join(runDir, provenanceName)).text());
  if (
    !isRecord(parsed) ||
    parsed.schema_version !== 1 ||
    !isRecord(parsed.artifact) ||
    typeof parsed.artifact.sha256 !== "string" ||
    !isRecord(parsed.params)
  ) {
    throw new Error(`canonical provenance is invalid for ${artifactName}`);
  }
  return {
    artifact: parsed.artifact,
    params: parsed.params,
    ...(isRecord(parsed.tool) ? { tool: parsed.tool } : {}),
  };
}

function assertOpaqueArtifact(sidecar: ParsedArtifactSidecar, artifactName: string): void {
  const metadata = sidecar.params.metadata;
  const isConcept = isRecord(metadata) && metadata.stage === "concept";
  const isOpaqueBackdrop = isRecord(metadata) && metadata.opaque === true;
  if (!isConcept && !isOpaqueBackdrop) {
    throw new Error(
      `artifact ${artifactName} has neither transparency derivation nor opaque provenance`,
    );
  }
}

function runRelativePath(runDir: string, artifactPath: string): string {
  const root = resolve(runDir);
  const relativePath = relative(root, resolve(artifactPath));
  if (!relativePath || relativePath.startsWith("..") || isAbsolute(relativePath)) {
    throw new Error("derived transparency source must stay inside the run directory");
  }
  return relativePath;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

interface RunMusicResolution {
  source: "per-run" | "generated-fallback";
  rightsStatus: MusicRightsStatus;
  noticePath?: string;
}

interface ValidatedBundledFallback {
  artifactBytes: Uint8Array;
  sidecarText: string;
  noticeBytes: Uint8Array;
  noticeName: string;
  noticePath: string;
  rights: ArtifactRights;
}

async function ensureRunMusicPair(
  targetPath: string,
  fallbackPath: string,
): Promise<RunMusicResolution> {
  const targetMetaPath = `${targetPath}.meta.json`;
  const [targetExists, targetMetaExists] = await Promise.all([
    isFile(targetPath),
    isFile(targetMetaPath),
  ]);
  if (targetExists || targetMetaExists) {
    if (!targetExists || !targetMetaExists) {
      throw new Error("per-run music must include both artifact and provenance");
    }
    const sidecar = await readJsonObject(targetMetaPath, "per-run music provenance");
    return {
      source: "per-run",
      rightsStatus: optionalRightsStatus(sidecar.rights, "per-run music provenance"),
    };
  }

  const fallbackMetaPath = `${fallbackPath}.meta.json`;
  if (!(await isFile(fallbackPath)) || !(await isFile(fallbackMetaPath))) {
    throw new Error(
      "scrolling-preview music is missing; generate a per-run artifact with the generate-music capability or provide a redistribution-approved bundled fallback",
    );
  }

  const fallback = await validateBundledFallback(fallbackPath, fallbackMetaPath);
  const targetNoticePath = join(dirname(targetPath), fallback.noticeName);
  const noticeAlreadyPresent = await isFile(targetNoticePath);
  if (
    noticeAlreadyPresent &&
    (await realpath(targetNoticePath)) !== fallback.noticePath
  ) {
    throw new Error(`bundled fallback notice target already exists: ${fallback.noticeName}`);
  }

  const token = randomUUID();
  const artifactTemp = `${targetPath}.${token}.tmp`;
  const metaTemp = `${targetMetaPath}.${token}.tmp`;
  const noticeTemp = `${targetNoticePath}.${token}.tmp`;
  let artifactInstalled = false;
  let metaInstalled = false;
  let noticeInstalled = false;
  try {
    await writeFile(artifactTemp, fallback.artifactBytes, { flag: "wx", mode: 0o600 });
    await writeFile(metaTemp, fallback.sidecarText, { flag: "wx", mode: 0o600 });
    if (!noticeAlreadyPresent) {
      await writeFile(noticeTemp, fallback.noticeBytes, { flag: "wx", mode: 0o600 });
    }
    await rename(artifactTemp, targetPath);
    artifactInstalled = true;
    await rename(metaTemp, targetMetaPath);
    metaInstalled = true;
    if (!noticeAlreadyPresent) {
      await rename(noticeTemp, targetNoticePath);
      noticeInstalled = true;
    }
  } catch (error) {
    await Promise.all([
      artifactInstalled ? rm(targetPath, { force: true }) : Promise.resolve(),
      metaInstalled ? rm(targetMetaPath, { force: true }) : Promise.resolve(),
      noticeInstalled ? rm(targetNoticePath, { force: true }) : Promise.resolve(),
    ]);
    await Promise.all([
      rm(artifactTemp, { force: true }),
      rm(metaTemp, { force: true }),
      rm(noticeTemp, { force: true }),
    ]);
    throw error;
  }
  return {
    source: "generated-fallback",
    rightsStatus: fallback.rights.status,
    noticePath: targetNoticePath,
  };
}

async function validateBundledFallback(
  fallbackPath: string,
  fallbackMetaPath: string,
): Promise<ValidatedBundledFallback> {
  const [artifactBuffer, sidecarText] = await Promise.all([
    readFile(fallbackPath),
    readFile(fallbackMetaPath, "utf8"),
  ]);
  const artifactBytes = new Uint8Array(artifactBuffer);
  const sidecar = parseJsonObject(sidecarText, "bundled fallback provenance");
  if (sidecar.schema_version !== 1 || !isRecord(sidecar.artifact)) {
    throw new Error("bundled fallback provenance is invalid");
  }
  const actualSha256 = createHash("sha256").update(artifactBytes).digest("hex");
  if (sidecar.artifact.sha256 !== actualSha256) {
    throw new Error("bundled fallback artifact digest does not match its provenance");
  }
  if (sidecar.artifact.bytes !== artifactBytes.length) {
    throw new Error("bundled fallback artifact byte count does not match its provenance");
  }

  let rights: ArtifactRights;
  try {
    rights = parseArtifactRights(sidecar.rights);
  } catch {
    throw new Error("bundled fallback rights are missing or invalid");
  }
  if (rights.status !== "redistribution-approved") {
    throw new Error(
      `bundled fallback is not publication-approved (rights.status=${rights.status}); generate per-run music or record an approved asset license and notice`,
    );
  }
  assertPublishableReferences(sidecar, rights);
  const noticeName = publicationNoticeName(rights.notice);
  const fallbackDirectory = await realpath(dirname(fallbackPath));
  const noticeCandidate = resolve(fallbackDirectory, noticeName);
  let noticePath: string;
  try {
    noticePath = await realpath(noticeCandidate);
  } catch {
    throw new Error(`bundled fallback rights notice is missing: ${noticeName}`);
  }
  const noticeRelative = relative(fallbackDirectory, noticePath);
  if (!noticeRelative || noticeRelative.startsWith("..") || isAbsolute(noticeRelative)) {
    throw new Error("bundled fallback rights notice must stay beside the artifact");
  }
  const noticeInfo = await stat(noticePath);
  if (!noticeInfo.isFile() || noticeInfo.size === 0) {
    throw new Error(`bundled fallback rights notice is empty or invalid: ${noticeName}`);
  }
  const noticeBytes = new Uint8Array(await readFile(noticePath));
  if (noticeBytes.length === 0) {
    throw new Error(`bundled fallback rights notice is empty: ${noticeName}`);
  }
  return {
    artifactBytes,
    sidecarText,
    noticeBytes,
    noticeName,
    noticePath,
    rights,
  };
}

function optionalRightsStatus(value: unknown, label: string): MusicRightsStatus {
  if (value === undefined) return "unrecorded";
  try {
    return parseArtifactRights(value).status;
  } catch {
    throw new Error(`${label} rights are invalid`);
  }
}

function assertPublishableReferences(
  sidecar: Record<string, unknown>,
  rights: ArtifactRights,
): void {
  for (const key of ["references", "refs"] as const) {
    const value = sidecar[key];
    if (value === undefined) continue;
    if (!isStringArray(value)) throw new Error(`bundled fallback ${key} are invalid`);
    for (const reference of value) assertStablePublicationReference(reference, key);
  }
  if (sidecar.inputs !== undefined) {
    if (!Array.isArray(sidecar.inputs)) throw new Error("bundled fallback inputs are invalid");
    for (const input of sidecar.inputs) {
      if (!isRecord(input) || typeof input.ref !== "string") {
        throw new Error("bundled fallback input reference is invalid");
      }
      assertStablePublicationReference(input.ref, "input ref");
    }
  }
  for (const basis of rights.basis) assertStablePublicationReference(basis, "rights basis");
}

function assertStablePublicationReference(reference: string, label: string): void {
  if (!isPortableArtifactReference(reference)) {
    throw new Error(`bundled fallback ${label} must use a stable non-temporary reference`);
  }
}

function publicationNoticeName(notice: string): string {
  const value = notice.trim();
  if (
    value.length === 0 ||
    value !== basename(value) ||
    value === "." ||
    value === ".." ||
    value.includes("\\") ||
    /^[a-z][a-z0-9+.-]*:/i.test(value)
  ) {
    throw new Error("bundled fallback rights notice must name an adjacent file");
  }
  return value;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((entry) => typeof entry === "string");
}

async function readJsonObject(path: string, label: string): Promise<Record<string, unknown>> {
  return parseJsonObject(await readFile(path, "utf8"), label);
}

function parseJsonObject(text: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${label} is not valid JSON`);
  }
  if (!isRecord(parsed)) throw new Error(`${label} must be an object`);
  return parsed;
}

async function isFile(path: string): Promise<boolean> {
  try {
    return (await stat(path)).isFile();
  } catch {
    return false;
  }
}

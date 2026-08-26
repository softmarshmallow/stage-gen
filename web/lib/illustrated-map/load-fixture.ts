import { createHash } from "node:crypto";
import { lstat, readFile, realpath } from "node:fs/promises";
import path from "node:path";
import {
  parseIllustratedMapManifest,
  type IllustratedMapManifestV1,
} from "./contract";

export interface IllustratedMapFixture {
  readonly manifest: IllustratedMapManifestV1;
  readonly manifest_url: string;
  readonly raster_url: string;
}

interface LoadFixtureOptions {
  readonly asset_directory?: string;
  readonly public_base_url?: string;
  readonly manifest_name?: string;
}

function digest(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function publicUrl(base: string, relativePath: string): string {
  const encodedPath = relativePath.split("/").map(encodeURIComponent).join("/");
  return `${base.replace(/\/$/, "")}/${encodedPath}`;
}

async function readContainedRegularFile(
  assetDirectory: string,
  relativePath: string,
): Promise<Buffer> {
  const root = await realpath(assetDirectory);
  const candidate = path.resolve(root, relativePath);
  if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) {
    throw new Error(`${relativePath}: path escapes the illustrated-map asset directory`);
  }

  const directMetadata = await lstat(candidate);
  if (!directMetadata.isFile() || directMetadata.isSymbolicLink()) {
    throw new Error(`${relativePath}: expected a regular, non-symlink file`);
  }
  const resolvedCandidate = await realpath(candidate);
  if (resolvedCandidate !== root && !resolvedCandidate.startsWith(`${root}${path.sep}`)) {
    throw new Error(`${relativePath}: resolved path escapes the asset directory`);
  }
  return readFile(resolvedCandidate);
}

function pngDimensions(bytes: Buffer): { width: number; height: number } {
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (
    bytes.length < 24 ||
    !bytes.subarray(0, signature.length).equals(signature) ||
    bytes.subarray(12, 16).toString("ascii") !== "IHDR"
  ) {
    throw new Error("raster: expected a PNG with an IHDR header");
  }
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

export async function loadIllustratedMapFixture(
  options: LoadFixtureOptions = {},
): Promise<IllustratedMapFixture> {
  const assetDirectory =
    options.asset_directory ?? path.join(process.cwd(), "public", "demo", "map");
  const publicBaseUrl = options.public_base_url ?? "/demo/map";
  const manifestName = options.manifest_name ?? "ashen-reaches.json";

  const manifestBytes = await readContainedRegularFile(assetDirectory, manifestName);
  const manifest = parseIllustratedMapManifest(JSON.parse(manifestBytes.toString("utf8")));

  const rasterBytes = await readContainedRegularFile(assetDirectory, manifest.raster.path);
  if (rasterBytes.byteLength !== manifest.raster.bytes) {
    throw new Error("raster: byte count does not match the manifest");
  }
  if (digest(rasterBytes) !== manifest.raster.sha256) {
    throw new Error("raster: SHA-256 does not match the manifest");
  }
  const dimensions = pngDimensions(rasterBytes);
  if (
    dimensions.width !== manifest.raster.width ||
    dimensions.height !== manifest.raster.height
  ) {
    throw new Error("raster: decoded dimensions do not match the manifest");
  }

  return {
    manifest,
    manifest_url: publicUrl(publicBaseUrl, manifestName),
    raster_url: publicUrl(publicBaseUrl, manifest.raster.path),
  };
}

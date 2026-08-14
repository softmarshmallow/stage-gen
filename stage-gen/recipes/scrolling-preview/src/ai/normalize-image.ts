import { createHash } from "node:crypto";
import sharp from "sharp";
import { throwIfAborted } from "../../../../src/abort.ts";

export interface ImageNormalizationRecord {
  operation: "resize" | "png-reencode";
  source: {
    width: number;
    height: number;
    bytes: number;
    sha256: string;
    media_type: "image/png";
  };
  output: {
    width: number;
    height: number;
    bytes: number;
    sha256: string;
    media_type: "image/png";
  };
  transform: {
    fit: "fill";
    kernel: "lanczos3";
    format: "png";
    compression_level: 9;
  };
  tool: { name: "sharp"; version: string };
}

export async function normalizeImageBytes(
  sourceBytes: Uint8Array,
  options: { width: number; height: number; signal?: AbortSignal },
): Promise<{ bytes: Uint8Array; record: ImageNormalizationRecord }> {
  assertDimension(options.width, "width");
  assertDimension(options.height, "height");
  throwIfAborted(options.signal);

  const source = await sharp(Buffer.from(sourceBytes), { failOn: "error" }).metadata();
  if (!source.width || !source.height || source.format !== "png") {
    throw new Error("provider image must be a decodable PNG with dimensions");
  }
  throwIfAborted(options.signal);

  const outputBuffer = await sharp(Buffer.from(sourceBytes), { failOn: "error" })
    .resize(options.width, options.height, {
      fit: "fill",
      kernel: sharp.kernel.lanczos3,
    })
    .png({ compressionLevel: 9, adaptiveFiltering: false, force: true })
    .toBuffer();
  throwIfAborted(options.signal);

  const output = await sharp(outputBuffer, { failOn: "error" }).metadata();
  if (output.width !== options.width || output.height !== options.height) {
    throw new Error(
      `normalization produced ${output.width}x${output.height}, expected ${options.width}x${options.height}`,
    );
  }

  const bytes = new Uint8Array(outputBuffer);
  return {
    bytes,
    record: {
      operation:
        source.width === options.width && source.height === options.height
          ? "png-reencode"
          : "resize",
      source: {
        width: source.width,
        height: source.height,
        bytes: sourceBytes.length,
        sha256: sha256(sourceBytes),
        media_type: "image/png",
      },
      output: {
        width: options.width,
        height: options.height,
        bytes: bytes.length,
        sha256: sha256(bytes),
        media_type: "image/png",
      },
      transform: {
        fit: "fill",
        kernel: "lanczos3",
        format: "png",
        compression_level: 9,
      },
      tool: { name: "sharp", version: sharp.versions.sharp },
    },
  };
}

function assertDimension(value: number, label: string): void {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${label} must be a positive integer`);
  }
}

function sha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

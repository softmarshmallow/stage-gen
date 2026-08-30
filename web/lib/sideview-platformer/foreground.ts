export type ForegroundPixelBounds = Readonly<{
  left: number;
  top: number;
  right: number;
  bottom: number;
}>;

export type ForegroundContactStrip = Readonly<{
  top: number;
  bottom: number;
  minimumCoveragePixels: number;
  maximumCoveragePixels: number;
}>;

export type ForegroundRaster = Readonly<{
  width: number;
  height: number;
  data: Uint8ClampedArray;
}>;

export type PreparedForegroundRaster = ForegroundRaster &
  Readonly<{
    sourceWidth: number;
    sourceHeight: number;
    sourceContentBounds: ForegroundPixelBounds;
    sourceMeaningfulContentBounds: ForegroundPixelBounds;
    contentBounds: ForegroundPixelBounds;
    meaningfulContentBounds: ForegroundPixelBounds;
    contactStrip: ForegroundContactStrip;
    contactSourceY: number;
    repeatPeriod: number;
    overlap: number;
  }>;

const RGBA_CHANNELS = 4;
export const FOREGROUND_PAINTED_ALPHA_THRESHOLD = 64;
const MEANINGFUL_WIDTH_FRACTION = 0.25;
const CONTACT_MINIMUM_WIDTH_FRACTION = 0.25;
const CONTACT_MAXIMUM_FRACTION = 0.9;

function assertRaster(raster: ForegroundRaster): void {
  if (
    !Number.isSafeInteger(raster.width) ||
    !Number.isSafeInteger(raster.height) ||
    raster.width <= 0 ||
    raster.height <= 0
  ) {
    throw new Error("foreground dimensions must be positive integers");
  }
  const expected = raster.width * raster.height * RGBA_CHANNELS;
  if (!Number.isSafeInteger(expected) || raster.data.length !== expected) {
    throw new Error(
      "foreground RGBA byte length does not match its dimensions",
    );
  }
}

function alphaAt(raster: ForegroundRaster, x: number, y: number): number {
  return raster.data[(y * raster.width + x) * RGBA_CHANNELS + 3]!;
}

export function measureForegroundRaster(raster: ForegroundRaster): Readonly<{
  contentBounds: ForegroundPixelBounds;
  meaningfulContentBounds: ForegroundPixelBounds;
  contactStrip: ForegroundContactStrip;
}> {
  assertRaster(raster);
  let left = raster.width;
  let top = raster.height;
  let right = 0;
  let bottom = 0;
  const rowCoverage = new Uint32Array(raster.height);
  for (let y = 0; y < raster.height; y += 1) {
    for (let x = 0; x < raster.width; x += 1) {
      if (alphaAt(raster, x, y) <= FOREGROUND_PAINTED_ALPHA_THRESHOLD) continue;
      rowCoverage[y] += 1;
      left = Math.min(left, x);
      top = Math.min(top, y);
      right = Math.max(right, x + 1);
      bottom = Math.max(bottom, y + 1);
    }
  }
  if (right === 0 || bottom === 0) {
    throw new Error("foreground must contain painted alpha");
  }
  const maximumCoveragePixels = rowCoverage.reduce(
    (maximum, coverage) => Math.max(maximum, coverage),
    0,
  );
  const meaningfulCoveragePixels = Math.max(
    2,
    Math.ceil(raster.width * MEANINGFUL_WIDTH_FRACTION),
  );
  let meaningfulLeft = raster.width;
  let meaningfulTop = raster.height;
  let meaningfulRight = 0;
  let meaningfulBottom = 0;
  for (let y = top; y < bottom; y += 1) {
    if (rowCoverage[y]! < meaningfulCoveragePixels) continue;
    meaningfulTop = Math.min(meaningfulTop, y);
    meaningfulBottom = Math.max(meaningfulBottom, y + 1);
    for (let x = 0; x < raster.width; x += 1) {
      if (alphaAt(raster, x, y) <= FOREGROUND_PAINTED_ALPHA_THRESHOLD) continue;
      meaningfulLeft = Math.min(meaningfulLeft, x);
      meaningfulRight = Math.max(meaningfulRight, x + 1);
    }
  }
  if (meaningfulRight === 0 || meaningfulBottom === 0) {
    throw new Error("foreground has no sufficiently wide meaningful content");
  }
  const minimumCoveragePixels = Math.max(
    2,
    Math.ceil(raster.width * CONTACT_MINIMUM_WIDTH_FRACTION),
    Math.ceil(maximumCoveragePixels * CONTACT_MAXIMUM_FRACTION),
  );
  let contactBottom = -1;
  for (let y = bottom - 1; y >= top; y -= 1) {
    if (rowCoverage[y]! >= minimumCoveragePixels) {
      contactBottom = y + 1;
      break;
    }
  }
  if (contactBottom < 0) {
    throw new Error("foreground has no sufficiently wide painted contact row");
  }
  let contactTop = contactBottom - 1;
  while (
    contactTop > top &&
    rowCoverage[contactTop - 1]! >= minimumCoveragePixels
  ) {
    contactTop -= 1;
  }
  return Object.freeze({
    contentBounds: Object.freeze({ left, top, right, bottom }),
    meaningfulContentBounds: Object.freeze({
      left: meaningfulLeft,
      top: meaningfulTop,
      right: meaningfulRight,
      bottom: meaningfulBottom,
    }),
    contactStrip: Object.freeze({
      top: contactTop,
      bottom: contactBottom,
      minimumCoveragePixels,
      maximumCoveragePixels,
    }),
  });
}

/**
 * Describe a producer-verified repeat without changing one decoded pixel.
 *
 * Unlike the compatibility preparation below, this performs no vertical trim and no horizontal
 * overlap-add. The decoded width itself is the promised period; a disagreement is a forged or
 * mismatched artifact and fails closed before Phaser registers the texture.
 */
export function measureVerifiedForegroundRepeat(
  source: ForegroundRaster,
  repeatPeriod: number,
): Pick<
  PreparedForegroundRaster,
  | "sourceWidth"
  | "sourceHeight"
  | "contentBounds"
  | "meaningfulContentBounds"
  | "contactStrip"
  | "contactSourceY"
  | "repeatPeriod"
  | "overlap"
> {
  assertRaster(source);
  if (!Number.isSafeInteger(repeatPeriod) || repeatPeriod !== source.width) {
    throw new Error("verified foreground decoded width must equal its repeat period");
  }
  const measured = measureForegroundRaster(source);
  return Object.freeze({
    sourceWidth: source.width,
    sourceHeight: source.height,
    contentBounds: measured.contentBounds,
    meaningfulContentBounds: measured.meaningfulContentBounds,
    contactStrip: measured.contactStrip,
    contactSourceY: measured.contactStrip.bottom - 1,
    repeatPeriod,
    overlap: 0,
  });
}

function copyPixel(
  source: Uint8ClampedArray,
  sourceOffset: number,
  target: Uint8ClampedArray,
  targetOffset: number,
): void {
  target[targetOffset] = source[sourceOffset]!;
  target[targetOffset + 1] = source[sourceOffset + 1]!;
  target[targetOffset + 2] = source[sourceOffset + 2]!;
  target[targetOffset + 3] = source[sourceOffset + 3]!;
}

function blendPremultipliedPixel(
  source: Uint8ClampedArray,
  headOffset: number,
  tailOffset: number,
  headWeight: number,
  tailWeight: number,
  denominator: number,
  target: Uint8ClampedArray,
  targetOffset: number,
): void {
  if (headWeight === 0) {
    copyPixel(source, tailOffset, target, targetOffset);
    return;
  }
  if (tailWeight === 0) {
    copyPixel(source, headOffset, target, targetOffset);
    return;
  }
  const headAlpha = source[headOffset + 3]!;
  const tailAlpha = source[tailOffset + 3]!;
  const weightedAlpha = headAlpha * headWeight + tailAlpha * tailWeight;
  const outputAlpha = Math.round(weightedAlpha / denominator);
  target[targetOffset + 3] = outputAlpha;
  if (weightedAlpha === 0) {
    target[targetOffset] = 0;
    target[targetOffset + 1] = 0;
    target[targetOffset + 2] = 0;
    return;
  }
  for (let channel = 0; channel < 3; channel += 1) {
    const weightedPremultiplied =
      source[headOffset + channel]! * headAlpha * headWeight +
      source[tailOffset + channel]! * tailAlpha * tailWeight;
    target[targetOffset + channel] = Math.round(
      weightedPremultiplied / weightedAlpha,
    );
  }
}

/**
 * Vertically trim a full-width alpha-bearing layer and derive one periodic
 * overlap-add raster. Source columns [overlap, period) remain byte-identical.
 */
export function prepareForegroundRaster(
  source: ForegroundRaster,
  overlap: number,
): PreparedForegroundRaster {
  assertRaster(source);
  if (
    !Number.isSafeInteger(overlap) ||
    overlap < 2 ||
    overlap * 2 >= source.width
  ) {
    throw new Error(
      "foreground overlap must leave a nonempty byte-preserved middle band",
    );
  }
  const measured = measureForegroundRaster(source);
  const trimTop = measured.contentBounds.top;
  const trimBottom = measured.contentBounds.bottom;
  const height = trimBottom - trimTop;
  const repeatPeriod = source.width - overlap;
  const output = new Uint8ClampedArray(repeatPeriod * height * RGBA_CHANNELS);
  const denominator = overlap - 1;
  for (let y = 0; y < height; y += 1) {
    const sourceY = trimTop + y;
    for (let x = 0; x < repeatPeriod; x += 1) {
      const targetOffset = (y * repeatPeriod + x) * RGBA_CHANNELS;
      if (x >= overlap) {
        const sourceOffset = (sourceY * source.width + x) * RGBA_CHANNELS;
        copyPixel(source.data, sourceOffset, output, targetOffset);
        continue;
      }
      const headOffset = (sourceY * source.width + x) * RGBA_CHANNELS;
      const tailOffset =
        (sourceY * source.width + repeatPeriod + x) * RGBA_CHANNELS;
      blendPremultipliedPixel(
        source.data,
        headOffset,
        tailOffset,
        x,
        denominator - x,
        denominator,
        output,
        targetOffset,
      );
    }
  }
  const prepared = { width: repeatPeriod, height, data: output };
  const preparedMeasurement = measureForegroundRaster(prepared);
  return {
    ...prepared,
    sourceWidth: source.width,
    sourceHeight: source.height,
    sourceContentBounds: measured.contentBounds,
    sourceMeaningfulContentBounds: measured.meaningfulContentBounds,
    contentBounds: preparedMeasurement.contentBounds,
    meaningfulContentBounds: preparedMeasurement.meaningfulContentBounds,
    contactStrip: Object.freeze({
      ...measured.contactStrip,
      top: measured.contactStrip.top - trimTop,
      bottom: measured.contactStrip.bottom - trimTop,
    }),
    // Bounds are half-open, while the placement contract anchors the last
    // painted contact row itself (653 in the approved 1280x720 source).
    contactSourceY: measured.contactStrip.bottom - 1 - trimTop,
    repeatPeriod,
    overlap,
  };
}

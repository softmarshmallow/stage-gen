import type { PreparedLayerPresentation } from "./prepared-manifest";

function clampByte(value: number): number {
  return Math.max(0, Math.min(255, Math.round(value)));
}

function parseHexColor(value: string): readonly [number, number, number] {
  return Object.freeze([
    Number.parseInt(value.slice(1, 3), 16),
    Number.parseInt(value.slice(3, 5), 16),
    Number.parseInt(value.slice(5, 7), 16),
  ]);
}

export function isNeutralLayerPresentation(
  presentation: PreparedLayerPresentation,
): boolean {
  return (
    presentation.contrast === 1 &&
    presentation.saturation === 1 &&
    presentation.atmosphere_strength === 0 &&
    presentation.detail_blur_screen_pixels === 0
  );
}

function gaussianKernel(sigma: number): readonly number[] {
  const radius = Math.max(1, Math.ceil(sigma * 2.5));
  const values: number[] = [];
  let total = 0;
  for (let offset = -radius; offset <= radius; offset += 1) {
    const weight = Math.exp(-(offset * offset) / (2 * sigma * sigma));
    values.push(weight);
    total += weight;
  }
  return Object.freeze(values.map((weight) => weight / total));
}

function alphaAwareBlurPass(
  source: Uint8ClampedArray,
  width: number,
  height: number,
  kernel: readonly number[],
  horizontal: boolean,
): Uint8ClampedArray {
  const output = new Uint8ClampedArray(source);
  const radius = Math.floor(kernel.length / 2);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let red = 0;
      let green = 0;
      let blue = 0;
      let contributingWeight = 0;
      for (let kernelIndex = 0; kernelIndex < kernel.length; kernelIndex += 1) {
        const offset = kernelIndex - radius;
        // X wraps because every map layer is one admitted repeat period. Y clamps because the
        // layer does not repeat vertically.
        const sampleX = horizontal
          ? (x + offset + width) % width
          : x;
        const sampleY = horizontal
          ? y
          : Math.max(0, Math.min(height - 1, y + offset));
        const sampleIndex = (sampleY * width + sampleX) * 4;
        const alphaWeight = (source[sampleIndex + 3]! / 255) * kernel[kernelIndex]!;
        red += source[sampleIndex]! * alphaWeight;
        green += source[sampleIndex + 1]! * alphaWeight;
        blue += source[sampleIndex + 2]! * alphaWeight;
        contributingWeight += alphaWeight;
      }
      if (contributingWeight <= 0) continue;
      const targetIndex = (y * width + x) * 4;
      output[targetIndex] = clampByte(red / contributingWeight);
      output[targetIndex + 1] = clampByte(green / contributingWeight);
      output[targetIndex + 2] = clampByte(blue / contributingWeight);
      // Deliberately retain the source alpha. Depth blur softens painted detail without changing
      // the producer-admitted silhouette or its horizontal repeat boundary.
      output[targetIndex + 3] = source[targetIndex + 3]!;
    }
  }
  return output;
}

export function presentPreparedLayerPixels(
  source: Uint8ClampedArray,
  width: number,
  height: number,
  presentation: PreparedLayerPresentation,
  sourcePixelsPerScreenPixel: number,
): Uint8ClampedArray {
  if (source.length !== width * height * 4 || width <= 0 || height <= 0) {
    throw new Error("prepared layer pixels do not match their dimensions");
  }
  if (!Number.isFinite(sourcePixelsPerScreenPixel) || sourcePixelsPerScreenPixel <= 0) {
    throw new Error("prepared layer scale must be finite and positive");
  }
  if (isNeutralLayerPresentation(presentation)) return new Uint8ClampedArray(source);

  const output = new Uint8ClampedArray(source);
  const atmosphere = parseHexColor(presentation.atmosphere_color);
  for (let index = 0; index < output.length; index += 4) {
    if (output[index + 3] === 0) continue;
    let red = ((output[index]! / 255 - 0.5) * presentation.contrast + 0.5) * 255;
    let green = ((output[index + 1]! / 255 - 0.5) * presentation.contrast + 0.5) * 255;
    let blue = ((output[index + 2]! / 255 - 0.5) * presentation.contrast + 0.5) * 255;
    const luminance = red * 0.2126 + green * 0.7152 + blue * 0.0722;
    red = luminance + (red - luminance) * presentation.saturation;
    green = luminance + (green - luminance) * presentation.saturation;
    blue = luminance + (blue - luminance) * presentation.saturation;
    const atmosphereStrength = presentation.atmosphere_strength;
    output[index] = clampByte(red * (1 - atmosphereStrength) + atmosphere[0] * atmosphereStrength);
    output[index + 1] = clampByte(
      green * (1 - atmosphereStrength) + atmosphere[1] * atmosphereStrength,
    );
    output[index + 2] = clampByte(
      blue * (1 - atmosphereStrength) + atmosphere[2] * atmosphereStrength,
    );
  }

  const sigma = presentation.detail_blur_screen_pixels * sourcePixelsPerScreenPixel;
  if (sigma < 0.05) return output;
  const kernel = gaussianKernel(sigma);
  const horizontal = alphaAwareBlurPass(output, width, height, kernel, true);
  return alphaAwareBlurPass(horizontal, width, height, kernel, false);
}

export function presentPreparedLayerCanvas(
  canvas: HTMLCanvasElement,
  presentation: PreparedLayerPresentation,
  sourcePixelsPerScreenPixel: number,
): void {
  if (isNeutralLayerPresentation(presentation)) return;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("prepared layer presentation requires a 2d canvas");
  const image = context.getImageData(0, 0, canvas.width, canvas.height);
  image.data.set(
    presentPreparedLayerPixels(
      image.data,
      canvas.width,
      canvas.height,
      presentation,
      sourcePixelsPerScreenPixel,
    ),
  );
  context.putImageData(image, 0, 0);
}

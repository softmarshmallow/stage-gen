declare module "pngjs" {
  export type DecodedPng = Readonly<{
    width: number;
    height: number;
    depth: number;
    colorType: number;
    alpha: boolean;
    palette: boolean;
    interlace: boolean;
    data: Buffer;
  }>;

  export type PngWriteInput = Readonly<{
    width: number;
    height: number;
    data: Buffer;
  }>;

  export class PNG {
    static readonly sync: {
      read(
        bytes: Buffer,
        options?: Readonly<{ checkCRC?: boolean; skipRescale?: boolean }>,
      ): DecodedPng;
      write(
        png: PngWriteInput,
        options?: Readonly<{
          colorType?: number;
          inputColorType?: number;
          inputHasAlpha?: boolean;
        }>,
      ): Buffer;
    };
  }
}

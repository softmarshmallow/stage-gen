import type Phaser from "phaser";

/**
 * Runtime-only stand-ins for missing presentation art.
 *
 * A missing image must not remove the mechanic that would have used it. These
 * deliberately loud textures keep the relevant Phaser systems constructible
 * while the runtime diagnostic makes the incomplete presentation fail formal
 * verification.
 */
export type PresentationFallbackKind =
  | "sprite"
  | "four_frame_strip"
  | "portal_sheet"
  | "inventory_panel"
  | "panel_frame"
  | "button_sheet"
  | "icon_sheet";

export type PresentationFallbackDiagnostic = (message: string) => void;

const CELL_PX = 64;
const PORTAL_HEIGHT_PX = 96;
const PANEL_WIDTH_PX = 384;
const PANEL_HEIGHT_PX = 256;
// Atlas sheets are sliced by the cell rects the manifest publishes, so the stand-in has to be
// the whole declared canvas for any published cell to fall inside it.
const ATLAS_CANVAS_PX = 1024;
const MAX_DIAGNOSTIC_LENGTH = 256;
const MAX_KEY_LENGTH = 96;

type FallbackLayout = Readonly<{
  width: number;
  height: number;
  columns: number;
  rows: number;
}>;

function fallbackLayout(kind: PresentationFallbackKind): FallbackLayout {
  switch (kind) {
    case "sprite":
      return { width: CELL_PX, height: CELL_PX, columns: 1, rows: 1 };
    case "four_frame_strip":
      return { width: CELL_PX * 4, height: CELL_PX, columns: 4, rows: 1 };
    case "portal_sheet":
      return {
        width: CELL_PX * 2,
        height: PORTAL_HEIGHT_PX,
        columns: 2,
        rows: 1,
      };
    case "inventory_panel":
      return {
        width: PANEL_WIDTH_PX,
        height: PANEL_HEIGHT_PX,
        columns: 4,
        rows: 2,
      };
    case "panel_frame":
      return { width: ATLAS_CANVAS_PX, height: ATLAS_CANVAS_PX, columns: 1, rows: 1 };
    case "button_sheet":
      return { width: ATLAS_CANVAS_PX, height: ATLAS_CANVAS_PX, columns: 1, rows: 4 };
    case "icon_sheet":
      return { width: ATLAS_CANVAS_PX, height: ATLAS_CANVAS_PX, columns: 4, rows: 4 };
  }
}

function safeDiagnosticKey(key: string): string {
  return key
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_KEY_LENGTH);
}

function reportFallback(
  reportDiagnostic: PresentationFallbackDiagnostic | undefined,
  key: string,
  kind: PresentationFallbackKind | "grid_sheet",
): void {
  if (!reportDiagnostic) return;
  const message =
    `Missing ${kind.replaceAll("_", " ")} presentation for ` +
    `"${safeDiagnosticKey(key)}"; using a magenta runtime placeholder.`;
  try {
    reportDiagnostic(message.slice(0, MAX_DIAGNOSTIC_LENGTH));
  } catch {
    // Diagnostics are observational. A broken reporter must not disable play.
  }
}

function drawFallbackCell(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
): void {
  context.fillStyle = "#ff00ff";
  context.fillRect(x, y, width, height);
  context.strokeStyle = "#160016";
  context.lineWidth = 4;
  context.strokeRect(x + 2, y + 2, width - 4, height - 4);
  context.beginPath();
  context.moveTo(x + 8, y + 8);
  context.lineTo(x + width - 8, y + height - 8);
  context.moveTo(x + width - 8, y + 8);
  context.lineTo(x + 8, y + height - 8);
  context.stroke();
}

/**
 * Register a deterministic magenta texture under `key` and emit one bounded
 * non-fatal diagnostic. Existing data under the key is replaced so a failed
 * partial load cannot leak into the degraded runtime.
 */
export function registerPresentationFallback(
  textures: Phaser.Textures.TextureManager,
  key: string,
  kind: PresentationFallbackKind,
  reportDiagnostic?: PresentationFallbackDiagnostic,
): HTMLCanvasElement {
  const layout = fallbackLayout(kind);
  const canvas = document.createElement("canvas");
  canvas.width = layout.width;
  canvas.height = layout.height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("presentation fallback requires a 2d canvas");

  const cellWidth = layout.width / layout.columns;
  const cellHeight = layout.height / layout.rows;
  for (let row = 0; row < layout.rows; row += 1) {
    for (let column = 0; column < layout.columns; column += 1) {
      drawFallbackCell(
        context,
        column * cellWidth,
        row * cellHeight,
        cellWidth,
        cellHeight,
      );
    }
  }

  if (textures.exists(key)) textures.remove(key);
  textures.addCanvas(key, canvas);
  const texture = textures.get(key);
  if (kind === "four_frame_strip") {
    for (let frame = 0; frame < 4; frame += 1) {
      texture.add(frame, 0, frame * CELL_PX, 0, CELL_PX, CELL_PX);
    }
  } else if (kind === "portal_sheet") {
    texture.add("portal_entry", 0, 0, 0, CELL_PX, PORTAL_HEIGHT_PX);
    texture.add(
      "portal_exit",
      0,
      CELL_PX,
      0,
      CELL_PX,
      PORTAL_HEIGHT_PX,
    );
  }

  reportFallback(reportDiagnostic, key, kind);
  return canvas;
}

/** Register a magenta row-major grid with the named frames dialogue consumes. */
export function registerGridPresentationFallback(
  textures: Phaser.Textures.TextureManager,
  key: string,
  columns: number,
  rows: number,
  framePrefix: string,
  reportDiagnostic?: PresentationFallbackDiagnostic,
): HTMLCanvasElement {
  if (
    !Number.isSafeInteger(columns) ||
    !Number.isSafeInteger(rows) ||
    columns < 1 ||
    rows < 1 ||
    columns * rows > 64
  ) {
    throw new Error("presentation fallback grid dimensions are invalid");
  }
  const canvas = document.createElement("canvas");
  canvas.width = columns * CELL_PX;
  canvas.height = rows * CELL_PX;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("presentation fallback requires a 2d canvas");
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      drawFallbackCell(
        context,
        column * CELL_PX,
        row * CELL_PX,
        CELL_PX,
        CELL_PX,
      );
    }
  }
  if (textures.exists(key)) textures.remove(key);
  textures.addCanvas(key, canvas);
  const texture = textures.get(key);
  for (let frame = 0; frame < columns * rows; frame += 1) {
    texture.add(
      `${framePrefix}_${frame}`,
      0,
      (frame % columns) * CELL_PX,
      Math.floor(frame / columns) * CELL_PX,
      CELL_PX,
      CELL_PX,
    );
  }
  reportFallback(reportDiagnostic, key, "grid_sheet");
  return canvas;
}

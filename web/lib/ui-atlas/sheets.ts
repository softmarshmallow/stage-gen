// Loading the generated atlas sheets, in one place for every genre.
//
// The texture keys are shared vocabulary on purpose: a platformer, a visual novel, a puzzle room
// and a runner all load `ui_panel_frame` and `ui_button_rect`, so the widget layer never has to
// learn a per-genre naming scheme. A sheet that will not load is replaced by the conspicuous
// stand-in under the same key, which keeps every widget constructible while leaving the missing
// presentation visible to verification.

import type Phaser from "phaser";
import type { UiAtlasRoleLayout, UiAtlasRoleName } from "../manifest/ui-atlas-layout";
import type { PresentationFallbackDiagnostic, PresentationFallbackKind } from "./fallback";
import { registerPresentationFallback } from "./fallback";

/**
 * The sheets an interface draws from: manifest role, texture key, and the stand-in kind
 * registered when the sheet is missing. Declared once so every scene loads exactly what its
 * widgets slice.
 */
export const UI_ATLAS_SHEETS: readonly (readonly [
  UiAtlasRoleName,
  string,
  PresentationFallbackKind,
])[] = Object.freeze([
  Object.freeze(["panel_frame", "ui_panel_frame", "panel_frame"] as const),
  Object.freeze(["button_rect", "ui_button_rect", "button_sheet"] as const),
]);

/** The texture key one role's sheet is loaded under. */
export function uiAtlasSheetKey(role: UiAtlasRoleName): string {
  const entry = UI_ATLAS_SHEETS.find(([name]) => name === role);
  if (!entry) throw new Error(`no atlas sheet is declared for ${role}`);
  return entry[1];
}

/** What a caller must publish for each role: the parsed geometry and the URL of its sheet. */
export type UiAtlasSource = Readonly<{
  layout: UiAtlasRoleLayout;
  url: string;
}>;

export type LoadUiAtlasSheetsOptions = Readonly<{
  textures: Phaser.Textures.TextureManager;
  /** Per role, where its sheet is and what geometry it publishes. */
  sources: Readonly<Record<UiAtlasRoleName, UiAtlasSource>>;
  /** How this consumer loads one image; the caller owns its transparency policy. */
  load: (url: string, key: string) => Promise<unknown>;
  reportDiagnostic?: PresentationFallbackDiagnostic;
}>;

/**
 * Load every declared atlas sheet, installing the stand-in for any that fails.
 *
 * Loading is per sheet rather than all-or-nothing: one unreadable button sheet must not also cost
 * the panel that did load.
 */
export async function loadUiAtlasSheets(options: LoadUiAtlasSheetsOptions): Promise<void> {
  await Promise.all(
    UI_ATLAS_SHEETS.map(async ([role, key, kind]) => {
      try {
        await options.load(options.sources[role].url, key);
      } catch {
        registerPresentationFallback(options.textures, key, kind, options.reportDiagnostic);
      }
    }),
  );
}

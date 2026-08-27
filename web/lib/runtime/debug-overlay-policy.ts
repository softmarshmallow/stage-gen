export type DebugOverlayItem = Readonly<{
  label: string;
  quantity: number;
}>;

export type DebugOverlayState = Readonly<{
  health: number;
  maximumHealth: number;
  inventory: readonly DebugOverlayItem[];
}>;

/** The debug layer toggles only on a fresh Command+Backtick chord. */
export function debugOverlayToggleRequested(input: Readonly<{
  justPressed: boolean;
  metaKey: boolean;
}>): boolean {
  return input.justPressed && input.metaKey;
}

export function debugOverlayText(state: DebugOverlayState): string {
  const inventory = state.inventory
    .filter((item) => item.quantity > 0)
    .map((item) => `${item.label} ×${item.quantity}`)
    .join("  ·  ");
  return `DEBUG\nHP ${state.health}/${state.maximumHealth}\n${inventory || "Inventory empty"}`;
}

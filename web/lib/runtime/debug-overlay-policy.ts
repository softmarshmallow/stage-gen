export type DebugOverlayItem = Readonly<{
  label: string;
  quantity: number;
}>;

export type DebugOverlayProgression = Readonly<{
  level: number;
  experienceIntoLevel: number;
  /** Null once the authored maximum level is reached and there is nothing left to earn. */
  experienceForNext: number | null;
}>;

/** What the bot is doing, for the one surface where that question is worth a line of screen. */
export type DebugOverlayAutoPlay = Readonly<{
  enabled: boolean;
  /** False while a human has the controls, which is a different thing from being switched off. */
  driving: boolean;
  goal: string | null;
  reason: string | null;
}>;

export type DebugOverlayState = Readonly<{
  health: number;
  maximumHealth: number;
  inventory: readonly DebugOverlayItem[];
  /** Absent for a package that ships progression disabled; the line is then omitted entirely. */
  progression?: DebugOverlayProgression | null;
  /** Absent when the preview runs without a bot at all, as a fixed-frame capture does. */
  autoPlay?: DebugOverlayAutoPlay | null;
  /**
   * The kit being played, and whether it is the package's own.
   *
   * On the overlay because an override is invisible otherwise: a developer who switched, took a
   * screenshot, and came back an hour later has no other way to tell whether they are looking at
   * the package or at their own experiment. Absent for a run with nothing to switch to.
   */
  kit?: DebugOverlayKit | null;
}>;

export type DebugOverlayKit = Readonly<{
  label: string;
  /** False while a developer override is in force, which the line marks rather than hides. */
  published: boolean;
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
  const progression = state.progression
    ? `\nLV ${state.progression.level}  XP ${state.progression.experienceIntoLevel}${
        state.progression.experienceForNext === null
          ? " (max)"
          : `/${state.progression.experienceForNext}`
      }`
    : "";
  const autoPlay = state.autoPlay
    ? `\nAUTO ${
        !state.autoPlay.enabled
          ? "off"
          : state.autoPlay.driving
            ? `${state.autoPlay.goal ?? "thinking"}${
                state.autoPlay.reason ? ` — ${state.autoPlay.reason}` : ""
              }`
            : "yielded"
      }`
    : "";
  const kit = state.kit
    ? `\nKIT ${state.kit.label}${state.kit.published ? "" : " (override)"}`
    : "";
  return `DEBUG\nHP ${state.health}/${state.maximumHealth}${progression}${autoPlay}${kit}\n${
    inventory || "Inventory empty"
  }`;
}

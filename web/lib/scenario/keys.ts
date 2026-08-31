// Which key press means which scenario action, and when a page-level listener
// should keep its hands off.
//
// Moved here from the visual novel's own playback module when the beat list was
// retired: the mapping was never genre-specific, and the document-level gating
// rules - don't steal a key the page already handled, don't steal Enter from a
// focused button, don't type into a text field - are the kind of thing that is
// wrong in exactly one place and then copied.

import type { ScenarioAction } from "./runtime";

export interface ScenarioDocumentKeyContext {
  readonly defaultPrevented: boolean;
  readonly modified: boolean;
  /** The event target is a text input, textarea, or contenteditable. */
  readonly editableTarget: boolean;
  /** The event target activates on Enter or Space of its own accord. */
  readonly activationTarget: boolean;
}

/** The action a bare key press means, or null for a key the scenario does not own. */
export function scenarioActionForKey(key: string): ScenarioAction | null {
  if (key === "ArrowRight" || key === "Enter" || key === " " || key === "Spacebar") {
    return { kind: "advance" };
  }
  return null;
}

/**
 * The same mapping, for a listener bound to the document rather than a canvas.
 *
 * A page-level listener sees every key in the page, so it has to decline the
 * ones that already belong to something else. Getting this wrong is not a
 * cosmetic bug: a scene that swallows Enter makes every button on the page
 * unusable by keyboard.
 */
export function scenarioActionForDocumentKey(
  key: string,
  context: ScenarioDocumentKeyContext,
): ScenarioAction | null {
  if (context.defaultPrevented || context.modified || context.editableTarget) return null;
  if (context.activationTarget && (key === "Enter" || key === " " || key === "Spacebar")) {
    return null;
  }
  return scenarioActionForKey(key);
}

/** The 1-based option a number key selects, or null when it is not a digit key. */
export function scenarioOptionForKey(key: string): number | null {
  if (!/^[1-9]$/.test(key)) return null;
  return Number(key) - 1;
}

// What the node drawer shows, keyed by node id, with wording already applied: the port of
// the retired showcase's `drawer_data`, `check_words` and CHECK_WORDS. PageShell hands it to
// <GraphPlayer> as the graph player's config, where the showcase inlined it as
// `const NODES = {...}`.
//
// The keys are the showcase's (snake_case): the graph player reads them as it did. The JSON
// inside `verdict` and `pictures` is passed through as the example document holds it.

import type { JsonObject, JsonValue } from "@stage-gen/ui/contracts/wire";
import type { Page } from "@/lib/page";
import { clock, money } from "./shared";

/** What the drawer says for a node that was planned but not needed, by its reason. */
export const NOT_NEEDED: Readonly<Record<string, string>> = {
  verdict_reused: "Nothing changed, so the first verdict stands",
  revision_reused: "The first round passed",
  recovery_not_started: "Not needed: the first rig passed",
};

const CHECK_WORDS: Readonly<Record<string, string>> = {
  all_native_frames_lossless_verified: "Every frame decoded again and verified lossless",
  canonical_first_frame_exact: "The first frame is exactly the handed-on picture",
  loop_endpoints_exact: "The first and last frames match exactly",
  middle_motion_preserved_outside_authored_fields: "Motion outside the held face is left as generated",
  alpha_exact: "Transparency is unchanged",
  decoded_visible_rgba_and_alpha_exact: "The saved files decode to exactly the same pixels",
  feature_masks_disjoint: "Eye and mouth areas do not overlap",
  outside_support_rgba_exact: "Every pixel outside the patches is unchanged",
  rest_rgba_exact: "The resting face matches the original exactly",
  paint_canvas_exact: "The sheet came back at exactly the size it was asked for",
  joins_within_tone_limit: "No join between two tiles steps in tone beyond the limit",
  material_painted: "Every tile is painted, none left flat",
  no_transparent_pixels: "No tile has a hole in it",
  lookup_complete: "Every one of the 47 neighbour patterns has a tile",
  reserved_cell_clear: "The one reserved cell is left empty",
  exterior_transparent: "Everything outside the art is fully transparent",
  bands_tile_cleanly: "The edge bands repeat without a visible seam",
  text_area_quiet: "The text area is quiet enough to write on",
  text_readable: "Text on it reaches readable contrast",
  states_same_shape: "All four states keep the same outline and size",
  states_distinct: "Each state is visibly different from the normal one",
  glyphs_in_order: "All 16 icons are there, each in its own cell",
  glyphs_one_size: "The icons read as one set, at one size",
  nothing_outside_cells: "Nothing is drawn outside the cells",
  transparent_ground: "The drawing has a truly transparent background",
  canvas_edges_clear: "Nothing touches the edge of the canvas",
  every_frame_drawn: "Every frame has a pose in it",
  one_pose_per_frame: "Each pose was found whole and given its own cell",
  wrap_like_its_interior: "The wrap steps no more than the layer's own columns do",
  cuts_like_its_interior:
    "Both cuts step no more than the layer's own columns do, and the two pictures agreed there",
  repaint_admitted: "The repaint passed that test",
  loops_after_trim: "It still loops after its empty rows are trimmed",
};

export function checkWords(name: string): string {
  const text = CHECK_WORDS[name] ?? name.replaceAll("_", " ");
  return text.slice(0, 1).toUpperCase() + text.slice(1);
}

/** One node as the drawer reads it. */
export interface DrawerNode {
  readonly id: string;
  readonly title: string;
  readonly kind: string;
  readonly description: string;
  readonly model: string;
  readonly time: string | null;
  readonly cost: string | null;
  readonly tries: string | null;
  readonly not_needed: string | null;
  readonly verdict: JsonObject | null;
  readonly rationale: string | null;
  readonly open_issues: readonly JsonValue[];
  readonly pictures: readonly JsonObject[];
  readonly depends_on: readonly string[];
  readonly checks: readonly { readonly name: string; readonly passed: boolean }[];
  readonly prompt: string | null;
}

export type DrawerData = Record<string, DrawerNode>;

/** What the node drawer shows, keyed by node id, with wording already applied. */
export function drawerData(page: Page): DrawerData {
  const out: DrawerData = {};
  for (const [nid, n] of Object.entries(page.record.nodes)) {
    const tries = n.attempts;
    out[nid] = {
      id: nid,
      title: page.titleOf(nid),
      kind: n.kind,
      description: n.description,
      model: n.model ? `${n.model} via ${n.provider}` : "Runs locally",
      time: clock(n.durationMs),
      cost: money(n.costUsd),
      tries: !tries ? null : tries === 1 ? "first try" : `${tries} tries of ${n.maxAttempts}`,
      not_needed: n.notNeeded ? (NOT_NEEDED[n.notNeeded] ?? "Not needed") : null,
      verdict: n.verdict,
      rationale: n.rationale,
      open_issues: n.openIssues,
      pictures: n.pictures,
      depends_on: n.dependsOn,
      checks: n.checks.map((c) => ({ name: checkWords(String(c.name)), passed: Boolean(c.passed) })),
      prompt: n.prompt,
    };
  }
  return out;
}

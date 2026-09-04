// A hand-authored three-beat case, for the tests and for `/case/demo`.
//
// The case container is being authored on the producer side in parallel with
// this consumer, so the consumer was built against this instead of waiting. It
// is a fixture in the house sense - hand-written, no generator involved - and it
// exercises the whole loop the pilot needs: a scenario that stages five people
// and exports a fact, a room whose exit exports another, and a closing scenario
// that branches on both. Play it and the chaining, the fact hand-off, the five
// slots, the speaker emphasis, the autosave and the backlog are all on screen.
//
// The art is real. Every plate, backdrop and interface sheet is streamed from
// runs that already exist under `out/`, because a fixture drawn in flat colours
// proves the wiring and nothing about the picture. Two of the five actors are
// deliberately drawn from a third actor's spare plates: this package has three
// faces and the point of the beat is five slots, so the demo reuses a face
// rather than pretending a sixth exists. Nothing here is a rights claim on that
// art and nothing here is published; it is the demo route's scenery.

import { UI_ATLAS_FIXTURE_ROLES } from "@/lib/shell/prepared-runtime.fixture";
import type { UiAtlasRoleLayout } from "@/lib/manifest/ui-atlas-layout";
import { validateDialogueSceneFixture } from "@/lib/dialogue-scene/schema";
import type { DialogueSceneFixture } from "@/lib/dialogue-scene/schema";
import { parseRoomManifest } from "@/lib/pointclick/contract";
import type { RoomManifest } from "@/lib/pointclick/contract";
import { preparedAssetUrl } from "@/lib/shell/asset-url";
import { parseCase, type CaseDocument } from "./case";

/** The tag `/case/demo` plays under, and the key its autosave is written at. */
export const DEMO_CASE_TAG = "demo";

/** The runs the demo borrows its scenery from. */
const ART_RUN = "larkfield-ui-v1";
const ICON_RUN = "larkfield-icons-v1";

const SCRIPT_SHA256 = "0123456789abcdef".repeat(4);

/**
 * The interface geometry these two sheets actually publish.
 *
 * Written out rather than invented, because a nine-slice is cut by exactly these
 * numbers: a plausible-looking rectangle slices the wrong part of the drawn frame
 * and the demo becomes evidence of nothing but a misaligned panel. A real case
 * reads this off the run's own bundle; only the demo has to carry it. The icon
 * grid is the shared fixture's, whose declared cells are the same grid.
 */
const DEMO_PANEL_FRAME: UiAtlasRoleLayout = {
  role: "panel_frame",
  layout: "nine_slice_panel_1024_v1",
  scale_mode: "nine_slice",
  alpha_policy: "transparent_exterior_opaque_body_v1",
  band_fill: "stretch",
  draw_scale: 2,
  canvas: {
    width: 1024,
    height: 1024
  },
  insets: {
    left: 96,
    top: 96,
    right: 96,
    bottom: 96
  },
  cells: [
    {
      state: "default",
      cell: {
        x: 41,
        y: 328,
        width: 942,
        height: 337
      },
      content_rect: {
        x: 137,
        y: 424,
        width: 750,
        height: 145
      },
      safe_rect: {
        x: 137,
        y: 424,
        width: 750,
        height: 145
      }
    }
  ]
};

const DEMO_BUTTON_RECT: UiAtlasRoleLayout = {
  role: "button_rect",
  layout: "nine_slice_button_sheet_4x1024_v1",
  scale_mode: "nine_slice",
  alpha_policy: "transparent_exterior_opaque_body_v1",
  band_fill: "stretch",
  draw_scale: 2,
  canvas: {
    width: 1024,
    height: 1024
  },
  insets: {
    left: 80,
    top: 40,
    right: 80,
    bottom: 40
  },
  cells: [
    {
      state: "normal",
      cell: {
        x: 90,
        y: 104,
        width: 844,
        height: 152
      },
      content_rect: {
        x: 170,
        y: 144,
        width: 684,
        height: 72
      },
      safe_rect: {
        x: 170,
        y: 144,
        width: 684,
        height: 72
      }
    },
    {
      state: "hover",
      cell: {
        x: 90,
        y: 319,
        width: 844,
        height: 150
      },
      content_rect: {
        x: 170,
        y: 359,
        width: 684,
        height: 70
      },
      safe_rect: {
        x: 170,
        y: 359,
        width: 684,
        height: 70
      }
    },
    {
      state: "pressed",
      cell: {
        x: 90,
        y: 532,
        width: 844,
        height: 150
      },
      content_rect: {
        x: 170,
        y: 572,
        width: 684,
        height: 70
      },
      safe_rect: {
        x: 170,
        y: 572,
        width: 684,
        height: 70
      }
    },
    {
      state: "disabled",
      cell: {
        x: 90,
        y: 745,
        width: 844,
        height: 149
      },
      content_rect: {
        x: 170,
        y: 785,
        width: 684,
        height: 69
      },
      safe_rect: {
        x: 170,
        y: 785,
        width: 684,
        height: 69
      }
    }
  ]
};

/** The same three roles as a raw manifest block, for the room's JSON fixture. */
function demoUiBlock(): Record<string, unknown> {
  return {
    panel_frame: { ...DEMO_PANEL_FRAME, asset: "ui/panel_frame.png" },
    button_rect: { ...DEMO_BUTTON_RECT, asset: "ui/button_rect.png" },
    preview_icons: { ...UI_ATLAS_FIXTURE_ROLES.preview_icons, asset: "ui/preview_icons.png" },
  };
}

function art(file: string): string {
  return preparedAssetUrl(ART_RUN, `assets/${file}`);
}

export function demoCaseDocument(): CaseDocument {
  return parseCase(demoCaseWire());
}

/** The wire form, so a test can prove the parser on the same bytes the route plays. */
export function demoCaseWire(): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: "case-runtime-v1",
    case_id: "demo_case",
    display_name: "A demonstration case",
    entry: "demo_supper",
    facts: [
      {
        fact_id: "heard_the_toast",
        establishment: "defaults_false",
        summary: "Somebody said something before the soup went cold.",
      },
      {
        fact_id: "saw_the_card",
        establishment: "defaults_false",
        summary: "The card on the console was read.",
      },
      {
        fact_id: "asked_about_the_bell",
        establishment: "defaults_false",
        summary: "The service bell was looked at.",
      },
      {
        fact_id: "left_the_room",
        establishment: "required",
        summary: "The room was left by its own door.",
      },
    ],
    beats: [
      {
        beat_id: "demo_supper",
        kind: "scenario",
        run_tag: ART_RUN,
        display_name: "The table",
        writes: ["heard_the_toast"],
        edges: [{ outcome: "to_the_room", to: "demo_room" }],
      },
      {
        beat_id: "demo_room",
        kind: "room",
        run_tag: ART_RUN,
        display_name: "The broadcast room",
        writes: ["saw_the_card", "asked_about_the_bell", "left_the_room"],
        edges: [{ outcome: "win", to: "demo_close" }],
      },
      {
        beat_id: "demo_close",
        kind: "scenario",
        run_tag: ART_RUN,
        display_name: "After",
        reads: ["heard_the_toast", "saw_the_card", "asked_about_the_bell"],
        terminal: true,
        edges: [],
      },
    ],
  };
}

/** The scenario or room one beat plays, or null when the beat id names nothing. */
export function demoCaseLeaf(
  beatId: string,
): { scene: DialogueSceneFixture; room: null } | { scene: null; room: RoomManifest } | null {
  if (beatId === "demo_supper") return { scene: demoSupperFixture(), room: null };
  if (beatId === "demo_close") return { scene: demoCloseFixture(), room: null };
  if (beatId === "demo_room") return { scene: null, room: demoRoomManifest() };
  return null;
}

// -------------------------------------------------------------------- scene

interface DemoActor {
  readonly actorId: string;
  readonly label: string;
  readonly plates: readonly [string, string];
}

/**
 * Five people at one table.
 *
 * `composed` and `pleased` rather than a generic mood pair, because the
 * expression vocabulary belongs to the cast declaration now and a fixture that
 * kept using the old closed four would not exercise that.
 */
const DEMO_CAST: readonly DemoActor[] = Object.freeze([
  Object.freeze({ actorId: "nao", label: "Nao", plates: ["nao-neutral", "nao-delighted"] as const }),
  Object.freeze({
    actorId: "haruki",
    label: "Haruki",
    plates: ["haruki-neutral", "haruki-delighted"] as const,
  }),
  Object.freeze({
    actorId: "sayaka",
    label: "Sayaka",
    plates: ["sayaka-neutral", "sayaka-delighted"] as const,
  }),
  Object.freeze({
    actorId: "mari",
    label: "Mari",
    plates: ["nao-flustered", "nao-concerned"] as const,
  }),
  Object.freeze({
    actorId: "kenji",
    label: "Kenji",
    plates: ["haruki-flustered", "haruki-concerned"] as const,
  }),
]);

const EXPRESSIONS = Object.freeze(["composed", "pleased"] as const);

function castFixtureEntry(actor: DemoActor): Record<string, unknown> {
  return {
    actorId: actor.actorId,
    appearance: {
      id: `${actor.actorId}-demo`,
      label: actor.label,
      age: 18,
      role: "One of five at the table, for the five-slot demonstration",
      description: "An original character, drawn for the demo route only.",
      visualIdentity: "Borrowed from a generated plate in an existing run; see this file's header.",
      artDirection: "clean 2D illustration",
    },
    expressions: actor.plates.map((plate, index) => ({
      id: `${actor.actorId}-${EXPRESSIONS[index]}`,
      src: art(`${plate}.png`),
      alt: `${actor.label} looking ${EXPRESSIONS[index]}`,
      state: EXPRESSIONS[index]!,
      label: EXPRESSIONS[index] === "composed" ? "Composed" : "Pleased",
      description: `${actor.label}, ${EXPRESSIONS[index]}.`,
    })),
  };
}

function sceneShell(
  fixtureId: string,
  title: string,
  sceneLabel: string,
  scenario: Record<string, unknown>,
): DialogueSceneFixture {
  return validateDialogueSceneFixture({
    schemaVersion: 1,
    fixtureId,
    title,
    sceneLabel,
    presentation: { framingZoom: 70, sourceFramingZoom: 70 },
    styleSrc: art("style-plate.png"),
    stages: [
      {
        stageId: "supper_room",
        id: "supper-room",
        src: art("stage-classroom-day.png"),
        alt: "A room laid for a meal, no people",
      },
      {
        stageId: "after_dark",
        id: "after-dark",
        src: art("stage-classroom-dusk.png"),
        alt: "The same room at blue hour, no people",
      },
    ],
    tracks: [],
    actors: DEMO_CAST.map(castFixtureEntry),
    ui: {
      panelFrame: {
        layout: DEMO_PANEL_FRAME,
        src: preparedAssetUrl(ART_RUN, "ui/panel_frame.png"),
      },
      buttonRect: {
        layout: DEMO_BUTTON_RECT,
        src: preparedAssetUrl(ART_RUN, "ui/button_rect.png"),
      },
      previewIcons: {
        layout: UI_ATLAS_FIXTURE_ROLES.preview_icons,
        src: preparedAssetUrl(ICON_RUN, "ui/preview_icons.png"),
      },
    },
    scenario,
  });
}

function castDeclaration(): readonly Record<string, unknown>[] {
  return [
    ...DEMO_CAST.map((actor) => ({
      actor_id: actor.actorId,
      display_name: actor.label,
      expressions: [...EXPRESSIONS],
    })),
    // The protagonist convention: speaks, is never drawn, needs no plates.
    { actor_id: "you", display_name: "You", expressions: [] },
  ];
}

function stageDeclaration(): readonly Record<string, unknown>[] {
  return [
    { stage_id: "supper_room", brief: "A room laid for a meal, warm lamps, no people" },
    { stage_id: "after_dark", brief: "The same room after dark, no people" },
  ];
}

/** Beat one: five slots, a speaker moving around the table, and one exported fact. */
export function demoSupperFixture(): DialogueSceneFixture {
  return sceneShell("demo-supper", "The table", "Beat one of the demonstration case", {
    schema_version: 2,
    kind: "scenario-program-v2",
    game_id: "demo_case",
    scenario_id: "demo_supper",
    display_name: "The table",
    revision: 1,
    script_sha256: SCRIPT_SHA256,
    entry: "table",
    cast: castDeclaration(),
    stages: stageDeclaration(),
    flags: [{ flag_id: "heard_the_toast" }],
    endings: [{ outcome_id: "to_the_room", label: "You went down to the room" }],
    blocks: [
      {
        label: "table",
        statements: [
          { kind: "stage", stage: "supper_room" },
          {
            kind: "line",
            text: "Five of them are already seated when you come in, and the sixth chair is yours.",
          },
          { kind: "show", actor: "mari", expression: "composed", slot: "far_left" },
          { kind: "show", actor: "nao", expression: "composed", slot: "left" },
          { kind: "show", actor: "haruki", expression: "composed", slot: "center" },
          { kind: "show", actor: "sayaka", expression: "composed", slot: "right" },
          { kind: "show", actor: "kenji", expression: "composed", slot: "far_right" },
          {
            kind: "line",
            speaker: "haruki",
            text: "Sit down. Nobody has said anything worth repeating yet.",
          },
          {
            kind: "line",
            speaker: "nao",
            expression: "pleased",
            text: "That is not true. Mari said something about the card.",
          },
          {
            kind: "line",
            speaker: "mari",
            text: "I said the eighth one was turned the wrong way round. That is all I said.",
          },
          {
            kind: "line",
            speaker: "kenji",
            text: "From where I am sitting you can see it perfectly well.",
          },
          { kind: "jump", target: "the_toast" },
        ],
      },
      {
        label: "the_toast",
        statements: [
          {
            kind: "line",
            speaker: "sayaka",
            text: "Somebody should say something before the soup goes cold.",
          },
          {
            kind: "choice",
            options: [
              { text: "Let Sayaka give the toast.", target: "toast_given" },
              { text: "Say nothing, and watch the card.", target: "toast_skipped" },
            ],
          },
        ],
      },
      {
        label: "toast_given",
        statements: [
          { kind: "hide", actor: "kenji" },
          { kind: "hide", actor: "mari" },
          { kind: "show", actor: "sayaka", expression: "pleased", slot: "center" },
          { kind: "hide", actor: "haruki" },
          {
            kind: "line",
            speaker: "sayaka",
            text: "To the ones who came, and to the one who did not.",
          },
          { kind: "set", flag: "heard_the_toast" },
          { kind: "jump", target: "downstairs" },
        ],
      },
      {
        label: "toast_skipped",
        statements: [
          {
            kind: "line",
            text: "You say nothing. The eighth card stays turned inward, and nobody moves it.",
          },
          { kind: "jump", target: "downstairs" },
        ],
      },
      {
        label: "downstairs",
        statements: [
          { kind: "stage", stage: "after_dark" },
          {
            kind: "line",
            text: "The telephone goes at nine, and it is for you. The room it means is downstairs.",
          },
          { kind: "end", outcome: "to_the_room" },
        ],
      },
    ],
  });
}

/** Beat three: the same cast, reading what the first two beats exported. */
export function demoCloseFixture(): DialogueSceneFixture {
  return sceneShell("demo-close", "After", "Beat three of the demonstration case", {
    schema_version: 2,
    kind: "scenario-program-v2",
    game_id: "demo_case",
    scenario_id: "demo_close",
    display_name: "After",
    revision: 1,
    script_sha256: SCRIPT_SHA256,
    entry: "after",
    cast: castDeclaration(),
    stages: stageDeclaration(),
    // Every flag this beat reads is a fact an earlier beat established, so each is
    // declared `imported` and none of them is set here.
    flags: [
      { flag_id: "heard_the_toast", origin: "imported" },
      { flag_id: "saw_the_card", origin: "imported" },
      { flag_id: "asked_about_the_bell", origin: "imported" },
    ],
    endings: [
      { outcome_id: "closed_with_the_card", label: "You told them about the card" },
      { outcome_id: "closed_quietly", label: "You kept it" },
    ],
    blocks: [
      {
        label: "after",
        statements: [
          { kind: "stage", stage: "after_dark" },
          { kind: "show", actor: "haruki", expression: "composed", slot: "left" },
          { kind: "show", actor: "nao", expression: "composed", slot: "right" },
          {
            kind: "line",
            speaker: "haruki",
            text: "They will want to know what you looked at down there.",
          },
          {
            kind: "branch",
            edges: [{ condition: { requires: ["saw_the_card"] }, target: "you_saw_it" }],
            default: "you_did_not",
          },
        ],
      },
      {
        label: "you_saw_it",
        statements: [
          {
            kind: "line",
            speaker: "you",
            text: "The card on the console had a name on it, and it was not the one on the door.",
          },
          {
            kind: "line",
            speaker: "nao",
            expression: "pleased",
            text: "Then you were paying attention after all.",
          },
          { kind: "jump", target: "the_bell" },
        ],
      },
      {
        label: "you_did_not",
        statements: [
          { kind: "line", speaker: "you", text: "Not enough. I went down and I came back." },
          {
            kind: "line",
            speaker: "haruki",
            text: "That is the answer of a man who wants his supper.",
          },
          { kind: "jump", target: "the_bell" },
        ],
      },
      {
        label: "the_bell",
        statements: [
          {
            kind: "branch",
            edges: [
              { condition: { requires: ["asked_about_the_bell"] }, target: "close_with_the_card" },
              { condition: { requires: ["heard_the_toast"] }, target: "close_quietly" },
            ],
            default: "close_quietly",
          },
        ],
      },
      {
        label: "close_with_the_card",
        statements: [
          {
            kind: "line",
            text: "You tell them about the bell, and then about the card, and the table goes quiet in the right order.",
          },
          { kind: "end", outcome: "closed_with_the_card" },
        ],
      },
      {
        label: "close_quietly",
        statements: [
          { kind: "line", text: "You keep it. The evening closes over the top of it." },
          { kind: "end", outcome: "closed_quietly" },
        ],
      },
    ],
  });
}

// --------------------------------------------------------------------- room

/**
 * Beat two: an inspect-only room with one exit.
 *
 * Every look is optional and exports a fact; the exit is the only interaction
 * the win depends on, exactly the shape the pilot's two rooms use. There are no
 * items, so nothing crosses the boundary but flags.
 */
export function demoRoomManifest(): RoomManifest {
  return parseRoomManifest(demoRoomWire());
}

export function demoRoomWire(): Record<string, unknown> {
  return {
    schema_version: 3,
    kind: "pointclick-room-runtime-v3",
    room_id: "demo_room",
    display_name: "The broadcast room",
    revision: 1,
    room_sha256: "d".repeat(64),
    cover: "assets/style-plate.png",
    scene: { width: 1672, height: 941, backdrop: "assets/stage-radio-room.png" },
    hotspots: [
      {
        id: "card",
        label: "The card on the console",
        art: "scenery",
        region: { x: 0.36, y: 0.52, w: 0.18, h: 0.16 },
        hidden: false,
        sprite: null,
      },
      {
        id: "bell",
        label: "The service bell",
        art: "scenery",
        region: { x: 0.62, y: 0.48, w: 0.14, h: 0.18 },
        hidden: false,
        sprite: null,
      },
      {
        id: "door",
        label: "The stair door",
        art: "scenery",
        region: { x: 0.04, y: 0.24, w: 0.16, h: 0.6 },
        hidden: false,
        sprite: null,
      },
    ],
    items: [],
    interactions: [
      {
        on: { verb: "inspect", hotspot: "card", item: null },
        requires: [],
        effects: [{ set_flag: "saw_the_card" }],
        narration:
          "A card is propped against the console with a name written on it in green ink. It is not the name on the door.",
      },
      {
        on: { verb: "inspect", hotspot: "bell", item: null },
        requires: [],
        effects: [{ set_flag: "asked_about_the_bell" }],
        narration:
          "The service bell has been pressed hard enough to leave the brass bright in one small place.",
      },
      {
        on: { verb: "use", hotspot: "door", item: null },
        requires: [],
        effects: [{ set_flag: "left_the_room" }],
        narration: "You put your hand on the stair door and go back up.",
      },
    ],
    win: { requires: ["left_the_room"], narration: "You leave the room behind you." },
    ui: demoUiBlock(),
  };
}

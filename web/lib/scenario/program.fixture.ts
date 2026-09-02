// A hand-authored `scenario-program-v2` wire document for tests.
//
// Deliberately an untyped record, like every `*.fixture.ts` here: the parser
// under test is what gives it shape. It replaces a committed copy of the Python
// compiler's output - a derived file has no business in the tree - so the wire
// truth both sides answer to is the contract in `docs/spec/game/scenario.md`,
// held by two strict parsers that each refuse unknown keys. The compiled seam
// itself is exercised every time a produced bundle is played.
//
// The story is a two-scene ferry crossing written to use the whole statement
// vocabulary at least once: stage, audio play/stop, narration and spoken lines,
// expression-bearing lines, show with and without an expression, hide, set,
// a conditional choice option, an ordered branch with a default, jump, and
// three distinct endings.

const SCRIPT_SHA256 = "0123456789abcdef".repeat(4);

/** A fresh document each call, so a test can mutate its copy freely. */
export function ferryProgramDocument(): Record<string, unknown> {
  return {
    schema_version: 2,
    kind: "scenario-program-v2",
    game_id: "harborlight",
    scenario_id: "ferry_bell",
    display_name: "The Ferry Bell",
    revision: 1,
    script_sha256: SCRIPT_SHA256,
    entry: "opening",
    cast: [
      {
        actor_id: "mara",
        display_name: "Mara",
        expressions: ["neutral", "delighted", "concerned"],
      },
      { actor_id: "teo", display_name: "Teo", expressions: ["neutral", "delighted"] },
      { actor_id: "you", expressions: [] },
    ],
    stages: [
      { stage_id: "pier_dusk", brief: "A wooden harbor pier at dusk, lanterns just lit." },
      { stage_id: "boathouse", brief: "Inside the boathouse, coiled rope and a ticket booth." },
    ],
    tracks: [
      {
        track_id: "harbor_wind",
        brief: "Low wind over water and a far bell buoy.",
        generation: {
          intent: "generate",
          instrumental: true,
          seamless_loop: true,
          target_duration_seconds: 60,
        },
      },
    ],
    flags: [
      { flag_id: "asked_the_fare" },
      { flag_id: "has_token" },
      { flag_id: "rang_the_bell" },
    ],
    endings: [
      { outcome_id: "crossed", label: "You crossed at dusk" },
      { outcome_id: "stayed", label: "The harbor kept you" },
      { outcome_id: "stranded", label: "The last ferry left without you" },
    ],
    blocks: [
      {
        label: "opening",
        statements: [
          { kind: "stage", stage: "pier_dusk" },
          { kind: "audio", action: "play", track: "harbor_wind" },
          {
            kind: "line",
            text: "The last ferry of the day rocks against the pier, and nobody has rung for it.",
          },
          { kind: "show", actor: "mara", expression: "neutral", slot: "center" },
          {
            kind: "line",
            speaker: "mara",
            text: "You're cutting it close. She won't wait past dark.",
          },
          {
            kind: "choice",
            options: [
              { text: "Ring the bell.", target: "ringing" },
              { text: "Ask what the crossing costs.", target: "asking" },
            ],
          },
        ],
      },
      {
        label: "ringing",
        statements: [
          { kind: "set", flag: "rang_the_bell", value: true },
          {
            kind: "line",
            speaker: "mara",
            expression: "delighted",
            text: "There it is. She'll hear that from the far shore.",
          },
          { kind: "jump", target: "boathouse_door" },
        ],
      },
      {
        label: "asking",
        statements: [
          { kind: "set", flag: "asked_the_fare", value: true },
          { kind: "line", speaker: "you", text: "What does the crossing cost this late?" },
          {
            kind: "line",
            speaker: "mara",
            expression: "concerned",
            text: "More than the bell would have. Asking first is how people end up staying.",
          },
          { kind: "jump", target: "boathouse_door" },
        ],
      },
      {
        label: "boathouse_door",
        statements: [
          { kind: "stage", stage: "boathouse" },
          { kind: "show", actor: "mara", slot: "left" },
          {
            kind: "line",
            text: "Inside, the light is the colour of old rope. Mara follows you to the booth.",
          },
          {
            kind: "choice",
            options: [
              {
                text: "Trade your coin for a token.",
                target: "token_booth",
                condition: { requires: ["rang_the_bell"] },
              },
              { text: "Wait by the door.", target: "waiting" },
              { text: "Walk back up the hill.", target: "hill" },
            ],
          },
        ],
      },
      {
        label: "token_booth",
        statements: [
          { kind: "set", flag: "has_token", value: true },
          {
            kind: "line",
            speaker: "mara",
            expression: "neutral",
            text: "One token, one crossing. Keep it in your fist, not your pocket.",
          },
          { kind: "jump", target: "departure" },
        ],
      },
      {
        label: "waiting",
        statements: [
          { kind: "line", text: "You lean on the door frame and watch the water go grey." },
          { kind: "jump", target: "departure" },
        ],
      },
      {
        label: "hill",
        statements: [
          { kind: "audio", action: "stop", track: "harbor_wind" },
          { kind: "hide", actor: "mara" },
          { kind: "line", text: "You climb until the wind drops and the pier is a line of lamps." },
          { kind: "jump", target: "departure" },
        ],
      },
      {
        label: "departure",
        statements: [
          { kind: "line", text: "Out on the water, the ferry swings her bow toward the pier." },
          {
            kind: "branch",
            edges: [
              { condition: { requires: ["has_token"] }, target: "token_departure" },
              { condition: { requires: ["rang_the_bell"] }, target: "bell_departure" },
            ],
            default: "left_behind",
          },
        ],
      },
      {
        label: "token_departure",
        statements: [
          {
            kind: "line",
            speaker: "mara",
            expression: "delighted",
            text: "Token and bell both. She'd cross a storm for a passenger this sure.",
          },
          { kind: "end", outcome: "crossed" },
        ],
      },
      {
        label: "bell_departure",
        statements: [
          { kind: "show", actor: "teo", expression: "neutral", slot: "right" },
          {
            kind: "line",
            speaker: "teo",
            expression: "delighted",
            text: "You rang, no token. She'll take you as far as the breakwater and no further.",
          },
          { kind: "end", outcome: "stayed" },
        ],
      },
      {
        label: "left_behind",
        statements: [
          {
            kind: "line",
            speaker: "mara",
            expression: "concerned",
            text: "She only answers the bell. Come back tomorrow with less caution.",
          },
          { kind: "end", outcome: "stranded" },
        ],
      },
    ],
  };
}

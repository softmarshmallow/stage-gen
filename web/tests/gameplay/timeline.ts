import { PLATFORMER_FIXED_STEP_SECONDS } from "../../lib/runtime/vertical";

export const GAMEPLAY_FPS = 1 / PLATFORMER_FIXED_STEP_SECONDS;
export const GAMEPLAY_FRAME_COUNT = 900;
export const GAMEPLAY_DURATION_SECONDS = GAMEPLAY_FRAME_COUNT / GAMEPLAY_FPS;
export const GAMEPLAY_STEP_MS = PLATFORMER_FIXED_STEP_SECONDS * 1000;

export type GameplayKey =
  | "ArrowLeft"
  | "ArrowRight"
  | "ArrowUp"
  | "ArrowDown"
  | "Shift"
  | "Space"
  | "j"
  | "s"
  | "i";

export type KeyboardAction = Readonly<{
  type: "down" | "up";
  key: GameplayKey;
}>;

export type GameplayFrame = Readonly<{
  index: number;
  actions: readonly KeyboardAction[];
}>;

const actionsAt = new Map<number, readonly KeyboardAction[]>([
  [30, [{ type: "down", key: "j" }]],
  [31, [{ type: "up", key: "j" }]],
  [54, [{ type: "down", key: "ArrowRight" }]],
  // Every terrain rise is a wall now, so the approach climbs the two faces
  // between the spawn and the platform section instead of walking up them.
  [
    70,
    [
      { type: "down", key: "Shift" },
      { type: "down", key: "Space" },
    ],
  ],
  [71, [{ type: "up", key: "Space" }]],
  [81, [{ type: "down", key: "Space" }]],
  [82, [{ type: "up", key: "Space" }]],
  // Launch five frames earlier than the ledge itself. The tier-one deck is
  // flush with the terrain running into it, so a jump pressed at the ledge now
  // leaves from the deck rather than the ground 64px below and lands back on
  // it too late for the drop that follows to read.
  [125, [{ type: "down", key: "Space" }]],
  [126, [{ type: "up", key: "Space" }]],
  [
    145,
    [
      { type: "up", key: "ArrowRight" },
      { type: "up", key: "Shift" },
    ],
  ],
  // Crouch where the player is already stationary, so it exercises the state
  // without costing the run ground or widening the sprite inside the drop
  // clearance window measured later.
  [146, [{ type: "down", key: "s" }]],
  [152, [{ type: "up", key: "s" }]],
  [
    153,
    [
      { type: "down", key: "ArrowRight" },
      { type: "down", key: "Shift" },
      { type: "down", key: "ArrowDown" },
      { type: "down", key: "Space" },
    ],
  ],
  [
    154,
    [
      { type: "up", key: "ArrowDown" },
      { type: "up", key: "Space" },
    ],
  ],
  [
    162,
    [
      { type: "up", key: "ArrowRight" },
      { type: "up", key: "Shift" },
    ],
  ],
  [
    172,
    [
      { type: "down", key: "ArrowLeft" },
      { type: "down", key: "Shift" },
    ],
  ],
  // The column the recovery walks back into is a tile higher, so the way onto
  // the deck is a double jump off its face rather than a stroll and a hop.
  [174, [{ type: "down", key: "Space" }]],
  [175, [{ type: "up", key: "Space" }]],
  [184, [{ type: "down", key: "Space" }]],
  [
    185,
    [
      { type: "up", key: "Space" },
      { type: "up", key: "ArrowLeft" },
      { type: "up", key: "Shift" },
    ],
  ],
  [
    196,
    [
      { type: "down", key: "ArrowRight" },
      { type: "down", key: "Shift" },
      { type: "down", key: "Space" },
    ],
  ],
  [197, [{ type: "up", key: "Space" }]],
  [216, [{ type: "down", key: "Space" }]],
  [217, [{ type: "up", key: "Space" }]],
  [241, [{ type: "down", key: "Space" }]],
  [242, [{ type: "up", key: "Space" }]],
  // Five frames later than before: the recovery now leaves from a wall face a
  // little further right, so the summit run needs those frames to reach the
  // ladder's activation band.
  [
    274,
    [
      { type: "up", key: "ArrowRight" },
      { type: "up", key: "Shift" },
      { type: "down", key: "ArrowDown" },
    ],
  ],
  [296, [{ type: "up", key: "ArrowDown" }]],
  [299, [{ type: "down", key: "ArrowDown" }]],
  [320, [{ type: "up", key: "ArrowDown" }]],
  [
    321,
    [
      { type: "down", key: "ArrowRight" },
      { type: "down", key: "Shift" },
    ],
  ],
  // The closing run climbs the terrain it crosses. Each press is placed so
  // the foot is above the next column face as it passes over it; the two
  // marked pairs are two-tile walls that only the air jump clears.
  [370, [{ type: "down", key: "Space" }]],
  [371, [{ type: "up", key: "Space" }]],
  [448, [{ type: "down", key: "Space" }]],
  [449, [{ type: "up", key: "Space" }]],
  [469, [{ type: "down", key: "Space" }]],
  [470, [{ type: "up", key: "Space" }]],
  [
    480,
    [
      { type: "down", key: "Space" }, // air jump: second impulse over a two-tile wall
      { type: "down", key: "i" },
    ],
  ],
  [
    481,
    [
      { type: "up", key: "Space" },
      { type: "up", key: "i" },
    ],
  ],
  [522, [{ type: "down", key: "Space" }]],
  [523, [{ type: "up", key: "Space" }]],
  [569, [{ type: "down", key: "Space" }]],
  [570, [{ type: "up", key: "Space" }]],
  [633, [{ type: "down", key: "Space" }]],
  [634, [{ type: "up", key: "Space" }]],
  [660, [{ type: "down", key: "Space" }]],
  [661, [{ type: "up", key: "Space" }]],
  [713, [{ type: "down", key: "Space" }]],
  [714, [{ type: "up", key: "Space" }]],
  [723, [{ type: "down", key: "Space" }]],  // air jump: second impulse over a two-tile wall
  [724, [{ type: "up", key: "Space" }]],
  [743, [{ type: "down", key: "Space" }]],
  [744, [{ type: "up", key: "Space" }]],
  [771, [{ type: "down", key: "Space" }]],
  [772, [{ type: "up", key: "Space" }]],
  // Standing in the portal is not using it. The run halts inside its mouth,
  // waits, and then presses; travel that fired on contact could not tell a
  // player crossing the threshold from one who meant to step through.
  [
    852,
    [
      { type: "up", key: "ArrowRight" },
      { type: "up", key: "Shift" },
    ],
  ],
  [858, [{ type: "down", key: "ArrowUp" }]],
  [859, [{ type: "up", key: "ArrowUp" }]],
  // Arrival on the next stage keeps playing: its opening columns rise too, so
  // the last second climbs rather than leaning on the first face it meets.
  // The first face is barely half a tile from where the portal sets the player
  // down, so the climb starts before the run does.
  [861, [{ type: "down", key: "Space" }]],
  [862, [{ type: "up", key: "Space" }]],
  [
    866,
    [
      { type: "down", key: "ArrowRight" },
      { type: "down", key: "Shift" },
    ],
  ],
  [883, [{ type: "down", key: "Space" }]],
  [884, [{ type: "up", key: "Space" }]],
  [
    899,
    [
      { type: "up", key: "Shift" },
      { type: "up", key: "ArrowRight" },
    ],
  ],
]);

function freezeActions(actions: readonly KeyboardAction[]): readonly KeyboardAction[] {
  return Object.freeze(actions.map((action) => Object.freeze({ ...action })));
}

/**
 * A fixed 30-second keyboard script. Actions are applied before the indexed
 * simulation step. The two rightward runs intentionally traverse the whole
 * 12,800-pixel stage and enter the exit portal without private scene mutation.
 */
export const GAMEPLAY_TIMELINE: readonly GameplayFrame[] = Object.freeze(
  Array.from({ length: GAMEPLAY_FRAME_COUNT }, (_, index) =>
    Object.freeze({
      index,
      actions: freezeActions(actionsAt.get(index) ?? []),
    }),
  ),
);

export const GAMEPLAY_SELECTED_FRAMES = Object.freeze([
  1,
  31,
  35,
  43,
  49,
  67,
  125,
  126,
  146,
  153,
  154,
  161,
  162,
  165,
  171,
  172,
  175,
  176,
  190,
  196,
  197,
  211,
  217,
  231,
  242,
  256,
  275,
  297,
  300,
  320,
  481,
  858,
  859,
  860,
  900,
] as const);

export const GAMEPLAY_POSTER_FRAME = 35;

export const GAMEPLAY_EVENT_VISIBILITY_WINDOWS = Object.freeze({
  hit: Object.freeze({ start: 34, end: 36 }),
  death: Object.freeze({ start: 43, end: 45 }),
  drop: Object.freeze({ start: 49, end: 51 }),
  pickup: Object.freeze({ start: 67, end: 76 }),
  // The exit portal's mouth is 60% of the sprite's width, centred, so the
  // player crosses into it three frames after the sprite first overlaps them.
  stageAdvance: Object.freeze({ start: 859, end: 859 }),
});

export const GAMEPLAY_REQUIRED_STATES = Object.freeze([
  "idle",
  "walk",
  "run",
  "jump",
  "crouch",
  "attack",
  "climb",
] as const);

export const GAMEPLAY_REQUIRED_EVENTS = Object.freeze([
  "mob-hit",
  "mob-death",
  "mob-drop",
  "item-pickup",
  "stage-advance",
] as const);

export const GAMEPLAY_VERTICAL_EVENT_SEQUENCE = Object.freeze([
  Object.freeze({
    kind: "ladder-enter",
    ladderId: "ladder-summit",
    endpoint: "platform",
  }),
  Object.freeze({
    kind: "ladder-exit",
    ladderId: "ladder-summit",
    endpoint: "terrain",
  }),
] as const);

export const GAMEPLAY_PLATFORM_EVENT_SEQUENCE = Object.freeze([
  Object.freeze({ kind: "platform-land", platformId: "tier-1-launch" }),
  Object.freeze({ kind: "platform-drop", platformId: "tier-1-launch" }),
  Object.freeze({ kind: "platform-land", platformId: "tier-1-launch" }),
  Object.freeze({ kind: "platform-land", platformId: "tier-2-transfer" }),
  Object.freeze({ kind: "platform-land", platformId: "tier-3-bridge" }),
  Object.freeze({ kind: "platform-land", platformId: "tier-4-summit" }),
] as const);

export const GAMEPLAY_DROP_EVENT_SEQUENCE = Object.freeze([
  Object.freeze({ kind: "platform-drop", platformId: "tier-1-launch" }),
  Object.freeze({
    kind: "platform-underside-clear",
    platformId: "tier-1-launch",
  }),
  Object.freeze({
    kind: "platform-lower-land",
    platformId: "tier-1-launch",
  }),
  Object.freeze({
    kind: "platform-lower-settle",
    platformId: "tier-1-launch",
  }),
  Object.freeze({
    kind: "platform-recovery-launch",
    platformId: "tier-1-launch",
  }),
  Object.freeze({
    kind: "platform-recovery-land",
    platformId: "tier-1-launch",
  }),
] as const);

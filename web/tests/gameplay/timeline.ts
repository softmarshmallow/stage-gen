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
  [70, [{ type: "down", key: "Shift" }]],
  [130, [{ type: "down", key: "Space" }]],
  [131, [{ type: "up", key: "Space" }]],
  [
    145,
    [
      { type: "up", key: "ArrowRight" },
      { type: "up", key: "Shift" },
    ],
  ],
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
  [
    175,
    [
      { type: "up", key: "ArrowLeft" },
      { type: "up", key: "Shift" },
      { type: "down", key: "Space" },
    ],
  ],
  [176, [{ type: "up", key: "Space" }]],
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
  [
    269,
    [
      { type: "up", key: "ArrowRight" },
      { type: "up", key: "Shift" },
      { type: "down", key: "ArrowDown" },
    ],
  ],
  [291, [{ type: "up", key: "ArrowDown" }]],
  [294, [{ type: "down", key: "ArrowDown" }]],
  [315, [{ type: "up", key: "ArrowDown" }]],
  [
    316,
    [
      { type: "down", key: "ArrowRight" },
      { type: "down", key: "Shift" },
    ],
  ],
  [
    450,
    [
      { type: "up", key: "Shift" },
      { type: "down", key: "s" },
    ],
  ],
  [
    480,
    [
      { type: "up", key: "s" },
      { type: "down", key: "i" },
      { type: "down", key: "Shift" },
    ],
  ],
  [481, [{ type: "up", key: "i" }]],
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
  130,
  131,
  145,
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
  270,
  292,
  295,
  315,
  481,
  869,
  881,
  900,
] as const);

export const GAMEPLAY_POSTER_FRAME = 35;

export const GAMEPLAY_EVENT_VISIBILITY_WINDOWS = Object.freeze({
  hit: Object.freeze({ start: 34, end: 36 }),
  death: Object.freeze({ start: 43, end: 45 }),
  drop: Object.freeze({ start: 49, end: 51 }),
  pickup: Object.freeze({ start: 67, end: 76 }),
  stageAdvance: Object.freeze({ start: 869, end: 869 }),
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

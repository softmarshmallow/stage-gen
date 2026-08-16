export const GAMEPLAY_FPS = 30;
export const GAMEPLAY_FRAME_COUNT = 900;
export const GAMEPLAY_DURATION_SECONDS = GAMEPLAY_FRAME_COUNT / GAMEPLAY_FPS;
export const GAMEPLAY_STEP_MS = 1000 / GAMEPLAY_FPS;

export type GameplayKey =
  | "ArrowRight"
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
  [150, [{ type: "down", key: "Shift" }]],
  [270, [{ type: "down", key: "Space" }]],
  [271, [{ type: "up", key: "Space" }]],
  [
    450,
    [
      { type: "up", key: "Shift" },
      { type: "up", key: "ArrowRight" },
      { type: "down", key: "s" },
    ],
  ],
  [
    480,
    [
      { type: "up", key: "s" },
      { type: "down", key: "i" },
    ],
  ],
  [481, [{ type: "up", key: "i" }]],
  [
    541,
    [
      { type: "down", key: "ArrowRight" },
      { type: "down", key: "Shift" },
    ],
  ],
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
  271,
  481,
  870,
  900,
] as const);

export const GAMEPLAY_POSTER_FRAME = 35;

export const GAMEPLAY_EVENT_VISIBILITY_WINDOWS = Object.freeze({
  hit: Object.freeze({ start: 34, end: 36 }),
  death: Object.freeze({ start: 43, end: 45 }),
  drop: Object.freeze({ start: 49, end: 51 }),
  pickup: Object.freeze({ start: 67, end: 76 }),
  stageAdvance: Object.freeze({ start: 885, end: 899 }),
});

export const GAMEPLAY_REQUIRED_STATES = Object.freeze([
  "idle",
  "walk",
  "run",
  "jump",
  "crouch",
  "attack",
] as const);

export const GAMEPLAY_REQUIRED_EVENTS = Object.freeze([
  "mob-hit",
  "mob-death",
  "mob-drop",
  "item-pickup",
  "stage-advance",
] as const);

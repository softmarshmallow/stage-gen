import { describe, expect, test } from "bun:test";
import {
  NEUTRAL_PLAYER_INTENT,
  playerIntent,
  type PlayerIntent,
} from "./player-intent";

describe("player intent", () => {
  test("the neutral intent asks for nothing at all", () => {
    // A source with nothing to say must not move, swing, or spend anything on the player's behalf.
    expect(Object.values(NEUTRAL_PLAYER_INTENT).every((value) => value === false)).toBe(
      true,
    );
    expect(playerIntent()).toEqual(NEUTRAL_PLAYER_INTENT);
  });

  test("states only what it asks for and inherits silence everywhere else", () => {
    const intent = playerIntent({ right: true, run: true });
    expect(intent).toEqual({
      ...NEUTRAL_PLAYER_INTENT,
      right: true,
      run: true,
    });
  });

  test("is frozen, so a controller cannot rewrite what it was asked to do", () => {
    const intent = playerIntent({ jump: true });
    expect(Object.isFrozen(intent)).toBe(true);
    expect(() => {
      (intent as { -readonly [K in keyof PlayerIntent]: boolean }).jump = false;
    }).toThrow();
    expect(intent.jump).toBe(true);
  });

  test("covers every action the controller and scene read", () => {
    // The keyboard source and any future automated policy both fill this exact set; a field added
    // to the type without a default would reach the controller as undefined.
    expect(Object.keys(NEUTRAL_PLAYER_INTENT).sort()).toEqual([
      "attack",
      "down",
      "jump",
      "left",
      "right",
      "run",
      "toggleInventory",
      "up",
      "useHealing",
    ]);
  });
});

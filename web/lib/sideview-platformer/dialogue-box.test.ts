import { describe, expect, test } from "bun:test";
import {
  DIALOGUE_CURSOR_BEFORE_FIRST,
  DialogueBox,
  dialogueBeatAt,
  legacyDialogueBeats,
  nextDialogueCursor,
  type DialoguePortraitTextureKeys,
  type DialoguePresentationBeat,
} from "./dialogue-box";
import type Phaser from "phaser";

/** The three lines the recipe publishes per villager: greeting, remark, farewell. */
const PUBLISHED_LINE_COUNT = 3;

describe("nextDialogueCursor", () => {
  test("walks a published conversation from greeting to farewell exactly once each", () => {
    // The whole conversation, driven the way the scene drives it: one open, then one advance per
    // key press until the machine says it is over. Showing a line twice or dropping the farewell
    // only appears at the end of a conversation, which is the part a screenshot never reaches.
    const shown: number[] = [];
    let cursor = nextDialogueCursor(
      DIALOGUE_CURSOR_BEFORE_FIRST,
      PUBLISHED_LINE_COUNT,
    );
    while (cursor !== null) {
      shown.push(cursor);
      cursor = nextDialogueCursor(cursor, PUBLISHED_LINE_COUNT);
    }
    expect(shown).toEqual([0, 1, 2]);
  });

  test("opens on the first line from any pre-open cursor", () => {
    // `open()` and `advance()` are the same call, so there is only one path into line 0 and no
    // second place for an off-by-one to hide.
    expect(nextDialogueCursor(DIALOGUE_CURSOR_BEFORE_FIRST, 3)).toBe(0);
    expect(nextDialogueCursor(-1, 1)).toBe(0);
    expect(nextDialogueCursor(-9, 3)).toBe(0);
  });

  test("steps forward one line at a time", () => {
    expect(nextDialogueCursor(0, 3)).toBe(1);
    expect(nextDialogueCursor(1, 3)).toBe(2);
  });

  test("reports the end instead of clamping to the last line", () => {
    // Clamping is how a dialogue box gets stuck on its farewell, refusing to close, with the
    // player's movement still gated behind it.
    expect(nextDialogueCursor(2, 3)).toBeNull();
    expect(nextDialogueCursor(0, 1)).toBeNull();
    expect(nextDialogueCursor(7, 3)).toBeNull();
  });

  test("is over before it starts when the villager has no lines", () => {
    // A villager whose manifest published no lines must not open an empty panel that then traps
    // input until the player guesses that pressing the key again will close it.
    for (const cursor of [DIALOGUE_CURSOR_BEFORE_FIRST, 0, 2]) {
      expect(nextDialogueCursor(cursor, 0)).toBeNull();
      expect(nextDialogueCursor(cursor, -3)).toBeNull();
    }
  });

  test("refuses a corrupted cursor or line count rather than rendering one", () => {
    // Total by construction: every input maps to a line index inside the conversation or to
    // null. Nothing here may return a cursor that would index past the published lines.
    for (const value of [Number.NaN, 1.5, Number.POSITIVE_INFINITY]) {
      expect(nextDialogueCursor(value, PUBLISHED_LINE_COUNT)).toBeNull();
      expect(nextDialogueCursor(0, value)).toBeNull();
    }
  });

  test("never returns a cursor outside the conversation, for any input", () => {
    for (let lineCount = 0; lineCount <= 5; lineCount += 1) {
      for (let cursor = -3; cursor <= 8; cursor += 1) {
        const next = nextDialogueCursor(cursor, lineCount);
        if (next === null) continue;
        expect(next).toBeGreaterThanOrEqual(0);
        expect(next).toBeLessThan(lineCount);
        // Never backwards from a line that is already showing: a conversation only moves on.
        if (cursor >= 0) expect(next).toBeGreaterThan(cursor);
      }
    }
  });
});

class FakeDisplayObject {
  visible = true;
  depth = 0;
  scrollFactor = 1;
  originX = 0;
  originY = 0;
  displayWidth = 0;
  displayHeight = 0;
  destroyed = false;

  setVisible(value: boolean) {
    this.visible = value;
    return this;
  }

  setDepth(value: number) {
    this.depth = value;
    return this;
  }

  setScrollFactor(value: number) {
    this.scrollFactor = value;
    return this;
  }

  setOrigin(x: number, y: number) {
    this.originX = x;
    this.originY = y;
    return this;
  }

  setDisplaySize(width: number, height: number) {
    this.displayWidth = width;
    this.displayHeight = height;
    return this;
  }

  destroy() {
    this.destroyed = true;
  }
}

class FakeContainer extends FakeDisplayObject {
  readonly children: unknown[] = [];

  add(child: unknown) {
    this.children.push(child);
    return this;
  }
}

class FakeGraphics extends FakeDisplayObject {
  fillStyle() {
    return this;
  }

  fillRoundedRect() {
    return this;
  }

  lineStyle() {
    return this;
  }

  strokeRoundedRect() {
    return this;
  }
}

class FakeText extends FakeDisplayObject {
  height = 18;

  constructor(public text: string) {
    super();
  }

  setText(value: string) {
    this.text = value;
    return this;
  }
}

class FakeImage extends FakeDisplayObject {
  constructor(
    readonly x: number,
    readonly y: number,
    public texture: string,
  ) {
    super();
  }

  setTexture(value: string) {
    this.texture = value;
    return this;
  }
}

function fakeScene(): Readonly<{
  scene: Phaser.Scene;
  containers: FakeContainer[];
  images: FakeImage[];
}> {
  const containers: FakeContainer[] = [];
  const images: FakeImage[] = [];
  const scene = {
    add: {
      container() {
        const container = new FakeContainer();
        containers.push(container);
        return container;
      },
      graphics() {
        return new FakeGraphics();
      },
      text(_x: number, _y: number, text: string) {
        return new FakeText(text);
      },
      image(x: number, y: number, texture: string) {
        const image = new FakeImage(x, y, texture);
        images.push(image);
        return image;
      },
    },
  } as unknown as Phaser.Scene;
  return { scene, containers, images };
}

const PORTRAIT_TEXTURE_KEYS: DialoguePortraitTextureKeys = Object.freeze({
  neutral: "portrait-neutral",
  delighted: "portrait-delighted",
  flustered: "portrait-flustered",
  concerned: "portrait-concerned",
});

const RICH_BEATS: readonly DialoguePresentationBeat[] = Object.freeze([
  Object.freeze({
    speaker: "Elowen",
    text: "The sunpetals are ready.",
    expressionState: "neutral" as const,
  }),
  Object.freeze({
    speaker: "You",
    text: "You remembered.",
    expressionState: "delighted" as const,
  }),
  Object.freeze({
    speaker: "Elowen",
    text: "Some things are easy to remember.",
    expressionState: "flustered" as const,
  }),
  Object.freeze({
    speaker: "Elowen",
    text: "A storm is close.",
    expressionState: "concerned" as const,
  }),
]);

describe("DialogueBox presentation", () => {
  test("renders every rich beat with its own speaker, text, expression, and portrait texture", () => {
    const { scene, images } = fakeScene();
    const box = new DialogueBox({ scene, viewW: 1280, viewH: 720 });

    expect(box.snapshot()).toEqual({
      open: false,
      speaker: "",
      line: "",
      lineIndex: DIALOGUE_CURSOR_BEFORE_FIRST,
      lineCount: 0,
      expressionState: null,
      portraitVisible: false,
    });

    box.openBeats(RICH_BEATS, PORTRAIT_TEXTURE_KEYS);
    expect(images).toHaveLength(1);
    const portrait = images[0]!;
    expect({
      x: portrait.x,
      y: portrait.y,
      originX: portrait.originX,
      originY: portrait.originY,
      displayHeight: portrait.displayHeight,
      scrollFactor: portrait.scrollFactor,
    }).toEqual({
      x: 1256,
      y: 696,
      originX: 1,
      originY: 1,
      displayHeight: 620,
      scrollFactor: 0,
    });

    for (let index = 0; index < RICH_BEATS.length; index += 1) {
      const expected = RICH_BEATS[index]!;
      expect(box.snapshot()).toMatchObject({
        open: true,
        speaker: expected.speaker,
        line: expected.text,
        lineIndex: index,
        lineCount: RICH_BEATS.length,
        expressionState: expected.expressionState,
        portraitVisible: true,
      });
      expect(portrait.texture).toBe(
        PORTRAIT_TEXTURE_KEYS[expected.expressionState!],
      );
      if (index < RICH_BEATS.length - 1) expect(box.advance()).toBeTrue();
    }
    expect(box.advance()).toBeFalse();

    box.close();
    expect(box.snapshot()).toMatchObject({
      open: false,
      expressionState: null,
      portraitVisible: false,
    });
    expect(portrait.visible).toBeFalse();
  });

  test("keeps legacy lines portrait-free while preserving the original speaker fallback", () => {
    const { scene, images } = fakeScene();
    const box = new DialogueBox({ scene, viewW: 1280, viewH: 720 });

    box.open("Mara", ["Welcome home.", "Mind the bridge."]);
    expect(box.snapshot()).toEqual({
      open: true,
      speaker: "Mara",
      line: "Welcome home.",
      lineIndex: 0,
      lineCount: 2,
      expressionState: null,
      portraitVisible: false,
    });
    expect(images).toHaveLength(0);
    expect(box.advance()).toBeTrue();
    expect(box.snapshot().line).toBe("Mind the bridge.");
    expect(box.snapshot().portraitVisible).toBeFalse();
  });
});

describe("dialogue beat adapters", () => {
  test("maps legacy strings to immutable neutral presentation beats", () => {
    const beats = legacyDialogueBeats("Mara", ["One", "Two"]);
    expect(beats).toEqual([
      { speaker: "Mara", text: "One", expressionState: null },
      { speaker: "Mara", text: "Two", expressionState: null },
    ]);
    expect(Object.isFrozen(beats)).toBeTrue();
    expect(Object.isFrozen(beats[0])).toBeTrue();
    expect(dialogueBeatAt(beats, 1)).toEqual(beats[1]);
    expect(dialogueBeatAt(beats, -1)).toBeNull();
    expect(dialogueBeatAt(beats, 2)).toBeNull();
  });
});

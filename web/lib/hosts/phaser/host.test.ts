import { describe, expect, mock, test } from "bun:test";

// What the one boot has to get right, measured rather than described.
//
// The four boots it replaced differed in exactly three ways — the design space,
// the background, and whether this was a capture — and got a fourth thing
// inconsistently right: the order of teardown. Each of those is a case below.

class StubCamera {
  readonly width = 640;
  readonly height = 360;
  zoomX = 1;
  zoomY = 1;
  originX = 0.5;
  originY = 0.5;
  setZoom(x: number, y?: number): this {
    this.zoomX = x;
    this.zoomY = y ?? x;
    return this;
  }
  setOrigin(x: number, y: number): this {
    this.originX = x;
    this.originY = y;
    return this;
  }
}

class StubText {
  name = "";
  constructor(readonly content: string) {}
  setOrigin(): this {
    return this;
  }
  setScrollFactor(): this {
    return this;
  }
  setDepth(): this {
    return this;
  }
  setName(name: string): this {
    this.name = name;
    return this;
  }
  destroy(): void {
    destroyed.push(this.name);
  }
}

const destroyed: string[] = [];
const booted: Record<string, unknown>[] = [];
const teardown: string[] = [];

class StubScenePlugin {
  readonly cameras = { main: new StubCamera() };
  readonly texts: StubText[] = [];
  readonly add = {
    text: (_x: number, _y: number, content: string) => {
      const text = new StubText(content);
      this.texts.push(text);
      return text;
    },
  };
  readonly children = {
    getByName: (name: string) => this.texts.find((text) => text.name === name) ?? null,
  };
  constructor(_config: unknown) {}
}

mock.module("phaser", () => ({
  default: {
    Scene: StubScenePlugin,
    AUTO: "auto",
    CANVAS: "canvas",
    Scale: { FIT: "fit", NONE: "none", CENTER_BOTH: "center" },
    Game: class {
      constructor(config: Record<string, unknown>) {
        booted.push(config);
      }
      destroy(removeCanvas: boolean): void {
        teardown.push(`game:${removeCanvas}`);
      }
    },
  },
}));

const Phaser = (await import("phaser")).default;
const { bootGame } = await import("./host");
const { hostScene } = await import("./scene-base");

interface TestWorld {
  readonly tick: number;
}

class TestScene extends hostScene<TestWorld>(Phaser.Scene) {
  constructor(mode: "interactive" | "capture" = "interactive") {
    super({
      key: "test",
      designSpace: { width: 640, height: 360 },
      background: "#123456",
      mode,
    });
  }

  runFrame(tick: number): void {
    this.publish({ tick }, [{ type: "tick" }]);
  }

  beginLoad(): void {
    this.zoomToDesignSpace();
    this.showLoading("loading…");
  }

  arrive(): void {
    this.finishLoading();
  }

  refuse(message: string): void {
    this.failLoading("Unable to load", new Error(message));
  }

  override hostSealedOrder(): readonly string[] {
    return ["a", "b"];
  }

  override hostDispose(): void {
    teardown.push("scene");
    super.hostDispose();
  }
}

const parent = {} as HTMLElement;

describe("one boot for every genre", () => {
  test("a person's canvas is device-sized and fitted; a capture keeps the design space", () => {
    booted.length = 0;
    bootGame(parent, new TestScene("interactive"));
    bootGame(parent, new TestScene("capture"));
    const [interactive, capture] = booted;
    // No window in a test process, so the device scale is one and the two canvases
    // agree on size. What differs is the renderer and the scaling, which is the
    // whole of what capture means to the host.
    expect(interactive).toMatchObject({
      type: "auto",
      width: 640,
      height: 360,
      backgroundColor: "#123456",
      scale: { mode: "fit", autoCenter: "center" },
    });
    expect(capture).toMatchObject({
      type: "canvas",
      width: 640,
      height: 360,
      scale: { mode: "none", autoCenter: "center" },
    });
  });

  test("destroy runs the scene's own teardown before the game's", () => {
    teardown.length = 0;
    bootGame(parent, new TestScene()).destroy(true);
    // The order is the point. `game.destroy` drops every reference to the scene,
    // so anything the scene owns and the engine does not — an audio element,
    // most of all — has to be stopped first. One of the four dispose orders this
    // replaced never stopped the platformer's soundtrack at all.
    expect(teardown).toEqual(["scene", "game:true"]);
  });

  test("the sealed order is read through the handle, live", () => {
    expect(bootGame(parent, new TestScene()).sealedOrder).toEqual(["a", "b"]);
  });
});

describe("the subscription that replaced the poll", () => {
  test("a listener hears every frame, and stops hearing when it unsubscribes", () => {
    const scene = new TestScene();
    const handle = bootGame(parent, scene);
    const heard: number[] = [];
    const stop = handle.subscribe((world, frame) => {
      expect(frame).toEqual([{ type: "tick" }]);
      heard.push(world.tick);
    });
    scene.runFrame(1);
    scene.runFrame(2);
    stop();
    scene.runFrame(3);
    expect(heard).toEqual([1, 2]);
  });

  test("a listener that throws does not take the frame down with it", () => {
    const scene = new TestScene();
    const handle = bootGame(parent, scene);
    const heard: number[] = [];
    handle.subscribe(() => {
      throw new Error("a console with a bug");
    });
    handle.subscribe((world) => heard.push(world.tick));
    scene.runFrame(7);
    expect(heard).toEqual([7]);
  });
});

describe("one loading, failure and ready state machine", () => {
  test("loading gives way to ready, and the label goes with it", () => {
    destroyed.length = 0;
    const scene = new TestScene();
    scene.beginLoad();
    expect(scene.hostLoadState).toBe("loading");
    // The device zoom is the first act of every scene, done once, by the base.
    expect(scene.cameras.main.zoomX).toBe(1);
    scene.arrive();
    expect(scene.hostLoadState).toBe("ready");
    expect(destroyed).toEqual(["host-loading-label"]);
  });

  test("a failure names itself, and ready cannot undo it", () => {
    const scene = new TestScene();
    scene.beginLoad();
    scene.refuse("no backdrop");
    expect(scene.hostLoadState).toBe("failed");
    expect(scene.hostLoadFailure).toBe("no backdrop");
    // Two of the four scenes drew this card by hand and two drew nothing at all.
    // A late `finishLoading` must not clear a failure that already happened.
    scene.arrive();
    expect(scene.hostLoadState).toBe("failed");
  });
});

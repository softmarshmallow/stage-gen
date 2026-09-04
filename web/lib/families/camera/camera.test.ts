import { describe, expect, test } from "bun:test";
import { sealSystems, type FixedStep } from "@/lib/kernel/systems";
import { KILL_SHAKE_PROFILE, sampleShake, sumShake } from "../screen-fx/shake";
import {
  anchoredScroll,
  createCameraSystem,
  followBounds,
  NO_SHAKE,
  ShakeCarrier,
  shiftByShake,
  type ShakeOffset,
} from "./camera";

const step = (frame: number, now: number): FixedStep => ({ dt: 1000 / 60, now, frame });

describe("the anchored mode", () => {
  test("scroll is the tracked position less the anchor, and nothing else", () => {
    expect(anchoredScroll(10 * 48, 220)).toBe(260);
    // A tracked thing behind its anchor scrolls the world the other way; the
    // mode has no clamp, because a streamed world has nothing to clamp against.
    expect(anchoredScroll(0, 220)).toBe(-220);
  });
});

describe("the follow mode", () => {
  test("without a vertical axis the box is one viewport tall", () => {
    expect(
      followBounds({ followAxes: ["x"], worldWidth: 4096, topY: 0, baselineY: 720, viewportHeight: 720 }),
    ).toEqual({ x: 0, y: 0, width: 4096, height: 720 });
  });

  test("with one the box is the authored grid itself", () => {
    expect(
      followBounds({ followAxes: ["x", "y"], worldWidth: 4096, topY: 96, baselineY: 720, viewportHeight: 720 }),
    ).toEqual({ x: 0, y: 96, width: 4096, height: 624 });
  });
});

describe("shake is an input", () => {
  test("the carried offset comes off before the next one goes on", () => {
    expect(shiftByShake({ scrollX: 100, scrollY: 50 }, { x: 3, y: -1 }, { x: -2, y: 4 })).toEqual({
      scrollX: 95,
      scrollY: 55,
    });
  });

  test("a whole tremor leaves the view exactly where the follower put it", () => {
    // The property the old scroll mutation did not have: whatever a follower
    // writes between two shifts survives, and the sum of a finished shake is
    // zero displacement rather than a drift.
    const carrier = new ShakeCarrier();
    let scroll = { scrollX: 400, scrollY: 0 };
    for (let elapsed = 0; elapsed <= KILL_SHAKE_PROFILE.durationMs + 32; elapsed += 16) {
      const offset = sumShake(
        [sampleShake({ seed: 7, elapsedMs: elapsed, dirSign: 1, scale: 1 }, KILL_SHAKE_PROFILE)],
        KILL_SHAKE_PROFILE.amplitudePx,
      );
      scroll = carrier.shift(scroll, offset);
      // The follower advances the view a pixel a frame underneath the tremor.
      scroll = { scrollX: scroll.scrollX + 1, scrollY: scroll.scrollY };
    }
    scroll = carrier.release(scroll);
    expect(carrier.offset).toEqual(NO_SHAKE);
    expect(scroll).toEqual({ scrollX: 400 + 11, scrollY: 0 });
  });
});

// --- E4: one family file, two worlds that share no field ----------------------------------------

describe("E4: the camera family sealed into two worlds", () => {
  test("an anchored, auto-run world: the view is derived from distance", () => {
    // Runner-shaped: a world whose camera is a slice, whose tracked thing is an
    // avatar pinned at a screen column, and which never shakes.
    type Runnerish = { avatar: { distancePx: number }; camera: { scrollX: number } };
    const world: Runnerish = { avatar: { distancePx: 0 }, camera: { scrollX: 0 } };
    const sealed = sealSystems<Runnerish>([
      {
        id: "runnerish/avatar",
        contractVersion: "avatar-v1",
        reads: [],
        writes: [],
        owns: ["avatar"],
        update: (w) => {
          w.avatar.distancePx += 12;
        },
      },
      createCameraSystem<Runnerish>({
        mode: "anchored",
        id: "runnerish/camera",
        contractVersion: "camera-v1",
        reads: ["avatar"],
        owns: ["camera"],
        track: (w) => w.avatar.distancePx,
        anchor: () => 220,
        apply: (w, scrollX) => {
          w.camera.scrollX = scrollX;
        },
      }),
    ]);
    expect(sealed.order).toEqual(["runnerish/avatar", "runnerish/camera"]);
    sealed.tick(world, step(1, 16));
    expect(world.camera.scrollX).toBe(12 - 220);
    sealed.tick(world, step(2, 32));
    expect(world.camera.scrollX).toBe(24 - 220);
  });

  test("a following, shaken world: the view is moved by somebody else and carries a tremor", () => {
    // Platformer-shaped: no camera slice at all — the view is a game object the
    // host holds — a hold that quiets the frame, and a blow that shakes it.
    type Platformerish = { hold: boolean; blowAtMs: number | null; readonly view?: never };
    const view = { scrollX: 0, scrollY: 0 };
    const carrier = new ShakeCarrier();
    const world: Platformerish = { hold: false, blowAtMs: null };
    const shake = (w: Platformerish, nowMs: number): ShakeOffset =>
      w.blowAtMs === null
        ? NO_SHAKE
        : sampleShake(
            { seed: 3, elapsedMs: nowMs - w.blowAtMs, dirSign: -1, scale: 1 },
            KILL_SHAKE_PROFILE,
          );
    const sealed = sealSystems<Platformerish>([
      createCameraSystem<Platformerish>({
        mode: "follow",
        id: "platformerish/camera",
        contractVersion: "camera-v1",
        reads: ["hold"],
        writes: ["view"],
        quiet: (w) => w.hold,
        shake,
        carry: (_w, next) => {
          const moved = carrier.shift(view, next);
          view.scrollX = moved.scrollX;
          view.scrollY = moved.scrollY;
        },
      }),
    ]);
    sealed.tick(world, step(1, 0));
    expect(view).toEqual({ scrollX: 0, scrollY: 0 });
    world.blowAtMs = 0;
    sealed.tick(world, step(2, 16));
    expect(view.scrollX).not.toBe(0);
    // A conversation opens: the frame is quiet, so the tremor is neither
    // advanced nor released — it is exactly where the last frame left it.
    const held = { ...view };
    world.hold = true;
    sealed.tick(world, step(3, 32));
    expect(view).toEqual(held);
    // And once the blow has run out the view is back where the follower had it.
    world.hold = false;
    sealed.tick(world, step(4, 1_000));
    expect(view).toEqual({ scrollX: 0, scrollY: 0 });
  });
});

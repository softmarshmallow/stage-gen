// What the view is pointed at, and how far it may travel to keep pointing there.
//
// Two implementations existed and they looked like two different subjects. The
// runner's is one line — the avatar is pinned at a screen anchor and the world
// scrolls under it, so scroll is a pure function of distance — and the
// platformer's is a bounds box handed to the engine's own follow, with a dead
// zone and a per-map axis list. The vocabularies are disjoint too:
// `auto_run_x_v1` against `player_follow` + `follow_axes`.
//
// They are one family with a **mode**. What both answer is "where is the view",
// and the two modes are two answers to it: `anchored` derives the scroll from a
// tracked position and a fixed screen anchor; `follow` does not derive a scroll
// at all — it states the box the view may move inside and lets a follower do
// the moving. Neither mode knows anything about the other's world.
//
// Shake is an **input**, not a mode and not a mutation. It used to be a private
// scene method writing `camera.scrollX` directly, which is why every parallax
// layer inherited it undeclared; step 3 made the arithmetic a pure offset in
// `screen-fx/shake.ts`, and this family is where the offset finally becomes a
// camera input: the frame's applied offset is removed and this frame's is
// added, so the scroll a follower computed is never permanently displaced by a
// tremor. That is one function with one author, and it is `shiftByShake`.

import type { GameSystem } from "@/lib/kernel/systems";
import type { ShakeOffset } from "../screen-fx/shake";
import { NO_SHAKE } from "../screen-fx/shake";

/** The two answers to "where is the view". */
export type CameraMode = "anchored" | "follow";

/** A scroll position, in the host's own pixels. */
export type CameraScroll = Readonly<{ scrollX: number; scrollY: number }>;

/**
 * Scroll that pins a tracked thing to a fixed screen anchor.
 *
 * The whole of `auto_run_x_v1`: the tracked position in world pixels, less the
 * screen column it is pinned at. A genre supplies both numbers; the family
 * supplies the subtraction, which is the only thing about the mode that is not
 * the genre's own units.
 */
export function anchoredScroll(trackedPx: number, anchorPx: number): number {
  return trackedPx - anchorPx;
}

/** Which axes a `follow` camera is allowed to travel along. */
export type FollowAxis = "x" | "y";

export type FollowBoundsInput = Readonly<{
  followAxes: readonly FollowAxis[];
  worldWidth: number;
  /** Top of the authored grid, in world coordinates. */
  topY: number;
  /** The floor the world is built up from, in world coordinates. */
  baselineY: number;
  viewportHeight: number;
}>;

export type FollowBounds = Readonly<{ x: number; y: number; width: number; height: number }>;

/**
 * The box a `follow` camera may move inside, from the declared axes.
 *
 * This is the whole of axis enablement, and it is deliberately not a second
 * code path: the follow itself is unconditional, and an axis is switched off by
 * giving the camera no room to travel along it. A view with no vertical axis
 * gets a box exactly one viewport tall, and the follower's own clamp then pins
 * it to the floor for free.
 */
export function followBounds(input: FollowBoundsInput): FollowBounds {
  for (const value of [input.worldWidth, input.topY, input.baselineY, input.viewportHeight]) {
    if (!Number.isFinite(value)) throw new Error("camera bounds inputs must be finite");
  }
  if (input.worldWidth <= 0 || input.viewportHeight <= 0) {
    throw new Error("camera world width and viewport height must be positive");
  }
  if (input.baselineY <= input.topY) {
    throw new Error("camera bounds require a floor below the top of the terrain");
  }
  const followsVertically = input.followAxes.includes("y");
  return Object.freeze({
    x: 0,
    y: followsVertically ? input.topY : 0,
    width: input.worldWidth,
    height: followsVertically ? input.baselineY - input.topY : input.viewportHeight,
  });
}

/**
 * Move a scroll from the shake it is currently carrying to the one it should.
 *
 * Removing `applied` before adding `next` is what makes the offset an input
 * rather than a displacement: the scroll a follower or an anchor produced is
 * recovered exactly, every frame, however many frames the tremor lasted.
 */
export function shiftByShake(
  scroll: CameraScroll,
  applied: ShakeOffset,
  next: ShakeOffset,
): CameraScroll {
  return Object.freeze({
    scrollX: scroll.scrollX - applied.x + next.x,
    scrollY: scroll.scrollY - applied.y + next.y,
  });
}

/**
 * The offset the view is currently carrying.
 *
 * The tremor is an input, so it has to be *removed* before the next one is
 * added or a run of shakes walks the view away from wherever the anchor or the
 * follower put it. Something must therefore remember what was applied last, and
 * this is that something: one object per camera, with the whole of the rule in
 * two methods, so a host that shakes from inside its own teardown path (letting
 * go of a world mid-frame) and a host that shakes from the sealed frame are
 * using the same record rather than two.
 */
export class ShakeCarrier {
  private carried: ShakeOffset = NO_SHAKE;

  /** What the view is displaced by right now. */
  get offset(): ShakeOffset {
    return this.carried;
  }

  /** Move a scroll from the offset it carries to `next`, and remember `next`. */
  shift(scroll: CameraScroll, next: ShakeOffset): CameraScroll {
    const moved = shiftByShake(scroll, this.carried, next);
    this.carried = next;
    return moved;
  }

  /** Let go: the view keeps nothing of the tremor. */
  release(scroll: CameraScroll): CameraScroll {
    return this.shift(scroll, NO_SHAKE);
  }
}

/** What every camera binding states, whatever its mode. */
interface CameraSystemBase<W> {
  /** The system id in this genre's roster. */
  readonly id: string;
  readonly contractVersion: string;
  readonly reads?: readonly (keyof W & string)[];
  readonly writes?: readonly (keyof W & string)[];
  /** The slice this camera owns, when the world holds one. */
  readonly owns?: readonly (keyof W & string)[];
  readonly after?: readonly string[];
}

/**
 * The anchored mode: derive a scroll, write it.
 *
 * `track` and `anchor` are the genre's own units resolved to pixels; the family
 * subtracts and hands the result to `apply`, which is where a host that keeps
 * its scroll on a game object rather than in a world slice puts it.
 */
export interface AnchoredCameraBinding<W> extends CameraSystemBase<W> {
  readonly mode: "anchored";
  readonly track: (world: W) => number;
  readonly anchor: (world: W) => number;
  readonly apply: (world: W, scrollX: number) => void;
}

/**
 * The follow mode: the view is moved by somebody else, and this states the
 * tremor it carries while they do.
 *
 * `shake` answers what is shaking the view this frame, and `carry` puts the
 * view where that answer says — through a `ShakeCarrier`, which is what makes
 * the offset an input rather than a displacement.
 */
export interface FollowCameraBinding<W> extends CameraSystemBase<W> {
  readonly mode: "follow";
  readonly shake: (world: W, nowMs: number) => ShakeOffset;
  readonly carry: (world: W, next: ShakeOffset) => void;
  /** Skip the frame entirely — a held simulation shakes nothing new. */
  readonly quiet?: (world: W) => boolean;
}

export type CameraBinding<W> = AnchoredCameraBinding<W> | FollowCameraBinding<W>;

/**
 * The camera system, in whichever mode the genre binds.
 *
 * Both modes are the same shape — read the world, decide where the view is, put
 * it there — and neither holds state of its own: the anchored mode is a pure
 * function of the frame, and the follow mode's one piece of memory is the
 * carrier, which belongs to the host because the host also lets go of it
 * outside the frame.
 */
export function createCameraSystem<W>(binding: CameraBinding<W>): GameSystem<W> {
  const declared = {
    id: binding.id,
    contractVersion: binding.contractVersion,
    reads: binding.reads ?? [],
    writes: binding.writes ?? [],
    ...(binding.owns ? { owns: binding.owns } : {}),
    ...(binding.after ? { after: binding.after } : {}),
  };
  if (binding.mode === "anchored") {
    return {
      ...declared,
      update(world: W) {
        binding.apply(world, anchoredScroll(binding.track(world), binding.anchor(world)));
      },
    } as GameSystem<W>;
  }
  return {
    ...declared,
    update(world: W, step) {
      if (binding.quiet?.(world)) return;
      binding.carry(world, binding.shake(world, step.now));
    },
  } as GameSystem<W>;
}

export type { ShakeOffset };
export { NO_SHAKE };
